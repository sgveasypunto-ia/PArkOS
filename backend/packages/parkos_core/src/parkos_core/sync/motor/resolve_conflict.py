"""motor/resolve_conflict.py — per-audit-class conflict policy (T-PR7-005/006).

REQ-MOT-007..010, REQ-MOT-013 (``specs/sync-motor.md``), design.md §5 / §7.5.
Replaces the permanent-``APPLIED``-for-append-only / ``None``-seq-stub
policy the PR9a-era ``conflict_resolver.py`` implemented (T-PR7-004 turns
that module into a thin shim over :func:`resolve_conflict`). Dispatch table:

| ``audit_class`` | Strategy | Outcome |
|---|---|---|
| ``V`` with ``natural_key`` | delegate to ``spec.hook_pre_insert`` (``IdentityReconciler``, D17) | ``APPLIED``, never blocking |
| ``V`` without ``natural_key`` | ``remote_seq > local_seq`` via :class:`~parkos_core.sync.motor.read_local_seq.ReadLocalSeq` (D4) | ``APPLIED`` else ``MANUAL`` (``sync_conflict`` row, ``politica='seq_tiebreak'``) |
| ``L_E`` / ``L_W`` / ``A`` | every declared ``depends_on`` parent resolves, via ``spec.hook_validate_parent`` (``ValidateParentChain``, D18) | ``APPLIED`` else ``RETRY`` (``reason='parent_missing'``) |
| ``L_S`` | 24h grace window (``PARKOS_SESSION_GRACE_HOURS``, REQ-MOT-013) | ``APPLIED`` within window, else ``MANUAL`` |

**``ValidateParentChain`` has no concrete implementation yet (documented
gap, out of PR7 scope).** ``hooks.md``'s own "Out of Scope" section defers
every hook *implementation* (``IdentityReconciler`` is the one exception,
already shipped in PR5) to ``hooks.md``, and no task across the entire
``tasks.md`` delivery plan (PR2-PR14) assigns building
``hooks/impls/validate_parent_chain.py``. This function still satisfies
REQ-MOT-010 exactly as written — it delegates to ``spec.hook_validate_parent``
via ``hooks.registry.resolve()`` — but since no catalog entry sets that hook
slot yet, the registry's no-op default (``HookResult(proceed=True)``, T-PR4-004)
always runs, so the ``[L_E]``/``[L_W]``/``[A]`` branch resolves ``APPLIED``
today. This mirrors ``motor/apply_row.py``'s identical, already-merged
behavior for its own ``hook_validate_parent`` step (PR4) — not a regression
introduced here. A test-injected hook (the ``REQ-HOOK-015`` precedent, e.g.
``make_spec(name, hook_validate_parent=lambda ctx: HookResult(parent_valid=False))``)
proves the ``RETRY(parent_missing)`` branch is reachable once a real hook is
wired.

**``[L-S]`` grace-window gap for ``sesion`` (documented, not corrected —
see ``catalog/entries/sync_entries_ls.py``'s module docstring).** REQ-MOT-013
reads ``remote["timestamp_evento"]`` for both ``login`` and ``sesion``, but
nothing maps ``sesion``'s own ``timestamp_apertura``/``timestamp_cierre``
onto that key. A missing key resolves ``MANUAL`` (safe, operator-reviewable)
rather than crashing or silently inventing a mapping.
"""

from __future__ import annotations

import inspect
import os
import uuid as uuid_lib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from ..catalog.schema import SyncCatalogEntry
from ..hooks import registry
from ..hooks.base import HookContext, HookResult, ReconciliationKind
from .read_local_seq import ReadLocalSeq

ConflictStatus = Literal["APPLIED", "MANUAL", "RETRY"]

DEFAULT_SESSION_GRACE_HOURS = 24

# REQ-MOT-009: which key of the REMOTE payload carries the comparable value
# for each ``seq_strategy`` (parsed from ``datos->>'seq'`` on the wire for
# ``seq_via_datos``, else the time-based column's own value).
_REMOTE_SEQ_FIELD: dict[str, str] = {
    "seq_via_datos": "seq",
    "max_timestamp_evento": "timestamp_evento",
    "max_created_at": "created_at",
}

_PARENT_RESOLVED_AUDIT_CLASSES = frozenset({"L_E", "L_W", "A"})


@dataclass(frozen=True)
class ConflictResolution:
    """Outcome of one :func:`resolve_conflict` call (design.md §5).

    ``status``: ``APPLIED`` | ``MANUAL`` | ``RETRY``.
    ``reason``: ``None`` on ``APPLIED``; ``"seq_tiebreak"`` /
    ``"missing_timestamp_evento"`` / ``"invalid_timestamp_evento"`` /
    ``"grace_window_expired"`` on ``MANUAL``; ``"parent_missing"`` on
    ``RETRY``.
    ``reconciliation``: set only for the ``[V]`` + ``natural_key`` branch —
    the ``IdentityReconciler`` classification (``noop`` | ``forward`` |
    ``historical``).
    """

    status: ConflictStatus
    reason: str | None = None
    reconciliation: ReconciliationKind | None = None


