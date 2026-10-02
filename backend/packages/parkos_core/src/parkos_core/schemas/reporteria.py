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
from typing import Literal

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


class ReporteFacturaItem(BaseModel):
    """One ``prod.facturas`` row resolved against its REAL columns (HU-F17.3).

    A prior spec for this screen named ``numero_completo``/``iva``/``estado``
    as if they were plain ``facturas`` columns -- they are not (the real
    table is ``uuid, uuid_sucursal, subtotal, descuento, total,
    uuid_ingreso, uuid_salida, fecha_retencion_hasta``; confirmed against
    ``models/L_E/facturas.py``). Each is resolved here instead:

    - ``numero_completo`` -- ``prefijo + consecutivo`` from the ``factura_
      electronica`` row joined on ``uuid_factura`` (``None`` when this
      factura has no FE associated -- not every factura is electronically
      invoiced).
    - ``iva`` -- ``SUM(factura_impuestos.valor)`` for this factura (``0``
      when no tax rows exist yet).
    - ``estado`` -- derived AD HOC in the query: EXISTS a ``anulaciones``
      row (``estado='ejecutada'``) pointing at this factura's
      ``uuid_ingreso``/``uuid_salida`` -> ``anulada``, else ``vigente``.
      Same "EXISTS anulaciones ejecutada" pattern ``reporte_operacional``'s
      ``ingresos_activos_subq`` already uses (``tipo_anulable`` is only
      ever ``ingreso``/``salida`` -- confirmed against
      ``models/L_W/anulaciones.py`` -- never ``factura`` directly, which
      is why the derivation goes through the factura's own ingreso/salida
      pointers rather than a direct FK).
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid: uuid_lib.UUID
    uuid_sucursal: uuid_lib.UUID | None
    created_at: datetime
    numero_completo: str | None
    subtotal: float | None
    descuento: float | None
    iva: float
    total: float | None
    estado: Literal["vigente", "anulada"]


class ReporteFacturasResponse(BaseModel):
    """``GET /admin/reporteria/facturas`` (HU-F17.3; HU-F20.1 cliente filter).

    ``uuid_sucursal`` is ``None`` only in the HU-F20.1 cross-branch mode
    (caller passed ``uuid_cliente`` without ``uuid_sucursal``) -- rows then
    legitimately span multiple branches, so there is no single branch to
    report at the top level. Every existing branch-scoped caller
    (``uuid_sucursal`` given) keeps getting a concrete value here, exactly
    as before; use each ``ReporteFacturaItem.uuid_sucursal`` to know which
    branch a given row belongs to in cross-branch mode.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid_sucursal: uuid_lib.UUID | None
    desde: date
    hasta: date
    items: list[ReporteFacturaItem]
    next_cursor: str | None
    generado_en: datetime


class ReporteFeItem(BaseModel):
    """One ``factura_electronica`` row + its latest DIAN ack (HU-F17.3, BR1).

    ``estado_dian`` is the RAW ``prod.v_factura_electronica_acuse.estado``
    value (migration ``0009_add_derived_read_views.py``) -- deliberately
    NOT the simplified 4-value
    ``schemas.facturacion.FacturaDisplayFE.estado_dian`` display
    projection a prior spec for this screen confused it with. The real
    domain is the UNION of ``repo.workflow.STATE_MACHINES["envio_dian"]``
    (``pendiente|enviado|ack|error``, the ``POST /envio-dian`` transition
    endpoint's state machine) and ``dian.cloud.dispatcher``'s own
    ``ESTADO_*`` constants that mutate ``envio_dian.estado`` directly,
    bypassing that state machine (``aceptado|rechazado|timeout|
    en_proceso``) -- confirmed against every writer of this column, see
    ``dian/cloud_router.py``'s ``_ENVIO_DIAN_ESTADOS`` module comment
    (same drift already found there for HU-F13.4). ``None`` when the FE
    has no ``envio_dian`` row yet (never dispatched).

    ``estado_dian`` is intentionally typed ``str | None`` (not a
    ``Literal``): BR1 asks for "the raw state of the view", and a new
    ``ESTADO_*`` constant added later to the dispatcher must not require
    a schema migration here to keep showing up.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid: uuid_lib.UUID
    uuid_sucursal: uuid_lib.UUID | None
    uuid_factura: uuid_lib.UUID | None
    numero_completo: str | None
    cufe: str | None
    estado_dian: str | None
    timestamp_evento: datetime | None


class ReporteFeResponse(BaseModel):
    """``GET /admin/reporteria/fe`` (HU-F17.3, BR1). Cross-branch (every
    branch the admin can see), same reasoning as ``reporte_ocupacion``.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    items: list[ReporteFeItem]
    next_cursor: str | None
    generado_en: datetime


