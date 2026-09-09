"""Pydantic v2 schemas for the Facturación + Billing domain (PR6, T-PR6-08).

Covers 2 ``[L-E]`` event tables + 4 ``[A]`` billing tables in ``prod``:

- :class:`Facturas` — operational invoice event (branch-originated)
- :class:`FacturaElectronica` — DIAN official invoice event (cloud-only,
  server-assigned ``prefijo`` + ``consecutivo`` per REQ-34, REQ-35)
- :class:`FacturaDetalle` — invoice line items (one row per concept)
- :class:`FacturaImpuestos` — tax snapshots applied to a ``factura``
- :class:`FacturaOtrosCobros` — surcharges (recargos, propinas, ajustes)
- :class:`FacturaPagos` — payment events + reversals (REQ-OP-09, SC-11)

Special validators (defense in depth):

- ``FacturaElectronicaCreate`` EXCLUDES ``prefijo`` / ``consecutivo``.
  ``extra='forbid'`` (from :class:`_Base`) blocks client smuggling; the
  legacy cloud-only router (``dian/cloud_router.py``, T-PR6-09,
  pre-D1-rev, still live but NOT the branch's numbering path) atomically
  assigns them via ``SELECT FOR UPDATE`` on ``resolucion_facturacion`` +
  incrementing its ``consecutivo`` counter.
- ``FacturaPagosCreate.tipo_movimiento`` defaults to ``"pago"``;
  ``FacturaPagosReversoCreate`` is the dedicated compensating variant
  (``uuid_pago_revertido`` REQUIRED, ``tipo_movimiento='reverso'``
  server-set, duplicates blocked by the partial unique index
  ``uq_factura_pagos_reverso`` created in migration 0004).

All schemas inherit :class:`_Base` (``extra='forbid'``,
``from_attributes=True``). Server-controlled columns
(``created_at``, ``created_by``, ``sync_status``, ``sync_timestamp``,
``sync_attempts``, ``fecha_retencion_hasta`` where server-defaulted)
are excluded from ``Create`` / ``Update`` per design §6.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import StringConstraints

from .common import FilterBase, ReadListBase, _Base

# ---------------------------------------------------------------------------
# Facturas ([L-E] operational invoice event)
# ---------------------------------------------------------------------------


class FacturasRead(_Base):
    """Read-back for ``prod.facturas`` (composite PK ``uuid + fecha_retencion_hasta``).

    State (``emitida`` | ``anulada`` | ``pagada``) is NEVER stored on the
    row — it is derived via the ``V_FACTURA_ESTADO`` view (PR6 schema
    work) by joining ``factura_pagos`` + ``anulaciones``.
    """

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    fecha_retencion_hasta: date
    uuid_sucursal: uuid_lib.UUID | None
    subtotal: Decimal | None
    descuento: Decimal | None
    total: Decimal | None
    uuid_ingreso: uuid_lib.UUID | None
    uuid_salida: uuid_lib.UUID | None


class FacturasCreate(_Base):
    """INSERT payload for ``prod.facturas``.

    Branch-originated; cloud-merged via sync. Server sets
    ``fecha_retencion_hasta`` via ``RetentionMixin`` server-default.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    subtotal: Decimal | None = None
    descuento: Decimal | None = None
    total: Decimal | None = None
    uuid_ingreso: uuid_lib.UUID | None = None
    uuid_salida: uuid_lib.UUID | None = None


class FacturasUpdate(_Base):
    """[L-E] UPDATE payload — kept for quintet completeness only.

    The API surface will NOT expose a PATCH route (append-only at write
    time per design §4.5); defined here to satisfy the
    ``Read / Create / Update / Filter / ReadList`` quintet (T-PR6-08).
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    subtotal: Decimal | None = None
    descuento: Decimal | None = None
    total: Decimal | None = None
    uuid_ingreso: uuid_lib.UUID | None = None
    uuid_salida: uuid_lib.UUID | None = None


class FacturasFilter(FilterBase):
    """Query filter for ``prod.facturas``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_ingreso: uuid_lib.UUID | None = None
    uuid_salida: uuid_lib.UUID | None = None
    created_at__gte: datetime | None = None
    created_at__lte: datetime | None = None


class FacturasReadList(ReadListBase[FacturasRead]):
    """Cursor-paginated list of :class:`FacturasRead` items."""


# ---------------------------------------------------------------------------
# FacturaElectronica ([L-E] DIAN, CLOUD-ONLY — REQ-34, REQ-35)
# ---------------------------------------------------------------------------


