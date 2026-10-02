"""HU-F19.4 / REQ-26-W-ALERTA-DESCARTADA — alerta "descartar" transition.

One POST endpoint on a dedicated ``APIRouter`` — mirrors the DEC-TKT-06
precedent set by ``workflows_reimpresion.py`` (HU-F1.11): the
factory-mounted router at ``api/v1/workflows.py`` stays reserved for the
C+Q GET mount (``write_enabled=False`` for ``alerta`` — see that module's
docstring, "Custom transition endpoints ship in PR7"; this HU IS that
custom transition). Any write on an ``[L-W]`` workflow table ships as a
dedicated custom endpoint reusing ``repo.workflow.append_transition`` /
``STATE_MACHINES`` directly — same pattern ``dian.cloud_router`` uses for
``envio_dian`` / ``validacion_evento``, and the same pattern
``workflows_reimpresion.anular_reimpresion_ticket`` uses for the sibling
``reimpresion-ticket`` resource.

**Design note — ``write_enabled`` was intentionally NOT flipped on the
generic factory mount.** plan.md's HU-F19.4 BR3 literal wording says
"``write_enabled`` pasa de ``False`` a ``True``"; flipping that kwarg on
``_mount_workflow(resource="alerta", ...)`` in ``api/v1/workflows.py``
would instead wire up the GENERIC ``POST``/``PUT`` endpoints built by
``router_factory.make_router`` for ``repo_kind="versioned"``, which call
``repo.versioned.close_and_insert`` — the WRONG write helper for an
``[L-W]`` workflow chain (no ``STATE_MACHINES`` validation, no
``append_transition`` semantics). ``api/v1/workflows.py``'s own module
docstring already warns about this exact trap. The HU's own "ARCHIVOS DE
REFERENCIA" section additionally says to reuse
``append_transition``/``STATE_MACHINES`` "mismo patrón que
``envio_dian``/``validacion_evento``" — i.e. a bespoke endpoint, not the
factory flag. This module is that bespoke endpoint; ``workflows.py`` is
left untouched.

``STATE_MACHINES['alerta']`` (``repo/workflow.py``) already allows
``abierta|en_revision -> resuelta``; ``resuelta`` is terminal (``[]``), so
re-discarding an already-resolved alert is rejected with 409.

Permission: ``descartar_alerta`` — already seeded (canonical permission
set, migration ``0002_seed_permisos_canonicos.py``; deterministic UUID
assigned in ``0019_deterministic_permisos_uuids.py``). Enforced here via
an explicit ``require_permission`` dependency, per BR3's explicit mention
of ``permission_required="descartar_alerta"`` — stricter than the
``workflows_reimpresion`` precedent (which relies on issuer-only +
role-grant enforcement without an explicit ``require_permission`` call).
"""
from __future__ import annotations

import uuid as uuid_lib

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.permissions import require_permission
from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...db.engine import get_session
from ...models.L_W.alerta import Alerta
from ...repo import workflow as repo_workflow
from ...repo.workflow import _now_naive
from ...schemas.workflows import AlertaDescartarEndpoint, AlertaRead
from ..deps import requires_issuer
from . import _helpers

_descartar_alerta_issuer_dep = requires_issuer("operador-", "admin-")
_descartar_alerta_perm_dep = require_permission("descartar_alerta")

# New dedicated router (mirrors DEC-TKT-06). The parent router at
# ``api/v1/workflows.py`` keeps the factory-mounted C+Q GET mount for
# ``alerta``; this custom POST lives here to keep the factory path
# reserved for C+Q.
router = APIRouter(prefix="/workflows/alerta", tags=["workflows"])