class ReportePagoMedioItem(BaseModel):
    """One ``(fecha, medio_pago)`` net-amount bucket (HU-F17.3, BR2).

    ``monto_neto`` nets ``tipo_movimiento='reverso'`` rows against
    ``'pago'`` rows for the same ``medio_pago``/day -- a reverso is NEVER
    filtered out, only subtracted (BR2), mirroring
    ``reporte_operacional``'s ``monto_cobrado_neto_expr``. ``medio_pago``
    is a plain ``str`` (the column has no DB-level enum -- the real
    values observed across writers are ``efectivo|tarjeta|datafono|
    transferencia|mixto|suscripcion``, see ``repo/factura.py::
    crear_factura_pago``); a row with no ``medio_pago`` recorded groups
    under ``"sin_especificar"`` (same fallback label
    ``admin_views.dashboard_resumen`` already uses).
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    fecha: date
    medio_pago: str
    monto_neto: float


class ReportePagosResponse(BaseModel):
    """``GET /admin/reporteria/pagos`` (HU-F17.3, BR2)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid_sucursal: uuid_lib.UUID
    desde: date
    hasta: date
    items: list[ReportePagoMedioItem]
    generado_en: datetime


class CohorteSuscripcionItem(BaseModel):
    """One cohort's membership size (HU-F17.4, BR1).

    A cohort is every CURRENT-version ``subscripciones_cliente`` row
    (``vigente_hasta IS NULL``) whose ``fecha_inicio_cobertura`` falls
    in the same UTC calendar month (``mes_cohorte``, always the first
    day of that month). "Current version" matters here: a renewal or an
    early cancellation both go through ``repo.versioned.close_and_insert``
    (REQ-04/05), so this is always each logical subscription's LATEST
    state -- an early cancellation's adjusted (earlier)
    ``fecha_vencimiento`` is what the retention math in
    :class:`CohorteRetencionCell` sees, never a stale superseded value.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    mes_cohorte: date
    cohorte_size: int


class CohorteRetencionCell(BaseModel):
    """One (cohort-month, months-after-start) retention cell (HU-F17.4, BR1).

    ``porcentaje_retencion`` = % of ``mes_cohorte``'s members whose
    ``fecha_vencimiento`` reaches at least ``mes_cohorte + mes_offset``
    months -- an AGE-based approximation, exactly as BR1 names it
    ("aproximación por antigüedad"): each row is its own cohort member,
    including a renewal row (a renewal is a NEW ``subscripciones_cliente``
    row with its own ``fecha_inicio_cobertura`` -- see
    ``models/V/subscripciones_cliente.py``'s docstring), so this is NOT a
    true behavioral retention curve that follows the same customer across
    renewals. A ``None`` ``fecha_vencimiento`` (no expiry recorded) counts
    as retained at every offset. Only cells where enough calendar time has
    actually elapsed (``mes_offset <= months_between(mes_cohorte, hoy)``)
    are emitted at all -- a MISSING cell (no entry in the response's
    ``data`` list for a given ``mes_cohorte``/``mes_offset`` pair) means
    "not measurable yet", which is deliberately distinct from a present
    cell reporting ``porcentaje_retencion == 0`` (measured, and nobody
    made it) -- the frontend heatmap keeps that distinction visible
    (dataviz skill consulted for this HU; see
    ``SuscripcionesCohorte.tsx``'s docstring).
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    mes_cohorte: date
    mes_offset: int
    cohorte_size: int
    retenidos: int
    porcentaje_retencion: float


class SuscripcionPorVencerItem(BaseModel):
    """One subscription nearing expiry (HU-F17.4).

    Reuses the EXACT ``dias_para_vencer`` criterion already established
    by HU-F9.2 / REQ-OPS-181 (``apps/electron-sucursal``'s
    ``useSuscripcionesProximasVencer.ts``, ``computeProximasVencer``):
    ``floor((fecha_vencimiento - hoy) / 1 día)``, only non-negative values
    (vencidas excluded), ascending by ``fecha_vencimiento``. That prior
    art is single-branch (``uuid_sucursal`` required by its endpoint,
    which does not exist in this backend yet); this is the cross-branch
    admin equivalent (every branch the admin can see), same reasoning
    ``reporte_fe``/``reporte_ocupacion`` already use for this router. No
    day-window upper bound is applied (REQ-OPS-181 has none either) --
    the top-20 cap (closest-``fecha_vencimiento``-first) is the only
    limiter.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid: uuid_lib.UUID
    uuid_cliente: uuid_lib.UUID | None
    uuid_sucursal: uuid_lib.UUID | None
    fecha_vencimiento: date
    dias_para_vencer: int


class ReporteSuscripcionesCohorteResponse(BaseModel):
    """``GET /admin/reporteria/suscripciones/cohorte`` (HU-F17.4)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    desde: date
    hasta: date
    cohortes: list[CohorteSuscripcionItem]
    data: list[CohorteRetencionCell]
    max_offset_meses: int
    proximas_a_vencer: list[SuscripcionPorVencerItem]
    generado_en: datetime


__all__ = [
    "CohorteRetencionCell",
    "CohorteSuscripcionItem",
    "ReporteEstanciaItem",
    "ReporteFacturaItem",
    "ReporteFacturasResponse",
    "ReporteFeItem",
    "ReporteFeResponse",
    "ReporteOcupacionAgregada",
    "ReporteOcupacionHeatmapCell",
    "ReporteOcupacionResponse",
    "ReporteOcupacionSucursalItem",
    "ReporteOperacionalIngresoItem",
    "ReporteOperacionalItem",
    "ReporteOperacionalResponse",
    "ReportePagoMedioItem",
    "ReportePagosResponse",
    "ReporteSuscripcionesCohorteResponse",
    "SuscripcionPorVencerItem",
]