"""Pydantic v2 schemas for the Caja domain (PR7, T-PR7-08).

Covers 3 tables in ``prod``:

- :class:`Caja` — ``[A]`` cash-drawer snapshot (composite PK
  ``uuid + fecha_retencion_hasta``, monthly ``pg_partman`` partition).
- :class:`Arqueo` — ``[A]`` cash-count event (composite PK
  ``uuid + fecha_retencion_hasta``, monthly ``pg_partman`` partition).
- :class:`Sesion` — ``[L-S]`` cash session, NO versioning columns.
  Open on shift start, close on shift end. Writes MUST go through
  ``repo.session_cycle.open_session`` / ``close_session_with_log``
  (REQ-40, REQ-41); the ``ls_session_guard`` trigger blocks any UPDATE
  without a co-transactional ``log_transaccional`` row (SC-40, SC-42).

Append-only at write time (design §4.5, §4.7): every table here is
either ``[A]`` (REVOKE UPDATE/DELETE + BEFORE UPDATE OR DELETE trigger)
or ``[L-S]`` (UPDATE allowed only via the session-cycle helpers). The
``Update`` schemas exist to satisfy the
``Read / Create / Update / Filter / ReadList`` quintet per T-PR7-08; the
router layer does NOT expose PATCH routes for ``caja`` / ``arqueo``
and only mounts ``PUT /sesion/{uuid}/cerrar`` for :class:`SesionUpdate`.

``SesionUpdate`` narrows the writable surface to the four fields the
``close_session_with_log`` helper mutates:

- ``valor_inicial_efectivo``, ``valor_inicial_datafono`` (corrections to
  the initial drawer counts recorded at open time)
- ``timestamp_cierre``, ``uuid_usuario_cierre`` (set atomically at close)

Server-assigned ``uuid_sucursal`` / ``uuid_usuario`` /
``timestamp_apertura`` are intentionally excluded from ``Update`` —
they are fixed at ``open_session`` time and never change afterwards.
``extra='forbid'`` (from :class:`_Base`) is the T-PR4-08-style
fast-fail assertion: any attempt to PATCH those fields returns
``ValidationError`` (HTTP 422) before the request hits the router.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime
from decimal import Decimal

from .common import FilterBase, ReadListBase, _Base

# ---------------------------------------------------------------------------
# Caja ([A] cash-drawer snapshot, REQ-26-A-CAJA)
# ---------------------------------------------------------------------------


class CajaRead(_Base):
    """Read-back for ``prod.caja`` (composite PK; monthly partitioned).

    The cash + datafono balances are recorded at sesion close; the
    reverso pattern (insert a compensating ``caja`` row with negative
    deltas) handles corrections. There is no UPDATE path on this table.
    """

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    fecha_retencion_hasta: date
    uuid_sucursal: uuid_lib.UUID | None
    valor_efectivo: Decimal | None
    valor_datafono: Decimal | None


class CajaCreate(_Base):
    """INSERT payload for ``prod.caja``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    valor_efectivo: Decimal | None = None
    valor_datafono: Decimal | None = None


class CajaUpdate(_Base):
    """[A] UPDATE payload — append-only, REVOKE UPDATE on the DB.

    Defined for quintet completeness; no route mounts it. Corrections
    are expressed as new ``caja`` rows with opposite deltas.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    valor_efectivo: Decimal | None = None
    valor_datafono: Decimal | None = None


class CajaFilter(FilterBase):
    """Query filter for ``prod.caja``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    created_at__gte: datetime | None = None
    created_at__lte: datetime | None = None


class CajaReadList(ReadListBase[CajaRead]):
    """Cursor-paginated list of :class:`CajaRead` items."""


# ---------------------------------------------------------------------------
# Arqueo ([A] cash-count event, REQ-26-A-ARQUEO)
# ---------------------------------------------------------------------------


class ArqueoRead(_Base):
    """Read-back for ``prod.arqueo`` (composite PK; monthly partitioned).

    Expected vs reported balances per payment method (cash + datafono).
    Corrections are compensating rows; no UPDATE path on this table.
    """

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    fecha_retencion_hasta: date
    uuid_sucursal: uuid_lib.UUID | None
    uuid_tipo_arqueo: uuid_lib.UUID | None
    uuid_sesion: uuid_lib.UUID | None
    valor_efectivo_esperado: Decimal | None
    valor_datafono_esperado: Decimal | None
    valor_efectivo_reportado: Decimal | None
    valor_datafono_reportado: Decimal | None


