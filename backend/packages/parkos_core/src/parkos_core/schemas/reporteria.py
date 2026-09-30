"""Pydantic schemas for HU-F17.1/F17.2 operational reports (PR-C).

The wire shape is intentionally minimal — totals per day plus a grand
total, with one entry per UTC date that had activity. We do NOT
materialize time series / heatmaps / chart series in this slice;
those arrive in a later PR per the explicit F17.1 user directive
("no charts, no heatmap 24h").

Two numeric axes:

- ``monto_facturado_total`` — ``SUM(Facturas.total)`` for the branch
  in the date range. This is the operational total, the value that
  powers the Dashboard's ``ingresos_monto_total`` card. It counts
  every factura (including anulada); excluding anuladas would
  require joining through ``anulaciones``, which PR6 wires but we
  keep this slice read-only against the existing shapes.
- ``monto_cobrado_total`` — ``SUM(FacturaPagos.valor WHERE tipo_movimiento='pago')
  - SUM(... WHERE tipo_movimiento='reverso')``. This is what actually
  hit the cash drawer net of voids. Reported as a separate field
  so the admin can see both numbers — a high facturado with low
  cobrado usually means invoices that customers walked away from.

The response keeps the two numbers per row so a per-day breakdown is
still readable when the admin wants it, while the grand total at the
end of the response lets the UI render a single KPI in two clicks.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ReporteOperacionalItem(BaseModel):
    """One day's roll-up, or the grand total when ``fecha is None``."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    fecha: date | None = Field(
        default=None,
        description=(
            "UTC date for this row, or NULL when the row carries the grand "
            "total over the requested range."
        ),
    )
    ingresos_count: int
    ingresos_activos_count: int
    salidas_count: int
    facturas_emitidas_count: int
    monto_facturado_total: float
    monto_cobrado_total: float


class ReporteOperacionalResponse(BaseModel):
    """Operational report for one branch over a date range."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid_sucursal: uuid_lib.UUID
    fecha_desde: date
    fecha_hasta: date
    items: list[ReporteOperacionalItem]
    totales: ReporteOperacionalItem
    generado_en: datetime


__all__ = [
    "ReporteOperacionalItem",
    "ReporteOperacionalResponse",
]