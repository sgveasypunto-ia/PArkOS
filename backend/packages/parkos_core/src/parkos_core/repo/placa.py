"""HU-F1.6 / REQ-OPS-038 — placa regex Colombia + UUID derivation (D-HU-F1.6-4).

Module-level regex constants for Auto (``ABC123``) and Moto
(``ABC12D``). :func:`detectar_tipo_vehiculo` lazy-looks up the vigente
row in ``prod.tipos_vehiculo`` keyed by the human-readable ``tipo``
string ('Auto', 'Moto'). Returns ``None`` when the regex doesn't match
OR when the catalog is missing the tipo (the latter triggers V4
``tipo_vehiculo_invalido``).

DEC-SUC-22: regex estricta, sin tolerancia O<->0 / I<->1. The tolerant
variant lives in ``buscarIngresoTolerante`` (HU-F1.7), not here.

KD-V2 / A-03: regex hardcoded for MVP. Configurable regex is out of
scope (future HU). Module-level constants make a future swap to a cat
tabla a one-file edit.
"""
from __future__ import annotations

import re
import uuid as uuid_lib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.tipos_vehiculo import TiposVehiculo

# Module-level constants (A-03 / KD-V2). Future cat-tabla swap is a
# one-file edit.
FORMATO_AUTO = re.compile(r"^[A-Z]{3}[0-9]{3}$")  # ABC123
FORMATO_MOTO = re.compile(r"^[A-Z]{3}[0-9]{2}[A-Z]$")  # ABC12D


async def detectar_tipo_vehiculo(
    session: AsyncSession,
    placa: str | None,
) -> uuid_lib.UUID | None:
    """V5: derive ``uuid_tipo_vehiculo`` from the placa regex.

    Returns:
        The UUID of the vigente row in ``prod.tipos_vehiculo`` whose
        ``tipo`` ('Auto' or 'Moto') matches the regex, or ``None`` if
        the regex does not match OR the catalog has no vigente row
        for that tipo (the latter triggers V4 ``tipo_vehiculo_invalido``
        at the handler level).
    """
    if placa is None:
        return None
    if FORMATO_AUTO.match(placa):
        tipo_nombre = "Auto"
    elif FORMATO_MOTO.match(placa):
        tipo_nombre = "Moto"
    else:
        return None

    stmt = select(TiposVehiculo.uuid).where(
        TiposVehiculo.tipo == tipo_nombre,
        TiposVehiculo.vigente_hasta.is_(None),
        TiposVehiculo.estado == "activo",
    )
    return (await session.execute(stmt)).scalar_one_or_none()


__all__ = [
    "FORMATO_AUTO",
    "FORMATO_MOTO",
    "detectar_tipo_vehiculo",
]