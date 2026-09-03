"""Pydantic v2 schemas for the Workflows domain (PR6, T-PR6-08).

Covers 4 branch-originated ``[L-W]`` workflow tables + 2 cloud-only
``[L-W]`` tables (``envio_dian`` + ``validacion_evento``) in ``prod``:

- :class:`ReimpresionTicket` — branch ticket-reprint chain tip
- :class:`Anulaciones` — branch annulment of ingreso/salida (polymorphic FK)
- :class:`Reclamos` — branch claim against ingreso/salida/factura
  (polymorphic FK, REQ-23-W-POLYMORPHIC-FK, REQ-OP-08)
- :class:`Alerta` — branch cash-count anomaly (admin-only ``descartada``,
  REQ-26-W-ALERTA-DESCARTADA)
- :class:`EnvioDian` — cloud DIAN send/ack chain (CLOUD-ONLY,
  REQ-25-W-CLOUD-ONLY)
- :class:`ValidacionEvento` — cloud admin validation chain (CLOUD-ONLY,
  REQ-25)

Special validators (defense in depth):

- ``ReclamoCreate.tipo_reclamable`` MUST be
  ``Literal["ingreso", "salida", "factura"]``. Pydantic v2 enforces
  the closed enum at the API edge; full DB existence check on
  ``uuid_reclamable`` lives in ``repo.workflow.polymorphic_row_exists``
  (T-PR6-04) and is invoked from ``api/v1/workflows.py`` (T-PR6-10).
  This validator is the **fast-fail** layer (returns ``422`` before
  any DB hit for unknown discriminator values).
- ``AlertaCreate`` accepts any ``estado`` (defaults to ``"activa"``);
  the **admin-only reject** rule on ``estado='descartada'`` is enforced
  at the endpoint layer (``api/v1/workflows.py``) where the actor's
  ``uuid`` is available from the JWT context. This Pydantic layer only
  enforces shape.

All schemas inherit :class:`_Base` (``extra='forbid'``,
``from_attributes=True``). Versioning columns (``vigente_desde``,
``vigente_hasta``, ``estado``) are server-set by
``repo.workflow.append_transition`` and excluded from ``Create`` /
``Update`` per design §6.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import StringConstraints

from .common import FilterBase, ReadListBase, _Base

# ---------------------------------------------------------------------------
# ReimpresionTicket ([L-W] — branch-originated)
# ---------------------------------------------------------------------------


class ReimpresionTicketRead(_Base):
    """Read-back for ``prod.reimpresion_ticket``.

    Single-PK (``uuid`` only). The chain tip is walked by
    ``repo.workflow.read_chain_tip(uuid_ingreso)`` via the
    ``uuid_reimpresion_padre`` self-FK.
    """

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    uuid_sucursal: uuid_lib.UUID | None
    uuid_ingreso: uuid_lib.UUID | None
    uuid_usuario: uuid_lib.UUID | None
    uuid_costo_servicio: uuid_lib.UUID | None
    costo_aplicado: Decimal | None
    uuid_factura: uuid_lib.UUID | None
    motivo: str | None
    uuid_reimpresion_padre: uuid_lib.UUID | None
    timestamp_evento: datetime | None
    vigente_desde: datetime | None
    vigente_hasta: datetime | None
    estado: str | None  # 'activo' | 'inactivo'


class ReimpresionTicketCreate(_Base):
    """INSERT payload for ``prod.reimpresion_ticket``.

    Versioning columns (``vigente_desde``, ``vigente_hasta``, ``estado``)
    are server-set by ``repo.workflow.append_transition`` — excluded
    here per design §6.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_ingreso: uuid_lib.UUID | None = None
    uuid_usuario: uuid_lib.UUID | None = None
    uuid_costo_servicio: uuid_lib.UUID | None = None
    costo_aplicado: Decimal | None = None
    uuid_factura: uuid_lib.UUID | None = None
    motivo: Annotated[str, StringConstraints(max_length=1000)] | None = None
    uuid_reimpresion_padre: uuid_lib.UUID | None = None
    timestamp_evento: datetime | None = None


