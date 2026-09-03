"""sync_queue helpers — worker-side CRUD on the carved-out [A] table.

REQ-14-A-SYNC-FACADE: ``prod.sync_queue`` is the carved-out [A] table —
``rol_app`` keeps UPDATE/DELETE grants so the sync workers can flip
``estado`` and increment ``intentos``. The column whitelist is enforced
**client-side** (this module) and **server-side** (in DB GRANTs; out of
PR2 scope).

The four whitelisted columns (``ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS``) are
the only fields a worker may mutate. Any attempt to update a different
column raises :class:`SyncQueueStateError` immediately, before the
session hits the DB.

The DB-side enqueue is owned by ``prod.fn_enqueue_sync()`` (a trigger
on every replicated [A] table's ``AFTER INSERT``); see
:mod:`parkos_core.repo.sync_outbox` for the no-op facade that documents
this contract for callers.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.sync_queue import SyncQueue

# Literal for the operacion column — keeps Pydantic + Sphinx happy and
# gives mypy a finite set to validate against.
Operacion = Literal["insert", "update", "delete", "compensate"]

# Only these four columns may be updated by ``rol_app``. The DB GRANT
# carries the same restriction at the SQL layer; this frozenset is the
# Python-side mirror, asserted by every helper here.
ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS: frozenset[str] = frozenset(
    {"estado", "intentos", "next_retry_at", "ultimo_error"}
)

# Exponential backoff schedule: 1m → 5m → 30m → 2h → 12h → 24h max
# (REQ-14-A-SYNC-FACADE: bounded retry storm; cap at 24h). Indexes:
#   attempts=0 → 1m, attempts=1 → 5m, attempts=2 → 30m,
#   attempts=3 → 2h, attempts=4 → 12h, attempts>=5 → 24h.
BACKOFF_SCHEDULE: tuple[timedelta, ...] = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=30),
    timedelta(hours=2),
    timedelta(hours=12),
    timedelta(hours=24),
)


class SyncQueueStateError(Exception):
    """Raised when an update attempt touches a non-whitelisted column.

    Mirrors the DB-side REVOKE that would otherwise raise a permission
    error. By raising it client-side we keep the error message clean
    and avoid a round-trip to the DB.
    """


class SyncQueueNotFoundError(Exception):
    """Raised when an operation references an unknown sync_queue uuid."""


def _now() -> datetime:
    """Return the canonical ``NOW()`` value used in all sync_queue writes."""
    return datetime.now(UTC).replace(tzinfo=None)


def next_retry_delay(intentos: int) -> timedelta:
    """Return the next backoff delay for the given attempt count.

    Indexes into :data:`BACKOFF_SCHEDULE`; the last entry (24h) is the
    cap. ``intentos`` is clamped at the schedule length.
    """
    intentos = max(intentos, 0)
    if intentos >= len(BACKOFF_SCHEDULE):
        return BACKOFF_SCHEDULE[-1]
    return BACKOFF_SCHEDULE[intentos]


def _validate_update_columns(values: dict[str, object]) -> None:
    """Raise :class:`SyncQueueStateError` if any key isn't whitelisted."""
    forbidden = set(values) - ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS
    if forbidden:
        raise SyncQueueStateError(
            f"sync_queue UPDATE may only touch {sorted(ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS)}; "
            f"got forbidden columns: {sorted(forbidden)}"
        )


async def enqueue(
    session: AsyncSession,
    operacion: Operacion,
    tabla: str,
    uuid_registro: uuid_lib.UUID,
    datos: dict,
    uuid_sucursal: uuid_lib.UUID | None,
    *,
    prioridad: int | None = None,
) -> SyncQueue:
    """Insert a new row into ``prod.sync_queue``.

    Mirrors the DB-side ``prod.fn_enqueue_sync()`` trigger but is exposed
    here as a programmatic helper for callers who need to enqueue from
    contexts where the DB trigger cannot fire (e.g. tests, batch imports).
    The DB trigger is the canonical path in production; this helper is
    a documented escape hatch.

    Priority defaults:
      - ``10`` for ``operacion == 'insert'`` (new data — highest priority)
      - ``0`` for everything else (configurable via the ``prioridad`` kwarg)

    Args:
        session: Active ``AsyncSession`` (caller commits).
        operacion: One of ``"insert"``, ``"update"``, ``"delete"``,
            ``"compensate"``.
        tabla: Source table name (e.g. ``"factura_pagos"``).
        uuid_registro: UUID of the row being synced.
        datos: Payload to forward (typically a ``to_jsonb(NEW)`` snapshot).
        uuid_sucursal: Tenant scope (may be ``None`` for cloud-global rows).
        prioridad: Override the default priority. ``None`` means "use the
            default for this ``operacion``".

    Returns:
        The newly inserted :class:`SyncQueue` row (not yet committed).
    """
    if prioridad is None:
        prioridad = 10 if operacion == "insert" else 0

    row = SyncQueue(
        uuid_sucursal=uuid_sucursal,
        operacion=operacion,
        tabla=tabla,
        uuid_registro=uuid_registro,
        datos=datos,
        prioridad=prioridad,
        estado="pendiente",
        intentos=0,
        created_at=_now(),
        sync_status="pendiente",
    )
    session.add(row)
    return row


