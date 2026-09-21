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
    """``cobrar=false`` variant -- short-circuit for a monthly-subscription scenario.

    Returned when the ingreso's plate has an open subscription at the
    branch (REQ-OPS-023, design.md §3 step 2). The PL/pgSQL function
    short-circuits the pricing pipeline; no fiscal data is computed.

    Two ``motivo`` literals cover the CU-03M / DEC-SUC-21 second-vehicle
    rule (plan.md:64, ``prod.calcular_cotizacion`` Step 2):

      - ``'mensualidad_vigente'`` -- first plate of the subscription in
        patio; exits free (REQ-OPS-023 baseline).
      - ``'segunda_placa_misa_mensualidad'`` -- a different plate of the
        same ``subscripciones_cliente.uuid`` is already inside the patio;
        the salida handler (HU-F1.7 / HU-F7.2) MUST apply rotation
        pricing at cobro time (DEC-SUC-21 "detección de otra placa de
        la misma mensualidad ya en el patio"). The derivation lives in
        the quotation response only; nothing is persisted on
        ``prod.ingreso``.

    ``motivo`` is a closed literal so the contract is exhaustive --
    adding a new motivo requires a new ``Literal`` member, not
    free-form string injection.
    """

    model_config = ConfigDict(extra="forbid")

    cobrar: Literal[False]
    motivo: Literal["mensualidad_vigente", "segunda_placa_misma_mensualidad"]


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


# ---------------------------------------------------------------------------
# HU-F1.6 -- IngresoCreateForzado / IngresoReadForzado (REQ-OPS-034..041)
# ---------------------------------------------------------------------------


class IngresoCreateForzado(_Base):
    """INSERT payload for ``prod.ingreso`` with KD-FORZADO-01 bypass.

    Adds ``forzado: bool = False`` to the F1.5 ``IngresoCreate`` shape.
    Server-side validation enforces the prefix contract (D-HU-F1.6-5);
    ``forzado`` is NOT persisted in ``prod.ingreso``.

    ``extra='forbid'`` (inherited from ``_Base``) rejects extra fields
    including ``tipo_entrada`` (an attempted injection of a non-existent
    column).
    """

    # uuid_sucursal defaults to ctx.sucursal_uuid in the handler
    # (KD-3 chain); the field is Optional here.
    uuid_sucursal: uuid_lib.UUID | None = None
    placa: str | None = None
    # Server overwrites via V5 (regex-derived UUID wins over client value).
    uuid_tipo_vehiculo: uuid_lib.UUID | None = None
    uuid_subscripcion_cliente: uuid_lib.UUID | None = None
    fecha_ingreso: datetime | None = None
    observaciones: str | None = None
    forzado: bool = False  # D-HU-F1.6-5; validated against prefix


class IngresoReadForzado(_Base):
    """Response shape for ``POST /operacion/ingresos`` (REQ-OPS-041).

    Additive delta to ``IngresoRead`` (no field removed or renamed):
    - ``tipo_entrada``: Literal['MENSUALIDAD', 'ROTACION'] (DEC-SUC-21)
    - ``forzado_en_creacion``: True iff KD-FORZADO-01 bypass was used
    - ``motivo_forzado``: stripped motivo, or None
    """

    # Inherited from IngresoRead (6 base + 6 business columns):
    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    uuid_sucursal: uuid_lib.UUID | None
    placa: str | None
    uuid_tipo_vehiculo: uuid_lib.UUID | None
    uuid_subscripcion_cliente: uuid_lib.UUID | None
    fecha_ingreso: datetime | None
    observaciones: str | None
    # NEW:
    tipo_entrada: Literal["MENSUALIDAD", "ROTACION"]
    forzado_en_creacion: bool = False
    motivo_forzado: str | None = None


# --- Typed error schemas (D-HU-F1.6-10) ----------------------------------


class CupoNoConfiguradoError(_Base):
    """V1 422 discriminator."""

    error: Literal["cupo_no_configurado"]
    forzado_permitido: Literal[True]


class MotivoForzadoRequeridoError(_Base):
    """V2 422 discriminator (when cupo agotado without forzado)."""

    error: Literal["motivo_forzado_requerido"]
    cupo_maximo: int
    activos: int


class TarifaVigenteNoEncontradaError(_Base):
    """V3 422 discriminator."""

    error: Literal["tarifa_vigente_no_encontrada"]


class PlacaFormatoInvalidoError(_Base):
    """V5 422 discriminator."""

    error: Literal["placa_formato_invalido"]
    formatos_aceptados: list[str]


class SubscripcionInactivaOVencidaError(_Base):
    """V6 422 discriminator."""

    error: Literal["subscripcion_inactiva_o_vencida"]


class IngresoActivoExistenteError(_Base):
    """V8 409 discriminator."""

    error: Literal["ingreso_activo_existente"]
    uuid_ingreso_existente: uuid_lib.UUID


class TipoVehiculoInvalidoError(_Base):
    """V4 422 discriminator."""

    error: Literal["tipo_vehiculo_invalido"]


# ---------------------------------------------------------------------------
# HU-F1.7 -- SalidaCreateForzado / SalidaReadForzado / 4 typed errors
#            (REQ-OPS-042..052, D-HU-F1.7-19, D-HU-F1.7-20)
# ---------------------------------------------------------------------------


class SalidaCreateForzado(_Base):
    """INSERT payload for ``prod.salidas`` ([A] append-only event, HU-F1.7).

    Identifies the ingreso to close. Sucursal is resolved server-side from
    the ingreso (NEW in F1.7 -- client does not send). Placa is optional:
    if sent, server confirms against ingreso (V3); otherwise server trusts
    ``uuid_ingreso``.

    ``extra='forbid'`` (inherited from ``_Base``) rejects extra fields,
    including attempts to inject ``tipo_salida`` (DEC-SUC-21-NEW).
    """

    uuid_ingreso: uuid_lib.UUID         # REQUIRED -- ingreso to close
    placa: str | None = None            # OPTIONAL -- V3 confirmation
    observaciones: str | None = None    # OPTIONAL -- KD-FORZADO-01 prefix
    forzado: bool = False               # OPTIONAL -- bypass V2/V5