class ReimpresionTicketUpdate(_Base):
    """[L-W] UPDATE payload — close+insert via ``append_transition``.

    All business fields optional; the chain identity
    (``uuid_reimpresion_padre``) is preserved across updates.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_ingreso: uuid_lib.UUID | None = None
    uuid_usuario: uuid_lib.UUID | None = None
    uuid_costo_servicio: uuid_lib.UUID | None = None
    costo_aplicado: Decimal | None = None
    uuid_factura: uuid_lib.UUID | None = None
    motivo: Annotated[str, StringConstraints(max_length=1000)] | None = None
    uuid_reimpresion_padre: uuid_lib.UUID | None = None
    timestamp_evento: datetime | None = None


class ReimpresionTicketFilter(FilterBase):
    """Query filter for ``prod.reimpresion_ticket``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_ingreso: uuid_lib.UUID | None = None
    uuid_usuario: uuid_lib.UUID | None = None
    uuid_factura: uuid_lib.UUID | None = None
    estado: str | None = None
    timestamp_evento__gte: datetime | None = None
    timestamp_evento__lte: datetime | None = None


class ReimpresionTicketReadList(ReadListBase[ReimpresionTicketRead]):
    """Cursor-paginated list of :class:`ReimpresionTicketRead` items."""


# ---------------------------------------------------------------------------
# Anulaciones ([L-W] — branch-originated, polymorphic FK)
# ---------------------------------------------------------------------------


class AnulacionesRead(_Base):
    """Read-back for ``prod.anulaciones`` (composite PK; monthly partitioned).

    The polymorphic pointer ``tipo_anulable`` (``ingreso`` | ``salida``)
    + ``uuid_ingreso``/``uuid_salida`` is the source of the
    ``V_INGRESO_ESTADO`` derivation — an annulment writes a new row
    here and the view joins to surface ``anulada``. NO physical DELETE
    is permitted (REQ-04, AGENTS.md §2).
    """

    uuid: uuid_lib.UUID
    fecha_retencion_hasta: date
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    uuid_sucursal: uuid_lib.UUID | None
    tipo_anulable: str | None  # 'ingreso' | 'salida'
    uuid_ingreso: uuid_lib.UUID | None
    uuid_salida: uuid_lib.UUID | None
    uuid_usuario: uuid_lib.UUID | None
    motivo: str | None
    uuid_anulacion_padre: uuid_lib.UUID | None
    timestamp_evento: datetime | None
    vigente_desde: datetime | None
    vigente_hasta: datetime | None
    estado: str | None


class AnulacionesCreate(_Base):
    """INSERT payload for ``prod.anulaciones``.

    ``tipo_anulable`` is REQUIRED — it is the polymorphic FK
    discriminator that selects which of ``uuid_ingreso`` /
    ``uuid_salida`` is validated by the endpoint layer.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    tipo_anulable: Literal["ingreso", "salida"]
    uuid_ingreso: uuid_lib.UUID | None = None
    uuid_salida: uuid_lib.UUID | None = None
    uuid_usuario: uuid_lib.UUID | None = None
    motivo: str | None = None
    uuid_anulacion_padre: uuid_lib.UUID | None = None
    timestamp_evento: datetime | None = None


class AnulacionesUpdate(_Base):
    """[L-W] UPDATE payload — close+insert via ``append_transition``.

    The polymorphic discriminator stays optional on Update — it is
    inherited from the previous version and rarely changes.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    tipo_anulable: Literal["ingreso", "salida"] | None = None
    uuid_ingreso: uuid_lib.UUID | None = None
    uuid_salida: uuid_lib.UUID | None = None
    uuid_usuario: uuid_lib.UUID | None = None
    motivo: str | None = None
    uuid_anulacion_padre: uuid_lib.UUID | None = None
    timestamp_evento: datetime | None = None