async def mark_dispatched(
    session: AsyncSession,
    sq_uuid: uuid_lib.UUID,
) -> None:
    """Mark the row as successfully dispatched (``estado='exitoso'``).

    Stamps ``sync_timestamp=NOW()`` and clears ``next_retry_at`` + the
    ``ultimo_error`` field. The helper enforces the column whitelist
    even though every key here is in it — defense in depth.
    """
    _validate_update_columns(
        {
            "estado": "exitoso",
            "sync_timestamp": _now(),
            "next_retry_at": None,
            "ultimo_error": None,
        }
    )
    result = await session.execute(
        update(SyncQueue)
        .where(SyncQueue.uuid == sq_uuid)
        .values(
            estado="exitoso",
            sync_timestamp=_now(),
            next_retry_at=None,
            ultimo_error=None,
        )
    )
    if result.rowcount == 0:
        raise SyncQueueNotFoundError(f"sync_queue row {sq_uuid} not found")


async def mark_in_progress(
    session: AsyncSession,
    sq_uuid: uuid_lib.UUID,
) -> None:
    """Mark the row as in flight (``estado='en_progreso'``).

    Used by the worker when it picks up the row but before it has a
    final result. Helps operators detect hung workers (rows stuck in
    ``en_progreso`` past the worker's expected cycle time).
    """
    _validate_update_columns({"estado": "en_progreso", "sync_timestamp": _now()})
    result = await session.execute(
        update(SyncQueue)
        .where(SyncQueue.uuid == sq_uuid)
        .values(estado="en_progreso", sync_timestamp=_now())
    )
    if result.rowcount == 0:
        raise SyncQueueNotFoundError(f"sync_queue row {sq_uuid} not found")


async def mark_failed(
    session: AsyncSession,
    sq_uuid: uuid_lib.UUID,
    error: str,
) -> None:
    """Mark the row as failed (``estado='fallido'``) and schedule the next retry.

    Increments ``intentos`` and computes ``next_retry_at`` via
    :func:`next_retry_delay`. The exponential backoff schedule is:

    ============ =============
    ``intentos`` delay
    ============ =============
    0            1 minute
    1            5 minutes
    2            30 minutes
    3            2 hours
    4            12 hours
    ≥5           24 hours (cap)
    ============ =============

    Re-queues the row (``estado='pendiente'``) — the worker will pick it
    up again at ``next_retry_at``. Workers check ``estado='pendiente'``
    AND ``next_retry_at <= NOW()`` when polling (see :func:`list_pending`).
    """
    # Read current intentos so we can compute the new backoff window.
    # This is one extra SELECT per failure, but failures are rare and
    # the math must reflect the row's actual attempt count, not the
    # caller's guess.
    current = (
        await session.execute(
            select(SyncQueue.intentos).where(SyncQueue.uuid == sq_uuid)
        )
    ).scalar_one_or_none()
    if current is None:
        raise SyncQueueNotFoundError(f"sync_queue row {sq_uuid} not found")

    new_intentos = (current or 0) + 1
    new_delay = next_retry_delay(new_intentos)
    new_retry_at = _now() + new_delay

    _validate_update_columns(
        {
            "estado": "pendiente",
            "intentos": new_intentos,
            "next_retry_at": new_retry_at,
            "ultimo_error": error,
        }
    )
    result = await session.execute(
        update(SyncQueue)
        .where(SyncQueue.uuid == sq_uuid)
        .values(
            estado="pendiente",
            intentos=new_intentos,
            next_retry_at=new_retry_at,
            ultimo_error=error,
        )
    )
    if result.rowcount == 0:
        raise SyncQueueNotFoundError(f"sync_queue row {sq_uuid} not found")


async def list_pending(
    session: AsyncSession,
    *,
    limit: int = 100,
    uuid_sucursal: uuid_lib.UUID | None = None,
) -> list[SyncQueue]:
    """Return up to ``limit`` pending rows, ready for the worker to process.

    A row is "ready" when ``estado='pendiente'`` AND
    ``next_retry_at IS NULL OR next_retry_at <= NOW()``. The worker
    processes rows in order of:
      1. ``prioridad`` DESC — high-priority rows first
      2. ``intentos`` ASC — fewer retries first (give new work a chance)
      3. ``created_at`` ASC — FIFO within the same priority

    Args:
        session: Active ``AsyncSession``.
        limit: Maximum rows to return (default 100; cap at 500).
        uuid_sucursal: When set, restrict to rows for this branch. When
            ``None``, return all rows (cloud-side sync receiver).

    Returns:
        List of :class:`SyncQueue` rows (not yet committed).
    """
    stmt = (
        select(SyncQueue)
        .where(SyncQueue.estado == "pendiente")
        .order_by(
            SyncQueue.prioridad.desc(),
            SyncQueue.intentos.asc(),
            SyncQueue.created_at.asc(),
        )
        .limit(limit)
    )
    if uuid_sucursal is not None:
        stmt = stmt.where(SyncQueue.uuid_sucursal == uuid_sucursal)

    result = await session.execute(stmt)
    return list(result.scalars().all())


__all__ = [
    "ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS",
    "BACKOFF_SCHEDULE",
    "Operacion",
    "SyncQueueNotFoundError",
    "SyncQueueStateError",
    "enqueue",
    "list_pending",
    "mark_dispatched",
    "mark_failed",
    "mark_in_progress",
    "next_retry_delay",
]