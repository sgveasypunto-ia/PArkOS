"""motor/dependency_buffer.py — ``prod.sync_queue_lw_buffer`` ops + bounded
drain + TTL sweep (T-PR8-007, T-PR8-009, design.md §2 Issue #8, ADR-003 Part 2).

**Mechanism (design.md §2 Issue #8).** A ``RETRY(parent_missing)`` outcome is
*delivered-and-deferred*: the buffer owns the wait, the TTL sweep owns the
timeout, and ``prod.sync_queue`` is NEVER re-enqueued for this reason — a
dependency wait is not a transport failure, so ``intentos`` never increments
for it (D18). This module owns all three legs:

  - :func:`buffer_row` / :func:`handle_parent_missing` — INSERT, keyed on
    ``(tabla_padre, uuid_padre)``.
  - :func:`drain_dependency_buffer` — a **bounded iterative work queue**
    that applies buffered children once their parent lands.
  - :func:`_lw_buffer_sweep` — the hourly TTL sweep (T-PR8-009).

**No generic parent-resolution mechanism.** Nothing in this module (or
anywhere in ``SYNC_CATALOG``, T-PR4-009's documented gap) can derive WHICH
declared ``depends_on`` parent is missing, or that parent's ``uuid``, from a
``SyncCatalogEntry`` + payload alone across all 46 catalog entries — that
requires a real ``ValidateParentChain`` hook implementation, which no task
across this change's PR1-PR14 plan builds (see ``tasks.md`` T-PR7-006's own
"documented gap, out of PR7 scope" note). This module's public API therefore
takes ``tabla_padre``/``uuid_padre`` as EXPLICIT caller-supplied arguments —
today supplied by a test-injected ``hook_validate_parent`` (the REQ-HOOK-015
precedent), eventually by ``ValidateParentChain`` once it ships.

**Bounded iterative work queue, NOT recursion (the core design decision).**
``apply_row``'s OWN ``hook_post_insert`` -> ``cascade_rows`` mechanism
(``PlateChangeCascade``'s pattern) is genuinely recursive: it calls
``apply_row`` again for each cascade row, so Python's call stack grows one
frame per nesting level. Reusing that mechanism to drain a multi-level
dependency chain would recreate exactly the unbounded-recursion problem this
PR is asked to avoid. Instead, :func:`drain_dependency_buffer`:

  1. Seeds a plain ``collections.deque`` with the just-applied parent's
     ``(tabla, uuid)`` as the first ``(tabla_padre, uuid_padre)`` frontier.
  2. Loops ``while queue:`` — each iteration pops ONE frontier key, SELECTs
     its buffered children (capped at ``batch_size``), and calls
     :func:`apply_row.apply_row` **directly** (a plain function call, never
     through ``cascade_rows``) for each one.
  3. A successfully-applied child's OWN ``(tabla, uuid)`` is appended to the
     SAME queue, for the SAME loop's next iteration — this is what reaches
     grandchildren without adding a single stack frame; the loop, not the
     call stack, carries the traversal.

This keeps the call stack at O(1) regardless of dependency-chain depth. A
module-level reentrancy guard (:data:`_draining`, a ``ContextVar``) makes it
safe to attach this same function as a spec's ``hook_post_insert`` (the same
attachment point ``PlateChangeCascade`` uses): if ``apply_row`` for a
drained child happens to invoke this function again (because that child's
OWN spec also wires ``hook_post_insert`` here), the nested call is a no-op —
the ORIGINAL outer loop already owns continuing that child's frontier on a
later iteration. Iteration count is additionally capped at ``max_depth``
(defaults to the real 46-entry catalog's precomputed deepest topological
level + 1, see ``catalog/dependency_graph.py``) as a defensive bound against
a pathological chain — the real ``depends_on`` graph is asserted acyclic at
import time, so this is a safety net, not an expected code path.
"""
from __future__ import annotations

