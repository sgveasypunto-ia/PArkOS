"""HU-F20.3 / REQ-21, REQ-22 — anulaciones workflow transition handlers.

Two POST endpoints on a dedicated ``APIRouter`` (same DEC-TKT-06 pattern as
``workflows_reimpresion.py`` / ``workflows_alerta.py``): the factory-mounted
router at ``api/v1/workflows.py`` stays reserved for the C+Q GET mount
(``write_enabled=False`` for ``anulaciones`` — see that module's docstring).
Any write on an ``[L-W]`` workflow table ships as a dedicated custom endpoint
reusing ``repo.workflow.append_transition`` / ``STATE_MACHINES`` directly —
NEVER by flipping ``write_enabled=True`` on the generic mount, which would
instead wire the GENERIC ``POST``/``PUT`` built by
``router_factory.make_router`` for ``repo_kind="versioned"`` (calls
``repo.versioned.close_and_insert`` — the WRONG write helper for an
``[L-W]`` chain: no ``STATE_MACHINES`` validation, no ``append_transition``
semantics). ``api/v1/workflows.py``'s own module docstring already warns
about this exact trap.

* ``POST /api/v1/workflows/anulaciones`` — INSERT chain root with
  ``estado='iniciada'``, ``uuid_anulacion_padre=NULL``. Permission
  ``anular_ingreso_salida`` (seeded by migration
  ``0059_seed_router_permission_codes.py`` — NOT ``0029`` as plan.md's prose
  suggested; see module-level note below).
* ``POST /api/v1/workflows/anulaciones/{uuid}/transicion`` — the body names
  the destination ``estado``; ``append_transition`` validates
  ``tip.estado -> estado`` against ``STATE_MACHINES['anulaciones']``
  (``repo/workflow.py``) and raises ``IllegalTransitionError`` (mapped to
  409 here — no global exception handler exists for it anywhere in the
  codebase, including ``dian.cloud_router``, so this module adds the
  local ``try/except`` mapping).

PERMISSION DRIFT VS plan.md (confirmed by grepping the migrations, not by
trusting BR prose — same drift class already documented elsewhere in this
Parte II):

* plan.md's BR1 names ``anular_ingreso`` / ``anular_salida`` as two separate
  permissions. The ONLY permission the codebase ever seeded for this HU is
  the single combined ``anular_ingreso_salida``. The existing read-only
  factory mount (``api/v1/workflows.py``'s ``_ROUTER_CONFIG["anulaciones"]``)
  already uses exactly that combined string; this module reuses it verbatim
  for the root-creation endpoint.
* ``anular_ingreso_salida`` is NOT seeded by migration
  ``0029_reimpresion_siembra_and_permiso_anular.py`` (that migration seeds
  an UNRELATED code, ``anular_reimpresion``, for the ``reimpresion_ticket``
  sibling resource — confirmed by reading 0029 in full). The actual seed is
  migration ``0059_seed_router_permission_codes.py``
  (``_ROUTER_PERMISSION_UUIDS["anular_ingreso_salida"]``, a deterministic
  ``uuid5`` row, confirmed via ``grep``).
* ``aprobar_anulacion`` / ``ejecutar_anulacion`` ARE real, canonical codes —
  seeded by ``0002_seed_permisos_canonicos.py``, deterministic UUIDs assigned
  by ``0019_deterministic_permisos_uuids.py`` (confirmed via ``grep``; these
  are the ones migration ``0053``'s docstring lists as already-real for
  HU-R03).

STATE NAME DRIFT VS plan.md / the HU prose (confirmed via
``repo/workflow.py:STATE_MACHINES['anulaciones']``, not via BR wording):

    plan.md prose:  solicitada -> aprobada -> ejecutada
    Real STATE_MACHINES: iniciada -> autorizada -> ejecutada (+ rechazada
    from either non-terminal state)

The real state names visibly match ``STATE_MACHINES['reimpresion_ticket']``
(``solicitada -> {autorizada, rechazada}``, ``autorizada -> {ejecutada,
rechazada}``) — the sibling resource's OWN state names — which is almost
certainly the actual source of the drift in the HU prose. This module uses
the REAL ``anulaciones`` state names throughout; using the prose names would
make ``append_transition`` raise ``IllegalTransitionError`` on every single
call.

PERMISSION-PER-STEP DESIGN DECISION (not fully specified by the HU): the HU
names ``aprobar_anulacion`` for the ``iniciada`` step and ``ejecutar_anulacion``
for the ``autorizada`` step, but only describes the "approve" / "execute"
outcome of each — it does not say which permission gates REJECTING
(``-> rechazada``) at either step, and no third "reject" permission is
seeded (inventing one is explicitly out of scope). This module reads the
permission as gating the DECISION AT THE CURRENT STEP regardless of which
of its two legal outcomes the caller picks: ``aprobar_anulacion`` is checked
whenever the tip is ``iniciada`` (whether the request asks for
``autorizada`` or ``rechazada``), and ``ejecutar_anulacion`` whenever the
tip is ``autorizada``. A request against an already-terminal tip
(``ejecutada``/``rechazada``) has no step to gate, so no permission check
runs — ``append_transition`` still rejects it as an illegal transition
(409), under the plain issuer gate only.

PERMISSION CHECK IS INLINE, NOT A STATIC ``Depends`` (deviation from the
``workflows_alerta.py`` / ``workflows_reimpresion.py`` precedent, which use
``_perm: None = Depends(require_permission(code))``): the required code here
depends on the chain's CURRENT state, discovered only after reading the
chain tip, so it cannot be resolved at route-declaration time. The handler
calls ``auth.permissions.actor_has_permission`` directly once the tip is
known. This also makes the 403 path exercisable by calling the handler
function directly (the test style every sibling ``[L-W]`` endpoint test uses)
instead of being silently bypassed the way a ``Depends``-only permission gate
would be when a test passes ``None`` for that parameter.
"""
from __future__ import annotations

