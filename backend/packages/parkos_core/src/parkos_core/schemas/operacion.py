"""Pydantic v2 schemas for ``prod.ingreso`` (operation [L-E] lifecycle event, PR5).

Maps the ``Ingreso`` ORM (``models/L_E/ingreso.py``) to the API edge.
Quintet structure: ``Read`` / ``Create`` / ``Filter`` / ``ReadList``.
**NO ``Update`` class** — ``[L-E]`` events are append-only at write
time per design §4.5; the only valid mutation is ``repo.event.record_event``
(REQ-30, REQ-33) and the AST scan in
``tests/static/test_no_raw_dml_on_le_tables.py`` rejects any
``session.execute(update/delete)`` against this table outside that helper.

Ten columns are exposed by the ORM (``LifecycleEventBase`` adds 4 of
them — ``uuid``, ``created_at``, ``created_by`` + the 3 ``SyncMixin``
fields; 6 are business columns declared on ``Ingreso`` itself):

- ``uuid``, ``created_at``, ``created_by``, ``sync_status``,
  ``sync_timestamp``, ``sync_attempts`` (inherited, on ``Read``)
- ``uuid_sucursal``, ``placa``, ``uuid_tipo_vehiculo``,
  ``uuid_subscripcion_cliente``, ``fecha_ingreso``, ``observaciones``
  (business)

**Branch ownership.** ``uuid_sucursal`` is REQUIRED on ``IngresoCreate``
— every ingreso belongs to a branch. The other 5 business columns are
OPTIONAL: ad-hoc ingreso without subscription is allowed (parking lot
walk-in), and ``placa`` / ``uuid_tipo_vehiculo`` can be filled in by a
later lookup or by a derived-resource PATCH (PR6 mounts that route).

**Idempotency contract.** Clients MUST send an ``Idempotency-Key`` HTTP
header on ``POST /ingresos``. That check is enforced at the FastAPI
dependency layer (``api/v1/operacion.py``, T-PR5-07) — NOT here — so
the schema itself stays a pure data contract decoupled from transport.

**State derivation.** Current state (``abierto`` | ``cerrado`` |
``anulada``) is computed via the ``V_INGRESO_ESTADO`` view and surfaced
through a nested ``GET /ingresos/{uuid}/estado`` route (T-PR5-07, SC-30).
It is NEVER stored on the row itself, in keeping with the bi-temporal
contract (state belongs to the workflow, not to the event).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from .common import FilterBase, ReadListBase, _Base


class IngresoRead(_Base):
    """Full ORM column mapping for ``prod.ingreso``.

    Inherits ``from_attributes=True`` and ``extra='forbid'`` from
    :class:`_Base`. Used as the response model for ``GET /ingresos/{uuid}``
    and as the ``items`` element type for :class:`IngresoReadList`.
    """

    # Inherited from LifecycleEventBase (IdMixin + AuditMixin + SyncMixin)
    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None

    # Business columns (from models/L_E/ingreso.py)
    uuid_sucursal: uuid_lib.UUID | None
    placa: str | None
    uuid_tipo_vehiculo: uuid_lib.UUID | None
    uuid_subscripcion_cliente: uuid_lib.UUID | None
    fecha_ingreso: datetime | None
    observaciones: str | None


class IngresoCreate(_Base):
    """INSERT payload for ``prod.ingreso``.

    ``uuid_sucursal`` is REQUIRED — every ingreso belongs to a branch.
    The remaining 5 business columns are OPTIONAL and can be filled in by
    a later lookup, by a derived-resource PATCH (PR6), or left NULL for
    ad-hoc walk-in traffic that has no subscription attached.

    .. note::
       The ``Idempotency-Key`` HTTP header is REQUIRED at the API edge.
       That validation lives in a FastAPI dependency (``T-PR5-07``),
       NOT here, to keep this schema a pure data contract decoupled
       from transport concerns.

    .. warning::
       ``extra='forbid'`` (inherited from :class:`_Base`) rejects any
       unknown field — clients cannot smuggle audit columns
       (``created_at``, ``created_by``, ``sync_status``) or
       ``LifecycleEventBase`` internals; those are server-controlled.
    """

    # REQUIRED — branch ownership
    uuid_sucursal: uuid_lib.UUID

    # OPTIONAL — 5 business columns
    placa: str | None = None
    uuid_tipo_vehiculo: uuid_lib.UUID | None = None
    uuid_subscripcion_cliente: uuid_lib.UUID | None = None
    fecha_ingreso: datetime | None = None
    observaciones: str | None = None


class IngresoFilter(FilterBase):
    """Query filter for ``prod.ingreso``.

    All fields optional. Range-style fields use the ``__gte`` / ``__lte``
    suffix convention so the SQL builder can map them to ``>=`` / ``<=``
    on the ``fecha_ingreso`` column.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    placa: str | None = None
    fecha_ingreso__gte: datetime | None = None
    fecha_ingreso__lte: datetime | None = None


