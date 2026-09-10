"""motor/apply_guard.py — session-local echo-suppression GUC (post-PR14
Docker E2E hardening, real defect #3; migration ``0016_add_sync_apply_guard``).

**The defect this closes.** Every ``AFTER INSERT`` sync-outbox trigger
(``fn_enqueue_sync()`` since ``0001_initial_schema.py``,
``fn_enqueue_sync_catalog()`` since ``0014_add_catalog_triggers.py``) fires
UNCONDITIONALLY on every INSERT into its 48 attached tables — including the
ones the sync motor itself performs while APPLYING a row that already
arrived via sync. Confirmed against the real Docker deployment
(``openspec/changes/sync-overhaul/tasks.md``'s post-PR14 closing exercise):
a long-running ``job-sync-cloud`` apply loop picked its own echo row back up
and RE-APPLIED it, extending the ``log_transaccional``/``revocacion_factura``
SHA-256 hash chain a SECOND time for the same logical event —
``motor.verify_chain`` found dozens of real ``ChainAnomaly`` breaks.

**The fix.** ``SET LOCAL parkos.sync_apply_in_progress = 'true'`` — a
session-local Postgres GUC, transactional by construction (resets itself
automatically at the end of the current transaction, or reverts if set
within a savepoint that later rolls back; NEVER a column or a table). Both
trigger functions check
``current_setting('parkos.sync_apply_in_progress', true)`` (migration
``0016``) as the very first statement in their body and skip the
``INSERT INTO prod.sync_queue`` (never the real row write) when it reads
``'true'``.

**Call this ONCE per batch/request** — immediately before dispatching to
``SyncMotor.apply_batch``/``apply_row`` (or the legacy
``ConflictResolver.apply_pushed_row``) for rows that arrived via sync, never
for a genuinely new, locally-originated write (e.g. an admin creating a row
from the UI) — those must keep enqueueing normally. Wired into the 4 real
call sites where the motor applies an already-incoming row:

  - ``api/v1/sync_router.py::sync_events`` (mounted on BOTH ``api_admin``
    and ``api_sucursal`` — covers both push directions through one handler)
  - ``jobs/sync_cloud.py::SyncCloudWorker._apply_pending_batch_once``
  - ``jobs/sync_sucursal.py::SyncSucursalWorker._pull_and_apply`` (legacy
    engine, direct ``ConflictResolver`` dispatch)
  - ``jobs/sync_sucursal.py::SyncSucursalWorker._pull_and_apply_catalog``

Each of these already wraps its whole batch/request in ONE transaction (or
one ``session.begin_nested()`` savepoint) before this PR — see each
call site's own comment for its transaction-nesting shape — so ONE
``SET LOCAL`` per batch/request is sufficient; the GUC stays ``'true'`` for
every row applied within that same transaction/savepoint without needing to
be re-set per row, and resets itself the moment that transaction commits or
rolls back, never leaking into the next cycle or a genuinely new write on
the same connection.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

#: The session GUC name both trigger functions check (migration
#: ``0016_add_sync_apply_guard`` mirrors this exact literal on the SQL side).
SYNC_APPLY_GUC = "parkos.sync_apply_in_progress"


async def enable_echo_suppression(session: AsyncSession) -> None:
    """``SET LOCAL`` the echo-suppression GUC for the rest of the current
    transaction/savepoint on ``session``'s connection.

    Idempotent to call more than once within the same transaction (each
    call just re-asserts the same value) — callers should still prefer
    calling it exactly once per batch/request (see this module's own
    docstring) to avoid paying an extra round trip per row.
    """
    await session.execute(text(f"SET LOCAL {SYNC_APPLY_GUC} = 'true'"))


async def row_already_present(session: AsyncSession, model_cls: type, raw_uuid: Any) -> bool:
    """``True`` when a row identified by ``raw_uuid`` already exists in
    ``model_cls`` — regardless of audit class or ``[V]`` version state.

    Complements :func:`enable_echo_suppression`: that GUC stops a trigger
    from RE-ENQUEUEING the motor's own write; this stops the motor from
    RE-INSERTING a row it (or a peer node) already applied. Both gaps were
    confirmed real in Docker (T-PR11-001-era ``_apply_pending_batch_once``
    re-applying its own cloud-authored ``[V]`` writes, and the equivalent
    risk on a branch's repeated ``/sync/pull`` cycle) — see the two call
    sites (``jobs/sync_cloud.py``, ``jobs/sync_sucursal.py``) for the full
    defect writeups. A row missing ``uuid`` (stripped upstream, or a table
    with no such identity) is treated as never-seen (``False``) — callers
    own deciding whether that is safe for their specific payload shape.
    """
    if raw_uuid is None or not hasattr(model_cls, "uuid"):
        return False
    result = await session.execute(
        select(model_cls.uuid).where(model_cls.uuid == raw_uuid).limit(1)
    )
    return result.scalar_one_or_none() is not None


__all__ = ["SYNC_APPLY_GUC", "enable_echo_suppression", "row_already_present"]
