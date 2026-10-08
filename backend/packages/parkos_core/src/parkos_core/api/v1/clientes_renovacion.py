"""PT-3 -- subscription renewal + expiry-warning feed.

Routes (mounted under ``/clientes`` via ``api/v1/clientes.py``):

* ``POST /clientes/subscripciones/{uuid_subscripcion}/renovar``
* ``GET  /clientes/subscripciones/proximas-vencer`` (expiry banner feed)
* ``GET  /clientes/subscripciones/renovables`` (renewal list, expired included)

Renewal flow (one transaction for subscription + payment, FE afterwards):

  1. Issuer chain ``operador-``/``admin-`` + permission ``gestionar_clientes``
     (the code the ``clientes`` router family already requires).
  2. ``Idempotency-Key`` header is REQUIRED. The replay is done HERE with
     ``repo.idempotency.guard/store_response`` (same key + same body ->
     the stored 201 is returned with ``Idempotent-Replay: true``; same key +
     different body -> 409 ``idempotency_key_conflict``) because it must
     refresh the FE outcome on replay; ``IdempotencyKeyMiddleware``
     deliberately bypasses this path so nothing is processed twice. A second renewal
     of the same row with ANOTHER key is rejected on its own (the old row is
     closed -> 409 ``suscripcion_no_renovable``), which also covers two
     concurrent requests (they serialize on the row lock).
  3. ``repo.renovacion.renovar_vigencia``: no anticipation window (any open
     subscription can be renewed; the new period stacks on the remaining
     validity), current plan, plate copy, close old + insert new, audit row in ``log_transaccional``.
  4. ``repo.renovacion.cobrar_renovacion``: factura + detalle + IVA + pago
     for the FULL plan value (no proration).
  5. SINGLE ``await session.commit()`` (payment atomicity).
  6. Electronic invoice via the SAME best-effort mechanism the venta uses
     (``repo.fe_emision.emitir_fe_para_pago``, its own commit). Per the
     transversal policy it is always attempted -- there is no opt-out flag.

The FE helper is the one the venta uses (``repo/fe_emision.py``).
"""
from __future__ import annotations

import json
import uuid as uuid_lib

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.permissions import require_permission
from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...db.engine import get_session
from ...models.L_E.factura_electronica import FacturaElectronica
from ...repo import fe_emision as repo_fe_emision
from ...repo import idempotency as repo_idempotency
from ...repo import renovacion as repo_renovacion
from ...repo.sesion_activa import resolver_sesion_de_pago
from ...repo import subscripcion_activa as repo_activa
from ...repo import venta_suscripcion as repo_venta
from ...runtime.renovacion import RENOVACION_URGENTE_DIAS
from ...schemas.renovacion import (
    ProximaVencerItem,
    RenovarSuscripcionRequest,
    RenovarSuscripcionResponse,
)
from ..deps import requires_issuer
from . import _helpers
from ._factura_display import build_display_factura

# No "/clientes" prefix: api/v1/clientes.py includes this router into its own
# router (already prefixed) -- see the note in clientes_venta.py.
router = APIRouter(tags=["clientes"])

_issuer_dep = requires_issuer("operador-", "admin-")
_permission_dep = require_permission("gestionar_clientes")


def _error(status: int, code: str, **extra: object) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"error": code, **extra},
        headers=_helpers.no_store_headers(),
    )


