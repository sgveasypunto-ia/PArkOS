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

from sqlalchemy import inspect as _sa_inspect
from sqlalchemy import select as _sa_select
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.V.sucursal import Sucursal as _Sucursal
from ...runtime import engine_flag
from ..catalog.schema import SyncCatalogEntry
from ..conflict_resolver import ApplyOutcome, ConflictResolver
from . import apply_guard
from .apply_result import ApplyResult
from .apply_row import apply_row as _catalog_apply_row
from .dependency_orderer import order_batch
from .identity_fk_map import IDENTITY_FK_COLUMNS
from .identity_lookup import resolve_open_version
from .read_local_seq import ReadLocalSeq

# Columns the in-place update path on ``sucursal`` (the user-requirement
# special case) MUST NOT touch — the identity (uuid), the bi-temporal
# bookkeeping (vigente_desde/hasta, created_at/by) and the sync-state
# columns. Everything else is fair game for a cloud-pushed update.
_SUCURSAL_PROTECTED_COLUMNS: frozenset[str] = frozenset(
    {
        "uuid",
        "vigente_desde",
        "vigente_hasta",
        "created_at",
        "created_by",
        "sync_status",
        "sync_timestamp",
        "sync_attempts",
    }
)
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


def describe_apply_error(exc: BaseException) -> str:
    """Summarise a failed row apply into a short, stable, loggable label.

    For a foreign-key violation the actionable token is the CONSTRAINT name
    (it names the child table and the parent that is missing), not the
    driver message: asyncpg's text embeds every bound parameter, so logging
    ``str(exc)`` re-emits the row's data on every retry - which is exactly
    how this defect produced 522 near-identical log lines.
    """
    orig = getattr(exc, "orig", None)
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)
    if constraint:
        return f"fk_violation:{constraint}"
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate:
        return f"{type(orig).__name__}:{sqlstate}"
    return type(exc).__name__


_APPLY_ERROR_DETAIL_MAX = 240


def describe_apply_error_detail(exc: BaseException) -> str:
    """Short human-readable message of the ORIGINAL failure, for the log.

    ``describe_apply_error`` returns only a stable label (``StatementError``)
    which hides the actual cause. This unwraps SQLAlchemy's ``orig`` and
    truncates, so the log names the real error (e.g. ``TypeError: Object of
    type date is not JSON serializable``).

    Never uses ``str()`` of the SQLAlchemy wrapper (it embeds the bound
    parameter dict). A server-side database error (has a SQLSTATE) is
    reported as class + SQLSTATE (+ constraint) only: its message carries a
    ``DETAIL:`` with the offending key values, i.e. personal data.
    """
    orig = getattr(exc, "orig", None)
    if orig is None:
        orig = exc.__cause__
    if orig is None:
        if hasattr(exc, "params"):
            # SQLAlchemy wrapper without an unwrapped cause: its text holds
            # the bound row parameters.
            return type(exc).__name__
        orig = exc  # a plain Python error raised by our own code
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate:
        constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)
        suffix = f":{constraint}" if constraint else ""
        return f"{type(orig).__name__}:{sqlstate}{suffix}"
    text = " ".join(str(orig).split())
    if len(text) > _APPLY_ERROR_DETAIL_MAX:
        text = text[:_APPLY_ERROR_DETAIL_MAX] + "..."
    return f"{type(orig).__name__}: {text}"