class AnulacionesFilter(FilterBase):
    """Query filter for ``prod.anulaciones``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    tipo_anulable: str | None = None
    uuid_ingreso: uuid_lib.UUID | None = None
    uuid_salida: uuid_lib.UUID | None = None
    uuid_usuario: uuid_lib.UUID | None = None
    estado: str | None = None


class AnulacionesReadList(ReadListBase[AnulacionesRead]):
    """Cursor-paginated list of :class:`AnulacionesRead` items."""


# ---------------------------------------------------------------------------
# Reclamos ([L-W] — branch-originated, polymorphic FK)
# ---------------------------------------------------------------------------


class ReclamosRead(_Base):
    """Read-back for ``prod.reclamos``.

    Single-PK (``uuid`` only). The chain tip walks
    ``uuid_reclamo_padre`` self-FK. ``tipo_reclamable`` discriminates
    which table ``uuid_reclamable`` belongs to (``ingreso``,
    ``salida``, or ``factura``) — REQ-23-W-POLYMORPHIC-FK.
    """

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    uuid_sucursal: uuid_lib.UUID | None
    tipo_reclamable: str | None  # 'ingreso' | 'salida' | 'factura'
    uuid_reclamable: uuid_lib.UUID | None
    motivo: str | None
    uuid_reclamo_padre: uuid_lib.UUID | None
    timestamp_evento: datetime | None
    vigente_desde: datetime | None
    vigente_hasta: datetime | None
    estado: str | None


class ReclamosCreate(_Base):
    """REQ-OP-08 / REQ-23-W-POLYMORPHIC-FK.

    The polymorphic FK is enforced at TWO layers:

    1. **Pydantic (this layer)** — ``tipo_reclamable`` MUST be one of
       the 3 known types (``Literal["ingreso", "salida", "factura"]``);
       ``uuid_reclamable`` MUST be a valid UUID (Pydantic v2
       auto-coerces strings). Unknown discriminator values return
       ``422`` BEFORE any DB hit.
    2. **Endpoint layer** — the actual DB existence check via
       ``repo.workflow.polymorphic_row_exists`` (T-PR6-04). PR6 ships
       this validator as the fast-fail layer; full DB check is in
       ``api/v1/workflows.py`` (T-PR6-10).
    """

    tipo_reclamable: Literal["ingreso", "salida", "factura"]
    uuid_reclamable: uuid_lib.UUID
    uuid_sucursal: uuid_lib.UUID | None = None
    motivo: Annotated[str, StringConstraints(max_length=1000)] | None = None
    uuid_reclamo_padre: uuid_lib.UUID | None = None
    timestamp_evento: datetime | None = None


# Alias matching the singular task naming used in T-PR6-08 verification.
ReclamoCreate = ReclamosCreate


class ReclamosUpdate(_Base):
    """[L-W] UPDATE payload — close+insert via ``append_transition``.

    The polymorphic FK (``tipo_reclamable`` + ``uuid_reclamable``) is
    inherited from the previous version and stays optional on Update.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    tipo_reclamable: Literal["ingreso", "salida", "factura"] | None = None
    uuid_reclamable: uuid_lib.UUID | None = None
    motivo: Annotated[str, StringConstraints(max_length=1000)] | None = None
    uuid_reclamo_padre: uuid_lib.UUID | None = None
    timestamp_evento: datetime | None = None