import contextvars
import uuid as uuid_lib
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.A.sync_queue_lw_buffer import SyncQueueLwBuffer
from ..catalog.dependency_graph import TOPOLOGICAL_LEVELS
from .apply_result import ApplyResult
from .apply_row import apply_row

DEFAULT_TTL_HOURS = 24

# DAG-depth safety cap (design.md §2 Issue #8: "capped ... per row at the
# DAG depth") — one past the deepest precomputed topological level across
# the real SYNC_CATALOG graph. Computed once, at import time, same
# philosophy as ``dependency_graph.py`` itself.
_MAX_DRAIN_DEPTH: int = (max(TOPOLOGICAL_LEVELS.values()) + 1) if TOPOLOGICAL_LEVELS else 1

# Reentrancy guard — see the module docstring's "bounded iterative work
# queue, NOT recursion" section. Defaults to False for every new task/
# context (a fresh drain is always allowed to start).
_draining: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_lw_buffer_draining", default=False
)


def _now() -> datetime:
    """Naive UTC ``datetime`` — matches every other repo/motor module's style."""
    return datetime.now(UTC).replace(tzinfo=None)


def _json_safe(value: dict[str, Any]) -> dict[str, Any]:
    """Coerce ``UUID``/``datetime`` leaf values so the dict is JSONB-storable.

    ``sync_queue_lw_buffer.datos`` is a JSONB column; ``asyncpg`` does not
    auto-serialize ``uuid.UUID`` or ``datetime`` values embedded in a plain
    ``dict``. **Real bug found and fixed** while writing
    ``test_parent_missing_buffer_drain.py`` (T-PR8-006): a ``payload`` built
    from ``apply_row``'s own convention (real ``UUID``/``datetime`` values
    for FK/timestamp columns — see ``motor/apply_row.py``'s payload
    conventions) raised ``TypeError: Object of type UUID is not JSON
    serializable`` on the very first ``buffer_row`` call. Same shallow
    coercion ``hooks/impls/identity_reconciler.py::_json_safe`` already uses
    for the identical write path (``sync_conflict.datos_local`` /
    ``datos_cloud``) — not enhanced further (still shallow, top-level keys
    only) to stay consistent with that precedent.
    """
    safe: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, uuid_lib.UUID):
            safe[key] = str(item)
        elif isinstance(item, datetime):
            safe[key] = item.isoformat()
        else:
            safe[key] = item
    return safe