# ---------------------------------------------------------------------------
# ``resolve_identity_aliases`` + ``remap_foreign_keys`` — durable
# cross-cycle identity-alias remap for the catalog-driven push path.
#
# Restored in 2026-10-05 (commit missing in git history — last live in the
# qa/integracion-admin-sucursal session's container only). Without these
# two symbols the import in ``api/v1/sync_router.py`` (line 88) and the
# call at line 1255 raise ``ImportError`` at module load, which is the
# only thing preventing every service from booting at ``dev`` HEAD today.
#
# Why a single bounded query (not one per row): the callsite documents
# "ONCE for this whole request's catalog-driven rows (never one query per
# row — same bounded posture ``resolve_identity_aliases`` already
# documents)". All candidate uuids are collected up front, then one
# ``WHERE uuid_origen = ANY(:candidates)`` returns the whole map.
#
# ``prod.sync_identity_alias`` is local to each node (OUT_OF_CATALOG, never
# replicated). It is WRITTEN by ``record_identity_alias`` when
# ``identity_reconciler`` classifies an arrival as ``noop`` against an open
# version with a different uuid (``motor/apply_row.py``), and READ by
# ``remap_payload_with_aliases`` inside ``SyncMotor.apply_row`` -- so
# /sync/events, /sync/push, the pull and jobs/sync_cloud all remap alike.
# Only effective under the catalog engine: the legacy engine never runs the
# reconciler, hence never writes an alias.
# ---------------------------------------------------------------------------
async def resolve_identity_aliases(
    session: AsyncSession,
    catalog_rows: Sequence[tuple[SyncCatalogEntry, dict[str, Any]]],
) -> dict[uuid_lib.UUID, uuid_lib.UUID]:
    """Resolve durable ``prod.sync_identity_alias`` rows for every candidate
    uuid present in the request's catalog-driven rows — once, in one query.

    Returns an empty dict when ``catalog_rows`` is empty or no payload
    contains a uuid value (the common path for non-aliased tables).
    """
    candidates: set[uuid_lib.UUID] = set()
    for _spec, payload in catalog_rows:
        for value in payload.values():
            if isinstance(value, uuid_lib.UUID):
                candidates.add(value)
            elif isinstance(value, str):
                try:
                    candidates.add(uuid_lib.UUID(value))
                except ValueError:
                    continue
    if not candidates:
        return {}

    # ``prod.sync_identity_alias`` is intentionally NOT modeled as an
    # ORM class (it lives in ``OUT_OF_CATALOG`` and is never replicated,
    # so adding a model would force a migration registration that the
    # table never needs). Raw ``text()`` with one ``ANY()`` is the
    # minimal-surface access path.
    stmt = text(
        "SELECT uuid_origen, uuid_resuelto "
        "FROM prod.sync_identity_alias "
        "WHERE uuid_origen = ANY(:candidates)"
    )
    result = await session.execute(stmt, {"candidates": list(candidates)})
    return {row.uuid_origen: row.uuid_resuelto for row in result.all()}


def remap_foreign_keys(
    spec: SyncCatalogEntry,
    raw_payload: dict[str, Any],
    aliases: dict[uuid_lib.UUID, uuid_lib.UUID],
) -> dict[str, Any]:
    """Return a (possibly new) copy of ``raw_payload`` with any FK uuid
    value repointed to its locally-resolved sibling recorded in
    ``aliases``.

    The mapping is conservative: only values that ARE present in
    ``aliases`` are rewritten. A field whose value is not a uuid, or
    whose uuid is not in the alias map, is left untouched (returns a
    shallow copy of the dict, never the input itself, so the caller
    can safely pass it to ``apply_row`` without aliasing the original
    payload).
    """
    out = dict(raw_payload)
    if not aliases:
        return out
    # Column-filtered: ONLY columns that are foreign keys onto an identity
    # -reconciled master are candidates. ``uuid``, ``created_by``,
    # ``current_uuid`` and every other column are never rewritten, even when
    # their value happens to equal an aliased uuid.
    for key in identity_fk_columns(spec):
        candidate = _as_uuid(out.get(key))
        if candidate is not None and candidate in aliases:
            out[key] = aliases[candidate]
    return out


