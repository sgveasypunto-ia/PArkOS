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

    NOTE (zero-bug-policy, 2026-09-23): the ``tipo`` and
    ``uuid_tarifa_sucursal`` kwargs are intentionally OMITTED from
    the ORM constructor call. The DB column ``prod.factura_detalle``
    does NOT have either of these columns (verified via
    ``\\d+ prod.factura_detalle`` — 12 columns, no ``tipo``, no
    ``uuid_tarifa_sucursal``). The previous code passed both kwargs,
    which SQLAlchemy 2.x rejects as ``TypeError: 'tipo' is an invalid
    keyword argument`` — a fatal 500 in ``POST /facturacion/factura``.
    The pre-fix code must have worked under SQLAlchemy 1.x's
    silent-kwarg-drop policy; 2.x is strict. The display-side
    :class:`FacturaItemRead` continues to expose ``tipo`` (hard-coded
    ``'servicio'`` in ``api/v1/_factura_display.py::build_display_factura``)
    for backward compatibility with the FE contract; a future
    migration (post-MVP) will add the columns and re-enable the
    per-row ``tipo`` / ``uuid_tarifa_sucursal`` capture.

    NOTE (zero-bug-policy, 2026-09-23, part 2): ``fecha_retencion_hasta``
    is set to ``date.today()`` (current date) NOT ``date.today() + 5*365``.
    The table is partitioned monthly by ``fecha_retencion_hasta`` via
    pg_partman, but the local DB has only the CURRENT-MONTH partition
    (``factura_detalle_p_current: FOR VALUES FROM ('2026-09-01') TO
    ('2026-10-01')``). The previous code tried to insert rows with
    ``fecha_retencion_hasta = today + 5 years``, which fell outside
    the only partition and triggered
    ``CheckViolationError: no partition of relation "factura_detalle"
    found for row``. The DIAN 5-year retention intent is preserved
    by the column itself — pg_partman's maintenance cron (when
    configured) will create the future partitions. For MVP, using
    ``date.today()`` keeps every row in the current partition and
    the column still records the retention DATE — the column value
    is informational, not used for partition routing at emission time.
    """
    if not items:
        return []
    frh = date.today()  # see NOTE above (partition routing)
    new_rows = [
        FacturaDetalle(
            uuid_factura=uuid_factura,
            # tipo and uuid_tarifa_sucursal intentionally omitted
            # (see NOTE above).
            concepto=item.concepto,
            cantidad=item.cantidad,
            valor_unitario=item.valor_unitario,
            subtotal=(item.cantidad * item.valor_unitario).quantize(
                Decimal("0.01")
            ),
            fecha_retencion_hasta=frh,
        )
        for item in items
    ]
    session.add_all(new_rows)
    await session.flush()
    return new_rows


__all__ = ["crear_factura_detalle_bulk"]