@router.post(
    "/{uuid}/descartar",
    response_model=AlertaRead,
    status_code=201,
    summary=(
        "HU-F19.4 / REQ-26-W-ALERTA-DESCARTADA: INSERT NEW prod.alerta row "
        "with estado='resuelta', uuid_alerta_padre=<tip.uuid>. NEVER UPDATE "
        "the existing chain tip."
    ),
    responses={
        403: {"description": "tenant_scope_violation"},
        404: {"description": "alerta_not_found (V1)"},
        409: {"description": "alerta_ya_resuelta (V2 terminal)"},
        422: {"description": "Pydantic validation (observaciones vacía | missing_field)"},
    },
)
async def descartar_alerta(
    response: Response,
    uuid: uuid_lib.UUID,
    payload: AlertaDescartarEndpoint,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_descartar_alerta_issuer_dep),
    _perm: None = Depends(_descartar_alerta_perm_dep),  # requires 'descartar_alerta'
) -> AlertaRead:
    """REQ-26-W-ALERTA-DESCARTADA: discard/resolve an alerta via a NEW chain row.

    Sequence (mirrors ``workflows_reimpresion.anular_reimpresion_ticket``):
        1. issuer + permission claims (DI)
        2. V1 chain tip via ``read_chain_tip``; ``ChainNotFoundError`` -> 404
        3. tenant scope post-V1 (403 if operador- cross-branch)
        4. V2 terminal-state guard (409 if the tip is already 'resuelta')
        5. V3 INSERT NEW ``prod.alerta`` row via ``append_transition``
           (NEVER UPDATE the tip) — ``observaciones`` is stashed in
           ``datos_nuevos`` (no dedicated column; see module docstring)
        6. single ``await session.commit()`` + no-store header + response
    """
    no_store = _helpers.no_store_headers()

    # --- Step 2: V1 chain tip via read_chain_tip. ----------------------
    try:
        tip = await repo_workflow.read_chain_tip(
            session,
            Alerta,
            root_uuid=uuid,
            parent_fk_column="uuid_alerta_padre",
        )
    except repo_workflow.ChainNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"error": "alerta_not_found", "uuid": str(uuid)},
            headers=no_store,
        ) from None

    tip_row = (
        await session.execute(select(Alerta).where(Alerta.uuid == tip["uuid_actual"]))
    ).scalar_one_or_none()
    if tip_row is None:
        # Defensive: read_chain_tip returned a uuid that no longer exists.
        raise HTTPException(
            status_code=404,
            detail={"error": "alerta_not_found", "uuid": str(uuid)},
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

    # --- Step 4: V2 terminal-state guard. -------------------------------
    if tip["estado"] == "resuelta":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "alerta_ya_resuelta",
                "uuid": str(uuid),
                "estado_actual": "resuelta",
            },
            headers=no_store,
        )

    # --- Step 5: V3 INSERT NEW prod.alerta row (NEVER UPDATE the tip). -
    new_row = await repo_workflow.append_transition(
        session,
        Alerta,
        actor_uuid=ctx.actor_uuid,
        new_attrs={
            "uuid_sucursal": tip_row.uuid_sucursal,
            # The actor performing THIS transition, not the alert's
            # original reporter (mirrors
            # workflows_reimpresion.anular_reimpresion_ticket).
            "uuid_usuario": ctx.actor_uuid,
            "uuid_arqueo": tip_row.uuid_arqueo,
            "tipo_alerta": tip_row.tipo_alerta,
            "valor_diferencia_efectivo": tip_row.valor_diferencia_efectivo,
            "valor_diferencia_datafono": tip_row.valor_diferencia_datafono,
            "timestamp_evento": _now_naive(),
            # No dedicated `observaciones` column on prod.alerta (unlike
            # validacion_evento) — reuse the existing free-form JSONB
            # payload column (module docstring).
            "datos_nuevos": {"observaciones": payload.observaciones},
            "estado": "resuelta",
        },
        parent_uuid=tip["uuid_actual"],
        parent_fk_column="uuid_alerta_padre",
        log_tx=True,
    )

    # --- Step 6: single commit + response shape. ------------------------
    await session.commit()  # single commit

    _helpers.apply_no_store_header(response)
    return AlertaRead.model_validate(new_row)


__all__ = ["router"]