class ReclamosFilter(FilterBase):
    """Query filter for ``prod.reclamos``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    tipo_reclamable: str | None = None
    uuid_reclamable: uuid_lib.UUID | None = None
    estado: str | None = None
    timestamp_evento__gte: datetime | None = None
    timestamp_evento__lte: datetime | None = None


class ReclamosReadList(ReadListBase[ReclamosRead]):
    """Cursor-paginated list of :class:`ReclamosRead` items."""


# ---------------------------------------------------------------------------
# Alerta ([L-W] — branch-originated, REQ-26 admin-only descartada)
# ---------------------------------------------------------------------------


class AlertaRead(_Base):
    """Read-back for ``prod.alerta`` (composite PK; monthly partitioned).

    ``estado`` values: ``activa`` | ``descartada`` | ``resuelta``.
    Transitioning to ``descartada`` requires an admin actor (REQ-26)
    — enforced at the endpoint layer.
    """

    uuid: uuid_lib.UUID
    fecha_retencion_hasta: date
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    uuid_sucursal: uuid_lib.UUID | None
    uuid_usuario: uuid_lib.UUID | None
    uuid_arqueo: uuid_lib.UUID | None
    tipo_alerta: str | None
    valor_diferencia_efectivo: Decimal | None
    valor_diferencia_datafono: Decimal | None
    uuid_alerta_padre: uuid_lib.UUID | None
    timestamp_evento: datetime | None
    vigente_desde: datetime | None
    vigente_hasta: datetime | None
    estado: str | None


class AlertaCreate(_Base):
    """REQ-26-W-ALERTA-DESCARTADA.

    When ``estado='descartada'``, the alert's *user*
    (``uuid_usuario``) MUST NOT be the writer. Enforced at the endpoint
    layer — the endpoint checks
    ``ctx.actor_uuid != payload.uuid_usuario`` when ``estado='descartada'``
    and raises ``HTTPException(403)``.

    This validator only enforces shape; the policy lives at the API edge
    (T-PR6-10) where the JWT context is available.
    """

    uuid_sucursal: uuid_lib.UUID
    uuid_usuario: uuid_lib.UUID
    uuid_arqueo: uuid_lib.UUID | None = None
    tipo_alerta: Annotated[str, StringConstraints(max_length=64)]
    valor_diferencia_efectivo: Decimal | None = None
    valor_diferencia_datafono: Decimal | None = None
    uuid_alerta_padre: uuid_lib.UUID | None = None
    timestamp_evento: datetime | None = None
    estado: Literal["activa", "descartada", "resuelta"] = "activa"


class AlertaUpdate(_Base):
    """[L-W] UPDATE payload — close+insert via ``append_transition``.

    Endpoint layer enforces the admin-only ``descartada`` rule on Update
    paths too (REQ-26).
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_usuario: uuid_lib.UUID | None = None
    uuid_arqueo: uuid_lib.UUID | None = None
    tipo_alerta: Annotated[str, StringConstraints(max_length=64)] | None = None
    valor_diferencia_efectivo: Decimal | None = None
    valor_diferencia_datafono: Decimal | None = None
    uuid_alerta_padre: uuid_lib.UUID | None = None
    timestamp_evento: datetime | None = None
    estado: Literal["activa", "descartada", "resuelta"] | None = None


class AlertaFilter(FilterBase):
    """Query filter for ``prod.alerta``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_usuario: uuid_lib.UUID | None = None
    uuid_arqueo: uuid_lib.UUID | None = None
    tipo_alerta: str | None = None
    estado: str | None = None
    timestamp_evento__gte: datetime | None = None
    timestamp_evento__lte: datetime | None = None


class AlertaReadList(ReadListBase[AlertaRead]):
    """Cursor-paginated list of :class:`AlertaRead` items."""


# ---------------------------------------------------------------------------
# EnvioDian ([L-W] — CLOUD-ONLY, REQ-25-W-CLOUD-ONLY)
# ---------------------------------------------------------------------------


class EnvioDianRead(_Base):
    """Read-back for ``prod.envio_dian`` (cloud-only)."""

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    uuid_sucursal: uuid_lib.UUID | None
    uuid_factura_electronica: uuid_lib.UUID | None
    uuid_resolucion_facturacion: uuid_lib.UUID | None
    payload: dict | None  # JSONB
    respuesta_proveedor: dict | None  # JSONB
    cufe: str | None
    uuid_envio_padre: uuid_lib.UUID | None
    timestamp_evento: datetime | None
    vigente_desde: datetime | None
    vigente_hasta: datetime | None
    estado: str | None


class EnvioDianCreate(_Base):
    """INSERT payload for ``prod.envio_dian`` (cloud-only)."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura_electronica: uuid_lib.UUID | None = None
    uuid_resolucion_facturacion: uuid_lib.UUID | None = None
    payload: dict | None = None
    respuesta_proveedor: dict | None = None
    cufe: Annotated[str, StringConstraints(max_length=255)] | None = None
    uuid_envio_padre: uuid_lib.UUID | None = None
    timestamp_evento: datetime | None = None


class EnvioDianUpdate(_Base):
    """[L-W] UPDATE payload (close+insert via ``append_transition``, cloud-only)."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura_electronica: uuid_lib.UUID | None = None
    uuid_resolucion_facturacion: uuid_lib.UUID | None = None
    payload: dict | None = None
    respuesta_proveedor: dict | None = None
    cufe: Annotated[str, StringConstraints(max_length=255)] | None = None
    uuid_envio_padre: uuid_lib.UUID | None = None
    timestamp_evento: datetime | None = None


class EnvioDianFilter(FilterBase):
    """Query filter for ``prod.envio_dian``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura_electronica: uuid_lib.UUID | None = None
    uuid_resolucion_facturacion: uuid_lib.UUID | None = None
    cufe: str | None = None
    estado: str | None = None
    timestamp_evento__gte: datetime | None = None
    timestamp_evento__lte: datetime | None = None