class SalidaRead(_Base):
    """Full ORM column mapping for ``prod.salidas``.

    Inherits ``from_attributes=True`` and ``extra='forbid'`` from
    :class:`_Base`. Used as the base class for :class:`SalidaReadForzado`.
    """

    # Inherited from LifecycleEventBase (IdMixin + AuditMixin + SyncMixin)
    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None

    # Business columns (from models/A/salidas.py)
    uuid_sucursal: uuid_lib.UUID | None
    uuid_ingreso: uuid_lib.UUID | None
    fecha_salida: datetime | None


class SalidaReadForzado(_Base):
    """Response shape for ``POST /operacion/salidas`` (HU-F1.7).

    Additive delta to ``SalidaRead`` (no field removed or renamed):
    - ``tipo_salida``: Literal['MENSUALIDAD', 'ROTACION'] (DEC-SUC-21-NEW)
    - ``forzado_en_creacion``: True iff KD-FORZADO-01 bypass was used
    - ``motivo_forzado``: stripped motivo, or None
    - ``cotizacion_snapshot``: CotizarFacturacion if ROTACION, None if MENSUALIDAD
    """

    # Inherited from AppendOnlyBase (IdMixin + AuditMixin + SyncMixin) on
    # models/A/salidas.py::Salidas. Composite PK (uuid, fecha_retencion_hasta)
    # is mapped at the ORM; the schema only carries the uuid business key.
    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None

    # Business columns (from models/A/salidas.py)
    uuid_sucursal: uuid_lib.UUID | None
    uuid_ingreso: uuid_lib.UUID | None
    fecha_salida: datetime | None

    # NEW (F1.7):
    tipo_salida: Literal["MENSUALIDAD", "ROTACION"]
    forzado_en_creacion: bool = False
    motivo_forzado: str | None = None
    cotizacion_snapshot: CotizarFacturacion | None = None


# --- Typed error schemas (D-HU-F1.7-19) ----------------------------------


class IngresoNoEncontradoError(_Base):
    """V1 404 discriminator -- uuid_ingreso no existe, ya cerrado, o anulado."""

    error: Literal["ingreso_no_encontrado"]
    uuid_ingreso: uuid_lib.UUID


class SalidaDuplicadaError(_Base):
    """Step 8 409 discriminator -- partial unique index violated."""

    error: Literal["salida_duplicada"]
    uuid_ingreso: uuid_lib.UUID


class PlacaNoCoincideConIngresoError(_Base):
    """V3 422 discriminator -- optional placa mismatch."""

    error: Literal["placa_no_coincide_con_ingreso"]
    placa_request: str
    placa_ingreso: str


class TarifaVigenteNoEncontradaSalidaError(_Base):
    """V5 422 discriminator -- when not bypassed."""

    error: Literal["tarifa_vigente_no_encontrada"]


# ---------------------------------------------------------------------------
# HU-F12.1 -- MiTurnoRead (REQ-OPS-184)
# ---------------------------------------------------------------------------


class MiTurnoRead(_Base):
    """Per-turn aggregate response for ``GET /operacion/mi-turno``.

    Seven-field wire shape (REQ-OPS-184):

        uuid_sesion                   UUID
        uuid_sucursal                 UUID
        timestamp_calculo             datetime
        ingresos_count                int      (default 0)
        salidas_count                 int      (default 0)
        total_cobrado_efectivo_cop    Decimal  (default 0)
        total_cobrado_datafono_cop    Decimal  (default 0)

    All count/decimal fields default to ``0`` so a zero-state session
    parses into a well-formed response (REQ-OPS-184 S2 — backend always
    returns 200 with zeros, NEVER 404). ``extra='forbid'`` (inherited
    from :class:`_Base`) rejects hypothetical 8th-field drift — see
    :class:`test_mi_turno_schema.py` for the static key-set lock that
    mirrors the FE Zod schema (``apps/electron-sucursal/src/lib/api/
    schemas/mi-turno.ts``, DA-F12.1-1 / DA-F12.1-9 GATING).
    """

    uuid_sesion: uuid_lib.UUID
    uuid_sucursal: uuid_lib.UUID
    timestamp_calculo: datetime
    ingresos_count: int = 0
    salidas_count: int = 0
    total_cobrado_efectivo_cop: Decimal = Decimal(0)
    total_cobrado_datafono_cop: Decimal = Decimal(0)


__all__ = [
    "CotizarFacturacion",
    "CotizarMensualidad",
    "CotizarResponse",
    "CupoNoConfiguradoError",
    "IngresoActivoExistenteError",
    "IngresoCreate",
    "IngresoCreateForzado",
    "IngresoFilter",
    "IngresoNoEncontradoError",
    "IngresoRead",
    "IngresoReadForzado",
    "IngresoReadList",
    "MiTurnoRead",
    "MotivoForzadoRequeridoError",
    "OcupacionItem",
    "OcupacionResponse",
    "PlacaFormatoInvalidoError",
    "PlacaNoCoincideConIngresoError",
    "SalidaCreateForzado",
    "SalidaDuplicadaError",
    "SalidaRead",
    "SalidaReadForzado",
    "SubscripcionInactivaOVencidaError",
    "TarifaVigenteNoEncontradaError",
    "TarifaVigenteNoEncontradaSalidaError",
    "TipoVehiculoInvalidoError",
]