class FacturaElectronicaRead(_Base):
    """Read-back for ``prod.factura_electronica`` (cloud-only)."""

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    uuid_sucursal: uuid_lib.UUID | None
    uuid_factura: uuid_lib.UUID | None
    uuid_cliente: uuid_lib.UUID | None
    uuid_resolucion_facturacion: uuid_lib.UUID | None
    prefijo: str | None  # server-assigned (REQ-34)
    consecutivo: int | None  # server-assigned (REQ-34)
    descuento: Decimal | None


class FacturaElectronicaCreate(_Base):
    """REQ-34 + REQ-35. Server assigns ``prefijo`` and ``consecutivo``.

    The cloud-only ``dian/cloud_router.py`` (T-PR6-09) atomically:

    1. ``SELECT FOR UPDATE`` on ``prod.resolucion_facturacion`` row
    2. ``UPDATE`` the row's ``consecutivo`` counter (``next_consecutivo``,
       T-PR11-05 helper)
    3. ``INSERT INTO prod.factura_electronica`` with the assigned values

    This is the pre-D1-rev cloud-only path (still live, out of PR9's scope
    to remove — see ``models/L_E/factura_electronica.py``'s own docstring);
    it is NOT the branch's numbering path (``repo.resolucion_facturacion
    .assign_consecutivo``, branch-local, D1-rev).

    The Pydantic schema here excludes both fields — ``extra='forbid'``
    (from :class:`_Base`) blocks client smuggling. That is the
    T-PR4-08-style fast-fail assertion: any ``prefijo`` / ``consecutivo``
    in the request body returns ``ValidationError`` (``HTTP 422``).
    """

    uuid_sucursal: uuid_lib.UUID
    uuid_factura: uuid_lib.UUID
    uuid_cliente: uuid_lib.UUID | None = None
    uuid_resolucion_facturacion: uuid_lib.UUID
    descuento: Decimal | None = None  # Numeric(18,4)


class FacturaElectronicaUpdate(_Base):
    """[L-E] UPDATE payload — append-only at write time per design §4.5.

    The cloud router does NOT expose a PATCH route. Defined here for
    quintet completeness.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura: uuid_lib.UUID | None = None
    uuid_cliente: uuid_lib.UUID | None = None
    uuid_resolucion_facturacion: uuid_lib.UUID | None = None
    descuento: Decimal | None = None


class FacturaElectronicaFilter(FilterBase):
    """Query filter for ``prod.factura_electronica``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura: uuid_lib.UUID | None = None
    uuid_cliente: uuid_lib.UUID | None = None
    uuid_resolucion_facturacion: uuid_lib.UUID | None = None
    prefijo: str | None = None
    consecutivo: int | None = None


class FacturaElectronicaReadList(ReadListBase[FacturaElectronicaRead]):
    """Cursor-paginated list of :class:`FacturaElectronicaRead` items."""


# ---------------------------------------------------------------------------
# FacturaDetalle ([A] line items — monthly pg_partman partition)
# ---------------------------------------------------------------------------


class FacturaDetalleRead(_Base):
    """Read-back for ``prod.factura_detalle`` (composite PK; monthly partitioned)."""

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    fecha_retencion_hasta: date
    uuid_sucursal: uuid_lib.UUID | None
    uuid_factura: uuid_lib.UUID | None
    concepto: str | None
    cantidad: int | None
    valor_unitario: Decimal | None
    subtotal: Decimal | None


class FacturaDetalleCreate(_Base):
    """INSERT payload for ``prod.factura_detalle``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura: uuid_lib.UUID | None = None
    concepto: Annotated[str, StringConstraints(max_length=255)] | None = None
    cantidad: int | None = None
    valor_unitario: Decimal | None = None
    subtotal: Decimal | None = None


class FacturaDetalleUpdate(_Base):
    """[A] UPDATE payload — append-only, REVOKE UPDATE on the DB.

    Defined for quintet completeness; no route mounts it.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura: uuid_lib.UUID | None = None
    concepto: Annotated[str, StringConstraints(max_length=255)] | None = None
    cantidad: int | None = None
    valor_unitario: Decimal | None = None
    subtotal: Decimal | None = None