@router.post(
    "/subscripciones/{uuid_subscripcion}/renovar",
    response_model=RenovarSuscripcionResponse,
    status_code=201,
    responses={
        400: {"description": "idempotency_key_requerido / voucher_requerido"},
        403: {"description": "permission_denied"},
        404: {"description": "subscripcion_no_encontrada"},
        409: {
            "description": (
                "suscripcion_no_renovable / plan_no_vigente"
            )
        },
        422: {
            "description": (
                "placa_con_suscripcion_vigente / suscripcion_sin_vehiculos / "
                "cantidad_maxima_excedida / tipo_vehiculo_incompatible / "
                "plan_duracion_dias_invalido"
            )
        },
    },
)
async def renovar_subscripcion(
    uuid_subscripcion: uuid_lib.UUID,
    payload: RenovarSuscripcionRequest,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_issuer_dep),
    _perm: dict = Depends(_permission_dep),  # noqa: B008
) -> RenovarSuscripcionResponse:
    """Renew a subscription: new row + same plates + full-price charge + FE."""
    if not idempotency_key:
        raise _error(400, "idempotency_key_requerido")
    if ctx.sucursal_uuid is None:
        raise _error(400, "missing_sucursal_context")
    if payload.medio_pago == "datafono" and not payload.referencia:
        raise _error(400, "voucher_requerido", medio_pago=payload.medio_pago)

    # --- Idempotency: replay the stored 201 for (key, endpoint, body). ----
    endpoint = f"/clientes/subscripciones/{uuid_subscripcion}/renovar"
    request_body = payload.model_dump_json().encode("utf-8")
    try:
        cached = await repo_idempotency.guard(
            session,
            endpoint=endpoint,
            idempotency_key=idempotency_key,
            request_body=request_body,
            actor_uuid=ctx.actor_uuid,
        )
    except repo_idempotency.IdempotencyConflictError as exc:
        raise _error(409, "idempotency_key_conflict") from exc
    if cached is not None:
        contenido = json.loads(cached.body)
        # The stored body predates the FE attempt: refresh the FE uuid from
        # the DB (the FE error code is not replayed; null + null means "no
        # electronic invoice recorded yet").
        if contenido.get("uuid_factura"):
            uuid_fe_actual = (
                await session.execute(
                    select(FacturaElectronica.uuid)
                    .where(FacturaElectronica.uuid_factura == uuid_lib.UUID(contenido["uuid_factura"]))
                    .limit(1)
                )
            ).scalar_one_or_none()
            if uuid_fe_actual is not None:
                contenido["uuid_factura_electronica"] = str(uuid_fe_actual)
        return JSONResponse(  # type: ignore[return-value]
            status_code=cached.status,
            content=contenido,
            headers={**_helpers.no_store_headers(), "Idempotent-Replay": "true"},
        )

    try:
        resultado = await repo_renovacion.renovar_vigencia(
            session,
            actor_uuid=ctx.actor_uuid,
            uuid_subscripcion=uuid_subscripcion,
            uuid_sucursal=ctx.sucursal_uuid,
        )
        cobro = await repo_renovacion.cobrar_renovacion(
            session,
            actor_uuid=ctx.actor_uuid,
            uuid_sucursal=ctx.sucursal_uuid,
            uuid_sesion=await resolver_sesion_de_pago(
                session,
                actor_uuid=ctx.actor_uuid,
                uuid_sucursal=ctx.sucursal_uuid,
                uuid_sesion_explicita=ctx.uuid_sesion,
            ),
            uuid_subscripcion_nueva=resultado.nueva.uuid,
            monto=resultado.monto,
            medio_pago=payload.medio_pago,
            referencia=payload.referencia,
        )
    except repo_renovacion.SubscripcionNoEncontradaError as exc:
        await session.rollback()
        raise _error(
            404, "subscripcion_no_encontrada", uuid_subscripcion=str(exc.uuid_subscripcion)
        ) from exc
    except repo_renovacion.SubscripcionNoRenovableError as exc:
        await session.rollback()
        raise _error(
            409, "suscripcion_no_renovable", uuid_subscripcion=str(exc.uuid_subscripcion)
        ) from exc
    except repo_renovacion.PlanNoVigenteError as exc:
        await session.rollback()
        raise _error(409, "plan_no_vigente") from exc
    except repo_renovacion.SubscripcionSinVehiculosError as exc:
        await session.rollback()
        raise _error(422, "suscripcion_sin_vehiculos") from exc
    except repo_renovacion.VehiculoNoResueltoError as exc:
        await session.rollback()
        raise _error(422, "vehiculo_no_resuelto", uuid_vehiculo=str(exc.uuid_vehiculo)) from exc
    except repo_renovacion.PlacaEnOtraSuscripcionError as exc:
        await session.rollback()
        raise _error(422, "placa_con_suscripcion_vigente", placa=exc.placa) from exc
    except repo_venta.TipoVehiculoIncompatibleError as exc:
        await session.rollback()
        raise _error(
            422, "tipo_vehiculo_incompatible", tipos_encontrados=exc.tipos_encontrados
        ) from exc
    except repo_venta.CantidadMaximaExcedidaError as exc:
        await session.rollback()
        raise _error(
            422,
            "cantidad_maxima_excedida",
            cantidad_maxima_vehiculos=exc.cantidad_maxima_vehiculos,
            placas_proporcionadas=exc.placas_proporcionadas,
        ) from exc
    except repo_venta.PlanDuracionDiasInvalidoError as exc:
        await session.rollback()
        raise _error(422, "plan_duracion_dias_invalido") from exc
    except repo_renovacion.VoucherRequeridoError as exc:
        await session.rollback()
        raise _error(400, "voucher_requerido", medio_pago=payload.medio_pago) from exc
    except repo_renovacion.IvaNoConfiguradoError as exc:
        await session.rollback()
        raise _error(500, "iva_no_configurado") from exc

    # The display projection only READS rows inserted above (same TX).
    await session.flush()
    await session.refresh(cobro.factura)
    factura_display = await build_display_factura(
        session,
        new_factura=cobro.factura,
        detalles_creados=cobro.detalles,
        payload=payload,  # type: ignore[arg-type]  # only medio_pago is read
        total_server=cobro.total_con_iva,
        cliente_uuid=resultado.anterior.uuid_cliente,
    )

    respuesta = RenovarSuscripcionResponse(
        uuid_subscripcion_anterior=resultado.anterior.uuid,
        uuid_subscripcion=resultado.nueva.uuid,
        uuid_cliente=resultado.nueva.uuid_cliente,
        uuid_sucursal=ctx.sucursal_uuid,
        uuid_tipo_subscripcion=resultado.plan.uuid,
        uuid_vehiculos=[v.uuid for v in resultado.vehiculos],
        placas=[v.placa for v in resultado.vehiculos if v.placa is not None],
        fecha_inicio_cobertura=resultado.inicio,
        fecha_vencimiento=resultado.vencimiento,
        dias_restantes=resultado.dias_restantes_nueva,
        renovacion_anticipada=resultado.anticipada,
        ventana_renovacion_dias=RENOVACION_URGENTE_DIAS,
        valor_total_plan=resultado.monto,
        total_con_iva=cobro.total_con_iva,
        uuid_factura=cobro.factura.uuid,
        uuid_factura_electronica=None,
        factura_electronica_error=None,
        factura=factura_display,
    )

    # SINGLE COMMIT: renewal + plate copy + audit row + factura/pago + the
    # idempotency record (stored WITHOUT the FE outcome, which is only known
    # after this commit; replays re-read it, see below). If the process dies
    # right after, the key is already recorded and the replay works.
    await repo_idempotency.store_response(
        session,
        endpoint=endpoint,
        idempotency_key=idempotency_key,
        request_body=request_body,
        actor_uuid=ctx.actor_uuid,
        response_status=201,
        response_body=respuesta.model_dump_json().encode("utf-8"),
    )
    await session.commit()

    # ALWAYS-ON best-effort FE (own commit, AFTER the payment is durable),
    # same helper and pattern as the venta: the recipient is the subscriber;
    # a failure keeps the payment, leaves the pending marker and the branch
    # worker retries automatically. Snapshots first: the helper may roll back
    # and expire the ORM objects.
    uuid_cliente_sub = respuesta.uuid_cliente
    uuid_nueva = respuesta.uuid_subscripcion
    fe_res = await repo_fe_emision.emitir_fe_para_pago(
        session,
        actor_uuid=ctx.actor_uuid,
        uuid_sucursal=ctx.sucursal_uuid,
        uuid_factura=respuesta.uuid_factura,
        uuid_cliente=uuid_cliente_sub,
        payload_extra={"uuid_subscripcion_cliente": str(uuid_nueva)},
    )

    _helpers.apply_no_store_header(response)
    await session.refresh(cobro.factura)
    factura_display = await build_display_factura(
        session,
        new_factura=cobro.factura,
        detalles_creados=cobro.detalles,
        payload=payload,  # type: ignore[arg-type]  # only medio_pago is read
        total_server=cobro.total_con_iva,
        cliente_uuid=uuid_cliente_sub,
        fe_resultado=fe_res,
    )
    return respuesta.model_copy(
        update={
            "uuid_factura_electronica": fe_res.uuid_factura_electronica,
            "factura_electronica_error": fe_res.error,
            "factura_electronica_pendiente": fe_res.pendiente,
            "factura": factura_display,
        }
    )


