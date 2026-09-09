"""motor/sync_motor.py — ``SyncMotor`` skeleton (T-PR4-008, T-PR4-009).

REQ-MOT-011: ``SyncMotor`` reads the ``PARKOS_SYNC_ENGINE`` feature flag
(``runtime.engine_flag.get_engine()``) so legacy and catalog-driven paths
coexist during the cutover (D12 kill switch). ``EngineMode.LEGACY``
dispatches ``apply_row`` to the existing legacy applier —
``sync.conflict_resolver.ConflictResolver.apply_pushed_row`` (the module
already wired into ``jobs/sync_cloud.py`` / ``jobs/sync_sucursal.py`` today)
— unchanged. Every other ``EngineMode`` dispatches through the catalog-driven
``motor.apply_row.apply_row`` this PR ships.

REQ-MOT-015: ``apply_batch`` composes the already-selected, already-ordered
batch (``repo.sync_queue.list_pending``, unchanged) with the in-batch
topological sort ``motor.dependency_orderer.order_batch`` computes over
``spec.depends_on`` (D18, PR3), then applies each row via ``apply_row`` in
that order. A row that returns ``RETRY(parent_missing)`` is buffered
in-memory for the remainder of this call, and so is every subsequent row in
the same batch whose declared ``depends_on`` includes a buffered table — the
whole point of D18 Issue #8 (design.md) is that dependency ordering must
prevent an already-known-doomed apply attempt, not just observe its failure.

**PR4-stub note.** The real dependency buffer
(``motor.dependency_buffer.py``, persisting to
``prod.sync_queue_lw_buffer`` keyed on the exact ``(tabla_padre,
uuid_padre)``) lands in PR8. ``apply_batch`` here buffers **per table name**
only, in-memory, for the lifetime of one call — coarser than the real
buffer (it does not verify the child's specific FK value points at the
buffered row), but sufficient to prove the "children of a buffered row are
never attempted" contract this PR ships, and strictly more conservative
(it never under-buffers) than the real thing that replaces it.
"""
from __future__ import annotations

import uuid as uuid_lib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...runtime import engine_flag
from ..catalog.schema import SyncCatalogEntry
from ..conflict_resolver import ApplyOutcome, ConflictResolver
from .apply_result import ApplyResult
from .apply_row import apply_row as _catalog_apply_row
from .dependency_orderer import order_batch
from .read_local_seq import ReadLocalSeq
from .resolve_conflict import ConflictResolution
from .resolve_conflict import resolve_conflict as _resolve_conflict

# Maps the legacy ConflictResolver.apply_pushed_row outcome onto the
# catalog-era ApplyResult.status vocabulary, so SyncMotor.apply_row returns
# a uniform type regardless of `engine` — REQ-MOT-011's "legacy | catalog_*"
# dispatch table describes *where* the row goes, not a different return
# shape for callers.
_LEGACY_OUTCOME_TO_STATUS: dict[ApplyOutcome, str] = {
    ApplyOutcome.APPLIED: "APPLIED",
    ApplyOutcome.CONFLICT_V: "CONFLICT",
    ApplyOutcome.CONFLICT_LS: "CONFLICT",
    ApplyOutcome.ERROR: "RETRY",
}


@dataclass
class _OrderableRow:
    """Adapts a ``(spec, payload)`` pair to ``dependency_orderer``'s
    ``QueueRowLike`` protocol (which only reads ``.tabla``)."""

    tabla: str
    spec: SyncCatalogEntry
    payload: dict[str, Any]


@dataclass
class BatchResult:
    """Outcome of one ``SyncMotor.apply_batch`` call.

    ``applied`` carries one :class:`ApplyResult` per row that actually went
    through ``apply_row`` (whatever its resulting status). ``buffered``
    carries every ``(spec, payload)`` pair that was buffered instead of
    attempted — either because its own ``hook_validate_parent`` rejected it,
    or because a declared parent was already buffered earlier in this same
    batch (see the PR4-stub note in this module's docstring).
    """

    applied: list[ApplyResult] = field(default_factory=list)
    buffered: list[tuple[SyncCatalogEntry, dict[str, Any]]] = field(default_factory=list)