class FacturaDetalleFilter(FilterBase):
    """Query filter for ``prod.factura_detalle``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura: uuid_lib.UUID | None = None


class FacturaDetalleReadList(ReadListBase[FacturaDetalleRead]):
    """Cursor-paginated list of :class:`FacturaDetalleRead` items."""


# ---------------------------------------------------------------------------
# FacturaImpuestos ([A] tax snapshot)
# ---------------------------------------------------------------------------


class FacturaImpuestosRead(_Base):
    """Read-back for ``prod.factura_impuestos``.

    ``fecha_retencion_hasta`` is inherited from ``RetentionMixin`` and
    stays NULL-able here (no DIAN 5-year enforcement at the column level
    for this table; the helper sets it on insert).
    """

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    fecha_retencion_hasta: date | None
    uuid_sucursal: uuid_lib.UUID | None
    uuid_factura: uuid_lib.UUID | None
    uuid_impuesto: uuid_lib.UUID | None
    base_calculo: Decimal | None
    porcentaje_aplicado: Decimal | None
    valor: Decimal | None


class FacturaImpuestosCreate(_Base):
    """INSERT payload for ``prod.factura_impuestos``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura: uuid_lib.UUID | None = None
    uuid_impuesto: uuid_lib.UUID | None = None
    base_calculo: Decimal | None = None
    porcentaje_aplicado: Decimal | None = None
    valor: Decimal | None = None


class FacturaImpuestosUpdate(_Base):
    """[A] UPDATE payload — append-only. Defined for quintet completeness."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura: uuid_lib.UUID | None = None
    uuid_impuesto: uuid_lib.UUID | None = None
    base_calculo: Decimal | None = None
    porcentaje_aplicado: Decimal | None = None
    valor: Decimal | None = None


class FacturaImpuestosFilter(FilterBase):
    """Query filter for ``prod.factura_impuestos``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura: uuid_lib.UUID | None = None
    uuid_impuesto: uuid_lib.UUID | None = None


class FacturaImpuestosReadList(ReadListBase[FacturaImpuestosRead]):
    """Cursor-paginated list of :class:`FacturaImpuestosRead` items."""


# ---------------------------------------------------------------------------
# FacturaOtrosCobros ([A] surcharges)
# ---------------------------------------------------------------------------


class FacturaOtrosCobrosRead(_Base):
    """Read-back for ``prod.factura_otros_cobros``."""

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    fecha_retencion_hasta: date | None
    uuid_sucursal: uuid_lib.UUID | None
    uuid_factura: uuid_lib.UUID | None
    uuid_otro_cobro: uuid_lib.UUID | None
    base_calculo: Decimal | None
    valor_aplicado: Decimal | None
    valor: Decimal | None


class FacturaOtrosCobrosCreate(_Base):
    """INSERT payload for ``prod.factura_otros_cobros``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura: uuid_lib.UUID | None = None
    uuid_otro_cobro: uuid_lib.UUID | None = None
    base_calculo: Decimal | None = None
    valor_aplicado: Decimal | None = None
    valor: Decimal | None = None


class FacturaOtrosCobrosUpdate(_Base):
    """[A] UPDATE payload — append-only. Defined for quintet completeness."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura: uuid_lib.UUID | None = None
    uuid_otro_cobro: uuid_lib.UUID | None = None
    base_calculo: Decimal | None = None
    valor_aplicado: Decimal | None = None
    valor: Decimal | None = None


