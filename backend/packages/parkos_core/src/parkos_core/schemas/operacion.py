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