@router.get(
    "/subscripciones/proximas-vencer",
    response_model=list[ProximaVencerItem],
)
async def listar_proximas_vencer(
    response: Response,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_issuer_dep),
) -> list[ProximaVencerItem]:
    """Feed of the expiry banner for the current branch.

    A subscription is listed when it is still valid and its remaining days are
    within ITS OWN ``dias_alerta_pre_vencimiento`` (default 7), computed with
    Bogota's calendar date. ``puede_renovar`` is the 10-day renewal window
    (independent from the warning window).
    """
    if ctx.sucursal_uuid is None:
        raise _error(400, "missing_sucursal_context")
    _helpers.apply_no_store_header(response)
    rows = await repo_activa.listar_proximas_a_vencer(session, uuid_sucursal=ctx.sucursal_uuid)
    return [ProximaVencerItem(**r) for r in rows]


@router.get(
    "/subscripciones/renovables",
    response_model=list[ProximaVencerItem],
)
async def listar_renovables(
    response: Response,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_issuer_dep),
) -> list[ProximaVencerItem]:
    """Subscriptions of the branch that can be renewed now (<= 10 days left,
    expired ones included). ``dias_restantes`` <= 0 means expired.

    Read-only listing: like ``GET /clientes/subscripciones-activas`` and the
    banner feed it needs only the issuer chain; the mutation
    (``.../renovar``) is the one gated by ``gestionar_clientes``."""
    if ctx.sucursal_uuid is None:
        raise _error(400, "missing_sucursal_context")
    _helpers.apply_no_store_header(response)
    rows = await repo_renovacion.listar_renovables(session, uuid_sucursal=ctx.sucursal_uuid)
    return [ProximaVencerItem(**r) for r in rows]
