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

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.sync_queue import SyncQueue

# Literal for the operacion column — keeps Pydantic + Sphinx happy and
# gives mypy a finite set to validate against.
Operacion = Literal["insert", "update", "delete", "compensate"]

# Only these five columns may be updated by ``rol_app``. The DB GRANT
# carries the same restriction at the SQL layer; this frozenset is the
# Python-side mirror, asserted by every helper here.
#
# T-PR2-000 (pre-existing bug, found during PR1's carve-out AST-check
# draft): ``sync_timestamp`` was missing from this whitelist even though
# both ``mark_dispatched`` and ``mark_in_progress`` always set it, so both
# helpers unconditionally raised ``SyncQueueStateError`` on every call.
# ``mark_failed`` was unaffected — it never touches ``sync_timestamp``.
ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS: frozenset[str] = frozenset(
    {"estado", "intentos", "next_retry_at", "ultimo_error", "sync_timestamp"}
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

# CU-07 BR3 (Track 3, sync-sucursal-sweep-exhausted): the absolute
# lifetime a pending row may live in the queue before the worker converts
# it to ``fallido permanente`` + raises an ``evento_no_procesado`` alert.
# Per plan.md L6980 BR3 the clock starts at FIRST enqueue (``created_at``),
# not at the last retry — an event can burn its 6 backoff steps in minutes;
# the 24h cap is the queue-lifetime ceiling.
EXHAUSTION_MAX_AGE: timedelta = timedelta(hours=24)


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


def next_retry_delay(
    intentos: int, *, schedule: tuple[timedelta, ...] | None = None
) -> timedelta:
    """Return the next backoff delay for the given attempt count.

    Indexes into ``schedule`` (T-PR9-006 override) or, when ``schedule``
    is ``None`` (default), the module-level :data:`BACKOFF_SCHEDULE` — the
    last entry of whichever schedule is in effect is the cap. ``intentos``
    is clamped at the schedule length.
    """
    curve = schedule if schedule is not None else BACKOFF_SCHEDULE
    intentos = max(intentos, 0)
    if intentos >= len(curve):
        return curve[-1]
    return curve[intentos]


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
    *,
    backoff_schedule: tuple[timedelta, ...] | None = None,
    max_retries: int | None = None,
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

    Args:
        session: Active ``AsyncSession``.
        sq_uuid: The ``sync_queue`` row to mark failed.
        error: Human-readable failure detail (stored in ``ultimo_error``).
        backoff_schedule: Per-entry override (T-PR9-006, design.md §2
            Issue #9) — e.g. ``dian.backoff.DIAN_BACKOFF_SCHEDULE`` for
            the ``factura_electronica`` / ``revocacion_factura`` catalog
            entries. ``None`` (default) uses the module-level
            :data:`BACKOFF_SCHEDULE` (the general curve) — unchanged
            behavior for every other caller. The override is passed
            **into** this function, never applied by the caller around
            it, so the R-D3 sync_queue carve-out AST check still passes
            (this module stays the ONLY place that computes
            ``next_retry_at`` and issues the UPDATE).
        max_retries: Per-entry terminal-attempt-count override, paired
            with ``backoff_schedule``. Purely informational here — this
            function only ever re-queues (``estado='pendiente'``); a
            caller reading ``intentos >= max_retries`` decides whether to
            treat the row as exhausted and raise its own
            ``on_exhaustion`` alert instead of calling this function
            again.
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

    current = current or 0
    new_intentos = current + 1
    # Delay is indexed by the attempt count *before* this failure (see the
    # docstring table above) — the first failure (current=0) gets the 1m
    # entry, not the 5m one. ``backoff_schedule`` overrides which curve
    # :func:`next_retry_delay` indexes into (T-PR9-006); ``None`` keeps
    # today's general-curve behavior.
    new_delay = next_retry_delay(current, schedule=backoff_schedule)
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


async def mark_exhausted(
    session: AsyncSession,
    sq_uuid: uuid_lib.UUID,
    error: str,
) -> None:
    """Mark the row as permanently failed (``estado='fallido'``, CU-07 BR3).

    THE terminal state. Unlike :func:`mark_failed` — which re-queues
    (``estado='pendiente'``) and schedules another retry via the backoff
    curve — this helper ONLY transitions to ``fallido`` and clears
    ``next_retry_at`` (``NULL`` means ``list_pending`` will never pick
    the row up again). ``intentos`` is left untouched: exhaustion is
    detected from the row's OWN counters/age by ``list_exhausted``, not
    incremented here (each transition is a retry; this is not one).

    The ``estado`` / ``next_retry_at`` / ``ultimo_error`` keys are all
    inside :data:`ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS`, so the R-D3
    carve-out invariant holds: this module stays the ONLY place that
    issues the UPDATE.

    Args:
        session: Active ``AsyncSession``.
        sq_uuid: The ``sync_queue`` row to mark permanently failed.
        error: Human-readable failure detail (stored in ``ultimo_error``).

    Raises:
        SyncQueueNotFoundError: No row with ``sq_uuid`` exists.
    """
    _validate_update_columns(
        {
            "estado": "fallido",
            "next_retry_at": None,
            "ultimo_error": error,
        }
    )
    result = await session.execute(
        update(SyncQueue)
        .where(SyncQueue.uuid == sq_uuid)
        .values(
            estado="fallido",
            next_retry_at=None,
            ultimo_error=error,
        )
    )
    if result.rowcount == 0:
        raise SyncQueueNotFoundError(f"sync_queue row {sq_uuid} not found")


async def list_exhausted(
    session: AsyncSession,
    *,
    limit: int = 100,
    uuid_sucursal: uuid_lib.UUID | None = None,
) -> list[SyncQueue]:
    """Return ``pendiente`` rows that exhausted the CU-07 BR3 SLA.

    A pending row is eligible for conversion to ``fallido permanente``
    when EITHER condition holds:

    * ``intentos`` has reached the end of the general backoff curve —
      ``len(BACKOFF_SCHEDULE)`` entries. After that many failures the
      curve has been walked to its 24h cap; another ``mark_failed``
      would only repeat the last step forever.
    * the row has lived in the queue for more than
      :data:`EXHAUSTION_MAX_AGE` (24h, BR3 — measured from
      ``created_at``, the FIRST enqueue, not the last retry).

    Rows already terminal (``estado != 'pendiente'``) are filtered out at
    the DB, which is the sweep's dedup: a row converted by
    :func:`mark_exhausted` stops matching on the next cycle, so the same
    event never raises a second alert.
    """
    cutoff = _now() - EXHAUSTION_MAX_AGE
    stmt = (
        select(SyncQueue)
        .where(SyncQueue.estado == "pendiente")
        .where(
            (SyncQueue.intentos >= len(BACKOFF_SCHEDULE))
            | (SyncQueue.created_at <= cutoff)
        )
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
        # Bug 8 fix: the docstring's own contract — a row mid-backoff
        # (next_retry_at in the future) must NOT be re-picked every cycle.
        # Without this predicate mark_failed's backoff schedule was
        # decorative and a 5xx push re-fired on every cycle.
        .where(
            (SyncQueue.next_retry_at.is_(None))
            | (SyncQueue.next_retry_at <= func.now())
        )
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
    "EXHAUSTION_MAX_AGE",
    "Operacion",
    "SyncQueueNotFoundError",
    "SyncQueueStateError",
    "enqueue",
    "list_exhausted",
    "list_pending",
    "mark_dispatched",
    "mark_exhausted",
    "mark_failed",
    "mark_in_progress",
    "next_retry_delay",
]