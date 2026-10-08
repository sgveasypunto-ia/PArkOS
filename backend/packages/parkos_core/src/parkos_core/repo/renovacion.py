"""parkos_core.repo.renovacion -- subscription renewal (PT-3), commit-free helpers.

Business rules (decided with evidence, see the module-level notes):

* A renewal is a NEW ``subscripciones_cliente`` row (no natural key, "renovar
  es una fila nueva"). Plan = the CURRENT version of the plan the subscription
  was sold under (matched by ``tipo``: a [V] bump mints a new uuid), price =
  full ``plan.valor`` (no proration), vencimiento =
  ``calcular_fecha_vencimiento(plan, inicio)``.
* ``inicio = max(vencimiento_anterior + 1, hoy_bogota)``. ``vencimiento >=
  hoy`` is the validity predicate (inclusive), so renewing ON the due date is
  an EARLY renewal (starts tomorrow: no gap, no day paid twice).
* The old row (and its plate links) is CLOSED in the same transaction
  (``vigente_hasta = now``, ``estado = 'inactivo'``) and the plate links are
  re-inserted on the new row (``vigente_desde = now``). Evidence that closing
  at renewal time -- even when the new period starts in the future -- loses no
  coverage: every consumer (ingreso/salida lookup, duplicate-plate checks,
  cupos) filters on ``vigente_hasta IS NULL AND fecha_vencimiento >= hoy`` and
  none looks at ``fecha_inicio_cobertura``; the new row's vencimiento is later
  than the old one, so the plate stays covered without interruption. In
  exchange the invariant "a plate is in at most one open subscription of a
  branch" holds at every instant (no overlap exception), a second renewal of
  the same row is rejected naturally (the row is closed), and the alert list /
  cohort reports never double-count a customer.
* Plates are never re-entered: the active links of the old row are copied
  (re-pointed to the CURRENT ``vehiculos`` version of the same placa).

This module NEVER commits (KD-VENTA-01 mirror): the handler owns the commit.
"""
from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.factura_detalle import FacturaDetalle
from ..models.A.log_transaccional import LogTransaccional
from ..models.L_E.facturas import Facturas
from ..models.V.clientes import Clientes
from ..models.V.subscripcion_vehiculos import SubscripcionVehiculos
from ..models.V.subscripciones_cliente import SubscripcionesCliente
from ..models.V.tipo_subscripciones import TipoSubscripciones
from ..models.V.vehiculos import Vehiculos
from ..runtime.renovacion import (
    RENOVACION_URGENTE_DIAS,
    calcular_inicio_renovacion,
    dias_restantes,
    renovacion_anticipada,
    renovacion_permitida,
)
from ..runtime.tiempo import hoy_bogota
from ..schemas.facturacion import FacturaItemCreate
from . import factura as repo_factura
from . import factura_detalle as repo_factura_detalle
from . import hash_chain, versioned
from . import impuestos as repo_impuestos
from . import subscripcion_activa as repo_activa
from . import venta_suscripcion as repo_venta

__all__ = [
    "CobroRenovacion",
    "IvaNoConfiguradoError",
    "PlacaEnOtraSuscripcionError",
    "PlanNoVigenteError",
    "ResultadoRenovacion",
    "SubscripcionNoEncontradaError",
    "SubscripcionNoRenovableError",
    "SubscripcionSinVehiculosError",
    "VehiculoNoResueltoError",
    "VoucherRequeridoError",
    "cobrar_renovacion",
    "listar_renovables",
    "renovar_vigencia",
]

CONCEPTO_FACTURA = "subscripcion_mensual"  # same concept as the venta flow


# ---------------------------------------------------------------------------
# Typed errors (the handler maps each to an HTTP status / error code)
# ---------------------------------------------------------------------------


class SubscripcionNoEncontradaError(Exception):
    """404 ``subscripcion_no_encontrada`` (unknown uuid or other branch)."""

    def __init__(self, *, uuid_subscripcion: uuid_lib.UUID) -> None:
        self.uuid_subscripcion = uuid_subscripcion
        super().__init__(f"subscripcion_no_encontrada: {uuid_subscripcion}")


class SubscripcionNoRenovableError(Exception):
    """409 ``suscripcion_no_renovable``: the row is closed (already renewed or
    administratively deactivated)."""

    def __init__(self, *, uuid_subscripcion: uuid_lib.UUID) -> None:
        self.uuid_subscripcion = uuid_subscripcion
        super().__init__(f"suscripcion_no_renovable: {uuid_subscripcion}")


