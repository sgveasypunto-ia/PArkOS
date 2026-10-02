"""HU-F20.3 / REQ-23-W-POLYMORPHIC-FK, REQ-OP-08 — reclamos workflow handlers.

Two POST endpoints on a dedicated ``APIRouter`` (same DEC-TKT-06 pattern as
``workflows_anulaciones.py`` / ``workflows_alerta.py``): the factory-mounted
router at ``api/v1/workflows.py`` stays reserved for the C+Q GET mount
(``write_enabled=False`` for ``reclamos``). See ``workflows_anulaciones.py``'s
module docstring for the full rationale against flipping that flag instead.

* ``POST /api/v1/workflows/reclamos`` — INSERT chain root with
  ``estado='recibido'``, ``uuid_reclamo_padre=NULL``. Permission
  ``registrar_reclamo`` (already used by the read-only factory mount's
  ``_ROUTER_CONFIG["reclamos"]``; seeded by migration
  ``0059_seed_router_permission_codes.py``).
* ``POST /api/v1/workflows/reclamos/{uuid}/transicion`` — the body names the
  destination ``estado``; ``append_transition`` validates
  ``tip.estado -> estado`` against ``STATE_MACHINES['reclamos']``
  (``repo/workflow.py``) and raises ``IllegalTransitionError`` (mapped to
  409 here, same local ``try/except`` as ``workflows_anulaciones.py`` — no
  global exception handler for it exists anywhere in the codebase).

STATE NAME DRIFT VS plan.md / the HU prose (confirmed via
``repo/workflow.py:STATE_MACHINES['reclamos']``):

    plan.md prose:       abierto -> en_revision -> resuelto | rechazado
    Real STATE_MACHINES: recibido -> en_investigacion -> resuelto | rechazado

The ``resuelto`` / ``rechazado`` terminal names match the prose; only the
root and middle state names differ. This module uses the REAL state names
throughout.

PERMISSION DRIFT VS plan.md's compliance matrix: plan.md names
``registrar_reclamo`` for the RESOLUTION transition too. Migration
``0053_seed_resolver_reclamo_permiso.py`` is explicit that this is wrong —
its own docstring says HU-R04 ("marcar un reclamo como en_revision y luego
resuelto/rechazado") had NO permission code at all until that migration
seeded ``resolver_reclamo`` specifically to close the gap. This module uses
``registrar_reclamo`` ONLY for the root-creation endpoint and
``resolver_reclamo`` for BOTH steps of the transition endpoint.

SINGLE PERMISSION COVERS BOTH TRANSITION STEPS (unlike ``anulaciones``,
which needed a per-step dynamic lookup): migration 0053's docstring frames
HU-R04 as ONE admin responsibility spanning ``recibido -> en_investigacion``
AND ``en_investigacion -> {resuelto, rechazado}``, gated by the ONE
``resolver_reclamo`` code it seeds. No per-step split exists in the seeded
catalogue, and inventing one is out of scope.

PERMISSION CHECK IS INLINE, NOT A STATIC ``Depends`` (same deviation as
``workflows_anulaciones.py``, applied here for consistency even though the
code is static per endpoint): keeps the 403 path exercisable by calling the
handler function directly, the test style every sibling ``[L-W]`` endpoint
test uses, instead of being silently bypassed the way a ``Depends``-only
permission parameter is when a test passes ``None`` for it.
"""
from __future__ import annotations

import uuid as uuid_lib

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.permissions import actor_has_permission
from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...db.engine import get_session
from ...models.L_W.reclamos import Reclamos
from ...repo import workflow as repo_workflow
from ...repo.workflow import _now_naive
from ...schemas.workflows import (
    ReclamosRead,
    ReclamosSolicitarEndpoint,
    ReclamosTransicionEndpoint,
)
from ..deps import requires_issuer
from . import _helpers

_reclamos_issuer_dep = requires_issuer("operador-", "admin-")

router = APIRouter(prefix="/workflows/reclamos", tags=["workflows"])


@router.post(
    "",
    response_model=ReclamosRead,
    status_code=201,
    summary=(
        "HU-F20.3: INSERT prod.reclamos row with estado='recibido', "
        "uuid_reclamo_padre=NULL. permission_required='registrar_reclamo'."
    ),
    responses={
        403: {"description": "permission_denied (missing 'registrar_reclamo')"},
        422: {"description": "Pydantic validation (motivo vacío | missing_field | extra_forbidden)"},
    },
)
async def solicitar_reclamo(
    response: Response,
    payload: ReclamosSolicitarEndpoint,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_reclamos_issuer_dep),
) -> ReclamosRead:
    """HU-F20.3: create the ``reclamos`` chain root.

    Sequence:
        1. KD-3 issuer claims + no_store headers (DI)
        2. Permission gate: ``registrar_reclamo`` (403 if missing)
        3. INSERT ``prod.reclamos`` root via ``append_transition``
           (``parent_uuid=None`` — no STATE_MACHINES check on a root row)
        4. Single ``await session.commit()``
        5. ``Cache-Control: no-store`` + response shape
    """
    no_store = _helpers.no_store_headers()

    if not await actor_has_permission(
        session, actor_uuid=ctx.actor_uuid, codigo="registrar_reclamo"
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "permission_denied", "detail": "registrar_reclamo"},
            headers=no_store,
        )

    new_row = await repo_workflow.append_transition(
        session,
        Reclamos,
        actor_uuid=ctx.actor_uuid,
        new_attrs={
            "uuid_sucursal": ctx.sucursal_uuid,
            "tipo_reclamable": payload.tipo_reclamable,
            "uuid_reclamable": payload.uuid_reclamable,
            "motivo": payload.motivo,
            "timestamp_evento": _now_naive(),
            "estado": "recibido",
        },
        parent_uuid=None,  # chain root
        parent_fk_column="uuid_reclamo_padre",
        log_tx=True,
    )

    await session.commit()  # single commit

    _helpers.apply_no_store_header(response)
    return ReclamosRead.model_validate(new_row)


