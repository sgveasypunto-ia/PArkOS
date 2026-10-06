"""HU-F1.6 / REQ-OPS-039 — subscripcion vigente (V6) + reused by F7 exit flow.

Adds :func:`validar_subscripcion_vigente` with bi-temporal predicate
``vigente_hasta IS NULL AND estado='activo' AND fecha_vencimiento >=
NOW()``. The helper is consumed by the dedicated handler
``create_ingreso`` (V6) and will be reused by F7 (Salida) without a
circular dependency on the router.

``resolve_active_subscription_for_exit`` (T-PR5-016) is preserved here
for F7 reuse; the handler layer in
``api/v1/operacion.py::resolve_active_subscription_for_exit`` is the
F1.5-era home of the same function, but F1.6 lifts it into this repo
module to give F7 a stable import surface.
"""
from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.clientes import Clientes
from ..models.V.subscripcion_vehiculos import SubscripcionVehiculos
from ..models.V.subscripciones_cliente import SubscripcionesCliente
from ..models.V.tipo_subscripciones import TipoSubscripciones
from ..models.V.vehiculos import Vehiculos
from ..runtime.renovacion import dias_restantes, renovacion_permitida
from ..runtime.tiempo import hoy_bogota

#: Default per-subscription warning window (NULL column value == 7).
DIAS_ALERTA_POR_DEFECTO = 7
#: Upper bound of ``dias_alerta_pre_vencimiento`` (schema: 1..90).
_DIAS_ALERTA_MAX = 90


@dataclass(frozen=True)
class SubscripcionValidationResult:
    """Outcome of :func:`validar_subscripcion_vigente`."""

    vigente: bool
    subscripcion: SubscripcionesCliente | None = None


async def validar_subscripcion_vigente(
    session: AsyncSession,
    *,
    uuid_subscripcion_cliente: uuid_lib.UUID,
    forzado: bool = False,
) -> SubscripcionValidationResult:
    """V6: True iff ``uuid_subscripcion_cliente`` is vigente at this branch.

    Predicate (bi-temporal [V]):
        vigente_hasta IS NULL
        AND estado = 'activo'
        AND fecha_vencimiento >= NOW()

    When ``forzado=True`` (KD-FORZADO-01), the predicate is bypassed
    (walk-in auditado) but the result still records the underlying state
    so the caller can log it.

    Note: this helper does NOT validate that the placa is in
    ``subscripcion_vehiculos`` — that is F7's responsibility
    (cobrar=false derivation). V6 accepts the subscripcion if vigente;
    walk-in auditado covers the "subscripcion vigente but placa not
    registered" edge case (R9 in proposal §8).
    """
    stmt = select(SubscripcionesCliente).where(
        SubscripcionesCliente.uuid == uuid_subscripcion_cliente,
        SubscripcionesCliente.vigente_hasta.is_(None),
        SubscripcionesCliente.estado == "activo",
        SubscripcionesCliente.fecha_vencimiento
        >= hoy_bogota(),
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is not None:
        return SubscripcionValidationResult(vigente=True, subscripcion=row)
    # In all failure cases (no row, forzado=True or not), vigente=False.
    # Caller decides what to do (422 vs walk-in auditado).
    return SubscripcionValidationResult(vigente=False, subscripcion=None)


# ---------------------------------------------------------------------------
# F1.5 / T-PR5-016 / R22 — exit-flow lookup (CU-03M). Lifted verbatim from
# ``api/v1/operacion.py`` (F1.5 commit `bb99e18`); preserved here so F7
# (Salida) can import from a stable module without circular dep on the
# router. Defense-in-depth (R22) carries over: ``WHERE uuid_sucursal ==
# :this_branch`` rejects cross-branch rows independently of sync scoping.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubscriptionLookupResult:
    """Outcome of :func:`resolve_active_subscription_for_exit`."""

    found: bool
    subscripcion: SubscripcionesCliente | None = None
    message: str | None = None


async def resolve_active_subscription_for_exit(
    session: AsyncSession,
    *,
    placa: str,
    uuid_sucursal: uuid_lib.UUID,
    as_of: date | None = None,
) -> SubscriptionLookupResult:
    """CU-03M exit-with-subscription validation query (R22).

    Lifted verbatim from ``api/v1/operacion.py::resolve_active_subscription_for_exit``
    (F1.5 commit ``bb99e18``). Returns one of:

    - ``SubscriptionLookupResult(found=False, message="no subscription at
      this branch")`` — R22's normal silent outcome.
    - ``SubscriptionLookupResult(found=False, message="subscription
      expired")`` — matching row exists but ``fecha_vencimiento`` is past.
    - ``SubscriptionLookupResult(found=True, subscripcion=...)``.
    """
    stmt = (
        select(SubscripcionesCliente)
        .join(
            SubscripcionVehiculos,
            SubscripcionVehiculos.uuid_subscripcion_cliente == SubscripcionesCliente.uuid,
        )
        .join(Vehiculos, Vehiculos.uuid == SubscripcionVehiculos.uuid_vehiculo)
        .where(
            SubscripcionesCliente.uuid_sucursal == uuid_sucursal,
            SubscripcionesCliente.vigente_hasta.is_(None),
            SubscripcionVehiculos.vigente_hasta.is_(None),
            Vehiculos.vigente_hasta.is_(None),
            Vehiculos.placa == placa,
        )
        .order_by(SubscripcionesCliente.vigente_desde.desc())
    )
    subscripcion = (await session.execute(stmt)).scalars().first()

    if subscripcion is None:
        return SubscriptionLookupResult(found=False, message="no subscription at this branch")

    reference_date = as_of or hoy_bogota()
    if (
        subscripcion.fecha_vencimiento is not None
        and subscripcion.fecha_vencimiento < reference_date
    ):
        return SubscriptionLookupResult(
            found=False, subscripcion=subscripcion, message="subscription expired"
        )

    return SubscriptionLookupResult(found=True, subscripcion=subscripcion)


async def listar_proximas_a_vencer(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    hoy: date | None = None,
) -> list[dict]:
    """Expiry-warning feed: valid subscriptions inside THEIR OWN alert window.

    * Valid = open row, ``estado='activo'``, ``fecha_vencimiento >= hoy``
      (Bogota). Expired rows are not listed (they show as "vencida" in the
      general listing).
    * Window = ``dias_restantes <= dias_alerta_pre_vencimiento`` of each row
      (NULL -> 7), with ``dias_restantes = fecha_vencimiento - hoy + 1``.
    * Ascending by ``fecha_vencimiento``.
    """
    referencia = hoy if hoy is not None else hoy_bogota()
    limite = referencia + timedelta(days=_DIAS_ALERTA_MAX)
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
            SubscripcionesCliente.fecha_vencimiento >= referencia,
            SubscripcionesCliente.fecha_vencimiento <= limite,
        )
        .order_by(SubscripcionesCliente.fecha_vencimiento.asc())
    )
    filas = (await session.execute(stmt)).all()

    seleccion = []
    for sub, cliente, plan in filas:
        restantes = dias_restantes(sub.fecha_vencimiento, hoy=referencia)
        alerta = sub.dias_alerta_pre_vencimiento or DIAS_ALERTA_POR_DEFECTO
        if restantes is not None and restantes <= alerta:
            seleccion.append((sub, cliente, plan, restantes, alerta))
    return await armar_items_vencimiento(session, seleccion)