class EnvioDianReadList(ReadListBase[EnvioDianRead]):
    """Cursor-paginated list of :class:`EnvioDianRead` items."""


# ---------------------------------------------------------------------------
# ValidacionEvento ([L-W] — CLOUD-ONLY, REQ-25)
# ---------------------------------------------------------------------------


class ValidacionEventoRead(_Base):
    """Read-back for ``prod.validacion_evento`` (cloud-only).

    ``hash_evento`` is ``CHAR(64)`` — the SHA-256 hex digest of the
    validated event payload (admin auditor tampering detection).
    """

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    uuid_sucursal: uuid_lib.UUID | None
    uuid_usuario: uuid_lib.UUID | None
    tabla_origen: str | None
    uuid_registro: uuid_lib.UUID | None
    hash_evento: str | None  # CHAR(64) hex digest
    observaciones: str | None
    uuid_validacion_padre: uuid_lib.UUID | None
    timestamp_evento: datetime | None
    vigente_desde: datetime | None
    vigente_hasta: datetime | None
    estado: str | None


class ValidacionEventoCreate(_Base):
    """INSERT payload for ``prod.validacion_evento`` (cloud-only).

    ``hash_evento`` constrained to exactly 64 chars (SHA-256 hex).
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_usuario: uuid_lib.UUID | None = None
    tabla_origen: Annotated[str, StringConstraints(max_length=128)] | None = None
    uuid_registro: uuid_lib.UUID | None = None
    hash_evento: Annotated[str, StringConstraints(min_length=64, max_length=64)] | None = None
    observaciones: str | None = None
    uuid_validacion_padre: uuid_lib.UUID | None = None
    timestamp_evento: datetime | None = None


class ValidacionEventoUpdate(_Base):
    """[L-W] UPDATE payload (close+insert via ``append_transition``, cloud-only)."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_usuario: uuid_lib.UUID | None = None
    tabla_origen: Annotated[str, StringConstraints(max_length=128)] | None = None
    uuid_registro: uuid_lib.UUID | None = None
    hash_evento: Annotated[str, StringConstraints(min_length=64, max_length=64)] | None = None
    observaciones: str | None = None
    uuid_validacion_padre: uuid_lib.UUID | None = None
    timestamp_evento: datetime | None = None


class ValidacionEventoFilter(FilterBase):
    """Query filter for ``prod.validacion_evento``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_usuario: uuid_lib.UUID | None = None
    tabla_origen: str | None = None
    uuid_registro: uuid_lib.UUID | None = None
    estado: str | None = None
    timestamp_evento__gte: datetime | None = None
    timestamp_evento__lte: datetime | None = None


class ValidacionEventoReadList(ReadListBase[ValidacionEventoRead]):
    """Cursor-paginated list of :class:`ValidacionEventoRead` items."""


__all__ = [
    "AlertaCreate",
    "AlertaFilter",
    "AlertaRead",
    "AlertaReadList",
    "AlertaUpdate",
    "AnulacionesCreate",
    "AnulacionesFilter",
    "AnulacionesRead",
    "AnulacionesReadList",
    "AnulacionesUpdate",
    "EnvioDianCreate",
    "EnvioDianFilter",
    "EnvioDianRead",
    "EnvioDianReadList",
    "EnvioDianUpdate",
    "ReclamoCreate",
    "ReclamosCreate",
    "ReclamosFilter",
    "ReclamosRead",
    "ReclamosReadList",
    "ReclamosUpdate",
    "ReimpresionTicketCreate",
    "ReimpresionTicketFilter",
    "ReimpresionTicketRead",
    "ReimpresionTicketReadList",
    "ReimpresionTicketUpdate",
    "ValidacionEventoCreate",
    "ValidacionEventoFilter",
    "ValidacionEventoRead",
    "ValidacionEventoReadList",
    "ValidacionEventoUpdate",
]