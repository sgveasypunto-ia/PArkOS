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
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.subscripcion_vehiculos import SubscripcionVehiculos
from ..models.V.subscripciones_cliente import SubscripcionesCliente
from ..models.V.vehiculos import Vehiculos


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
        >= datetime.now(UTC).date(),
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

    reference_date = as_of or datetime.now(UTC).date()
    if (
        subscripcion.fecha_vencimiento is not None
        and subscripcion.fecha_vencimiento < reference_date
    ):
        return SubscriptionLookupResult(
            found=False, subscripcion=subscripcion, message="subscription expired"
        )

    return SubscriptionLookupResult(found=True, subscripcion=subscripcion)


__all__ = [
    "SubscripcionValidationResult",
    "SubscriptionLookupResult",
    "resolve_active_subscription_for_exit",
    "validar_subscripcion_vigente",
]