class SyncMotor:
    """Stateless. Dispatches per spec to repo/* helpers. Honors audit-first
    (design.md §5)."""

    def __init__(
        self,
        *,
        engine: engine_flag.EngineMode = engine_flag.EngineMode.LEGACY,
        session_grace_hours: int = 24,
        dependency_buffer_ttl_hours: int = 24,
    ) -> None:
        self.engine = engine
        self.session_grace_hours = session_grace_hours
        self.dependency_buffer_ttl_hours = dependency_buffer_ttl_hours
        # One long-lived ReadLocalSeq per motor instance (T-PR7-002) — its
        # 5s TTL cache is only useful across calls, not re-created per row.
        self._read_local_seq = ReadLocalSeq()

    async def apply_row(
        self,
        session: AsyncSession,
        spec: SyncCatalogEntry,
        payload: dict[str, Any],
        *,
        actor_uuid: uuid_lib.UUID,
        log_tx: bool = True,
    ) -> ApplyResult:
        """Apply one row, honoring ``PARKOS_SYNC_ENGINE`` (REQ-MOT-011).

        ``EngineMode.LEGACY`` dispatches unchanged to the existing
        ``ConflictResolver.apply_pushed_row`` legacy applier — the kill
        switch (D12) that lets a stage be rolled back without a restart.
        Every other mode dispatches through the catalog-driven
        ``motor.apply_row.apply_row``.
        """
        if self.engine is engine_flag.EngineMode.LEGACY:
            return await self._apply_row_legacy(session, spec, payload, actor_uuid=actor_uuid)
        return await _catalog_apply_row(
            session, spec, payload, actor_uuid=actor_uuid, log_tx=log_tx
        )

    async def _apply_row_legacy(
        self,
        session: AsyncSession,
        spec: SyncCatalogEntry,
        payload: dict[str, Any],
        *,
        actor_uuid: uuid_lib.UUID,
    ) -> ApplyResult:
        """Dispatch to the pre-catalog legacy applier, unchanged (D12)."""
        legacy_row = {
            "tabla": spec.name,
            "uuid_registro": payload.get("uuid") or uuid_lib.uuid4(),
            "datos": payload,
            "uuid_sucursal": payload.get("uuid_sucursal"),
            "timestamp_evento": payload.get("timestamp_evento"),
            "actor_uuid": actor_uuid,
        }
        outcome = await ConflictResolver().apply_pushed_row(session, legacy_row)
        return ApplyResult(
            status=_LEGACY_OUTCOME_TO_STATUS[outcome],
            row_uuid=None,
            reason=None if outcome == ApplyOutcome.APPLIED else outcome.value,
        )

    async def apply_batch(
        self,
        session: AsyncSession,
        rows: Sequence[tuple[SyncCatalogEntry, dict[str, Any]]],
        *,
        actor_uuid: uuid_lib.UUID,
        log_tx: bool = True,
    ) -> BatchResult:
        """Apply an already-selected batch in dependency order (D18, REQ-MOT-015).

        ``rows`` MUST already come from ``repo.sync_queue.list_pending`` (or
        an equivalent ``prioridad DESC, intentos ASC, created_at ASC``
        selection) paired with each row's resolved ``SyncCatalogEntry`` and
        parsed payload — that selection is NOT re-done here. This method
        only (1) topologically sorts the batch over ``spec.depends_on`` via
        :func:`dependency_orderer.order_batch`, then (2) applies each row via
        :meth:`apply_row` in that order, buffering a row (and its
        already-known children within the same batch) instead of attempting
        it once a declared parent is known to be missing.
        """
        wrapped = [
            _OrderableRow(tabla=spec.name, spec=spec, payload=payload) for spec, payload in rows
        ]
        ordered = order_batch(wrapped)

        result = BatchResult()
        buffered_tables: set[str] = set()

        for row in ordered:
            spec, payload = row.spec, row.payload

            if spec.depends_on and buffered_tables.intersection(spec.depends_on):
                # A declared parent was already buffered earlier in this
                # same batch — buffer this child too rather than attempt
                # (and fail) it (REQ-MOT-015, design.md Issue #8).
                result.buffered.append((spec, payload))
                buffered_tables.add(spec.name)
                continue

            outcome = await self.apply_row(
                session, spec, payload, actor_uuid=actor_uuid, log_tx=log_tx
            )
            if outcome.status == "RETRY" and outcome.reason == "parent_missing":
                result.buffered.append((spec, payload))
                buffered_tables.add(spec.name)
            else:
                result.applied.append(outcome)

        return result

    async def resolve_conflict(
        self,
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
    ) -> ConflictResolution:
        """Per-audit-class conflict policy (T-PR7-006, REQ-MOT-007..010, -013).

        Thin delegation to :func:`motor.resolve_conflict.resolve_conflict`,
        passing this instance's own long-lived ``ReadLocalSeq`` (so its TTL
        cache is shared across every call through this motor) and
        ``session_grace_hours`` (the ``[L-S]`` grace window, finally
        consumed here — see this class's constructor).
        """
        return await _resolve_conflict(
            session,
            spec,
            uuid_registro=uuid_registro,
            local=local,
            remote=remote,
            actor_uuid=actor_uuid,
            branch_uuid=branch_uuid,
            parent_local=parent_local,
            open_version=open_version,
            read_local_seq=self._read_local_seq,
            session_grace_hours=self.session_grace_hours,
        )


__all__ = ["BatchResult", "ConflictResolution", "SyncMotor"]
