"""HU-F1.12 / REQ-OPS-083..090 + REQ-OPS-XR5 -- POST /clientes/venta-suscripcion.

9-step atomic handler on a NEW dedicated ``APIRouter`` (DEC-VENTA-05 +
KD-VENTA-01 mirror of F1.11 KD-TKT-01):

  1. KD-3 issuer chain via ``requires_issuer("operador-", "admin-")``
     with permission gate ``gestionar_clientes``.
  2. V2 plan lock: ``buscar_tipo_subscripcion_vigente_por_uuid``
     (SELECT ... FOR UPDATE exclusive, KD-VENTA-02 + DEC-VENTA-04).
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
  9. V9 INSERT subscription + junction (pg_advisory_xact_lock) + SINGLE
     COMMIT + response shape + ``Cache-Control: no-store``.

Defense in depth (REQ-OPS-XR5 cross-cutting):

  * Layer 1: KD-3 issuer chain + ``gestionar_clientes`` permission gate.
  * Layer 2: tenant scope -- enforced by the auth layer
    ``auth/tenancy.py::get_tenant_ctx`` (REQ-OPS-XR5 + REQ-OPS-089
    Scenario 3 footnote "cross-branch check NOT enforced in F1.12,
    deferred to a future cross-branch consistency HU"). For
    ``operador-`` tokens the dependency pins the request to the JWT
    ``claims["sucursal"]`` and rejects any ``X-Sucursal-Context`` header
    pointing at a DIFFERENT branch with 403
    ``unauthorized_sucursal_context`` (``auth/tenancy.py:127-133``). The
    handler MUST NOT re-check this invariant -- the request payload does
    not carry a target entity with its own ``uuid_sucursal`` (the
    subscription is being CREATED here), so a handler-level comparison
    would either be a no-op or a tautology. The handler body assumes
    ``ctx.sucursal_uuid`` is the authoritative branch for every write
    below.
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
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...db.engine import get_session
from ...repo import (
    factura as repo_factura,
)
from ...repo import (
    factura_detalle as repo_factura_detalle,
)
from ...repo import (
    factura_electronica as repo_factura_electronica,
)
from ...repo import (
    impuestos as repo_impuestos,
)
from ...repo import (
    resolucion_facturacion as repo_resolucion,
)
from ...repo import venta_suscripcion as repo_venta
from ...schemas.clientes import VentaSuscripcionCreate, VentaSuscripcionResponse
from ...schemas.facturacion import FacturaItemCreate
from ..deps import requires_issuer
from . import _helpers

# Dedicated router -- mounted via ``router.include_router`` from
# ``api/v1/clientes.py`` (DEC-VENTA-05). DEC-VENTA-06 layer 5 mirror of
# F1.11 reimpresion dedicated router pattern.
#
# Real bug found + fixed 2026-09-24 (HU-F9.2 realineada session): this
# router MUST NOT carry its own "/clientes" prefix. ``api/v1/clientes.py``
# includes this router into ITS OWN ``router`` (which already has
# ``prefix="/clientes"``) via a bare ``router.include_router(...)`` (no
# prefix arg) -- FastAPI's ``include_router`` bakes the PARENT's prefix
# onto every route it absorbs, on top of whatever prefix the child router
# already baked into its own route paths at decoration time. With
# ``prefix="/clientes"`` here too, every route doubled to
# ``/api/v1/clientes/clientes/venta-suscripcion`` (confirmed live via
# ``GET /openapi.json`` on the running container) while the frontend
# (``ventaSuscripcionApi.ts::POST_VENTA_SUSCRIPCION_PATH``) correctly
# calls the single-``/clientes`` path -- every real venta-suscripcion
# request 404'd. The existing e2e test never caught it because it calls
# the handler function directly, never through HTTP routing.
router = APIRouter(tags=["clientes"])

# KD-3 issuer chain + ``gestionar_clientes`` permission gate (DEC-VENTA-05).
_venta_suscripcion_issuer_dep = requires_issuer("operador-", "admin-")


@router.post(
    "/venta-suscripcion",
    response_model=VentaSuscripcionResponse,
    status_code=201,
    responses={
        400: {"description": "missing_sucursal_context"},
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
    """POST /clientes/venta-suscripcion -- 9-step atomic handler.

    See module docstring for the full step chain + defense in depth.
    KD-VENTA-01 single-commit invariant: this handler owns the ONLY
    ``await session.commit()`` in the chain. Cross-branch operator
    rejection is enforced at the auth layer (``get_tenant_ctx``,
    ``auth/tenancy.py:127-133``); this handler body MUST NOT re-check
    the tenant scope invariant (REQ-OPS-XR5 Layer 2 + REQ-OPS-089
    Scenario 3 footnote).
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
    try:
        repo_venta.validar_placas_mismo_tipo_vehiculo(
            plan=plan, vehiculos=vehiculos
        )
    except repo_venta.TipoVehiculoIncompatibleError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "tipo_vehiculo_incompatible",
                "tipos_encontrados": exc.tipos_encontrados,
            },
            headers=no_store,
        ) from exc

    # --- Step 6: V6 cantidad_maxima_vehiculos (in-process). ------------
    try:
        repo_venta.validar_cantidad_maxima_vehiculos(
            plan=plan, n_placas=len(payload.placas)
        )
    except repo_venta.CantidadMaximaExcedidaError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "cantidad_maxima_excedida",
                "cantidad_maxima_vehiculos": exc.cantidad_maxima_vehiculos,
                "placas_proporcionadas": exc.placas_proporcionadas,
            },
            headers=no_store,
        ) from exc

    # --- Step 7: V4 per-placa duplicate detection (F1.7 reuse). --------
    for placa in payload.placas:
        try:
            await repo_venta.validar_placa_duplicada_subscripcion(
                session,
                placa=placa,
                uuid_sucursal=ctx.sucursal_uuid,
                fecha_inicio_cobertura=payload.fecha_inicio_cobertura,
            )
        except repo_venta.SubscripcionDuplicadaPlacaError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "suscripcion_duplicada_placa",
                    "placa": exc.placa,
                },
                headers=no_store,
            ) from exc

    # --- Step 8: V7 A-09 prorrateo compute (DEC-VENTA-03). -------------
    try:
        monto_proporcional = repo_venta.calcular_prorrateo(
            plan=plan,
            fecha_inicio_cobertura=payload.fecha_inicio_cobertura,
        )
    except repo_venta.PlanDuracionDiasInvalidoError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "plan_duracion_dias_invalido"},
            headers=no_store,
        ) from exc

    # --- Step 9: V9 INSERT subscription + junction (REQ-OP-08 lock). ---
    duracion_dias = plan.duracion_dias or 0
    fecha_vencimiento = payload.fecha_inicio_cobertura + timedelta(days=duracion_dias)
    subscripcion = await repo_venta.crear_subscripcion_cliente(
        session,
        actor_uuid=ctx.actor_uuid,
        uuid_cliente=cliente.uuid,
        uuid_sucursal=ctx.sucursal_uuid,
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
    # V8 wires 4 sub-chain tables (facturas + factura_detalle +
    # factura_impuestos + factura_pagos) onto the same atomic TX as the
    # subscripcion INSERTs. The cobro amount is:
    # - monto_proporcional if fecha_inicio_cobertura.day > 15 (A-09 prorrateo,
    #   persisted as `concepto='subscripcion_mensual_prorrateada'`)
    # - plan.valor otherwise (`concepto='subscripcion_mensual'`)
    # IVA is server-sourced from prod.impuestos.IVA (DEC-FACT-03: never
    # hardcoded). The medio_pago='datafono' branch enforces voucher
    # presence inline (mirror F1.9 facturacion.py:449-457; the typed
    # VoucherRequeridoError exists but is dead code across the codebase).
    uuid_factura: uuid_lib.UUID | None = None
    if payload.cobrar_ahora:
        # Voucher check (Q4 mirror, inline).
        if payload.medio_pago == "datafono" and not payload.referencia:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "voucher_requerido",
                    "medio_pago": payload.medio_pago,
                },
                headers=no_store,
            )

        # IVA gate (Q3 handler-level, before any INSERT).
        iva_porcentaje = await repo_impuestos.obtener_iva_vigente(session)
        if iva_porcentaje is None:
            raise HTTPException(
                status_code=500,
                detail={"error": "iva_no_configurado"},
                headers=no_store,
            )

        # Compute cobro base.
        plan_valor_raw = plan.valor if plan.valor is not None else Decimal(0)
        plan_valor: Decimal = (
            Decimal(plan_valor_raw) if not isinstance(plan_valor_raw, Decimal) else plan_valor_raw
        )
        monto_a_cobrar: Decimal = (
            Decimal(monto_proporcional)
            if monto_proporcional is not None
            else plan_valor
        )
        detalle_concepto = (
            "subscripcion_mensual_prorrateada"
            if monto_proporcional is not None
            else "subscripcion_mensual"
        )
        iva_monto = (monto_a_cobrar * iva_porcentaje).quantize(Decimal("0.01"))
        total_con_iva = (monto_a_cobrar + iva_monto).quantize(Decimal("0.01"))

        # Step 9 (F1.9 equivalent): INSERT prod.facturas.
        uuid_factura = (
            await repo_factura.crear_factura_evento(
                session,
                actor_uuid=ctx.actor_uuid,
                new_attrs={
                    "uuid_sucursal": ctx.sucursal_uuid,
                    "subtotal": monto_a_cobrar,
                    "descuento": Decimal(0),
                    "total": total_con_iva,
                    # Q1-A: nullable FK to prod.subscripciones_cliente
                    # populated by V8 (subscripcion already INSERTed at
                    # Step 9 above). F1.8/F1.9 callers leave it None and
                    # use uuid_ingreso / uuid_salida instead.
                    "uuid_subscripcion_cliente": subscripcion.uuid,
                },
            )
        ).uuid

        # Step 10a (F1.9 equivalent): INSERT prod.factura_detalle.
        await repo_factura_detalle.crear_factura_detalle_bulk(
            session,
            uuid_factura=uuid_factura,
            items=[
                FacturaItemCreate(
                    tipo="servicio",
                    concepto=detalle_concepto,
                    cantidad=1,
                    valor_unitario=monto_a_cobrar,
                ),
            ],
        )

        # Step 10b: INSERT prod.factura_impuestos (IVA snapshot).
        await repo_factura.crear_factura_impuesto_iva(
            session,
            uuid_factura=uuid_factura,
            base=monto_a_cobrar,
            iva=iva_porcentaje,
        )

        # Step 10c: INSERT prod.factura_pagos (initial pago).
        # Q2: ``ctx.uuid_sesion`` is the active operator turno session
        # (sourced from JWT ``sesion`` claim). May be None when the
        # operator is between turnos; ``prod.factura_pagos.uuid_sesion``
        # is nullable so the INSERT is valid either way.
        await repo_factura.crear_factura_pago(
            session,
            uuid_factura=uuid_factura,
            medio_pago=payload.medio_pago,
            valor=total_con_iva,
            referencia=payload.referencia,
            uuid_sesion=ctx.uuid_sesion,
        )

    # --- Step 8b: Optional V8b FE sub-chain (F1.10 helpers reused). ----
    # V8b wires 2 more tables (factura_electronica + envio_dian) onto the
    # same atomic TX, gated on uuid_factura existing from Step 8a. It
    # auto-assigns the branch-local `consecutivo` from the vigente
    # `resolucion_facturacion` for `uuid_sucursal` (F1.10 REQ-OPS-064..074
    # single-commit invariant KD-FE-01).
    uuid_fe: uuid_lib.UUID | None = None
    uuid_envio: uuid_lib.UUID | None = None
    if payload.emitir_factura_electronica and uuid_factura is not None:
        target_sucursal_fe = ctx.sucursal_uuid
        if target_sucursal_fe is None:
            raise HTTPException(
                status_code=400,
                detail={"error": "missing_sucursal_context"},
                headers=no_store,
            )
        resolucion = await repo_resolucion.buscar_resolucion_vigente_por_sucursal(
            session, uuid_sucursal=target_sucursal_fe
        )
        if resolucion is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "resolucion_facturacion_no_encontrada",
                    "uuid_sucursal": str(target_sucursal_fe),
                },
                headers=no_store,
            )
        # assign_consecutivo is idempotent on (resolucion_uuid,
        # source_event_uuid); using subscripcion.uuid as the source
        # makes the FE consecutivo a deterministic function of the
        # subscripcion (no collisions across replays).
        try:
            consecutivo = await repo_resolucion.assign_consecutivo(
                session,
                resolucion_uuid=resolucion.uuid,
                source_event_uuid=subscripcion.uuid,
            )
        except repo_resolucion.ConsecutivoRangeExhaustedError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "numeracion_agotada",
                    "uuid_resolucion_facturacion": str(resolucion.uuid),
                    "detail": str(exc),
                },
                headers=no_store,
            ) from exc

        if not resolucion.prefijo:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "resolucion_sin_prefijo",
                    "uuid_resolucion_facturacion": str(resolucion.uuid),
                },
                headers=no_store,
            )

        fe_row = await repo_factura_electronica.crear_factura_electronica_inicial(
            session,
            actor_uuid=ctx.actor_uuid,
            uuid_sucursal=target_sucursal_fe,
            uuid_factura=uuid_factura,
            uuid_resolucion_facturacion=resolucion.uuid,
            prefijo=resolucion.prefijo,
            consecutivo=consecutivo,
        )
        uuid_fe = fe_row.uuid

        await repo_factura_electronica.crear_envio_dian_inicial(
            session,
            actor_uuid=ctx.actor_uuid,
            uuid_sucursal=target_sucursal_fe,
            uuid_factura_electronica=uuid_fe,
            uuid_resolucion_facturacion=resolucion.uuid,
            payload={
                "prefijo": resolucion.prefijo,
                "consecutivo": consecutivo,
                "uuid_factura": str(uuid_factura),
                "uuid_subscripcion_cliente": str(subscripcion.uuid),
            },
        )
        uuid_envio = None  # envio_dian is created via the helper; UUIDs are
        # not returned (no return value). For Fase 3 traceability, the
        # caller can SELECT envio_dian WHERE uuid_factura_electronica = uuid_fe.

    # --- Step 10: KD-VENTA-01 SINGLE COMMIT. ---------------------------
    await session.commit()

    # --- Step 11: DEC-VENTA-06 -- Cache-Control: no-store + response. ---
    _helpers.apply_no_store_header(response)
    return VentaSuscripcionResponse(
        uuid_cliente=cliente.uuid,
        uuid_subscripcion=subscripcion.uuid,
        uuid_vehiculos=[v.uuid for v in vehiculos],
        uuid_sucursal=ctx.sucursal_uuid,
        fecha_inicio_cobertura=payload.fecha_inicio_cobertura,
        fecha_vencimiento=fecha_vencimiento,
        valor_total_plan=plan.valor,
        monto_prorrateado=monto_proporcional
        if (payload.cobrar_ahora and monto_proporcional is not None)
        else None,
        uuid_factura=uuid_factura,
        uuid_factura_electronica=uuid_fe,
        uuid_envio_dian=uuid_envio,
    )


__all__ = ["router"]