async def armar_items_vencimiento(session: AsyncSession, seleccion: list[tuple]) -> list[dict]:
    """Shape ``(sub, cliente, plan, restantes, alerta)`` tuples into feed items
    (adds the active plates of each subscription in ONE extra query)."""
    if not seleccion:
        return []

    placas_stmt = (
        select(SubscripcionVehiculos.uuid_subscripcion_cliente, Vehiculos.placa)
        .join(Vehiculos, Vehiculos.uuid == SubscripcionVehiculos.uuid_vehiculo)
        .where(
            SubscripcionVehiculos.uuid_subscripcion_cliente.in_([s[0].uuid for s in seleccion]),
            SubscripcionVehiculos.vigente_hasta.is_(None),
            SubscripcionVehiculos.estado == "activo",
        )
        .order_by(SubscripcionVehiculos.created_at.asc())
    )
    placas: dict[uuid_lib.UUID, list[str]] = {}
    for uuid_sub, placa in (await session.execute(placas_stmt)).all():
        if placa is not None:
            placas.setdefault(uuid_sub, []).append(placa)

    items: list[dict] = []
    for sub, cliente, plan, restantes, alerta in seleccion:
        nombre = " ".join(
            p for p in (getattr(cliente, "nombre", None), getattr(cliente, "apellido", None)) if p
        )
        items.append(
            {
                "uuid": sub.uuid,
                "cliente_nombre": nombre,
                "plan_nombre": (plan.tipo if plan is not None and plan.tipo else ""),
                "placas": placas.get(sub.uuid, []),
                "fecha_vencimiento": sub.fecha_vencimiento,
                "dias_restantes": restantes,
                "dias_alerta_pre_vencimiento": alerta,
                "puede_renovar": renovacion_permitida(restantes),
            }
        )
    return items


__all__ = [
    "DIAS_ALERTA_POR_DEFECTO",
    "SubscripcionValidationResult",
    "SubscriptionLookupResult",
    "armar_items_vencimiento",
    "listar_proximas_a_vencer",
    "resolve_active_subscription_for_exit",
    "validar_subscripcion_vigente",
]