class PlanNoVigenteError(Exception):
    """409 ``plan_no_vigente``: the plan was withdrawn from the catalogue."""

    def __init__(self, *, uuid_tipo_subscripcion: uuid_lib.UUID | None) -> None:
        self.uuid_tipo_subscripcion = uuid_tipo_subscripcion
        super().__init__(f"plan_no_vigente: {uuid_tipo_subscripcion}")


class SubscripcionSinVehiculosError(Exception):
    """422 ``suscripcion_sin_vehiculos``: nothing to carry over."""


class VehiculoNoResueltoError(Exception):
    """422 ``vehiculo_no_resuelto``: a plate link points at a vehicle that no
    longer exists / has no open version; renewing would silently drop it."""

    def __init__(self, *, uuid_vehiculo: uuid_lib.UUID | None) -> None:
        self.uuid_vehiculo = uuid_vehiculo
        super().__init__(f"vehiculo_no_resuelto: {uuid_vehiculo}")


class PlacaEnOtraSuscripcionError(Exception):
    """422 ``placa_con_suscripcion_vigente``: the plate is also covered by a
    DIFFERENT open subscription of the same branch."""

    def __init__(self, *, placa: str) -> None:
        self.placa = placa
        super().__init__(f"placa_con_suscripcion_vigente: {placa}")


class VoucherRequeridoError(Exception):
    """400 ``voucher_requerido`` (medio_pago datafono without referencia)."""


class IvaNoConfiguradoError(Exception):
    """500 ``iva_no_configurado``."""


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoRenovacion:
    anterior: SubscripcionesCliente
    nueva: SubscripcionesCliente
    plan: TipoSubscripciones
    vehiculos: list[Vehiculos]
    monto: Decimal
    inicio: date
    vencimiento: date
    anticipada: bool
    dias_restantes_nueva: int


@dataclass(frozen=True)
class CobroRenovacion:
    factura: Facturas
    detalles: list[FacturaDetalle]
    total_con_iva: Decimal
    iva_porcentaje: Decimal


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