@router.post(
    "/{uuid}/transicion",
    response_model=ReclamosRead,
    status_code=201,
    summary=(
        "HU-F20.3: INSERT NEW prod.reclamos row chained via "
        "uuid_reclamo_padre. Destination estado is caller-supplied; "
        "append_transition validates it against STATE_MACHINES['reclamos']."
    ),
    responses={
        403: {
            "description": (
                "tenant_scope_violation | permission_denied "
                "(missing 'resolver_reclamo')"
            )
        },
        404: {"description": "reclamo_not_found (chain root does not exist)"},
        409: {"description": "illegal_transition (IllegalTransitionError)"},
        422: {"description": "Pydantic validation (motivo vacío | missing_field | extra_forbidden)"},
    },
)
async def transicionar_reclamo(
    response: Response,
    uuid: uuid_lib.UUID,
    payload: ReclamosTransicionEndpoint,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_reclamos_issuer_dep),
) -> ReclamosRead:
    """HU-F20.3: transition a ``reclamos`` chain via a NEW chain row.

    Sequence:
        1. KD-3 issuer claims + no_store headers (DI)
        2. V1 chain tip via ``read_chain_tip``; ``ChainNotFoundError`` -> 404
        3. Tenant scope post-V1 (403 if operador- cross-branch)
        4. Permission gate: ``resolver_reclamo`` (403 if missing) — same
           code for both ``recibido -> en_investigacion`` and
           ``en_investigacion -> {resuelto, rechazado}`` (module docstring)
        5. INSERT NEW ``prod.reclamos`` row via ``append_transition``
           (NEVER UPDATE the tip); ``IllegalTransitionError`` -> 409
        6. Single ``await session.commit()`` + no-store header + response
    """
    no_store = _helpers.no_store_headers()

    # --- Step 2: V1 chain tip via read_chain_tip. ----------------------
    try:
        tip = await repo_workflow.read_chain_tip(
            session,
            Reclamos,
            root_uuid=uuid,
            parent_fk_column="uuid_reclamo_padre",
        )
    except repo_workflow.ChainNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"error": "reclamo_not_found", "uuid": str(uuid)},
            headers=no_store,
        ) from None

    tip_row = (
        await session.execute(select(Reclamos).where(Reclamos.uuid == tip["uuid_actual"]))
    ).scalar_one_or_none()
    if tip_row is None:
        # Defensive: read_chain_tip returned a uuid that no longer exists.
        raise HTTPException(
            status_code=404,
            detail={"error": "reclamo_not_found", "uuid": str(uuid)},
            headers=no_store,
        )

    # --- Step 3: tenant scope (post-V1). -------------------------------
    if ctx.issuer_prefix == "operador-" and (
        ctx.sucursal_uuid is None or tip_row.uuid_sucursal != ctx.sucursal_uuid
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "tenant_scope_violation", "uuid": str(uuid)},
            headers=no_store,
        )

    # --- Step 4: permission gate (single code, both steps). ------------
    if not await actor_has_permission(
        session, actor_uuid=ctx.actor_uuid, codigo="resolver_reclamo"
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "permission_denied", "detail": "resolver_reclamo"},
            headers=no_store,
        )

    # --- Step 5: V3 INSERT NEW prod.reclamos row (NEVER UPDATE). --------
    try:
        new_row = await repo_workflow.append_transition(
            session,
            Reclamos,
            actor_uuid=ctx.actor_uuid,
            new_attrs={
                "uuid_sucursal": tip_row.uuid_sucursal,
                "tipo_reclamable": tip_row.tipo_reclamable,
                "uuid_reclamable": tip_row.uuid_reclamable,
                # prod.reclamos has NO uuid_usuario column (unlike
                # anulaciones/alerta) -- confirmed via models/L_W/reclamos.py.
                "motivo": payload.motivo,
                "timestamp_evento": _now_naive(),
                "estado": payload.estado,
            },
            parent_uuid=tip["uuid_actual"],
            parent_fk_column="uuid_reclamo_padre",
            log_tx=True,
        )
    except repo_workflow.IllegalTransitionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "illegal_transition",
                "uuid": str(uuid),
                "estado_actual": tip["estado"],
                "estado_solicitado": payload.estado,
                "detail": str(exc),
            },
            headers=no_store,
        ) from exc

    # --- Step 6: single commit + response shape. ------------------------
    await session.commit()  # single commit

    _helpers.apply_no_store_header(response)
    return ReclamosRead.model_validate(new_row)


__all__ = ["router"]
