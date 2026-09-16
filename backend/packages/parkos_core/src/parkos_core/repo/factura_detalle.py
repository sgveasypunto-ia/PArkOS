"""HU-F1.9 / REQ-OPS-053..063 -- bulk insert helper for ``prod.factura_detalle``.

Single helper :func:`crear_factura_detalle_bulk` that inserts N rows in a
single ``session.add_all([...])`` call (no per-row flush). The caller
commits (KD-FACT-01 single-commit invariant).

Uses the pre-existing ``models/A/factura_detalle.py::FacturaDetalle``
ORM (``AppendOnlyBase``, RANGE partitioned by ``fecha_retencion_hasta``,
monthly pg_partman, composite PK ``(uuid, fecha_retencion_hasta)``).

DEC-FACT-01: writes are append-only INSERTs. NO UPDATE, NO DELETE.
"""
from __future__ import annotations

import uuid as uuid_lib
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.factura_detalle import FacturaDetalle
from ..schemas.facturacion import FacturaItemCreate


async def crear_factura_detalle_bulk(
    session: AsyncSession,
    *,
    uuid_factura: uuid_lib.UUID,
    items: Sequence[FacturaItemCreate],
) -> list[FacturaDetalle]:
    """Bulk INSERT N ``FacturaDetalle`` rows for one factura.

    Uses :meth:`AsyncSession.add_all` (no per-row flush); single
    ``flush()`` at the end. Caller commits (KD-FACT-01).

    ``fecha_retencion_hasta`` = ``today() + 5 years`` (DIAN 5-year
    retention).
    """
    if not items:
        return []
    frh = date.today() + timedelta(days=5 * 365)
    new_rows = [
        FacturaDetalle(
            uuid_factura=uuid_factura,
            tipo=item.tipo,
            concepto=item.concepto,
            cantidad=item.cantidad,
            valor_unitario=item.valor_unitario,
            subtotal=(item.cantidad * item.valor_unitario).quantize(
                Decimal("0.01")
            ),
            uuid_tarifa_sucursal=item.uuid_tarifa_sucursal,
            fecha_retencion_hasta=frh,
        )
        for item in items
    ]
    session.add_all(new_rows)
    await session.flush()
    return new_rows


__all__ = ["crear_factura_detalle_bulk"]