async def buffer_row(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID | None,
    tabla: str,
    uuid_registro: uuid_lib.UUID,
    tabla_padre: str,
    uuid_padre: uuid_lib.UUID,
    datos: dict[str, Any],
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> SyncQueueLwBuffer:
    """INSERT a row into ``prod.sync_queue_lw_buffer`` (T-PR8-007).

    Keyed on ``(tabla_padre, uuid_padre)`` — the exact key the drain's
    partial index (``ix_sync_queue_lw_buffer_parent``,
    ``0012_add_sync_queue_lw_buffer.py``) is built for. The row stays
    ``estado='pendiente'`` until either :func:`drain_dependency_buffer`
    applies it (``estado='aplicado'``) or :func:`_lw_buffer_sweep` times it
    out (``estado='fallido'``) — never deleted, per the ``[A]`` append-only
    contract.

    Args:
        session: Active ``AsyncSession`` (caller commits/flushes).
        uuid_sucursal: Tenant scope of the buffered row.
        tabla: The buffered row's own catalog entry name.
        uuid_registro: The buffered row's own identity (the sender's
            client-assigned ``uuid`` — the row has not been applied yet,
            so no server-generated identity exists).
        tabla_padre: The name of the missing parent's catalog entry.
        uuid_padre: The missing parent's ``uuid``.
        datos: The full payload to replay via :func:`apply_row.apply_row`
            once the parent lands.
        ttl_hours: Hours until :func:`_lw_buffer_sweep` times this row out
            (default 24, D18 / REQ-CUT-011).

    Returns:
        The newly inserted, flushed :class:`SyncQueueLwBuffer` row.
    """
    now = _now()
    row = SyncQueueLwBuffer(
        uuid_sucursal=uuid_sucursal,
        tabla=tabla,
        uuid_registro=uuid_registro,
        tabla_padre=tabla_padre,
        uuid_padre=uuid_padre,
        datos=_json_safe(datos),
        estado="pendiente",
        buffered_at=now,
        expires_at=now + timedelta(hours=ttl_hours),
    )
    session.add(row)
    await session.flush()
    return row


async def handle_parent_missing(
    session: AsyncSession,
    spec: Any,
    payload: dict[str, Any],
    *,
    uuid_registro: uuid_lib.UUID,
    tabla_padre: str,
    uuid_padre: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID | None = None,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> ApplyResult:
    """Buffer a row and return the standard ``RETRY(parent_missing)`` outcome.

    design.md §2 Issue #8's mechanism table: ``RETRY(parent_missing)`` ->
    sender action ``mark_success`` (``repo.sync_queue.mark_dispatched`` in
    this codebase's naming) — the row IS delivered, ownership of the wait
    transfers to this buffer. The caller (today: a test-injected
    ``hook_validate_parent``; eventually ``ValidateParentChain``) already
    knows which declared parent is missing and its ``uuid`` — see the
    module docstring's "No generic parent-resolution mechanism" note.

    Returns:
        ``ApplyResult(status="RETRY", row_uuid=None,
        reason="parent_missing")`` — the same shape ``apply_row`` itself
        returns for this condition.
    """
    await buffer_row(
        session,
        uuid_sucursal=uuid_sucursal,
        tabla=spec.name,
        uuid_registro=uuid_registro,
        tabla_padre=tabla_padre,
        uuid_padre=uuid_padre,
        datos=payload,
        ttl_hours=ttl_hours,
    )
    return ApplyResult(status="RETRY", row_uuid=None, reason="parent_missing", metrics={})


async def _select_pending(
    session: AsyncSession,
    *,
    tabla_padre: str,
    uuid_padre: uuid_lib.UUID,
    limit: int,
) -> list[SyncQueueLwBuffer]:
    """SELECT buffered children waiting on ``(tabla_padre, uuid_padre)``."""
    stmt = (
        select(SyncQueueLwBuffer)
        .where(
            SyncQueueLwBuffer.tabla_padre == tabla_padre,
            SyncQueueLwBuffer.uuid_padre == uuid_padre,
            SyncQueueLwBuffer.estado == "pendiente",
        )
        .order_by(SyncQueueLwBuffer.buffered_at.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def drain_dependency_buffer(
    session: AsyncSession,
    *,
    tabla_padre: str,
    uuid_padre: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID,
    branch_uuid: uuid_lib.UUID | None = None,
    batch_size: int = 100,
    max_depth: int | None = None,
) -> int:
    """Drain every buffered row waiting on ``(tabla_padre, uuid_padre)``.

    See the module docstring's "Bounded iterative work queue, NOT
    recursion" section for the full design rationale. Safe to call directly
    (e.g. right after a parent's own ``apply_row`` call succeeds) or to
    attach as a spec's ``hook_post_insert`` — the reentrancy guard makes
    nested invocations of THIS function a no-op.

    Args:
        session: Active ``AsyncSession``.
        tabla_padre: The just-applied parent's catalog entry name.
        uuid_padre: The just-applied parent's ``uuid``.
        actor_uuid: JWT subject forwarded to every drained ``apply_row``
            call.
        branch_uuid: Forwarded to every drained ``apply_row`` call.
        batch_size: Cap per SELECT cycle (design.md §2 Issue #8: "capped
            per cycle at the batch size").
        max_depth: Cap on loop iterations (design.md: "capped ... per row
            at the DAG depth"). Defaults to :data:`_MAX_DRAIN_DEPTH`.

    Returns:
        The number of buffered rows successfully applied
        (``estado`` flipped to ``'aplicado'``).
    """
    if _draining.get():
        # Reentrancy guard — the outer (already-running) loop for this
        # same drain operation owns continuing the frontier; see the
        # module docstring.
        return 0

    token = _draining.set(True)
    try:
        depth_budget = max_depth if max_depth is not None else _MAX_DRAIN_DEPTH
        queue: deque[tuple[str, uuid_lib.UUID]] = deque([(tabla_padre, uuid_padre)])
        applied_count = 0

        while queue and depth_budget > 0:
            depth_budget -= 1
            current_tabla_padre, current_uuid_padre = queue.popleft()

            buffered_rows = await _select_pending(
                session,
                tabla_padre=current_tabla_padre,
                uuid_padre=current_uuid_padre,
                limit=batch_size,
            )
            if not buffered_rows:
                continue

            # Lazy import — avoids a module-load-time circular between
            # motor/dependency_buffer.py and catalog/sync_catalog.py
            # (same reasoning as apply_row.py's own cascade_rows lookup).
            from ..catalog.sync_catalog import SYNC_CATALOG_BY_NAME

            for buf_row in buffered_rows:
                child_spec = SYNC_CATALOG_BY_NAME[buf_row.tabla]
                result = await apply_row(
                    session,
                    child_spec,
                    dict(buf_row.datos or {}),
                    actor_uuid=actor_uuid,
                    branch_uuid=branch_uuid,
                )
                if result.status == "APPLIED":
                    buf_row.estado = "aplicado"
                    applied_count += 1
                    # This child may itself be a parent other buffered
                    # rows are waiting on — enqueue it as a NEW frontier
                    # for this SAME loop's next iteration (iterative, not
                    # recursive: no new apply_row/hook_post_insert call
                    # happens here, just a queue append).
                    if result.row_uuid is not None:
                        queue.append((buf_row.tabla, result.row_uuid))
                # RETRY/CONFLICT: leave estado='pendiente' — still blocked
                # on a different/deeper condition. Resolving a NEW
                # (tabla_padre, uuid_padre) wait for it is
                # ValidateParentChain's job (undelivered in this PR, see
                # the module docstring), not this drain loop's.

        return applied_count
    finally:
        _draining.reset(token)


async def _lw_buffer_sweep(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Hourly TTL sweep (T-PR8-009, design.md §2 Issue #8's "Escalation").

    Marks every ``expires_at < NOW()``, still-``'pendiente'`` row
    ``estado='fallido'``, ``ultimo_error='parent_missing_timeout'`` — NEVER
    deleted (``[A]`` append-only contract) and NEVER re-enqueued into
    ``prod.sync_queue`` (D18: a dependency wait is not a transport
    failure). Emits exactly one ``alerta tipo_alerta='orphan_workflow_chain'``
    per orphaned row via :func:`hooks.impls.alert_emitter.alert_emitter`
    (which itself calls ``repo.alert_types.validate`` first).

    Args:
        session: Active ``AsyncSession`` (caller commits).
        now: Override "current time" for deterministic tests. Defaults to
            :func:`_now`.

    Returns:
        The number of rows timed out (and alerted) by this sweep run.
    """
    # Lazy import — avoids a module-load-time circular (alert_emitter
    # imports repo.workflow, which is unrelated to this module, but the
    # lazy-import convention is kept consistent with every other
    # cross-package hook reference in this codebase).
    from ..hooks.impls.alert_emitter import alert_emitter

    current = now or _now()
    stmt = select(SyncQueueLwBuffer).where(
        SyncQueueLwBuffer.estado == "pendiente",
        SyncQueueLwBuffer.expires_at < current,
    )
    expired_rows = list((await session.execute(stmt)).scalars().all())

    for row in expired_rows:
        row.estado = "fallido"
        row.ultimo_error = "parent_missing_timeout"
        await alert_emitter(
            session,
            tipo_alerta="orphan_workflow_chain",
            uuid_sucursal=row.uuid_sucursal,
        )

    return len(expired_rows)


__all__ = [
    "DEFAULT_TTL_HOURS",
    "buffer_row",
    "drain_dependency_buffer",
    "handle_parent_missing",
]
