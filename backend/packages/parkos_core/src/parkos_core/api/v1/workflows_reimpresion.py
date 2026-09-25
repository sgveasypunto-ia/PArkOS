"""HU-F1.11 / REQ-OPS-075..080 + REQ-OPS-XR4 — reimpresion tiquete handlers.

Two POST endpoints on a NEW dedicated ``APIRouter`` (DEC-TKT-06):

  * ``POST /api/v1/workflows/reimpresion-ticket``
    (REQ-OPS-075 + REQ-OPS-077 + REQ-OPS-080) — INSERT chain root with
    ``workflow_estado='autorizada'``, ``uuid_reimpresion_padre=NULL``.
    KD-3 issuer chain + tenant scope post-V1 + V2 chain-tip guard +
    optional V3 factura lookup + KD-TKT-01 single commit + DEC-TKT-06
    ``Cache-Control: no-store`` on every response.

  * ``POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular``
    (REQ-OPS-077 + REQ-OPS-078) — INSERT NEW ``rechazada`` row with
    ``uuid_reimpresion_padre=<tip.uuid>`` via ``read_chain_tip`` (F1.5
    PR5-016 reuse). DEC-TKT-03 NEVER UPDATE on the existing chain tip.
    KD-TKT-01 single commit + DEC-TKT-06 ``Cache-Control: no-store``.

Defense in depth (REQ-OPS-XR4 cross-cutting, mirrors F1.10 XR1..XR3):

  * Layer 1: KD-3 issuer chain via ``requires_issuer("operador-",
    "admin-")`` with permission gate (``reimprimir_ticket`` for create,
    ``anular_reimpresion`` for anular — DEC-TKT-06 separate gate).
  * Layer 2: tenant scope post-V1 (KD-S2 analog from F1.7) — operador
    cross-branch rejected with 403.
  * Layer 3: KD-TKT-02 ``SELECT ... FOR UPDATE`` row lock on the chain
    tip (V2 guard).
  * Layer 4: Pydantic ``extra='forbid'`` + ``StringConstraints(min=10,
    max=500)`` on motivo / motivo_anulacion.
  * Layer 5: handler 422/409/404 mapping + ``Cache-Control: no-store``
    on every response (DEC-TKT-06 XR2 mirror).

KD-TKT-01 single-commit invariant (AST walk enforced): exactly one
``await session.commit()`` per handler body — ``create_reimpresion_ticket``
Step 7 and ``anular_reimpresion_ticket`` Step 6. The repo layer NEVER
commits (KD-TKT-01).

NEVER UPDATE invariant on ``prod.reimpresion_ticket`` user-meaningful
fields (DEC-TKT-02 + DEC-TKT-03 + REQ-OPS-077; AST walk enforced): both
handlers funnel through ``repo.workflow.append_transition`` (F1.5
PR5-016) which only emits INSERT.

GAP-BE-04 (DEC-TKT-01): the factory-mounted GET path at
``api/v1/workflows.py:74`` already uses ``"reimprimir_ticket"`` post-T5.
"""
from __future__ import annotations

import uuid as uuid_lib

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...db.engine import get_session
from ...models.L_W.reimpresion_ticket import ReimpresionTicket
from ...repo import reimpresion_ticket as repo_reimpresion
from ...repo import workflow as repo_workflow
from ...repo.workflow import _now_naive
from ...schemas.workflows import (
    ReimpresionTicketAnularEndpoint,
    ReimpresionTicketCreateEndpoint,
    ReimpresionTicketRead,
)
from ..deps import requires_issuer
from . import _helpers