class FacturaOtrosCobrosFilter(FilterBase):
    """Query filter for ``prod.factura_otros_cobros``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura: uuid_lib.UUID | None = None
    uuid_otro_cobro: uuid_lib.UUID | None = None


class FacturaOtrosCobrosReadList(ReadListBase[FacturaOtrosCobrosRead]):
    """Cursor-paginated list of :class:`FacturaOtrosCobrosRead` items."""


# ---------------------------------------------------------------------------
# FacturaPagos ([A] payment events + reversals, REQ-OP-09 + SC-11)
# ---------------------------------------------------------------------------


class FacturaPagosRead(_Base):
    """Read-back for ``prod.factura_pagos`` (composite PK; monthly partitioned).

    The ``tipo_movimiento`` discriminator (``pago`` | ``ajuste`` |
    ``reverso``) + ``uuid_pago_revertido`` pointer are guarded by the
    partial unique index ``uq_factura_pagos_reverso`` created in
    migration 0004.
    """

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    fecha_retencion_hasta: date
    uuid_sucursal: uuid_lib.UUID | None
    uuid_factura: uuid_lib.UUID | None
    uuid_sesion: uuid_lib.UUID | None
    medio_pago: str | None
    valor: Decimal | None
    referencia: str | None
    tipo_movimiento: str | None  # 'pago' | 'ajuste' | 'reverso'
    uuid_pago_revertido: uuid_lib.UUID | None
    timestamp_evento: datetime | None


class FacturaPagosCreate(_Base):
    """REQ-OP-09 — regular pago row.

    ``tipo_movimiento`` defaults to ``"pago"`` (Pydantic ``Literal``
    restricts to ``"pago" | "ajuste"`` at the edge). For reverso
    (compensation), use :class:`FacturaPagosReversoCreate` instead. The
    DB enforces at-most-once reversals via
    ``fn_factura_pagos_reverso_uniqueness`` trigger + the partial
    unique index created in migration 0004 (``uq_factura_pagos_reverso``).
    """

    uuid_sucursal: uuid_lib.UUID
    uuid_factura: uuid_lib.UUID
    uuid_sesion: uuid_lib.UUID | None = None
    medio_pago: Annotated[str, StringConstraints(max_length=64)] | None = None
    valor: Decimal | None = None
    referencia: Annotated[str, StringConstraints(max_length=255)] | None = None
    tipo_movimiento: Literal["pago", "ajuste"] = "pago"
    timestamp_evento: datetime | None = None


class FacturaPagosReversoCreate(_Base):
    """REQ-OP-09 / SC-11 — compensating pago row.

    ``uuid_pago_revertido`` is REQUIRED (no default) and the partial
    unique index ``uq_factura_pagos_reverso`` blocks a second reversal
    of the same pago with ``ERRCODE='unique_violation'`` → maps to
    ``DuplicateReversoError`` (HTTP 409). ``tipo_movimiento='reverso'``
    is server-set (NOT exposed on this schema) so the client cannot
    smuggle a reverso with a fresh ``uuid`` — the endpoint layer
    constructs the row with ``tipo_movimiento='reverso'`` after
    ``FacturaPagosReversoCreate`` validates.
    """

    uuid_sucursal: uuid_lib.UUID
    uuid_factura: uuid_lib.UUID
    uuid_sesion: uuid_lib.UUID | None = None
    medio_pago: Annotated[str, StringConstraints(max_length=64)] | None = None
    valor: Decimal | None = None
    referencia: Annotated[str, StringConstraints(max_length=255)] | None = None
    uuid_pago_revertido: uuid_lib.UUID  # MANDATORY for reverso
    timestamp_evento: datetime | None = None


class FacturaPagosUpdate(_Base):
    """[A] UPDATE payload — append-only, REVOKE UPDATE on the DB.

    Defined for quintet completeness; no route mounts it.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura: uuid_lib.UUID | None = None
    uuid_sesion: uuid_lib.UUID | None = None
    medio_pago: Annotated[str, StringConstraints(max_length=64)] | None = None
    valor: Decimal | None = None
    referencia: Annotated[str, StringConstraints(max_length=255)] | None = None
    timestamp_evento: datetime | None = None


class FacturaPagosFilter(FilterBase):
    """Query filter for ``prod.factura_pagos``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura: uuid_lib.UUID | None = None
    uuid_sesion: uuid_lib.UUID | None = None
    medio_pago: str | None = None
    tipo_movimiento: str | None = None
    timestamp_evento__gte: datetime | None = None
    timestamp_evento__lte: datetime | None = None


class FacturaPagosReadList(ReadListBase[FacturaPagosRead]):
    """Cursor-paginated list of :class:`FacturaPagosRead` items."""


__all__ = [
    "FacturaDetalleCreate",
    "FacturaDetalleFilter",
    "FacturaDetalleRead",
    "FacturaDetalleReadList",
    "FacturaDetalleUpdate",
    "FacturaElectronicaCreate",
    "FacturaElectronicaFilter",
    "FacturaElectronicaRead",
    "FacturaElectronicaReadList",
    "FacturaElectronicaUpdate",
    "FacturaImpuestosCreate",
    "FacturaImpuestosFilter",
    "FacturaImpuestosRead",
    "FacturaImpuestosReadList",
    "FacturaImpuestosUpdate",
    "FacturaOtrosCobrosCreate",
    "FacturaOtrosCobrosFilter",
    "FacturaOtrosCobrosRead",
    "FacturaOtrosCobrosReadList",
    "FacturaOtrosCobrosUpdate",
    "FacturaPagosCreate",
    "FacturaPagosFilter",
    "FacturaPagosRead",
    "FacturaPagosReadList",
    "FacturaPagosReversoCreate",
    "FacturaPagosUpdate",
    "FacturasCreate",
    "FacturasFilter",
    "FacturasRead",
    "FacturasReadList",
    "FacturasUpdate",
]