def _as_uuid(value: Any) -> uuid_lib.UUID | None:
    if isinstance(value, uuid_lib.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid_lib.UUID(value)
        except ValueError:
            return None
    return None


# Never remapped, regardless of metadata: identity and audit columns.
_NEVER_REMAPPED: frozenset[str] = frozenset({"uuid", "created_by", "current_uuid"})
def identity_fk_columns(spec: SyncCatalogEntry) -> frozenset[str]:
    """Columns of ``spec``'s table that are foreign keys onto a table whose
    catalog entry reconciles identity by natural key (``identity_reconciler``).

    Read from the explicit :data:`~.identity_fk_map.IDENTITY_FK_COLUMNS` (the ORM
    declares no ``ForeignKey`` on these columns, so SQLAlchemy metadata cannot
    be the source); ``test_sync_identity_alias_fk_columns`` keeps it in step
    with ``pg_constraint``.
    """
    return IDENTITY_FK_COLUMNS.get(spec.name, frozenset()) - _NEVER_REMAPPED


async def remap_payload_with_aliases(
    session: AsyncSession,
    spec: SyncCatalogEntry,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Repoint ``payload``'s reconciled-master FK columns through
    ``prod.sync_identity_alias`` (one indexed lookup).

    Returns ``payload`` itself, with no query, when the spec has no such FK
    column or none carries a value. A missing alias leaves the payload
    untouched (the apply then behaves as before and is retried next cycle).
    """
    columns = identity_fk_columns(spec)
    if not columns:
        return payload
    candidates = {c for c in (_as_uuid(payload.get(col)) for col in columns) if c is not None}
    if not candidates:
        return payload
    result = await session.execute(
        text(
            "SELECT uuid_origen, uuid_resuelto FROM prod.sync_identity_alias "
            "WHERE uuid_origen = ANY(:ids)"
        ),
        {"ids": list(candidates)},
    )
    aliases = {row.uuid_origen: row.uuid_resuelto for row in result.all()}
    if not aliases:
        return payload
    return remap_foreign_keys(spec, payload, aliases)


async def record_identity_alias(
    session: AsyncSession,
    tabla: str,
    uuid_origen: Any,
    uuid_resuelto: Any,
    actor_uuid: uuid_lib.UUID | None,
) -> bool:
    """Durably record ``uuid_origen -> uuid_resuelto`` (an arriving row that
    ``identity_reconciler`` collapsed onto an existing open version).

    Idempotent (``ON CONFLICT (uuid_origen) DO NOTHING``; the table is
    append-only). Skipped (returns ``False``) when either uuid is missing or
    malformed, or when both are equal. Runs inside the caller's transaction /
    SAVEPOINT, so it commits or rolls back together with the apply.
    """
    origen = _as_uuid(uuid_origen)
    resuelto = _as_uuid(uuid_resuelto)
    if origen is None or resuelto is None or origen == resuelto:
        return False
    await session.execute(
        text(
            "INSERT INTO prod.sync_identity_alias "
            "(tabla, uuid_origen, uuid_resuelto, created_by) "
            "VALUES (:tabla, :origen, :resuelto, :actor) "
            "ON CONFLICT (uuid_origen) DO NOTHING"
        ),
        {"tabla": tabla, "origen": origen, "resuelto": resuelto, "actor": actor_uuid},
    )
    return True


@dataclass
class BatchResult:
    """Outcome of one ``SyncMotor.apply_batch`` call.

    ``applied`` carries one :class:`ApplyResult` per row that actually went
    through ``apply_row`` (whatever its resulting status). ``buffered``
    carries every ``(spec, payload)`` pair that was buffered instead of
    attempted - either because its own ``hook_validate_parent`` rejected it,
    or because a declared parent was already buffered earlier in this same
    batch (see the PR4-stub note in this module's docstring).

    ``failed`` carries ``(spec, payload, reason)`` for every row whose apply
    raised, isolated to its own SAVEPOINT so the rest of the batch still
    lands. This exists because ``hook_validate_parent`` is a TEST-ONLY hook
    today (see :mod:`.dependency_buffer`), so in production nothing checks
    that a row's foreign-key parent is actually present locally: a
    ``permisos_usuario`` naming a ``uuid_permiso`` the node has never seen
    raised ``ForeignKeyViolationError``, which aborted the whole batch and
    left the pull cursor frozen. Measured live: 522 consecutive identical
    failures, the branch consuming nothing from the cloud, container health
    still reporting ``healthy``. Rows land here instead, and the caller
    reports them rather than dying.
    """

    applied: list[ApplyResult] = field(default_factory=list)
    buffered: list[tuple[SyncCatalogEntry, dict[str, Any]]] = field(default_factory=list)
    failed: list[tuple[SyncCatalogEntry, dict[str, Any], str]] = field(
        default_factory=list
    )
    # Parallel to ``failed``: a short, truncated message per failed row (see
    # :func:`describe_apply_error_detail`). Kept apart from ``failed`` so the
    # ``(spec, payload, reason)`` tuple shape stays stable for its consumers.
    failed_details: list[str] = field(default_factory=list)


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

        Real defect confirmed via manual QA + real HTTP identity-divergence
        exercise (2026-09-10): ``motor.apply_row.apply_row`` never resolves
        ``open_version`` itself — it only forwards whatever this method
        passes it. This was ALWAYS ``None`` on every real call (this is the
        one and only production caller of the catalog applier), so
        ``identity_reconciler`` never saw the currently-open row for a
        ``clientes``/``clientes_b2b``/``vehiculos`` natural key and always
        inserted a fresh, never-closed version — confirmed live: 2-3
        simultaneously-open rows for the same natural key across cloud +
        branch after one real push+pull cycle.
        ``motor.identity_lookup.resolve_open_version`` closes this by doing,
        automatically, exactly what ``test_identity_invariant.py`` used to
        do by hand for its own assertions only.
        """
        # Real defect confirmed live, 2026-10-06: the ``sucursal``
        # table is a special case where the user requirement is
        # "the only keys are UUIDs — an edit is an UPDATE, not a
        # new entity". This check has to run BEFORE the LEGACY
        # dispatch below, because the LEGACY path goes through
        # ``ConflictResolver`` (a verdict-only shim since PR7) and
        # returns CONFLICT for an already-known prefijo_nombre — which
        # would short-circuit before our direct UPDATE/INSERT can run.
        # The cloud's engine is also LEGACY (per compose default), so
        # the pull path lands here too: this branch is the only entry
        # point for both the cloud and the branch apply sides.
        if spec.name == "sucursal" and spec.audit_class == "V":
            target_uuid = payload.get("uuid")
            if target_uuid is None:
                return ApplyResult(
                    status="RETRY",
                    row_uuid=None,
                    reason="missing_uuid",
                )
            stmt = _sa_select(_Sucursal).where(_Sucursal.uuid == target_uuid)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is None:
                # First pull for this sucursal — INSERT directly with the
                # cloud's uuid, prefijo_nombre and other business fields.
                insert_payload: dict[str, Any] = {
                    "uuid": target_uuid,
                    "estado": payload.get("estado", "activo"),
                    "vigente_desde": payload.get("vigente_desde"),
                    "vigente_hasta": payload.get("vigente_hasta"),
                    "created_at": payload.get("created_at"),
                    "created_by": payload.get("created_by"),
                }
                for col in _sa_inspect(_Sucursal).columns:
                    if col.name in _SUCURSAL_PROTECTED_COLUMNS or col.name in {
                        "estado"
                    }:
                        continue
                    if col.name in payload:
                        insert_payload[col.name] = payload[col.name]
                new_row = _Sucursal(**insert_payload)
                session.add(new_row)
                await session.flush()
                return ApplyResult(
                    status="APPLIED",
                    row_uuid=target_uuid,
                    reason=None,
                )
            # Subsequent pulls — UPDATE the local row's fields in place.
            for col in _sa_inspect(_Sucursal).columns:
                if col.name in _SUCURSAL_PROTECTED_COLUMNS or col.name == "estado":
                    continue
                if col.name in payload:
                    setattr(existing, col.name, payload[col.name])
            return ApplyResult(
                status="APPLIED",
                row_uuid=target_uuid,
                reason=None,
            )

        # Identity-alias remap (single place for /sync/events, /sync/push, the
        # pull and jobs/sync_cloud): repoint FK columns that name an arriving
        # uuid ``identity_reconciler`` collapsed onto another open version.
        payload = await remap_payload_with_aliases(session, spec, payload)

        if self.engine is engine_flag.EngineMode.LEGACY:
            return await self._apply_row_legacy(session, spec, payload, actor_uuid=actor_uuid)

        # Universal self/repeat-duplication guard (real defect confirmed
        # live, 2026-09-10): every one of the 4 real apply entry points
        # (``api/v1/sync_router.py::sync_events``, ``jobs/sync_cloud.py::
        # _apply_pending_batch_once``, ``jobs/sync_sucursal.py::
        # _pull_and_apply_catalog``, ``sync/cutover/backfill.py::
        # run_backfill``) funnels through THIS method — placing the check
        # here, once, covers all of them instead of the first 3 needing
        # their own copy (already added separately, before this one, kept
        # as harmless defense-in-depth) and ``sync_events`` silently
        # missing it. Confirmed live: migration ``0019``'s deterministic
        # ``permisos`` uuid landed on cloud AND branch independently (each
        # side's own migration run), each side's own enqueue trigger fired
        # for its own INSERT, and BOTH pushed the "same" row to the other
        # via the real ``/sync/events`` receiver — which, lacking this
        # check, blindly inserted a THIRD, fresh-uuid duplicate on each
        # side instead of recognizing the incoming uuid already existed.
        # Real defect confirmed live, 2026-10-06: the user requirement
        # for the ``sucursal`` table is "the only keys are UUIDs — an
        # edit is an UPDATE, not a new entity". The apply_guard
        # ``row_already_present`` check is the duplicate-prevention
        # mechanism for [V] re-applies, but it also blocks the
        # admin's UPDATE-in-place from reaching an already-known
        # branch uuid. The pull already bypasses this guard for
        # ``sucursal`` (see jobs/sync_sucursal.py::_pull_and_apply*),
        # so the catalog apply_row must let the apply through too.
        # Without this, the pull's resolved list includes the
        # sucursal row but apply_row returns "APPLIED" without
        # re-running the dispatch — the local copy keeps the OLD
        # field values forever.
        if (
            spec.audit_class == "V"
            and spec.name != "sucursal"
            and await apply_guard.row_already_present(
                session, spec.model_cls, payload.get("uuid")
            )
        ):
            return ApplyResult(status="APPLIED", row_uuid=payload.get("uuid"), reason=None)

        open_version = (
            await resolve_open_version(session, spec, payload)
            if spec.hook_pre_insert is not None
            else None
        )
        return await _catalog_apply_row(
            session,
            spec,
            payload,
            actor_uuid=actor_uuid,
            log_tx=log_tx,
            open_version=open_version,
        )

    async def _apply_row_legacy(
        self,
        session: AsyncSession,
        spec: SyncCatalogEntry,
        payload: dict[str, Any],
        *,
        actor_uuid: uuid_lib.UUID,
    ) -> ApplyResult:
        """Dispatch to the pre-catalog legacy applier, unchanged (D12).

        Real defect confirmed live, 2026-10-06: PR7's ``e98cc37d`` turned
        ``ConflictResolver`` into a shim that only returns a conflict
        resolution VERDICT (APPLIED / CONFLICT_V / CONFLICT_LS / ERROR)
        without actually writing the row to the data table. The
        catalog-side ``motor.apply_row.apply_row`` is the one that does
        the real write via ``_dispatch_repo_call`` — and it is the same
        path every non-LEGACY engine mode already uses. So under
        ``EngineMode.LEGACY`` the wire-level sync transport kept
        accepting batches (HTTP 207) and reporting ``status: applied``,
        but the row never landed in the target table — the receiver
        silently dropped every pushed row. The cloud's data tables
        appeared consistent only because a separate path (the catalog
        ``/sync/events`` handler, not the legacy ``/sync/push``) was
        used while the engine mode was still in transition; once
        ``_detect_applier_mode`` on the branch settled on legacy, the
        data stopped moving.

        Fix: keep the conflict resolution verdict (it's still
        semantically meaningful — the legacy path is the kill switch
        and we don't want a silent behavioral change) but ALSO run
        the actual catalog apply when the verdict is APPLIED. A
        CONFLICT_* verdict still short-circuits, matching the pre-PR7
        semantic (an operator-resolved conflict is not a write).
        """
        legacy_row = {
            "tabla": spec.name,
            "uuid_registro": payload.get("uuid") or uuid_lib.uuid4(),
            "datos": payload,
            "uuid_sucursal": payload.get("uuid_sucursal"),
            "timestamp_evento": payload.get("timestamp_evento"),
            "actor_uuid": actor_uuid,
        }
        outcome = await ConflictResolver().apply_pushed_row(session, legacy_row)
        if outcome is not ApplyOutcome.APPLIED:
            return ApplyResult(
                status=_LEGACY_OUTCOME_TO_STATUS[outcome],
                row_uuid=None,
                reason=None if outcome == ApplyOutcome.APPLIED else outcome.value,
            )

        # Legacy path's APPLIED verdict used to be the write itself
        # (pre-PR7 ConflictResolver was the applier). After PR7 the
        # shim only returns the verdict, so the row would be lost.
        # Delegate the actual write to the catalog applier — the
        # one path every non-LEGACY engine mode already trusts to
        # do the real INSERT, so a kill-switch flip to LEGACY now
        # preserves behavior instead of silently dropping data.
        # log_tx=True so the cloud writes its own audit log entry
        # for the applied row (the post-PR7 shim writes nothing,
        # so the catalog applier is the single log writer today).
        return await _catalog_apply_row(
            session,
            spec,
            payload,
            actor_uuid=actor_uuid,
            log_tx=True,
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

            outcome = None
            try:
                # Per-row SAVEPOINT. Without it, the first row that violates
                # a foreign key aborts the enclosing transaction and every
                # OTHER row in the batch is lost with it, even though most of
                # them are perfectly applicable. Isolating the failure here is
                # what turns "the whole pull is wedged" into "one row is
                # reported, the rest land".
                async with session.begin_nested():
                    outcome = await self.apply_row(
                        session, spec, payload, actor_uuid=actor_uuid, log_tx=log_tx
                    )
            except Exception as exc:  # noqa: BLE001 — isolate the row, keep the batch
                result.failed.append((spec, payload, describe_apply_error(exc)))
                result.failed_details.append(describe_apply_error_detail(exc))
                continue

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


__all__ = [
    "BatchResult",
    "ConflictResolution",
    "SyncMotor",
    "remap_foreign_keys",
    "resolve_identity_aliases",
]