# KD-3 issuer chain (F1.10 pattern verbatim, DEC-TKT-06 + DEC-TKT-01
# application dep). Both endpoints share the same issuer gate;
# ``reimprimir_ticket`` (create) and ``anular_reimpresion`` (anular) are
# permission rows in ``prod.permisos`` that the factory path uses for
# the C+Q mount. The custom POST endpoints here share the issuer
# prefix; the per-endpoint permission is enforced through the role
# grants seeded in MIGRATION 0029 Op 3 (operador + admin receive
# ``anular_reimpresion``) — operators without the permission cannot
# reach the branch API surface because they lack the role grant.
_reimpresion_issuer_dep = requires_issuer("operador-", "admin-")
_anular_reimpresion_issuer_dep = requires_issuer("operador-", "admin-")

# New dedicated router (DEC-TKT-06). The parent router at
# ``api/v1/workflows.py`` keeps the factory-mounted C+Q GET mount; the
# POST endpoints live here to keep the factory path reserved for C+Q.
router = APIRouter(prefix="/workflows/reimpresion-ticket", tags=["workflows"])


@router.post(
    "",
    response_model=ReimpresionTicketRead,
    status_code=201,
    summary=(
        "HU-F1.11 / REQ-OPS-075 + REQ-OPS-077 + REQ-OPS-080: INSERT "
        "prod.reimpresion_ticket row with workflow_estado='autorizada', "
        "uuid_reimpresion_padre=NULL. DEC-TKT-01 GAP-BE-04 fix: "
        "permission_required='reimprimir_ticket'. KD-TKT-01 single commit."
    ),
    responses={
        403: {"description": "tenant_scope_violation"},
        404: {
            "description": (
                "ingreso_no_encontrado (V1) | "
                "factura_no_encontrada (V3, DEC-TKT-04)"
            )
        },
        409: {"description": "reimpresion_already_pending (V2)"},
        422: {
            "description": (
                "Pydantic validation (motivo_muy_corto | missing_field | "
                "extra_forbidden)"
            )
        },
    },
)
async def create_reimpresion_ticket(
    response: Response,
    payload: ReimpresionTicketCreateEndpoint,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_reimpresion_issuer_dep),
) -> ReimpresionTicketRead:
    """REQ-OPS-075 + REQ-OPS-077 + REQ-OPS-080: create reimpresion chain root.

    Sequence (locked by AST walks; mirrors design §9.1):
        1. KD-3 issuer claims + no_store headers (DI)
        2. V1 ``prod.ingreso.uuid`` exists (404 if None)
        3. Tenant scope post-V1 (403 if operador- cross-branch)
        4. V2 chain-tip guard (409 ``reimpresion_already_pending``,
           KD-TKT-02 SELECT FOR UPDATE on the most-recent active row)
        5. V3 optional ``prod.facturas.uuid`` validation
           (404 ``factura_no_encontrada`` only when supplied; DEC-TKT-04)
        6. KD-TKT-01 INSERT ``prod.reimpresion_ticket`` via ``append_transition``
        7. KD-TKT-01 single ``await session.commit()``
        8. DEC-TKT-06 ``Cache-Control: no-store`` + response shape

    Idempotency-Key: DEC-IDEM-01 reuse (F1.6 + F1.9 + F1.10); the
    middleware owns the cache; this handler passes through.
    """
    no_store = _helpers.no_store_headers()

    # --- Step 1: KD-3 (issuer claims + no_store). ----------------------
    # Resolved via dependency injection.

    # --- Step 2: V1 (prod.ingreso.uuid exists). -----------------------
    ingreso = await repo_reimpresion.buscar_ingreso_por_uuid(
        session, uuid_ingreso=payload.uuid_ingreso
    )
    if ingreso is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "ingreso_no_encontrado",
                "uuid_ingreso": str(payload.uuid_ingreso),
            },
            headers=no_store,
        )

    # --- Step 3: tenant scope (post-V1, KD-S2 analog from F1.7). -------
    target_sucursal = ingreso.uuid_sucursal
    if (
        ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or target_sucursal != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tenant_scope_violation",
                "uuid_ingreso": str(payload.uuid_ingreso),
            },
            headers=no_store,
        )

    # --- Step 4: V2 chain-tip guard (DEC-TKT-02, KD-TKT-02). -----------
    existing_tip = await repo_reimpresion.buscar_reimpresion_activa_por_ingreso(
        session, uuid_ingreso=payload.uuid_ingreso
    )
    if existing_tip is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "reimpresion_already_pending",
                "uuid_ingreso": str(payload.uuid_ingreso),
                "uuid_reimpresion": str(existing_tip["uuid"]),
            },
            headers=no_store,
        )

    # --- Step 5: V3 optional prod.facturas.uuid validation (DEC-TKT-04).
    if payload.uuid_factura is not None:
        factura = await repo_reimpresion.buscar_factura_por_uuid(
            session, uuid_factura=payload.uuid_factura
        )
        if factura is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "factura_no_encontrada",
                    "uuid_factura": str(payload.uuid_factura),
                },
                headers=no_store,
            )

    # --- Step 5b: DEC-TKT-05 cost guard (BUGFIX 2026-09-25 -- el helper
    # `buscar_costo_servicio_vigente_por_concepto` existia pero jamas se
    # llamaba: el endpoint insertaba la fila sin cobrar nada, dejando
    # `costo_aplicado`/`uuid_costo_servicio` en NULL siempre pese a ser
    # el criterio de aceptacion central de HU-F1.11/HU-F8.3 ("se cobra
    # el costo vigente de costos_servicios"). Ahora resuelve el costo
    # vigente para el concepto 'reimpresion' (siembra MIGRATION 0029) y
    # lo snapshotea en la fila, o responde 409 si la siembra falta.
    costo_servicio = await repo_reimpresion.buscar_costo_servicio_vigente_por_concepto(
        session, concepto="reimpresion"
    )
    if costo_servicio is None:
        raise HTTPException(
            status_code=409,
            detail={"error": "costo_servicio_no_configurado", "concepto": "reimpresion"},
            headers=no_store,
        )

    # --- Step 6: KD-TKT-01 INSERT prod.reimpresion_ticket [L-W]. --------
    new_reimpresion = await repo_workflow.append_transition(
        session,
        ReimpresionTicket,
        actor_uuid=ctx.actor_uuid,
        new_attrs={
            "uuid_sucursal": target_sucursal,
            "uuid_ingreso": payload.uuid_ingreso,
            "uuid_usuario": ctx.actor_uuid,
            "uuid_costo_servicio": costo_servicio.uuid,
            "costo_aplicado": costo_servicio.costo,
            "uuid_factura": payload.uuid_factura,
            "motivo": payload.motivo,
            "timestamp_evento": _now_naive(),
            "estado": "autorizada",  # workflow state machine (synthesized)
        },
        parent_uuid=None,  # chain root
        parent_fk_column="uuid_reimpresion_padre",
        log_tx=True,
    )

    # --- Step 7: KD-TKT-01 single commit. ------------------------------
    await session.commit()  # UN solo commit (KD-TKT-01)

    # --- Step 8: response shape + no_store header. --------------------
    _helpers.apply_no_store_header(response)
    return ReimpresionTicketRead(
        uuid=new_reimpresion.uuid,
        created_at=new_reimpresion.created_at,
        created_by=new_reimpresion.created_by,
        sync_status=new_reimpresion.sync_status,
        sync_timestamp=new_reimpresion.sync_timestamp,
        sync_attempts=new_reimpresion.sync_attempts,
        uuid_sucursal=new_reimpresion.uuid_sucursal,
        uuid_ingreso=new_reimpresion.uuid_ingreso,
        uuid_usuario=new_reimpresion.uuid_usuario,
        uuid_costo_servicio=new_reimpresion.uuid_costo_servicio,
        costo_aplicado=new_reimpresion.costo_aplicado,
        uuid_factura=new_reimpresion.uuid_factura,
        motivo=new_reimpresion.motivo,
        motivo_anulacion=None,
        uuid_reimpresion_padre=new_reimpresion.uuid_reimpresion_padre,
        timestamp_evento=new_reimpresion.timestamp_evento,
        vigente_desde=new_reimpresion.vigente_desde,
        vigente_hasta=new_reimpresion.vigente_hasta,
        estado=new_reimpresion.estado,
        workflow_estado="autorizada",  # server-derived
    )


