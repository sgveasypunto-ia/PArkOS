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


class ReporteOperacionalIngresoItem(BaseModel):
    """One ingreso row (HU-F17.2, BR1/filters).

    ``tiempo_estancia_segundos`` is ``None`` for an ingreso with no
    non-anulada ``salidas`` row yet (still parked, or its only exit was
    voided) -- computed in the query as
    ``EXTRACT(EPOCH FROM (salidas.fecha_salida - ingreso.fecha_ingreso))``,
    never persisted (BR1).
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid: uuid_lib.UUID
    uuid_sucursal: uuid_lib.UUID | None
    uuid_tipo_vehiculo: uuid_lib.UUID | None
    placa: str | None
    consecutivo: str | None
    fecha_ingreso: datetime | None
    fecha_salida: datetime | None
    tiempo_estancia_segundos: float | None


class ReporteEstanciaItem(BaseModel):
    """One (day) bucket of stay-time stats (HU-F17.2, BR1).

    Grouped by ``fecha`` (the UTC date of ``ingreso.fecha_ingreso``) for
    the single branch the request is scoped to -- BR1's "agrupado por
    sucursal y dia" collapses to "por dia" here since
    ``GET /admin/reporteria/operacional`` is single-branch-scoped
    (``uuid_sucursal`` is required). Only ingresos with a non-anulada
    ``salidas`` row (a completed stay) contribute a sample; an ingreso
    still parked has no stay time to average in.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    fecha: date
    muestras: int
    promedio_segundos: float
    maximo_segundos: float
    minimo_segundos: float


class ReporteOperacionalResponse(BaseModel):
    """Operational report for one branch over a date range."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid_sucursal: uuid_lib.UUID
    fecha_desde: date
    fecha_hasta: date
    items: list[ReporteOperacionalItem]
    totales: ReporteOperacionalItem
    generado_en: datetime
    # HU-F17.2 additions -- additive/optional so the existing "Totales
    # del periodo" panel (HU-F17.1, PR-D) keeps working unchanged against
    # ``items``/``totales`` alone. ``ingresos`` is cursor-paginated
    # (``ingresos_next_cursor``); ``tiempos_estancia`` is the full
    # per-day rollup for the requested range (BR1), never paginated --
    # it is already bounded by the date range, same reasoning as
    # ``totales`` above.
    ingresos: list[ReporteOperacionalIngresoItem] = Field(default_factory=list)
    ingresos_next_cursor: str | None = None
    tiempos_estancia: list[ReporteEstanciaItem] = Field(default_factory=list)


class ReporteOcupacionSucursalItem(BaseModel):
    """One branch label for the heatmap's row axis (HU-F17.2)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid: uuid_lib.UUID
    nombre: str | None


class ReporteOcupacionHeatmapCell(BaseModel):
    """One (sucursal, hour-of-day) cell, summed over ``[desde, hasta]``.

    Same shape/semantics as ``admin_views.DashboardOcupacionHorariaItem``
    (HU-F17.1): ``ingresos_count`` is an activity-intensity PROXY (count
    of ingresos created in that UTC hour-of-day bucket), not true
    concurrent occupancy. The only difference from the F17.1 heatmap is
    the window: ``[desde, hasta]`` (multi-day, inclusive UTC dates)
    instead of a fixed last-24h/today-only lookback.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid_sucursal: uuid_lib.UUID
    hora: int
    ingresos_count: int


class ReporteOcupacionAgregada(BaseModel):
    """Current-moment occupancy ratio across the resolved branch set (BR2).

    Unlike the heatmap cells (historical, bucketed over the requested
    range), this is a point-in-time snapshot -- "ingresos activos" only
    has meaning right now, the same reasoning
    ``admin_views.DashboardOcupacionAgregada`` documents. Reuses that
    exact ``ingreso sin salida no-anulada`` criterion (BR2: "reusalo tal
    cual").
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    ocupados: int
    capacidad: int
    porcentaje: float | None


class ReporteOcupacionResponse(BaseModel):
    """``GET /admin/reporteria/ocupacion`` (HU-F17.2)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    sucursales: list[ReporteOcupacionSucursalItem]
    data: list[ReporteOcupacionHeatmapCell]
    ocupacion_agregada: ReporteOcupacionAgregada
    desde: date
    hasta: date
    generado_en: datetime


__all__ = [
    "ReporteEstanciaItem",
    "ReporteOcupacionAgregada",
    "ReporteOcupacionHeatmapCell",
    "ReporteOcupacionResponse",
    "ReporteOcupacionSucursalItem",
    "ReporteOperacionalIngresoItem",
    "ReporteOperacionalItem",
    "ReporteOperacionalResponse",
]