async def _cargar_para_renovar(
    session: AsyncSession, *, uuid_subscripcion: uuid_lib.UUID, uuid_sucursal: uuid_lib.UUID
) -> SubscripcionesCliente:
    """``SELECT ... FOR UPDATE`` the subscription of THIS branch.

    The row lock serializes concurrent renewals of the same row: the loser
    sees it closed and gets :class:`SubscripcionNoRenovableError`.
    """
    stmt = (
        select(SubscripcionesCliente)
        .where(
            SubscripcionesCliente.uuid == uuid_subscripcion,
            SubscripcionesCliente.uuid_sucursal == uuid_sucursal,
        )
        .with_for_update()
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise SubscripcionNoEncontradaError(uuid_subscripcion=uuid_subscripcion)
    if row.vigente_hasta is not None or row.estado != "activo":
        raise SubscripcionNoRenovableError(uuid_subscripcion=uuid_subscripcion)
    return row


async def _resolver_plan_vigente(
    session: AsyncSession, *, uuid_tipo_subscripcion: uuid_lib.UUID | None
) -> TipoSubscripciones:
    """Current (open, active) version of the plan the subscription uses.

    ``subscripciones_cliente.uuid_tipo_subscripcion`` may point at a CLOSED
    version (a [V] update mints a new uuid and FKs are not propagated), so the
    logical plan is matched by its ``tipo`` (UK with ``vigente_desde``). The
    price and duration of the CURRENT version are the ones charged.
    """
    if uuid_tipo_subscripcion is None:
        raise PlanNoVigenteError(uuid_tipo_subscripcion=None)
    referencia = (
        await session.execute(
            select(TipoSubscripciones).where(TipoSubscripciones.uuid == uuid_tipo_subscripcion)
        )
    ).scalar_one_or_none()
    if referencia is None:
        raise PlanNoVigenteError(uuid_tipo_subscripcion=uuid_tipo_subscripcion)
    if referencia.vigente_hasta is None and referencia.estado == "activo":
        actual = await repo_venta.buscar_tipo_subscripcion_vigente_por_uuid(
            session, uuid_tipo_subscripcion=referencia.uuid
        )
    else:
        stmt = (
            select(TipoSubscripciones)
            .where(
                TipoSubscripciones.tipo == referencia.tipo,
                TipoSubscripciones.vigente_hasta.is_(None),
                TipoSubscripciones.estado == "activo",
            )
            .order_by(TipoSubscripciones.vigente_desde.desc())
            .limit(1)
            .with_for_update()
        )
        actual = (await session.execute(stmt)).scalar_one_or_none()
    if actual is None:
        raise PlanNoVigenteError(uuid_tipo_subscripcion=uuid_tipo_subscripcion)
    return actual


async def _vehiculos_a_copiar(
    session: AsyncSession, *, uuid_subscripcion: uuid_lib.UUID
) -> tuple[list[SubscripcionVehiculos], list[Vehiculos]]:
    """Active plate links of the old row + the CURRENT vehicle row per placa."""
    links = list(
        (
            await session.execute(
                select(SubscripcionVehiculos)
                .where(
                    SubscripcionVehiculos.uuid_subscripcion_cliente == uuid_subscripcion,
                    SubscripcionVehiculos.vigente_hasta.is_(None),
                    SubscripcionVehiculos.estado == "activo",
                )
                .order_by(SubscripcionVehiculos.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    vehiculos: list[Vehiculos] = []
    for link in links:
        veh = (
            await session.execute(select(Vehiculos).where(Vehiculos.uuid == link.uuid_vehiculo))
        ).scalar_one_or_none()
        if veh is None:
            raise VehiculoNoResueltoError(uuid_vehiculo=link.uuid_vehiculo)
        if veh.vigente_hasta is not None:
            vigente = (
                await session.execute(
                    select(Vehiculos)
                    .where(
                        Vehiculos.placa == veh.placa,
                        Vehiculos.vigente_hasta.is_(None),
                        Vehiculos.estado == "activo",
                    )
                    .order_by(Vehiculos.vigente_desde.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if vigente is None:
                # The vehicle was closed with no open replacement: copying the
                # link would leave the plate invisible to the exit lookup.
                raise VehiculoNoResueltoError(uuid_vehiculo=link.uuid_vehiculo)
            veh = vigente
        vehiculos.append(veh)
    return links, vehiculos


async def _validar_placas_libres(
    session: AsyncSession,
    *,
    placas: list[str],
    excluir_uuid_subscripcion: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    hoy: date,
) -> None:
    """No plate may ALSO be covered by a different open subscription of the branch."""
    for placa in placas:
        stmt = (
            select(SubscripcionesCliente.uuid)
            .join(
                SubscripcionVehiculos,
                SubscripcionVehiculos.uuid_subscripcion_cliente == SubscripcionesCliente.uuid,
            )
            .join(Vehiculos, Vehiculos.uuid == SubscripcionVehiculos.uuid_vehiculo)
            .where(
                Vehiculos.placa == placa,
                SubscripcionVehiculos.vigente_hasta.is_(None),
                SubscripcionVehiculos.estado == "activo",
                SubscripcionesCliente.uuid != excluir_uuid_subscripcion,
                SubscripcionesCliente.uuid_sucursal == uuid_sucursal,
                SubscripcionesCliente.vigente_hasta.is_(None),
                SubscripcionesCliente.estado == "activo",
                SubscripcionesCliente.fecha_vencimiento >= hoy,
            )
            .limit(1)
        )
        if (await session.execute(stmt)).first() is not None:
            raise PlacaEnOtraSuscripcionError(placa=placa)


# ---------------------------------------------------------------------------
# Renewal (vigencia) -- close old + insert new + copy plates + audit log
# ---------------------------------------------------------------------------


def _iso(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, uuid_lib.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


async def renovar_vigencia(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_subscripcion: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    hoy: date | None = None,
) -> ResultadoRenovacion:
    """Validate + write the renewal (no payment, no commit).

    Raises the typed errors above, plus the venta module's
    ``CantidadMaximaExcedidaError`` / ``TipoVehiculoIncompatibleError`` /
    ``PlanDuracionDiasInvalidoError`` when the CURRENT plan version no longer
    fits the carried-over plates.
    """
    referencia_hoy = hoy if hoy is not None else hoy_bogota()

    anterior = await _cargar_para_renovar(
        session, uuid_subscripcion=uuid_subscripcion, uuid_sucursal=uuid_sucursal
    )
    if anterior.fecha_vencimiento is None:
        raise SubscripcionNoRenovableError(uuid_subscripcion=uuid_subscripcion)

    # No anticipation window: any open subscription with a due date can be
    # renewed; the new period stacks on the remaining validity.
    plan = await _resolver_plan_vigente(
        session, uuid_tipo_subscripcion=anterior.uuid_tipo_subscripcion
    )
    links, vehiculos = await _vehiculos_a_copiar(session, uuid_subscripcion=anterior.uuid)
    if not vehiculos:
        raise SubscripcionSinVehiculosError()

    repo_venta.validar_placas_mismo_tipo_vehiculo(plan=plan, vehiculos=vehiculos)
    repo_venta.validar_cantidad_maxima_vehiculos(plan=plan, n_placas=len(vehiculos))
    await _validar_placas_libres(
        session,
        placas=[v.placa for v in vehiculos if v.placa is not None],
        excluir_uuid_subscripcion=anterior.uuid,
        uuid_sucursal=uuid_sucursal,
        hoy=referencia_hoy,
    )

    monto = repo_venta.calcular_monto_suscripcion(plan=plan)
    inicio = calcular_inicio_renovacion(anterior.fecha_vencimiento, hoy=referencia_hoy)
    vencimiento = repo_venta.calcular_fecha_vencimiento(plan=plan, fecha_inicio_cobertura=inicio)
    anticipada = renovacion_anticipada(anterior.fecha_vencimiento, hoy=referencia_hoy)

    # Close the old row and insert the new one in a single bi-temporal step.
    # ``close_and_insert`` carries cliente/sucursal/dias_alerta forward from
    # the closed row; the plan and the dates are the renewal's own.
    # ``log_tx=False``: the single audit row below describes the whole
    # operation (instead of a generic "actualizar").
    nueva = await versioned.close_and_insert(
        session,
        SubscripcionesCliente,
        current_uuid=anterior.uuid,
        new_attrs={
            "uuid_tipo_subscripcion": plan.uuid,
            "fecha_inicio_cobertura": inicio,
            "fecha_vencimiento": vencimiento,
        },
        actor_uuid=actor_uuid,
        log_tx=False,
    )

    # Plates: close the old links, re-create them on the new row.
    for link in links:
        await versioned.close_only(
            session, SubscripcionVehiculos, link.uuid, actor_uuid=actor_uuid
        )
    await repo_venta.crear_subscripcion_vehiculos_bulk(
        session,
        actor_uuid=actor_uuid,
        uuid_subscripcion_cliente=nueva.uuid,
        uuid_vehiculos=[v.uuid for v in vehiculos],
    )

    ahora = repo_venta.datetime_utcnow()
    await hash_chain.append(
        session,
        LogTransaccional,
        {
            "uuid_usuario": actor_uuid,
            "uuid_sucursal": uuid_sucursal,
            "accion": "renovar",
            "tabla_afectada": SubscripcionesCliente.__tablename__,
            "uuid_registro_afectado": nueva.uuid,
            "uuid_referencia": anterior.uuid,
            "datos_anteriores": {
                "uuid_subscripcion": _iso(anterior.uuid),
                "uuid_tipo_subscripcion": _iso(anterior.uuid_tipo_subscripcion),
                "fecha_inicio_cobertura": _iso(anterior.fecha_inicio_cobertura),
                "fecha_vencimiento": _iso(anterior.fecha_vencimiento),
            },
            "datos_nuevos": {
                "uuid_subscripcion": _iso(nueva.uuid),
                "uuid_tipo_subscripcion": _iso(plan.uuid),
                "plan": plan.tipo,
                "fecha_inicio_cobertura": _iso(inicio),
                "fecha_vencimiento": _iso(vencimiento),
                "duracion_dias": plan.duracion_dias,
                "valor": _iso(monto),
                "renovacion_anticipada": anticipada,
                "placas": [v.placa for v in vehiculos],
            },
            "timestamp_evento": ahora,
        },
        actor_uuid=actor_uuid,
    )

    restantes_nueva = (vencimiento - referencia_hoy).days + 1
    return ResultadoRenovacion(
        anterior=anterior,
        nueva=nueva,
        plan=plan,
        vehiculos=vehiculos,
        monto=monto,
        inicio=inicio,
        vencimiento=vencimiento,
        anticipada=anticipada,
        dias_restantes_nueva=restantes_nueva,
    )


# ---------------------------------------------------------------------------
# Payment (same repo helpers + same concept as the venta flow)
# ---------------------------------------------------------------------------


async def cobrar_renovacion(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    uuid_sesion: uuid_lib.UUID | None,
    uuid_subscripcion_nueva: uuid_lib.UUID,
    monto: Decimal,
    medio_pago: str,
    referencia: str | None,
) -> CobroRenovacion:
    """INSERT facturas + factura_detalle + factura_impuestos + factura_pagos.

    Mirrors the cobro sub-chain of ``api/v1/clientes_venta.py`` (full plan
    value, IVA-inclusive, server-sourced rate, DEC-FACT-03). Pre-checks run before any
    INSERT so a rejected payment leaves nothing behind.
    """
    if medio_pago == "datafono" and not referencia:
        raise VoucherRequeridoError()
    iva_porcentaje = await repo_impuestos.obtener_iva_vigente(session)
    if iva_porcentaje is None:
        raise IvaNoConfiguradoError()

    # The plan price IS the total (IVA included): the tax is a breakdown
    # inside it, never charged on top.
    base, iva_monto, total_con_iva = repo_impuestos.desglosar_iva_incluido(
        monto, iva_porcentaje
    )

    factura = await repo_factura.crear_factura_evento(
        session,
        actor_uuid=actor_uuid,
        new_attrs={
            "uuid_sucursal": uuid_sucursal,
            "subtotal": base,
            "descuento": Decimal(0),
            "total": total_con_iva,
            "uuid_subscripcion_cliente": uuid_subscripcion_nueva,
        },
    )
    detalles = await repo_factura_detalle.crear_factura_detalle_bulk(
        session,
        uuid_factura=factura.uuid,
        uuid_sucursal=uuid_sucursal,
        items=[
            FacturaItemCreate(
                tipo="servicio",
                concepto=CONCEPTO_FACTURA,
                cantidad=1,
                valor_unitario=base,
            )
        ],
    )
    await repo_factura.crear_factura_impuesto_iva(
        session,
        uuid_factura=factura.uuid,
        base=base,
        iva=iva_porcentaje,
        iva_monto=iva_monto,
        uuid_sucursal=uuid_sucursal,
    )
    await repo_factura.crear_factura_pago(
        session,
        uuid_factura=factura.uuid,
        uuid_sucursal=uuid_sucursal,
        medio_pago=medio_pago,  # type: ignore[arg-type]
        valor=total_con_iva,
        referencia=referencia,
        uuid_sesion=uuid_sesion,
    )
    return CobroRenovacion(
        factura=factura,
        detalles=detalles,
        total_con_iva=total_con_iva,
        iva_porcentaje=iva_porcentaje,
    )


# ---------------------------------------------------------------------------
# Renewable subscriptions listing (includes expired ones)
# ---------------------------------------------------------------------------


async def listar_renovables(
    session: AsyncSession, *, uuid_sucursal: uuid_lib.UUID, hoy: date | None = None
) -> list[dict]:
    """Open subscriptions of the branch that are urgent to renew.

    ``GET /clientes/subscripciones-activas`` only lists the still-valid ones,
    so expired subscriptions (which may be renewed) need their own listing.
    This feed is bounded to ``dias_restantes <= RENOVACION_URGENTE_DIAS``; it
    is a feed limit, NOT a renewal gate (any subscription can be renewed).
    Ordered by ``fecha_vencimiento`` ascending (oldest / most urgent first).
    """
    referencia = hoy if hoy is not None else hoy_bogota()
    limite = referencia + timedelta(days=RENOVACION_URGENTE_DIAS - 1)
    stmt = (
        select(SubscripcionesCliente, Clientes, TipoSubscripciones)
        .join(Clientes, Clientes.uuid == SubscripcionesCliente.uuid_cliente, isouter=True)
        .join(
            TipoSubscripciones,
            TipoSubscripciones.uuid == SubscripcionesCliente.uuid_tipo_subscripcion,
            isouter=True,
        )
        .where(
            SubscripcionesCliente.uuid_sucursal == uuid_sucursal,
            SubscripcionesCliente.vigente_hasta.is_(None),
            SubscripcionesCliente.estado == "activo",
            SubscripcionesCliente.fecha_vencimiento.is_not(None),
            SubscripcionesCliente.fecha_vencimiento <= limite,
        )
        .order_by(SubscripcionesCliente.fecha_vencimiento.asc())
    )
    seleccion = []
    for sub, cliente, plan in (await session.execute(stmt)).all():
        restantes = dias_restantes(sub.fecha_vencimiento, hoy=referencia)
        if restantes is not None and renovacion_permitida(restantes):
            alerta = sub.dias_alerta_pre_vencimiento or repo_activa.DIAS_ALERTA_POR_DEFECTO
            seleccion.append((sub, cliente, plan, restantes, alerta))
    return await repo_activa.armar_items_vencimiento(session, seleccion)
