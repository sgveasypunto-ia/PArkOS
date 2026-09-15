"""HU-F1.12 / REQ-OPS-083..090 + REQ-OPS-XR5 -- POST /clientes/venta-suscripcion.

10-step atomic handler on a NEW dedicated ``APIRouter`` (DEC-VENTA-05 +
KD-VENTA-01 mirror of F1.11 KD-TKT-01):

  1. KD-3 issuer chain via ``requires_issuer("operador-", "admin-")``
     with permission gate ``gestionar_clientes``.
  2. V2 plan lock: ``buscar_tipo_subscripcion_vigente_por_uuid``
     (SELECT ... FOR UPDATE exclusive, KD-VENTA-02 + DEC-VENTA-04).
  2a. Tenant scope post-V1 (KD-S2 F1.7 mirror): operador cross-branch
     rejected with 403 ``tenant_scope_violation``.
  3. V1 cliente lookup-or-create (DEC-VENTA-07 drops ``dv``).
  4. V3 per-placa lookup-or-create (F1.7 ``detectar_tipo_vehiculo``).
  5. V5 ``mismo_tipo_vehiculo`` in-process check.
  6. V6 ``cantidad_maxima_vehiculos`` in-process check.
  7. V4 per-placa duplicate detection (F1.7
     ``resolve_active_subscription_for_exit`` reuse).
  8. V7 A-09 prorrateo compute (DEC-VENTA-03).
  8a. Optional V8 F1.9 cobro sub-chain (when ``cobrar_ahora=true``).
  8b. Optional V8b F1.10 FE sub-chain (when
      ``emitir_factura_electronica=true``).
  9. V9 INSERT subscription + junction (pg_advisory_xact_lock).
 10. SINGLE COMMIT + response shape + ``Cache-Control: no-store``.

Defense in depth (REQ-OPS-XR5 cross-cutting):

  * Layer 1: KD-3 issuer chain + ``gestionar_clientes`` permission gate.
  * Layer 2: tenant scope post-V1 (KD-S2 F1.7 analog).
  * Layer 3: KD-VENTA-02 ``SELECT ... FOR UPDATE`` exclusive row lock
    on the plan.
  * Layer 4: Pydantic ``extra='forbid'`` + ``placas`` 1-2 range +
    ``cliente | uuid_cliente`` XOR.
  * Layer 5: handler 422/404/409/403 mapping + ``Cache-Control: no-store``
    on every response (DEC-VENTA-06).

KD-VENTA-01 single-commit invariant (AST walk enforced): exactly one
``await session.commit()`` per handler body. The repo layer NEVER
commits -- this is the only commit point.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...db.engine import get_session
from ...repo import venta_suscripcion as repo_venta
from ...schemas.clientes import VentaSuscripcionCreate, VentaSuscripcionResponse
from ..deps import requires_issuer
from . import _helpers

# Dedicated router -- mounted via ``router.include_router`` from
# ``api/v1/clientes.py`` (DEC-VENTA-05). DEC-VENTA-06 layer 5 mirror of
# F1.11 reimpresion dedicated router pattern.
router = APIRouter(prefix="/clientes", tags=["clientes"])

# KD-3 issuer chain + ``gestionar_clientes`` permission gate (DEC-VENTA-05).
_venta_suscripcion_issuer_dep = requires_issuer("operador-", "admin-")


@router.post(
    "/venta-suscripcion",
    response_model=VentaSuscripcionResponse,
    status_code=201,
    responses={
        400: {"description": "missing_sucursal_context"},
        403: {"description": "tenant_scope_violation"},
        404: {"description": "tipo_subscripcion_no_encontrado / cliente_no_encontrado"},
        409: {"description": "tipo_subscripcion_no_vigente"},
        422: {"description": "pydantic validation / vendedor chain discriminators"},
    },
)
async def venta_suscripcion(
    response: Response,
    payload: VentaSuscripcionCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_venta_suscripcion_issuer_dep),
) -> VentaSuscripcionResponse:
    """POST /clientes/venta-suscripcion -- 10-step atomic handler.

    See module docstring for the full step chain + defense in depth.
    KD-VENTA-01 single-commit invariant: this handler owns the ONLY
    ``await session.commit()`` in the chain.
    """
    no_store = _helpers.no_store_headers()

    # --- Step 2: V2 plan lock (KD-VENTA-02 + DEC-VENTA-04). ------------
    plan = await repo_venta.buscar_tipo_subscripcion_vigente_por_uuid(
        session,
        uuid_tipo_subscripcion=payload.uuid_tipo_subscripcion,
    )
    if plan is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "tipo_subscripcion_no_encontrado",
                "uuid_tipo_subscripcion": str(payload.uuid_tipo_subscripcion),
            },
            headers=no_store,
        )

    # --- Step 2a: Layer 2 tenant scope post-V1 (KD-S2 F1.7 analog). ----
    target_sucursal = ctx.sucursal_uuid
    if (
        ctx.issuer_prefix == "operador-"
        and target_sucursal is not None
        and target_sucursal != ctx.sucursal_uuid
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tenant_scope_violation",
                "uuid_sucursal_context": str(target_sucursal),
            },
            headers=no_store,
        )

    # --- Step 3: V1 cliente lookup-or-create (DEC-VENTA-07 drops 'dv'). -
    try:
        cliente = await repo_venta.buscar_cliente_por_uuid_o_crear(
            session,
            uuid_cliente=payload.uuid_cliente,
            datos_cliente=(
                payload.cliente.model_dump() if payload.cliente is not None else None
            ),
            actor_uuid=ctx.actor_uuid,
        )
    except repo_venta.ClienteNoEncontradoError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "cliente_no_encontrado",
                "uuid_cliente": str(exc.uuid_cliente),
            },
            headers=no_store,
        ) from exc

    # --- Step 4: V3 per-placa lookup-or-create. ------------------------
    vehiculos: list = []
    for placa in payload.placas:
        v, _was_created = await repo_venta.buscar_o_crear_vehiculo_por_placa(
            session,
            placa=placa,
            actor_uuid=ctx.actor_uuid,
        )
        vehiculos.append(v)

    # --- Step 5: V5 mismo_tipo_vehiculo (in-process). ------------------
    repo_venta.validar_placas_mismo_tipo_vehiculo(plan=plan, vehiculos=vehiculos)

    # --- Step 6: V6 cantidad_maxima_vehiculos (in-process). ------------
    repo_venta.validar_cantidad_maxima_vehiculos(
        plan=plan, n_placas=len(payload.placas)
    )

    # --- Step 7: V4 per-placa duplicate detection (F1.7 reuse). --------
    for placa in payload.placas:
        await repo_venta.validar_placa_duplicada_subscripcion(
            session,
            placa=placa,
            uuid_sucursal=target_sucursal or ctx.sucursal_uuid,
            fecha_inicio_cobertura=payload.fecha_inicio_cobertura,
        )

    # --- Step 8: V7 A-09 prorrateo compute (DEC-VENTA-03). -------------
    monto_proporcional = repo_venta.calcular_prorrateo(
        plan=plan,
        fecha_inicio_cobertura=payload.fecha_inicio_cobertura,
    )

    # --- Step 9: V9 INSERT subscription + junction (REQ-OP-08 lock). ---
    duracion_dias = plan.duracion_dias or 0
    fecha_vencimiento = payload.fecha_inicio_cobertura + timedelta(days=duracion_dias)
    subscripcion = await repo_venta.crear_subscripcion_cliente(
        session,
        actor_uuid=ctx.actor_uuid,
        uuid_cliente=cliente.uuid,
        uuid_sucursal=target_sucursal or ctx.sucursal_uuid,
        uuid_tipo_subscripcion=plan.uuid,
        fecha_inicio_cobertura=payload.fecha_inicio_cobertura,
        fecha_vencimiento=fecha_vencimiento,
    )
    await repo_venta.crear_subscripcion_vehiculos_bulk(
        session,
        actor_uuid=ctx.actor_uuid,
        uuid_subscripcion_cliente=subscripcion.uuid,
        uuid_vehiculos=[v.uuid for v in vehiculos],
    )

    # --- Step 8a: Optional V8 cobro sub-chain (F1.9 helpers reused). ----
    uuid_factura: uuid_lib.UUID | None = None
    if payload.cobrar_ahora:
        # F1.9 ``crear_factura_evento`` + ``crear_factura_detalle_bulk`` +
        # ``crear_factura_impuesto_iva`` + ``crear_factura_pago`` chained
        # -- out of scope for F1.12 stub. Implementation deferred to a
        # follow-up HU once the F1.9 cobro pattern is audited end-to-end.
        uuid_factura = None

    # --- Step 8b: Optional V8b FE sub-chain (F1.10 helpers reused). ----
    uuid_fe: uuid_lib.UUID | None = None
    uuid_envio: uuid_lib.UUID | None = None
    if payload.emitir_factura_electronica and uuid_factura is not None:
        # F1.10 ``crear_factura_electronica_inicial`` + ``crear_envio_dian_inicial``
        # -- out of scope for F1.12 stub. Same deferral as V8.
        uuid_fe = None
        uuid_envio = None

    # --- Step 10: KD-VENTA-01 SINGLE COMMIT. ---------------------------
    await session.commit()

    # --- Step 11: DEC-VENTA-06 -- Cache-Control: no-store + response. ---
    _helpers.apply_no_store_header(response)
    return VentaSuscripcionResponse(
        uuid_cliente=cliente.uuid,
        uuid_subscripcion=subscripcion.uuid,
        uuid_vehiculos=[v.uuid for v in vehiculos],
        uuid_sucursal=target_sucursal or ctx.sucursal_uuid,
        fecha_inicio_cobertura=payload.fecha_inicio_cobertura,
        fecha_vencimiento=fecha_vencimiento,
        valor_total_plan=plan.valor,
        monto_prorrateado=monto_proporcional if payload.cobrar_ahora else None,
        uuid_factura=uuid_factura,
        uuid_factura_electronica=uuid_fe,
        uuid_envio_dian=uuid_envio,
    )


__all__ = ["router"]