class ArqueoCreate(_Base):
    """INSERT payload for ``prod.arqueo``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_tipo_arqueo: uuid_lib.UUID | None = None
    uuid_sesion: uuid_lib.UUID | None = None
    valor_efectivo_esperado: Decimal | None = None
    valor_datafono_esperado: Decimal | None = None
    valor_efectivo_reportado: Decimal | None = None
    valor_datafono_reportado: Decimal | None = None


class ArqueoUpdate(_Base):
    """[A] UPDATE payload — append-only, REVOKE UPDATE on the DB.

    Defined for quintet completeness; no route mounts it.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_tipo_arqueo: uuid_lib.UUID | None = None
    uuid_sesion: uuid_lib.UUID | None = None
    valor_efectivo_esperado: Decimal | None = None
    valor_datafono_esperado: Decimal | None = None
    valor_efectivo_reportado: Decimal | None = None
    valor_datafono_reportado: Decimal | None = None


class ArqueoFilter(FilterBase):
    """Query filter for ``prod.arqueo``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_tipo_arqueo: uuid_lib.UUID | None = None
    uuid_sesion: uuid_lib.UUID | None = None
    created_at__gte: datetime | None = None
    created_at__lte: datetime | None = None


class ArqueoReadList(ReadListBase[ArqueoRead]):
    """Cursor-paginated list of :class:`ArqueoRead` items."""


# ---------------------------------------------------------------------------
# Sesion ([L-S] cash session, REQ-40 / REQ-41 / SC-40 / SC-42)
# ---------------------------------------------------------------------------


class SesionRead(_Base):
    """Read-back for ``prod.sesion`` (single PK, [L-S], NO versioning).

    The ``open_session`` helper INSERTs with ``timestamp_apertura`` +
    initial cash; ``close_session_with_log`` UPDATEs with
    ``timestamp_cierre`` + ``uuid_usuario_cierre`` in the SAME
    transaction as a ``log_transaccional`` row (the
    ``ls_session_guard`` trigger enforces this, SC-40).
    """

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    valor_inicial_efectivo: Decimal | None
    valor_inicial_datafono: Decimal | None
    uuid_sucursal: uuid_lib.UUID | None
    uuid_usuario: uuid_lib.UUID | None
    timestamp_apertura: datetime | None
    timestamp_cierre: datetime | None
    uuid_usuario_cierre: uuid_lib.UUID | None


class SesionCreate(_Base):
    """INSERT payload for ``prod.sesion`` (REQ-40-S-OPEN).

    Server-assigned ``timestamp_apertura`` is filled by
    ``open_session()`` — clients SHOULD NOT send it. ``extra='forbid'``
    blocks smuggling it; the helper ignores any client value.
    """

    valor_inicial_efectivo: Decimal | None = None
    valor_inicial_datafono: Decimal | None = None
    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_usuario: uuid_lib.UUID | None = None
    timestamp_apertura: datetime | None = None
    timestamp_cierre: datetime | None = None
    uuid_usuario_cierre: uuid_lib.UUID | None = None


class SesionUpdate(_Base):
    """[L-S] UPDATE payload — close-time fields only.

    Intentionally NARROW: only the four fields ``close_session_with_log``
    is allowed to mutate are exposed here:

    - ``valor_inicial_efectivo`` / ``valor_inicial_datafono`` — late
      corrections to the initial drawer counts recorded at open time.
    - ``timestamp_cierre`` / ``uuid_usuario_cierre`` — set atomically
      at sesion close.

    Server-fixed fields (``uuid_sucursal``, ``uuid_usuario``,
    ``timestamp_apertura``) are EXCLUDED so a PATCH cannot rewrite the
    identity of an opened sesion. ``extra='forbid'`` makes any attempt
    a 422 at the API edge.
    """

    valor_inicial_efectivo: Decimal | None = None
    valor_inicial_datafono: Decimal | None = None
    timestamp_cierre: datetime | None = None
    uuid_usuario_cierre: uuid_lib.UUID | None = None


class SesionFilter(FilterBase):
    """Query filter for ``prod.sesion``.

    ``timestamp_apertura__gte/lte`` is the natural range for shift
    reports (open sesions in a date window); the ``uuid_usuario_cierre
    IS NULL`` open-sesions case is encoded by the ``abierta`` flag
    computed in the router.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_usuario: uuid_lib.UUID | None = None
    timestamp_apertura__gte: datetime | None = None
    timestamp_apertura__lte: datetime | None = None


class SesionReadList(ReadListBase[SesionRead]):
    """Cursor-paginated list of :class:`SesionRead` items."""


__all__ = [
    "ArqueoCreate",
    "ArqueoFilter",
    "ArqueoRead",
    "ArqueoReadList",
    "ArqueoUpdate",
    "CajaCreate",
    "CajaFilter",
    "CajaRead",
    "CajaReadList",
    "CajaUpdate",
    "SesionCreate",
    "SesionFilter",
    "SesionRead",
    "SesionReadList",
    "SesionUpdate",
]