import uuid as uuid_lib

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.permissions import actor_has_permission
from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...db.engine import get_session
from ...models.L_W.anulaciones import Anulaciones
from ...repo import workflow as repo_workflow
from ...repo.workflow import _now_naive
from ...schemas.workflows import (
    AnulacionesRead,
    AnulacionesSolicitarEndpoint,
    AnulacionesTransicionEndpoint,
)
from ..deps import requires_issuer
from . import _helpers

# KD-3 issuer chain (F1.10 / HU-F19.4 pattern). Both endpoints share the
# same issuer gate; the per-step permission is enforced inline (see module
# docstring) because it depends on runtime chain state.
_anulaciones_issuer_dep = requires_issuer("operador-", "admin-")

# code -> permission required to decide a transition FROM that estado.
# Deliberately does NOT cover 'ejecutada'/'rechazada' (terminal; no decision
# left to gate -- see module docstring).
_PERMISO_POR_ESTADO_ORIGEN: dict[str, str] = {
    "iniciada": "aprobar_anulacion",
    "autorizada": "ejecutar_anulacion",
}

router = APIRouter(prefix="/workflows/anulaciones", tags=["workflows"])


@router.post(
    "",
    response_model=AnulacionesRead,
    status_code=201,
    summary=(
        "HU-F20.3: INSERT prod.anulaciones row with estado='iniciada', "
        "uuid_anulacion_padre=NULL. permission_required='anular_ingreso_salida'."
    ),
    responses={
        403: {"description": "permission_denied (missing 'anular_ingreso_salida')"},
        422: {
            "description": (
                "Pydantic validation (motivo vacío | missing_field | "
                "tipo_anulable/uuid_ingreso/uuid_salida mismatch | extra_forbidden)"
            )
        },
    },
)
async def solicitar_anulacion(
    response: Response,
    payload: AnulacionesSolicitarEndpoint,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_anulaciones_issuer_dep),
) -> AnulacionesRead:
    """HU-F20.3: create the ``anulaciones`` chain root.

    Sequence:
        1. KD-3 issuer claims + no_store headers (DI)
        2. Permission gate: ``anular_ingreso_salida`` (403 if missing)
        3. INSERT ``prod.anulaciones`` root via ``append_transition``
           (``parent_uuid=None`` — no STATE_MACHINES check on a root row)
        4. Single ``await session.commit()``
        5. ``Cache-Control: no-store`` + response shape
    """
    no_store = _helpers.no_store_headers()

    if not await actor_has_permission(
        session, actor_uuid=ctx.actor_uuid, codigo="anular_ingreso_salida"
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "permission_denied", "detail": "anular_ingreso_salida"},
            headers=no_store,
        )

    new_row = await repo_workflow.append_transition(
        session,
        Anulaciones,
        actor_uuid=ctx.actor_uuid,
        new_attrs={
            "uuid_sucursal": ctx.sucursal_uuid,
            "tipo_anulable": payload.tipo_anulable,
            "uuid_ingreso": payload.uuid_ingreso,
            "uuid_salida": payload.uuid_salida,
            "uuid_usuario": ctx.actor_uuid,
            "motivo": payload.motivo,
            "timestamp_evento": _now_naive(),
            "estado": "iniciada",
        },
        parent_uuid=None,  # chain root
        parent_fk_column="uuid_anulacion_padre",
        log_tx=True,
    )

    await session.commit()  # single commit

    _helpers.apply_no_store_header(response)
    return AnulacionesRead.model_validate(new_row)


