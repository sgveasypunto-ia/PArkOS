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
from typing import Annotated, Any, Literal

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


# ---------------------------------------------------------------------------
# HU-F1.9 / REQ-OPS-053..063 -- billing transactional surfaces
# ---------------------------------------------------------------------------
# See design §9.5. Defense in depth:
#
# - ``FacturaItemConDatosPropios._validar_nit_modulo11`` Pydantic v2
#   @field_validator rejects NIT with bad DV → ValidationError → 422
#   with discriminator ``nit_invalido`` (D-HU-F1.9-19).
# - ``extra='forbid'`` (from :class:`_Base`) rejects client-side attempts
#   to inject ``uuid_cliente`` (DEC-FACT-06), ``correlacion_id``
#   (DEC-IDEM-01), and ``prefijo`` / ``consecutivo`` (DEC-FACT-05).
# - ``medio_pago`` is a 5-value Literal — NO ``prod.forma_pago`` catalog
#   in MVP (DEC-FACT-07 Opción A).
# - ``uuid_cliente`` on the response is **server-derived**, NEVER persisted
#   on ``prod.facturas`` (DEC-FACT-06).
# ---------------------------------------------------------------------------

from pydantic import Field, field_validator

from ..repo.nit_modulo11 import dv_esperado, validar_nit_modulo11


class FacturaItemConDatosPropios(_Base):
    """Client data block for ``fe_con_datos=true`` payloads.

    Validates NIT módulo 11 via Pydantic v2 ``@field_validator`` when
    ``tipo_identificador='NIT'``. Re-uses :mod:`repo.nit_modulo11`.

    ``extra='forbid'`` (inherited from :class:`_Base`) rejects extra
    fields including attempts to inject ``uuid_cliente`` (DEC-FACT-06).
    """

    tipo_identificador: Literal["NIT", "CC", "CE", "pasaporte"]
    numero_identificacion: Annotated[str, StringConstraints(min_length=5, max_length=20)]
    dv: Annotated[str, StringConstraints(min_length=1, max_length=2)] | None = None
    nombre: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    apellido: Annotated[str, StringConstraints(min_length=1, max_length=120)] | None = None
    email: Annotated[str, StringConstraints(min_length=5, max_length=120)] | None = None
    telefono: Annotated[str, StringConstraints(min_length=7, max_length=20)] | None = None

    @field_validator("numero_identificacion")
    @classmethod
    def _validar_nit_modulo11(cls, v: str, info: Any) -> str:
        """If ``tipo_identificador='NIT'``, apply módulo 11 algorithm.

        Raises ``ValueError`` (Pydantic v2 maps to ``ValidationError`` →
        HTTP 422) when:

        - ``dv`` is missing for NIT (cannot validate without it).
        - the DV does not match the computed módulo 11 result.
        """
        tipo = info.data.get("tipo_identificador")
        if tipo == "NIT":
            dv = info.data.get("dv")
            if dv is None:
                raise ValueError("dv required when tipo_identificador='NIT'")
            if not validar_nit_modulo11(v, dv):
                expected = dv_esperado(v)
                raise ValueError(f"DV inválido: recibido={dv}, esperado={expected}")
        return v


class FacturaItemCreate(_Base):
    """INSERT payload for one ``prod.factura_detalle`` row."""

    tipo: Literal["servicio", "producto"]
    concepto: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    cantidad: int = Field(gt=0, le=999)
    valor_unitario: Decimal = Field(ge=Decimal(0), le=Decimal("999999999.9999"))
    uuid_tarifa_sucursal: uuid_lib.UUID | None = None


class FacturaCreate(_Base):
    """HU-F1.9: POST ``/api/v1/facturacion/factura`` payload.

    12-step handler chain (see design §7) consumes this payload. KD-FACT-01
    enforces single-commit atomicity on the 4-table insert.
    """

    uuid_salida: uuid_lib.UUID
    items: list[FacturaItemCreate] = Field(min_length=1, max_length=50)
    subtotal: Decimal
    total: Decimal
    medio_pago: Literal["efectivo", "tarjeta", "transferencia", "datafono", "mixto"]
    referencia: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None
    fe_con_datos: bool = False
    fe_datos_cliente: FacturaItemConDatosPropios | None = None


class FacturaItemRead(_Base):
    """Read-back for one ``prod.factura_detalle`` row."""

    uuid: uuid_lib.UUID
    tipo: str
    concepto: str
    cantidad: int
    valor_unitario: Decimal
    subtotal: Decimal


