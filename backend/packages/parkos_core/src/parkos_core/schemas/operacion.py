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

import math
import uuid as uuid_lib
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

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
    # REQ-OPS-192 / REQ-OPS-197: parking-lot identifier for ingresos sin
    # placa (bicicleta, patineta). Format ``<TIPO>-NNNNNN-<uuid8>`` -- NULL
    # for legacy carro/moto rows (backward compat, REQ-OPS-192 scenario 1).
    consecutivo: str | None = None


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
    # REQ-OPS-192/197: server-side computed (no client input); max 30
    # chars matches ``prod.ingreso.consecutivo`` column width (migration
    # 0044). Format ``<TIPO>-NNNNNN-<uuid8>``.
    consecutivo: str | None = Field(default=None, max_length=30)
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
    has a vigente ``tarifas_sucursal`` row for the combination, and has
    a vigente ``impuestos`` row with ``nombre='IVA'``.

    Three reachable caller paths feed this variant:

      a) **No subscription at all** (parking-lot walk-in) — the function
         short-circuits the ``subscripcion`` branch and runs Steps 3-5
         directly. ``motivo`` is ``None``.
      b) **1st plate of a subscription in patio** — covered by
         :class:`CotizarMensualidad` (separate variant, REQ-OPS-023).
      c) **2nd (or later) plate of the same ``subscripciones_cliente``
         already in patio** (CU-03M / DEC-SUC-21, plan.md:64,
         plan.md:436) — the function falls through to Steps 3-5 with a
         ``v_motivo := 'segunda_placa_misma_mensualidad'`` flag. The full
         fiscal breakdown IS returned; ``motivo`` carries the
         informational literal so the handler / auditor can trace the
         2nd-plate provenance. The salida handler (``api/v1/
         operacion.py::create_salida``) derives
         ``tipo_salida='ROTACION'`` from ``cobrar=True`` and exposes
         the snapshot via ``SalidaReadForzado.cotizacion_snapshot``.

    All seven GAP-BE-09 contract fields are REQUIRED (no defaults) --
    the contract is exhaustive; missing any field is a server bug.
    ``motivo`` is OPTIONAL (``None`` for paths (a) and (b); the literal
    ``'segunda_placa_misma_mensualidad'`` for path (c)).

    **``tiempo_minutos`` shape (apply-time fix, 2026-09-23).** The PL/pgSQL
    function computes ``EXTRACT(EPOCH FROM (NOW() - fecha_ingreso)) / 60.0``
    which returns a sub-second-precision ``numeric`` (e.g. ``0.109581``
    for a row ingested 6.5 seconds ago). Postgres serializes it as a
    Python ``float`` via the asyncpg jsonb bridge.

    **Before this fix (pre-2026-09-23):** the schema declared
    ``tiempo_minutos: int | float`` and clients received sub-second
    precision. The operator's directive (2026-09-23): "no salga decimales
    si no que lo aproxime al siguiente numero" — no decimals, round UP to
    the next integer (CEIL semantics). The apply phase now coerces
    ``tiempo_minutos`` to ``int`` via ``field_validator(mode='before')``:
    a 6.5-second estancia → ``1`` minute, a 89-minute → ``89``,
    a 89.0025-minute → ``90`` (rounded UP — billing-wise the operator
    is charging for the full minute they spent in the patio).

    **Decimal coercion (2026-09-23).** The PL/pgSQL function emits
    monetary values as strings (e.g. ``"81.0"`` for ``subtotal``,
    ``"19.0"`` for ``iva``, ``"100.0"`` for ``total``). The schema
    declared them as ``Decimal`` since the apply phase (pre-2026-09-23)
    which caused a runtime ``ValidationError`` blocking
    ``POST /facturacion/factura``. The ``model_validator(mode='before')``
    coerces string → ``Decimal`` before field validation runs.
    """

    model_config = ConfigDict(extra="forbid")

    cobrar: Literal[True]
    subtotal: Decimal
    iva: Decimal
    total: Decimal
    tiempo_minutos: int
    tarifa_uuid: uuid_lib.UUID
    vigente_hasta: datetime
    motivo: Literal["segunda_placa_misma_mensualidad"] | None = None

    @field_validator("tiempo_minutos", mode="before")
    @classmethod
    def _ceil_tiempo_minutos(cls, v: Any) -> int:
        """Coerce the float/string wire value to a CEIL'd integer.

        PL/pgSQL emits sub-second precision (e.g. ``0.109581`` for 6.5 s).
        Per operator directive (2026-09-23): "no salga decimales, que lo
        aproxime al siguiente numero" → CEIL to the next integer.

        Examples:
        - 0.109581 → 1 (sub-minute → 1 minute)
        - 89.0 → 89
        - 89.0025 → 90 (operator was charged 89, pays 90)
        - 1 → 1 (no change for whole minutes)

        Negative values are not expected (CotizarFacturacion represents a
        post-cotizar positive time delta). If a future PL/pgSQL change
        emits a negative value, we clamp to 0 — no cobrar por tiempo
        negativo.
        """
        try:
            value_f = float(v)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"tiempo_minutos must be numeric, got {v!r}"
            ) from exc
        if value_f < 0:
            return 0
        return math.ceil(value_f)

    @model_validator(mode="before")
    @classmethod
    def _coerce_decimal_strings(cls, data: Any) -> Any:
        """Coerce string numerics → Decimal before field validation.

        The PL/pgSQL ``prod.calcular_cotizacion`` function emits
        monetary fields as strings (Postgres jsonb serializes
        ``NUMERIC`` types as strings per the jsonb encoding contract).
        The schema declared them as ``Decimal`` since pre-2026-09-23
        which caused ``ValidationError`` (5 validation errors for
        CotizarFacturacion) blocking the entire
        ``POST /facturacion/factura`` flow.

        This validator is the bridge: it accepts the wire shape
        (``"81.0"``) and coerces it to ``Decimal('81.0')`` BEFORE
        field-level validation. Numerics already in correct type pass
        through untouched.

        Idempotent + total: a Decimal passes through, a numeric float
        passes through (Decimal accepts), only string→Decimal needs
        explicit coercion.
        """
        if not isinstance(data, dict):
            return data
        for field in ("subtotal", "iva", "total"):
            raw = data.get(field)
            if isinstance(raw, str):
                try:
                    data[field] = Decimal(raw)
                except InvalidOperation as exc:
                    raise ValueError(
                        f"{field} must be a valid decimal string, got {raw!r}"
                    ) from exc
        return data


class CotizarMensualidad(_Base):
    """``cobrar=false`` variant -- free exit for a subscribed plate.

    Returned when the ingreso's plate has an active subscription and
    EITHER (a) no other plate of the same subscription is currently in
    patio (``motivo='mensualidad_vigente'``, REQ-OPS-023, baseline), OR
    (b) another plate IS in patio but the plan is a fleet/enterprise
    plan (``tipo_subscripciones.cantidad_maxima_vehiculos > 2``,
    ``motivo='multiple_vehiculos_plan_empresa'`` -- operator directive
    2026-09-24: multiple simultaneous vehicles is the EXPECTED shape
    for a fleet plan, not the personal-plan 1-free-exit rule).

    **Full fiscal breakdown, even though ``cobrar=false`` (migration
    0050, operator directive 2026-09-24).** Before this migration the
    PL/pgSQL function short-circuited BEFORE computing tarifa/tiempo/
    subtotal/iva/total, so this variant carried only ``cobrar`` +
    ``motivo``. The operator now requires the salida-mensualidad flow
    to emit a full invoice (facturas + factura_detalle + factura_
    impuestos + factura_electronica DIAN, same CU-04/CU-05 pipeline as
    rotacion) showing ALL the normal values plus a discount line equal
    to the subscription's value, netting to $0 -- which requires the
    fiscal breakdown to exist in the first place. Every field below
    (except ``cobrar``/``motivo``) is REQUIRED -- the PL/pgSQL always
    computes them now, regardless of which subscription branch fires.

    ``uuid_subscripcion_cliente`` / ``concepto_descuento`` feed the
    discount line's concept text (``concepto_descuento`` is the plan's
    commercial name, ``tipo_subscripciones.tipo``, with a
    ``'Suscripcion'`` fallback when the subscription has no
    ``uuid_tipo_subscripcion`` assigned -- a real, pre-existing data
    shape covered by several test fixtures).

    See :class:`CotizarFacturacion` for the ``tiempo_minutos`` CEIL
    coercion and the string->Decimal coercion rationale -- both
    validators are mirrored here verbatim (PL/pgSQL emits the same
    wire shapes for both discriminated-union variants).

    ``motivo`` is a closed literal so the contract is exhaustive --
    adding a new motivo requires a new ``Literal`` member, not
    free-form string injection.
    """

    model_config = ConfigDict(extra="forbid")

    cobrar: Literal[False]
    motivo: Literal["mensualidad_vigente", "multiple_vehiculos_plan_empresa"]
    subtotal: Decimal
    iva: Decimal
    total: Decimal
    tiempo_minutos: int
    tarifa_uuid: uuid_lib.UUID
    vigente_hasta: datetime
    uuid_subscripcion_cliente: uuid_lib.UUID
    concepto_descuento: str = Field(min_length=1, max_length=255)

    @field_validator("tiempo_minutos", mode="before")
    @classmethod
    def _ceil_tiempo_minutos(cls, v: Any) -> int:
        """CEIL to the next integer. See :meth:`CotizarFacturacion._ceil_tiempo_minutos`."""
        try:
            value_f = float(v)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"tiempo_minutos must be numeric, got {v!r}"
            ) from exc
        if value_f < 0:
            return 0
        return math.ceil(value_f)

    @model_validator(mode="before")
    @classmethod
    def _coerce_decimal_strings(cls, data: Any) -> Any:
        """String->Decimal coercion. See :meth:`CotizarFacturacion._coerce_decimal_strings`."""
        if not isinstance(data, dict):
            return data
        for field in ("subtotal", "iva", "total"):
            raw = data.get(field)
            if isinstance(raw, str):
                try:
                    data[field] = Decimal(raw)
                except InvalidOperation as exc:
                    raise ValueError(
                        f"{field} must be a valid decimal string, got {raw!r}"
                    ) from exc
        return data


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

    Adds ``placa_presente: bool = False`` for HU-INGRESO-SIN-PLACA (REQ-OPS-194):
    the cliente Zod discriminated-union uses this boolean as the discriminator
    (``{placa_presente: true, placa: <regex>, ...} | {placa_presente: false,
    placa: null, uuid_tipo_vehiculo: <uuid>, ...}``). The server reads
    ``placa`` directly and IGNORES ``placa_presente`` — the discriminator is
    purely client-side for type-safety. Kept as a tolerated field so the
    frontend's strict Zod schema serializes without 422
    ``extra_forbidden`` (would otherwise reject the discriminator key).

    ``extra='forbid'`` (inherited from ``_Base``) still rejects truly
    unknown fields (e.g. ``tipo_entrada`` — an attempted injection of a
    non-existent column).
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
    # REQ-OPS-194 discriminated-union discriminator (client-side only,
    # server reads `placa` and ignores this field).
    placa_presente: bool = False  # noqa: F821 — intentionally tolerated


class IngresoReadForzado(_Base):
    """Response shape for ``POST /operacion/ingresos`` (REQ-OPS-041).

    Additive delta to ``IngresoRead`` (no field removed or renamed):
    - ``tipo_entrada``: Literal['MENSUALIDAD', 'ROTACION'] (DEC-SUC-21)
    - ``forzado_en_creacion``: True iff KD-FORZADO-01 bypass was used
    - ``motivo_forzado``: stripped motivo, or None
    """

    # Inherited from IngresoRead (6 base + 7 business columns):
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
    # REQ-OPS-192/197: format ``<TIPO>-NNNNNN-<uuid8>`` (max 30 chars,
    # matches ``prod.ingreso.consecutivo`` column width per migration
    # 0044).
    consecutivo: str | None = Field(default=None, max_length=30)
    # NEW (F1.6):
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


class TipoVehiculoRequeridoSinPlacaError(_Base):
    """REQ-OPS-194 422 discriminator.

    Raised at the revised Step 2 of the ``create_ingreso`` chain when the
    operator POSTs ``placa=None`` AND ``uuid_tipo_vehiculo=None`` -- the
    "Sin placa" UI flow requires the operator to pick a tipo (bici /
    patineta) before submitting. Empty ``uuid_tipo_vehiculo`` in the
    no-placa path is a UI bug, not a server validation gap.
    """

    error: Literal["tipo_vehiculo_requerido_sin_placa"]


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
    - ``cotizacion_snapshot``: ``CotizarFacturacion`` when ROTACION,
      ``CotizarMensualidad`` when MENSUALIDAD (migration 0050: the
      mensualidad branch now also carries the full fiscal breakdown +
      discount concept, needed by the frontend to build the discount
      factura), ``None`` only on a V2/V5 bypass (``bypass_reason`` set
      -- the snapshot would be misleading for a forced exit).
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
    cotizacion_snapshot: CotizarFacturacion | CotizarMensualidad | None = None


class AnularSalidaNoPagadaPayload(_Base):
    """F8.1-b (HU-F8.1-anular-salida-no-pagada, 2026-09-23): request body
    for ``POST /operacion/salidas/{uuid_salida}/anular-no-pagada``.

    The handler inserts a ``prod.anulaciones`` row with
    ``tipo_anulable='salida'`` so ``V_INGRESO_ESTADO`` recalculates
    the ingreso back to ``abierto``. The ``motivo`` is mandatory
    (≥10 chars, ≤500 chars — same validator as
    ``AnulacionesCreate.motivo`` in `schemas/workflows.py`) and
    doubles as the audit-trail entry in
    ``prod.anulaciones.motivo`` so operators can grep
    auto-annulments from manual ones.

    No FK fields are accepted from the client — the handler reads
    ``uuid_sucursal`` and ``uuid_ingreso`` from the existing
    ``prod.salidas`` row (defense in depth: the operator cannot
    annul a salida that belongs to another branch).
    """

    motivo: Annotated[str, Field(min_length=10, max_length=500)]


# --- Typed error schemas (D-HU-F1.7-19) ----------------------------------


class IngresoNoEncontradoError(_Base):
    """V1 404 discriminator -- uuid_ingreso no existe, ya cerrado, o anulado."""

    error: Literal["ingreso_no_encontrado"] = "ingreso_no_encontrado"
    uuid_ingreso: uuid_lib.UUID


class SalidaDuplicadaError(_Base):
    """Step 8 409 discriminator -- partial unique index violated."""

    error: Literal["salida_duplicada"] = "salida_duplicada"
    uuid_ingreso: uuid_lib.UUID


class PlacaNoCoincideConIngresoError(_Base):
    """V3 422 discriminator -- optional placa mismatch."""

    error: Literal["placa_no_coincide_con_ingreso"] = "placa_no_coincide_con_ingreso"
    placa_request: str
    placa_ingreso: str


class TarifaVigenteNoEncontradaSalidaError(_Base):
    """V5 422 discriminator -- when not bypassed."""

    error: Literal["tarifa_vigente_no_encontrada"] = "tarifa_vigente_no_encontrada"


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
    "TipoVehiculoRequeridoSinPlacaError",
]
