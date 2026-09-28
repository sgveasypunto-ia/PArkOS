"""repo/cantidad_vigencia.py — bi-temporal helper for ``cantidad_vehiculos_sucursal``.

Mirror of :mod:`parkos_core.repo.tarifas_vigencia`. Exists so a
potential dedicated ``GET /empresa/cantidad-vehiculos-sucursal`` handler
can apply the canonical bi-temporal predicate without duplicating the
WHERE / ORDER / cursor logic. The factory handler today does NOT use
this helper (it lists ``vigente_hasta IS NULL`` rows via
``make_router``); the helper is in place for the by-key/history
endpoint introduced in PR-C and for any future dedicated listing.

The bi-temporal predicate:

    vigente_desde <= :v AND (vigente_hasta IS NULL OR vigente_hasta > :v)
    AND estado = 'activo'

is the same string template the dedicated tarifas handler uses (see
:data:`parkos_core.repo.tarifas_vigencia.BITEMPORAL_VIGENTE_PREDICATE_
TEMPLATE`). The :func:`bitemporal_vigente_predicate` builder is
re-exported here to keep the import surface for cantidad-specific
callers local.
"""
from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.cantidad_vehiculos_sucursal import CantidadVehiculosSucursal
from .tarifas_vigencia import bitemporal_vigente_predicate


def _to_utc_naive(value: datetime) -> datetime:
    """Same tz normalization as :mod:`parkos_core.repo.tarifas_vigencia`."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class CantidadValidationResult:
    """Outcome of :func:`validar_cantidad_vigente`."""

    vigente: bool
    cantidad: CantidadVehiculosSucursal | None = None


async def validar_cantidad_vigente(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    at: datetime,
) -> CantidadValidationResult:
    """V1+V2 mirror (cantidad): is there a vigente ``cantidad_vehiculos_sucursal`` row?

    Reuses the canonical bi-temporal predicate from
    :func:`parkos_core.repo.tarifas_vigencia.bitemporal_vigente_predicate`.
    Returns the open row (or ``None``) so callers can read the
    configured ``cantidad`` directly without a second round-trip.
    """
    v_utc = _to_utc_naive(at)
    stmt = (
        select(CantidadVehiculosSucursal)
        .where(
            CantidadVehiculosSucursal.uuid_sucursal == uuid_sucursal,
            CantidadVehiculosSucursal.uuid_tipo_vehiculo == uuid_tipo_vehiculo,
        )
        .where(bitemporal_vigente_predicate(CantidadVehiculosSucursal, v_utc))
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is not None:
        return CantidadValidationResult(vigente=True, cantidad=row)
    return CantidadValidationResult(vigente=False, cantidad=None)


__all__ = [
    "CantidadValidationResult",
    "validar_cantidad_vigente",
]