class FacturaRead(_Base):
    """HU-F1.9: POST ``/api/v1/facturacion/factura`` response.

    ``uuid_cliente`` is **server-derived** (DEC-FACT-06). NOT persisted on
    ``prod.facturas``. ``estado`` is derived from the ``V_FACTURA_ESTADO``
    view (PR6 schema work, referenced in
    ``models/L_E/facturas.py`` lines 12-14 docstring).
    """

    uuid: uuid_lib.UUID
    created_at: datetime
    uuid_sucursal: uuid_lib.UUID
    uuid_ingreso: uuid_lib.UUID | None
    uuid_salida: uuid_lib.UUID | None
    subtotal: Decimal
    descuento: Decimal
    total: Decimal
    uuid_cliente: uuid_lib.UUID | None  # DEC-FACT-06 derivado, no persistido
    items: list[FacturaItemRead]
    estado: Literal["emitida", "pagada", "anulada"]


class FacturaPagoAdicionalCreate(_Base):
    """HU-F1.9: POST ``/api/v1/facturacion/factura-pagos`` payload."""

    uuid_factura: uuid_lib.UUID
    medio_pago: Literal["efectivo", "tarjeta", "transferencia", "datafono", "mixto"]
    valor: Decimal = Field(gt=Decimal(0))
    referencia: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None
    uuid_sesion: uuid_lib.UUID | None = None


class FacturaPagoRead(_Base):
    """HU-F1.9: POST ``/api/v1/facturacion/factura-pagos`` response."""

    uuid: uuid_lib.UUID
    uuid_factura: uuid_lib.UUID
    medio_pago: str
    valor: Decimal
    referencia: str | None
    timestamp_evento: datetime


# --- Typed error schemas (D-HU-F1.9-19) -------------------------------------


class NitInvalidoErrorSchema(_Base):
    """V5 422 discriminator — NIT módulo 11 mismatch."""

    error: Literal["nit_invalido"]
    dv_esperado: int
    dv_recibido: str


class ClienteNoEncontradoErrorSchema(_Base):
    """V2 404 discriminator — cliente does not exist (when fe_con_datos=true)."""

    error: Literal["cliente_no_encontrado"]
    numero_identificacion: str


class DetalleInvalidoErrorSchema(_Base):
    """V4 422 discriminator — items vacío."""

    error: Literal["detalle_invalido"]
    min_items: int


class TotalNoCoherenteErrorSchema(_Base):
    """V6 422 discriminator — total differs by >0.01 COP."""

    error: Literal["total_no_coherente"]
    total_recibido: str
    total_calculado: str
    diferencia: str


# ---------------------------------------------------------------------------
# HU-F1.10 / REQ-OPS-064..074 — Numeración FE + estado DIAN + reintento
# ---------------------------------------------------------------------------
#
# Defense in depth (DEC-FE-01..07 + KD-FE-01):
#
# - ``FacturaElectronicaCreate`` EXCLUDES ``prefijo``, ``consecutivo``, and
#   ``uuid_resolucion_facturacion`` (all server-assigned by
#   ``assign_consecutivo`` + V3 vigente lookup). ``extra='forbid'`` blocks
#   client smuggling; the server is the only source of truth.
# - ``FacturaElectronicaRead`` embeds ``envio_actual`` (the latest envio
#   chain tip from ``prod.v_factura_electronica_acuse``); ``estado`` is a
#   strict ``Literal`` (``pendiente|enviado|aceptado|rechazado``) — NEVER a
#   fabricated ``reportado_dian`` boolean (plan.md línea 947 FORBIDDEN).
# - 8 typed error schemas carry the discriminator strings the handler
#   emits (V1..V4 + /reintentar discriminators).
#
# KD-FE-01: the create handler commits ONCE; the response shape is built
# in-memory from the ORM rows after the single commit materializes FE row
# + initial envio row atomically.
# ---------------------------------------------------------------------------


class EnvioDianRead(_Base):
    """Read-back for one ``prod.envio_dian`` row (used inside FE responses)."""

    uuid: uuid_lib.UUID
    uuid_factura_electronica: uuid_lib.UUID
    estado: Literal["pendiente", "enviado", "aceptado", "rechazado"]
    timestamp_evento: datetime | None
    uuid_envio_padre: uuid_lib.UUID | None = None
    cufe: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None
    motivo_rechazo: Annotated[str, StringConstraints(max_length=500)] | None = None


class FacturaElectronicaCreate(_Base):
    """POST ``/api/v1/facturacion/factura-electronica`` payload.

    Server assigns ``prefijo``, ``consecutivo``, and resolves
    ``uuid_resolucion_facturacion`` from V3 vigente lookup. Client only
    supplies ``uuid_factura`` (the commercial invoice to number).
    ``extra='forbid'`` (inherited from :class:`_Base`) blocks smuggling.
    """

    uuid_factura: uuid_lib.UUID


class FacturaElectronicaRead(_Base):
    """POST/GET ``/factura-electronica`` response shape."""

    uuid: uuid_lib.UUID
    prefijo: Annotated[str, StringConstraints(min_length=1, max_length=10)]
    consecutivo: int = Field(ge=0)
    uuid_factura: uuid_lib.UUID
    uuid_resolucion_facturacion: uuid_lib.UUID
    created_at: datetime
    envio_actual: EnvioDianRead