async def _invoke_hook(hook: registry.HookFn, ctx: HookContext) -> HookResult:
    """Call ``hook``, awaiting the result only if it is actually awaitable.

    Deliberately duplicated (not imported) from ``motor/apply_row.py``'s
    identical private helper — same "avoid coupling two independent motor
    entry points" reasoning ``motor/verify_chain.py`` already documents for
    its own duplicated ``_genesis_hash`` helper.
    """
    result = hook(ctx)
    if inspect.isawaitable(result):
        result = await result
    return result


def _resolve_session_grace_hours(override: int | None) -> int:
    """Resolve the [L-S] grace window, re-reading the env var on every call.

    Mirrors ``runtime/engine_flag.py``'s "read fresh, no restart required"
    posture — a grace-window policy change should not need a worker
    restart. ``override`` (e.g. ``SyncMotor.session_grace_hours``) always
    wins over the env var when explicitly provided.
    """
    if override is not None:
        return override
    raw = os.environ.get("PARKOS_SESSION_GRACE_HOURS")
    if raw is None:
        return DEFAULT_SESSION_GRACE_HOURS
    return int(raw)


def _json_safe(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Coerce ``UUID``/``datetime`` leaf values so the dict is JSONB-storable.

    Duplicated (not imported) from
    ``hooks/impls/identity_reconciler.py::_json_safe`` — same small-utility
    duplication precedent ``motor/verify_chain.py`` documents for its own
    ``_genesis_hash`` helper. ``sync_conflict.datos_local`` / ``datos_cloud``
    are JSONB columns; asyncpg does not auto-serialize ``uuid.UUID`` or
    ``datetime`` values embedded in a plain ``dict``.
    """
    if value is None:
        return None
    safe: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, uuid_lib.UUID):
            safe[key] = str(item)
        elif isinstance(item, datetime):
            safe[key] = item.isoformat()
        else:
            safe[key] = item
    return safe


async def _write_seq_tiebreak_conflict(
    session: AsyncSession,
    spec: SyncCatalogEntry,
    uuid_registro: uuid_lib.UUID,
    branch_uuid: uuid_lib.UUID | None,
    local: dict[str, Any] | None,
    remote: dict[str, Any],
) -> None:
    """Write the ``sync_conflict`` row for a ``MANUAL(seq_tiebreak)`` outcome.

    Lazily imported — same module-load-time-cycle-avoidance convention
    ``hooks/impls/identity_reconciler.py::_write_divergence_conflict``
    already follows for the identical import.

    **Bug found and fixed here (T-PR7-006).** The first draft wrote
    ``local``/``remote`` verbatim into the JSONB columns; a ``datetime`` or
    ``UUID`` leaf value in either dict raises
    ``TypeError: Object of type datetime is not JSON serializable`` at
    flush time (asyncpg's JSONB codec has no default encoder for either
    type). ``identity_reconciler.py``'s own ``_write_divergence_conflict``
    already solved this for its identical write path via ``_json_safe`` —
    applied here too.
    """
    from ...models.A.sync_conflict import SyncConflict

    now = datetime.now(UTC).replace(tzinfo=None)
    conflict = SyncConflict(
        uuid_sucursal=branch_uuid,
        tabla=spec.name,
        uuid_registro=uuid_registro,
        datos_local=_json_safe(local),
        datos_cloud=_json_safe(remote),
        politica="seq_tiebreak",
        resolucion=None,
        timestamp_evento=now,
    )
    session.add(conflict)


async def resolve_conflict(
    session: AsyncSession,
    spec: SyncCatalogEntry,
    *,
    uuid_registro: uuid_lib.UUID,
    local: dict[str, Any] | None,
    remote: dict[str, Any],
    actor_uuid: uuid_lib.UUID,
    branch_uuid: uuid_lib.UUID | None = None,
    parent_local: dict[str, Any] | None = None,
    open_version: dict[str, Any] | None = None,
    read_local_seq: ReadLocalSeq | None = None,
    session_grace_hours: int | None = None,
) -> ConflictResolution:
    """Per-audit-class conflict policy (REQ-MOT-007..010, REQ-MOT-013).

    Args:
        session: Active ``AsyncSession`` (caller commits).
        spec: The catalog entry describing this table's conflict policy.
        uuid_registro: Identity of the row being resolved — the local-seq
            lookup key (``ReadLocalSeq``) and the ``sync_conflict.uuid_registro``
            value on a ``MANUAL`` outcome.
        local: The locally-known row (if any), written verbatim into
            ``sync_conflict.datos_local`` on a ``MANUAL`` outcome. Distinct
            from the local **seq** value, which is read fresh via
            ``read_local_seq`` regardless of what ``local`` holds.
        remote: The incoming row's business payload.
        actor_uuid: JWT subject (audit actor), forwarded into ``HookContext``.
        branch_uuid, parent_local, open_version: Forwarded into
            ``HookContext`` for the hooks that use them.
        read_local_seq: Injectable ``ReadLocalSeq`` instance (defaults to a
            fresh one) — callers holding a long-lived instance (e.g.
            ``SyncMotor``) pass theirs through so its TTL cache is actually
            useful across calls.
        session_grace_hours: Overrides ``PARKOS_SESSION_GRACE_HOURS`` for the
            ``[L-S]`` branch; ``None`` re-reads the env var (default 24h).

    Returns:
        :class:`ConflictResolution`.
    """
    if spec.audit_class == "V" and spec.natural_key:
        # REQ-MOT-008 — delegate to the spec's own hook_pre_insert
        # (IdentityReconciler, D17). Never blocking: the hook's own
        # HookResult.proceed is always True (see that module's docstring),
        # so this branch always resolves APPLIED.
        hook = registry.resolve(spec.hook_pre_insert)
        ctx = HookContext(
            spec=spec,
            payload=remote,
            session=session,
            actor_uuid=actor_uuid,
            open_version=open_version,
            branch_uuid=branch_uuid,
        )
        result = await _invoke_hook(hook, ctx)
        return ConflictResolution(status="APPLIED", reconciliation=result.reconciliation)

    if spec.audit_class == "V":
        # REQ-MOT-009 — seq comparison via ReadLocalSeq (D4).
        reader = read_local_seq if read_local_seq is not None else ReadLocalSeq()
        local_seq = await reader(session, spec, uuid_registro, branch_uuid=branch_uuid)

        if local_seq is None:
            # No locally-known seq for this row — nothing to conflict
            # against, the same "no conflict possible" precedent the
            # PR9a-era stub established.
            return ConflictResolution(status="APPLIED")

        remote_field = _REMOTE_SEQ_FIELD.get(spec.seq_strategy or "none")
        remote_seq = remote.get(remote_field) if remote_field else None

        if remote_seq is not None and remote_seq > local_seq:
            return ConflictResolution(status="APPLIED")

        # remote_seq is None (can't prove the incoming row is newer) or
        # remote_seq <= local_seq — both escalate to MANUAL for operator
        # review, recording both sides for offline reconciliation.
        await _write_seq_tiebreak_conflict(session, spec, uuid_registro, branch_uuid, local, remote)
        return ConflictResolution(status="MANUAL", reason="seq_tiebreak")

    if spec.audit_class in _PARENT_RESOLVED_AUDIT_CLASSES:
        # REQ-MOT-010 — every declared depends_on parent resolves via
        # spec.hook_validate_parent (ValidateParentChain, D18). See this
        # module's docstring for the "no concrete hook yet" gap.
        if spec.depends_on:
            hook = registry.resolve(spec.hook_validate_parent)
            ctx = HookContext(
                spec=spec,
                payload=remote,
                session=session,
                actor_uuid=actor_uuid,
                parent_local=parent_local,
                branch_uuid=branch_uuid,
            )
            result = await _invoke_hook(hook, ctx)
            if not result.parent_valid:
                return ConflictResolution(status="RETRY", reason="parent_missing")
        return ConflictResolution(status="APPLIED")

    if spec.audit_class == "L_S":
        # REQ-MOT-013 — 24h grace window (configurable).
        grace_hours = _resolve_session_grace_hours(session_grace_hours)
        timestamp_evento = remote.get("timestamp_evento")
        if timestamp_evento is None:
            return ConflictResolution(status="MANUAL", reason="missing_timestamp_evento")
        # ``remote`` is the incoming wire payload — over JSON, a datetime
        # always arrives as an ISO-8601 string, never a ``datetime``
        # instance. Confirmed live: a real Docker deployment crashed here
        # with "unsupported operand type(s) for -: 'datetime.datetime'
        # and 'str'" on every login/sesion row, silently masked by
        # ``sync_cloud``'s per-row fallback (which hit the exact same
        # crash on every retry, forever). Only local/test callers ever
        # passed an already-parsed ``datetime`` here, so both shapes
        # must be accepted.
        if isinstance(timestamp_evento, str):
            try:
                timestamp_evento = datetime.fromisoformat(timestamp_evento)
            except ValueError:
                return ConflictResolution(status="MANUAL", reason="invalid_timestamp_evento")
        if timestamp_evento.tzinfo is not None:
            timestamp_evento = timestamp_evento.astimezone(UTC).replace(tzinfo=None)
        now = datetime.now(UTC).replace(tzinfo=None)
        grace_age = now - timestamp_evento
        if grace_age <= timedelta(hours=grace_hours):
            return ConflictResolution(status="APPLIED")
        return ConflictResolution(status="MANUAL", reason="grace_window_expired")

    raise ValueError(f"{spec.name}: unhandled audit_class {spec.audit_class!r}")


__all__ = [
    "DEFAULT_SESSION_GRACE_HOURS",
    "ConflictResolution",
    "ConflictStatus",
    "resolve_conflict",
]