@router.post(
    "/{uuid}/transicion",
    response_model=AnulacionesRead,
    status_code=201,
    summary=(
        "HU-F20.3: INSERT NEW prod.anulaciones row chained via "
        "uuid_anulacion_padre. Destination estado is caller-supplied; "
        "append_transition validates it against STATE_MACHINES['anulaciones']."
    ),
    responses={
        403: {
            "description": (
                "tenant_scope_violation | permission_denied "
                "('aprobar_anulacion' from 'iniciada', 'ejecutar_anulacion' "
                "from 'autorizada')"
            )
        },
        404: {"description": "anulacion_not_found (chain root does not exist)"},
        409: {"description": "illegal_transition (IllegalTransitionError)"},
        422: {"description": "Pydantic validation (motivo vacío | missing_field | extra_forbidden)"},
    },
)
async def transicionar_anulacion(
    response: Response,
    uuid: uuid_lib.UUID,
    payload: AnulacionesTransicionEndpoint,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_anulaciones_issuer_dep),
) -> AnulacionesRead:
    """HU-F20.3: transition an ``anulaciones`` chain via a NEW chain row.

    Sequence:
        1. KD-3 issuer claims + no_store headers (DI)
        2. V1 chain tip via ``read_chain_tip``; ``ChainNotFoundError`` -> 404
        3. Tenant scope post-V1 (403 if operador- cross-branch)
        4. Permission gate resolved from the tip's CURRENT estado (403 if
           missing; no gate at all if the tip is already terminal — see
           module docstring)
        5. INSERT NEW ``prod.anulaciones`` row via ``append_transition``
           (NEVER UPDATE the tip); ``IllegalTransitionError`` -> 409
        6. Single ``await session.commit()`` + no-store header + response
    """
    no_store = _helpers.no_store_headers()

    # --- Step 2: V1 chain tip via read_chain_tip. ----------------------
    try:
        tip = await repo_workflow.read_chain_tip(
            session,
            Anulaciones,
            root_uuid=uuid,
            parent_fk_column="uuid_anulacion_padre",
        )
    except repo_workflow.ChainNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"error": "anulacion_not_found", "uuid": str(uuid)},
            headers=no_store,
        ) from None

    tip_row = (
        await session.execute(select(Anulaciones).where(Anulaciones.uuid == tip["uuid_actual"]))
    ).scalar_one_or_none()
    if tip_row is None:
        # Defensive: read_chain_tip returned a uuid that no longer exists.
        raise HTTPException(
            status_code=404,
            detail={"error": "anulacion_not_found", "uuid": str(uuid)},
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

    # --- Step 4: permission gate resolved from the CURRENT estado. -----
    permiso_requerido = _PERMISO_POR_ESTADO_ORIGEN.get(tip["estado"])
    if permiso_requerido is not None and not await actor_has_permission(
        session, actor_uuid=ctx.actor_uuid, codigo=permiso_requerido
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "permission_denied", "detail": permiso_requerido},
            headers=no_store,
        )
    # permiso_requerido is None -> tip is already terminal; no permission
    # to gate. append_transition below rejects it as an illegal transition.

    # --- Step 5: V3 INSERT NEW prod.anulaciones row (NEVER UPDATE). -----
    try:
        new_row = await repo_workflow.append_transition(
            session,
            Anulaciones,
            actor_uuid=ctx.actor_uuid,
            new_attrs={
                "uuid_sucursal": tip_row.uuid_sucursal,
                "tipo_anulable": tip_row.tipo_anulable,
                "uuid_ingreso": tip_row.uuid_ingreso,
                "uuid_salida": tip_row.uuid_salida,
                # The actor performing THIS transition, not the original
                # requester (mirrors workflows_alerta.descartar_alerta).
                "uuid_usuario": ctx.actor_uuid,
                "motivo": payload.motivo,
                "timestamp_evento": _now_naive(),
                "estado": payload.estado,
            },
            parent_uuid=tip["uuid_actual"],
            parent_fk_column="uuid_anulacion_padre",
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
    return AnulacionesRead.model_validate(new_row)


__all__ = ["router"]