class EnvioDianRetryRead(_Base):
    """POST ``/factura-electronica/{uuid}/reintentar`` response shape.

    A retry response is the NEW envio row (chain tip), so ``estado`` is
    ALWAYS ``pendiente`` on write.
    """

    uuid: uuid_lib.UUID
    uuid_factura_electronica: uuid_lib.UUID
    estado: Literal["pendiente"]
    timestamp_evento: datetime
    uuid_envio_padre: uuid_lib.UUID


# --- Typed error schemas for HU-F1.10 (8 discriminators) ---------------------


class NumeracionAgotadaError(_Base):
    """V4 409 — DIAN resolution's ``rango_hasta`` reached (DEC-FE-03)."""

    error: Literal["numeracion_agotada"]
    uuid_resolucion_facturacion: uuid_lib.UUID
    rango_hasta: int
    prefijo: str


class ReintentoNoPermitidoError(_Base):
    """V2 409 (retry) — chain tip is ``aceptado`` (DEC-FE-04)."""

    error: Literal["reintento_no_permitido"]
    uuid_factura_electronica: uuid_lib.UUID
    estado_actual: str | None


class EnvioDianAlreadyPendingError(_Base):
    """V2 409 (retry) — chain tip is ``pendiente`` (rapid-retry guard)."""

    error: Literal["envio_dian_already_pending"]
    uuid_factura_electronica: uuid_lib.UUID
    uuid_envio_pendiente: uuid_lib.UUID


class FacturaElectronicaYaExisteError(_Base):
    """V2 409 (create) — partial UK ``one_fe_per_factura`` race (REQ-OPS-067)."""

    error: Literal["factura_electronica_ya_existe"]
    uuid_factura: uuid_lib.UUID


class ResolucionNoVigenteError(_Base):
    """V3 409 (create) — no vigente resolution for the sucursal (REQ-OPS-073)."""

    error: Literal["resolucion_no_vigente"]
    uuid_sucursal: uuid_lib.UUID


class FacturaNoEncontradaElectronicaError(_Base):
    """V1 404 (create) — ``prod.facturas.uuid`` not found."""

    error: Literal["factura_no_encontrada"]
    uuid_factura: uuid_lib.UUID


class FacturaElectronicaNoEncontradaError(_Base):
    """V1 404 (GET + retry) — ``prod.factura_electronica.uuid`` not found."""

    error: Literal["factura_electronica_no_encontrada"]
    uuid_factura_electronica: uuid_lib.UUID


class NumeracionDuplicadaError(_Base):
    """UK01 race — pgcode 23505 on ``factura_electronica_uk01``."""

    error: Literal["numeracion_duplicada"]
    uuid_resolucion_facturacion: uuid_lib.UUID
    consecutivo: int


__all__ = [
    "ClienteNoEncontradoErrorSchema",
    "DetalleInvalidoErrorSchema",
    "EnvioDianAlreadyPendingError",
    "EnvioDianRead",
    "EnvioDianRetryRead",
    "FacturaCreate",
    "FacturaDetalleCreate",
    "FacturaDetalleFilter",
    "FacturaDetalleRead",
    "FacturaDetalleReadList",
    "FacturaDetalleUpdate",
    "FacturaElectronicaCreate",
    "FacturaElectronicaFilter",
    "FacturaElectronicaNoEncontradaError",
    "FacturaElectronicaRead",
    "FacturaElectronicaReadList",
    "FacturaElectronicaUpdate",
    "FacturaElectronicaYaExisteError",
    "FacturaImpuestosCreate",
    "FacturaImpuestosFilter",
    "FacturaImpuestosRead",
    "FacturaImpuestosReadList",
    "FacturaImpuestosUpdate",
    "FacturaItemConDatosPropios",
    "FacturaItemCreate",
    "FacturaItemRead",
    "FacturaNoEncontradaElectronicaError",
    "FacturaOtrosCobrosCreate",
    "FacturaOtrosCobrosFilter",
    "FacturaOtrosCobrosRead",
    "FacturaOtrosCobrosReadList",
    "FacturaOtrosCobrosUpdate",
    "FacturaPagoAdicionalCreate",
    "FacturaPagoRead",
    "FacturaPagosCreate",
    "FacturaPagosFilter",
    "FacturaPagosRead",
    "FacturaPagosReadList",
    "FacturaPagosReversoCreate",
    "FacturaPagosUpdate",
    "FacturaRead",
    "FacturasCreate",
    "FacturasFilter",
    "FacturasRead",
    "FacturasReadList",
    "FacturasUpdate",
    "NitInvalidoErrorSchema",
    "NumeracionAgotadaError",
    "NumeracionDuplicadaError",
    "ReintentoNoPermitidoError",
    "ResolucionNoVigenteError",
    "TotalNoCoherenteErrorSchema",
]