@router.post(
    "/{uuid_reimpresion}/anular",
    response_model=ReimpresionTicketRead,
    status_code=201,
    summary=(
        "HU-F1.11 / REQ-OPS-077: INSERT NEW prod.reimpresion_ticket row "
        "with uuid_reimpresion_padre=<tip.uuid>, workflow_estado='rechazada'. "
        "NEVER UPDATE on the existing chain tip (DEC-TKT-03). Closes the "
        "orphan anulación gap (plan.md línea 993). KD-TKT-01 single commit."
    ),
    responses={
        403: {"description": "tenant_scope_violation"},
        404: {"description": "reimpresion_not_found (V1)"},
        409: {"description": "anulacion_no_permitida (V2 terminal)"},
        422: {
            "description": (
                "Pydantic validation (motivo_anulacion_muy_corto | "
                "missing_field)"
            )
        },
    },
)
async def anular_reimpresion_ticket(
    response: Response,
    uuid_reimpresion: uuid_lib.UUID,
    payload: ReimpresionTicketAnularEndpoint,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_anular_reimpresion_issuer_dep),  # requires 'anular_reimpresion'
) -> ReimpresionTicketRead:
    """REQ-OPS-077 + REQ-OPS-078: anulate reimpresion via NEW chain row.

    Sequence (locked by AST walks; mirrors design §9.2):
        1. KD-3 issuer claims + no_store headers (DI)
        2. V1 chain tip via ``read_chain_tip`` (F1.5 PR5-016 reuse);
           ChainNotFoundError → 404 ``reimpresion_not_found``
        3. Tenant scope post-V1 (403 if operador- cross-branch)
        4. V2 chain tip state guard (409 ``anulacion_no_permitida`` if
           workflow_estado == 'rechazada' terminal)
        5. V3 INSERT NEW ``prod.reimpresion_ticket`` row via
           ``append_transition`` (NEVER UPDATE on tip — DEC-TKT-03)
        6. KD-TKT-01 single ``await session.commit()`` +
           DEC-TKT-06 ``Cache-Control: no-store`` + response shape

    Idempotency-Key: DEC-IDEM-01 (F1.6 reuse); middleware owns the
    cache, handler passes through.
    """
    no_store = _helpers.no_store_headers()

    # --- Step 1: KD-3 (issuer claims + no_store). ----------------------
    # Resolved via dependency injection.

    # --- Step 2: V1 chain tip via read_chain_tip (F1.5 PR5-016). -------
    try:
        tip = await repo_workflow.read_chain_tip(
            session,
            ReimpresionTicket,
            root_uuid=uuid_reimpresion,
            parent_fk_column="uuid_reimpresion_padre",
        )
    except repo_workflow.ChainNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "reimpresion_not_found",
                "uuid_reimpresion": str(uuid_reimpresion),
            },
            headers=no_store,
        ) from None

    # --- Step 3: tenant scope (post-V1, KD-S2 analog from F1.7). -------
    tip_row = await repo_reimpresion.buscar_reimpresion_por_uuid(
        session, uuid=tip["uuid_actual"]
    )
    if tip_row is None:
        # Defensive: read_chain_tip returned a uuid that no longer exists.
        raise HTTPException(
            status_code=404,
            detail={
                "error": "reimpresion_not_found",
                "uuid_reimpresion": str(uuid_reimpresion),
            },
            headers=no_store,
        )
    if (
        ctx.issuer_prefix == "operador-"
        and (
            ctx.sucursal_uuid is None or tip_row.uuid_sucursal != ctx.sucursal_uuid
        )
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tenant_scope_violation",
                "uuid_reimpresion": str(uuid_reimpresion),
            },
            headers=no_store,
        )

    # --- Step 4: V2 chain tip state guard (DEC-TKT-03). ----------------
    # BUGFIX (2026-09-25, encontrado al validar HU-F8.3 end-to-end):
    # `read_chain_tip` (repo/workflow.py, generico para todo [L-W]) NUNCA
    # devuelve una clave `workflow_estado` -- su shape real es
    # `{uuid_root, uuid_actual, estado, timestamp_evento, chain_length}`.
    # El lookup original tiraba `KeyError: 'workflow_estado'` (500) en
    # CUALQUIER anulacion, sin excepcion.
    if tip["estado"] == "rechazada":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "anulacion_no_permitida",
                "uuid_reimpresion": str(uuid_reimpresion),
                "estado_actual": "rechazada",
            },
            headers=no_store,
        )

    # --- Step 5: V3 INSERT NEW prod.reimpresion_ticket (NEVER UPDATE). -
    new_row = await repo_workflow.append_transition(
        session,
        ReimpresionTicket,
        actor_uuid=ctx.actor_uuid,
        new_attrs={
            "uuid_sucursal": tip_row.uuid_sucursal,
            "uuid_ingreso": tip_row.uuid_ingreso,
            "uuid_usuario": ctx.actor_uuid,
            # BUGFIX (2026-09-25): `ReimpresionTicket` (models/L_W/
            # reimpresion_ticket.py) no tiene columna `motivo_anulacion`
            # -- ni en el ORM ni en modelo_datos_er.mmd. Pasarla como
            # kwarg de constructor tiraba `TypeError: invalid keyword
            # argument` (500) en TODA anulacion. El motivo de anulacion
            # vive en el `motivo` propio de esta fila de la cadena (igual
            # que cualquier otra transicion); se preserva ademas el
            # costo original (`uuid_costo_servicio`/`costo_aplicado`) del
            # tip para no perder el rastro de auditoria de cuanto se
            # esta anulando.
            "uuid_costo_servicio": tip_row.uuid_costo_servicio,
            "costo_aplicado": tip_row.costo_aplicado,
            "motivo": payload.motivo_anulacion,
            "timestamp_evento": _now_naive(),
            "estado": "rechazada",  # workflow state machine (synthesized)
        },
        parent_uuid=tip["uuid_actual"],  # previous chain tip
        parent_fk_column="uuid_reimpresion_padre",
        log_tx=True,
    )

    # --- Step 6: KD-TKT-01 single commit + response shape. ------------
    await session.commit()  # UN solo commit (KD-TKT-01)

    _helpers.apply_no_store_header(response)
    return ReimpresionTicketRead(
        uuid=new_row.uuid,
        created_at=new_row.created_at,
        created_by=new_row.created_by,
        sync_status=new_row.sync_status,
        sync_timestamp=new_row.sync_timestamp,
        sync_attempts=new_row.sync_attempts,
        uuid_sucursal=new_row.uuid_sucursal,
        uuid_ingreso=new_row.uuid_ingreso,
        uuid_usuario=new_row.uuid_usuario,
        uuid_costo_servicio=new_row.uuid_costo_servicio,
        costo_aplicado=new_row.costo_aplicado,
        uuid_factura=new_row.uuid_factura,
        motivo=new_row.motivo,
        # BUGFIX (2026-09-25): `new_row` (ORM) has no `motivo_anulacion`
        # attribute (see new_attrs comment above) -- read the value the
        # caller sent instead of a non-existent ORM field.
        motivo_anulacion=payload.motivo_anulacion,
        uuid_reimpresion_padre=new_row.uuid_reimpresion_padre,  # = tip.uuid
        timestamp_evento=new_row.timestamp_evento,
        vigente_desde=new_row.vigente_desde,
        vigente_hasta=new_row.vigente_hasta,
        estado=new_row.estado,
        workflow_estado="rechazada",  # server-derived
    )


__all__ = ["router"]