class IngresoReadList(ReadListBase[IngresoRead]):
    """Cursor-paginated list of ``IngresoRead`` items.

    ``next_cursor=None`` signals EOF (see :class:`ReadListBase`).
    """


__all__ = [
    "IngresoCreate",
    "IngresoFilter",
    "IngresoRead",
    "IngresoReadList",
]


# ---------------------------------------------------------------------------
# HU-F1.8 -- CotizarResponse (discriminated union by ``cobrar: bool``)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


class CotizarFacturacion(_Base):
    """``cobrar=true`` variant -- full fiscal breakdown.

    Returned when an ``ingreso`` exists, has no non-anulada ``salidas``,
    has no active monthly subscription at the branch, has a vigente
    ``tarifas_sucursal`` row for the combination, and has a vigente
    ``impuestos`` row with ``nombre='IVA'``.

    All seven GAP-BE-09 contract fields are REQUIRED (no defaults) --
    the contract is exhaustive; missing any field is a server bug.

    **``tiempo_minutos`` shape (apply-time correction).** The PL/pgSQL
    function computes ``EXTRACT(EPOCH FROM (NOW() - fecha_ingreso)) / 60.0``
    which returns a sub-second-precision ``numeric`` (e.g. ``89.0025``
    for a 89-minute-old row). Postgres serializes it as a Python ``float``
    via the asyncpg jsonb bridge, so the schema accepts ``int | float``.
    Clients SHOULD treat it as informational (the actual billing uses
    ``CEIL(tiempo_minutos)`` minutes inside the function); the design's
    original ``int`` typing was relaxed in the apply phase to accept the
    real wire value.
    """

    model_config = ConfigDict(extra="forbid")

    cobrar: Literal[True]
    subtotal: Decimal
    iva: Decimal
    total: Decimal
    tiempo_minutos: int | float
    tarifa_uuid: uuid_lib.UUID
    vigente_hasta: datetime


class CotizarMensualidad(_Base):
    """``cobrar=false`` variant -- short-circuit for an active monthly subscription.

    Returned when the ingreso's plate has an open subscription at the
    branch (REQ-OPS-023, design.md §3 step 2). The PL/pgSQL function
    short-circuits the pricing pipeline; no fiscal data is computed.

    ``motivo`` is a literal string so the contract is closed -- adding
    a new motivo requires a new ``CotizarMensualidad`` variant, not
    free-form string injection.
    """

    model_config = ConfigDict(extra="forbid")

    cobrar: Literal[False]
    motivo: Literal["mensualidad_vigente"]


# Discriminated union: Pydantic v2 picks the variant by the value of
# ``cobrar`` (True -> CotizarFacturacion, False -> CotizarMensualidad).
# ``Annotated[..., Field(discriminator=...)]`` is the v2-native form;
# ``extra='forbid'`` on each variant still rejects smuggle attempts
# like ``{"cobrar": True, "motivo": "mensualidad_vigente"}``.
CotizarResponse = Annotated[
    CotizarFacturacion | CotizarMensualidad,
    Field(discriminator="cobrar"),
]


# ---------------------------------------------------------------------------
# HU-F1.5 -- OcupacionItem / OcupacionResponse (REQ-OPS-030)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


class OcupacionItem(_Base):
    """Una fila del breakdown por tipo de vehiculo (REQ-OPS-030).

    ``disponible`` puede ser negativo si ``cantidad_vehiculos_sucursal``
    no tiene fila para ``(uuid_sucursal, uuid_tipo_vehiculo)`` (KD-6);
    el cliente interpreta ``disponible < 0`` como "configuracion
    faltante, contacte al admin" y renderiza "N/A" en el strip.
    """

    uuid_tipo_vehiculo: uuid_lib.UUID
    tipo: str  # "Auto", "Moto", etc.
    cupo_maximo: int  # 0 si COALESCE(NULL) -> 0 (KD-6)
    activos: int  # count(*) de la MV materializada
    disponible: int  # cupo_maximo - activos (derivado server-side)


class OcupacionResponse(_Base):
    """Response shape de ``GET /operacion/ocupacion`` (REQ-OPS-030).

    ``generado_en`` se construye en el handler con
    ``datetime.now(tz=timezone.utc)``; Pydantic serializa como
    ISO-8601 con sufijo ``Z``. El timestamp captura cuando se
    ensamblo la respuesta (no cuando se refresco la MV).
    """

    uuid_sucursal: uuid_lib.UUID
    items: list[OcupacionItem]
    generado_en: datetime


__all__ = [
    "CotizarFacturacion",
    "CotizarMensualidad",
    "CotizarResponse",
    "IngresoCreate",
    "IngresoFilter",
    "IngresoRead",
    "IngresoReadList",
    "OcupacionItem",
    "OcupacionResponse",
]
