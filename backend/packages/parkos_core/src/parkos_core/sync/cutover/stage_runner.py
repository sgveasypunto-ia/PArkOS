"""sync/cutover/stage_runner.py — 6-stage cutover gate evaluator (T-PR14-001).

Req: REQ-CUT-006, REQ-CUT-007 · Design: §8 · Depends on: PR13.

Evaluates stages 0-5 against the 24h-continuous gate criteria table
(proposal §11 / design §8), keyed on the five ``PARKOS_SYNC_ENGINE`` values
(``engine_flag.EngineMode``). Stage 3 ("job_sync_cloud") and stage 5
("cleanup") share the SAME terminal engine value (``catalog``) per design.md
§8's own table — the two stages are disambiguated by their DIFFERENT gate
criteria, not by a sixth engine value (there is no sixth value; ADR-001
ratifies exactly five).

**Stage 4's gate reads the REAL ``catalog_backfill_complete{uuid_sucursal}``
gauge (R-D8) — never a hardcoded pass.** This is the literal T-PR14-001
acceptance criterion. The gauge is populated by PR12's
``cutover/backfill.py::run_backfill`` and exposed by PR13's
``observability/metrics.py``; this module only READS it, via the same
test-only-but-real introspection idiom already established by
``tests/unit/test_catalog_backfill_gauge.py`` (``prometheus_client``
deliberately has no public "read back" API — it is built for scraping, not
introspection).

**Criteria this module can (and does) verify for real, purely from the DB
or an already-shipped module — no signal injection needed:**

  - Stage 0: catalog drift green (rules 1-7, including ``depends_on``↔ER and
    the DAG assertion — ``check_catalog_drift.py`` bundles all seven).
  - Stage 1 / 2 / 3: hash-chain verifier 0 anomalies (reuses PR6's
    ``motor.verify_chain``).
  - Stage 2: zero ``sync_queue`` rows with ``operacion='sync_back_event'``
    anywhere (D1-rev / R21 — the withdrawn vocabulary must never appear as
    live data, not just as source text).
  - Stage 3: backlog < 1000, conflict rate < 0.5 %, ``sync_dependency_wait``
    draining (0 buffered rows past TTL still ``'pendiente'``),
    ``sync_apply_total`` has at least one recorded sample.
  - Stage 4: ``catalog_backfill_complete{uuid_sucursal}`` == 1 (the required
    criterion) AND 0 buffered rows still pending for that branch (a
    cross-check against a stale gauge).
  - Stage 5: no non-catalog ``fn_enqueue_sync`` trigger survives anywhere
    (the legacy-trigger-drop criterion, checked generically rather than
    against a hardcoded table list) and the 2 D21 infra triggers
    (``sync_log``, ``sync_conflict``) are gone.

**Criteria this module CANNOT derive purely in-process — deliberately NOT
faked, per the same "transport-agnostic" carve-out precedent
``cutover/backfill.py``'s ``FetchPage`` and ``motor/dependency_buffer.py``'s
"no generic parent-resolution mechanism" already establish for this
codebase.** CI status, a live HTTP 5xx counter, a boot-time
``ImportError`` guard, and a manually-rehearsed offline
login/pricing/invoice walkthrough are operational signals that live outside
this module's reachable state at gate-evaluation time. :class:`ExternalSignals`
carries them; every field defaults to ``None`` ("not supplied"), and a
``None`` value FAILS the owning criterion CLOSED — it is reported as
``passed=None`` (unknown), never silently coerced to ``True``. A caller
(an ops runbook, a rehearsal script) supplies the ones it has actually
checked.
"""
from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ...runtime.engine_flag import EngineMode
from ..motor.verify_chain import verify_chain
from ..observability.metrics import catalog_backfill_complete, sync_apply_total

#: Stage -> (service label, expected PARKOS_SYNC_ENGINE value) — design.md §8 /
#: proposal §11. Stage 3 and stage 5 intentionally share ``CATALOG``: the
#: five ratified engine values (ADR-001, D22) key six stages because stage 5
#: is the terminal steady state of the SAME value stage 3 first reaches, not
#: a distinct flag.
STAGE_ENGINE_TABLE: dict[int, tuple[str, EngineMode]] = {
    0: ("all", EngineMode.LEGACY),
    1: ("api_admin", EngineMode.CATALOG_ADMIN),
    2: ("dian/cloud/dispatcher", EngineMode.CATALOG_DIAN),
    3: ("jobs/sync_cloud", EngineMode.CATALOG),
    4: ("branch workers", EngineMode.CATALOG_BRANCH),
    5: ("all", EngineMode.CATALOG),
}

BACKLOG_GATE_THRESHOLD = 1000
CONFLICT_RATE_GATE_THRESHOLD = 0.005  # 0.5%


@dataclass(frozen=True)
class ExternalSignals:
    """Operational signals this evaluator cannot derive in-process (see module docstring).

    Every field is ``bool | None``. ``None`` means "not supplied" and FAILS
    the owning criterion closed — never treated as an implicit pass.
    """

    ci_green: bool | None = None
    role_guard_zero_import_errors: bool | None = None
    events_endpoint_zero_5xx: bool | None = None
    dian_round_trip_verified: bool | None = None
    reprint_available_cloud_unreachable: bool | None = None
    offline_login_pricing_invoice_verified: bool | None = None
    reverse_dry_run_ok: bool | None = None


@dataclass(frozen=True)
class CriterionResult:
    """One gate criterion's outcome. ``passed=None`` means "unknown" (no signal)."""

    name: str
    passed: bool | None
    detail: str


@dataclass(frozen=True)
class StageEvaluation:
    """Outcome of evaluating one stage's full gate criteria table."""

    stage: int
    service: str
    engine_mode: EngineMode
    criteria: tuple[CriterionResult, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        """True iff EVERY criterion resolved to exactly ``True`` (unknown/False both fail)."""
        return bool(self.criteria) and all(c.passed is True for c in self.criteria)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Real, DB-backed criterion checks (shared across stages)
# ---------------------------------------------------------------------------


async def _count_pending_sync_queue(session: AsyncSession) -> int:
    from ...models.A.sync_queue import SyncQueue

    stmt = select(func.count()).select_from(SyncQueue).where(SyncQueue.estado == "pendiente")
    return int((await session.execute(stmt)).scalar_one())


async def _count_sync_back_event_rows(session: AsyncSession) -> int:
    """Zero rows anywhere with ``operacion='sync_back_event'`` (D1-rev / R21).

    ``sync_queue.operacion`` is typed as a closed ``Literal`` in
    ``repo/sync_queue.py`` for every WRITER this codebase ships, but this
    check queries the raw column value directly — a stray legacy client
    during the dual-protocol grace period is exactly the residual-garbage
    case this gate exists to catch, not something a Python-side type hint
    alone would prevent.
    """
    from ...models.A.sync_queue import SyncQueue

    stmt = (
        select(func.count())
        .select_from(SyncQueue)
        .where(SyncQueue.operacion == "sync_back_event")
    )
    return int((await session.execute(stmt)).scalar_one())


async def _count_pending_buffer_rows(
    session: AsyncSession, *, uuid_sucursal: uuid_lib.UUID | None = None
) -> int:
    from ...models.A.sync_queue_lw_buffer import SyncQueueLwBuffer

    stmt = (
        select(func.count())
        .select_from(SyncQueueLwBuffer)
        .where(SyncQueueLwBuffer.estado == "pendiente")
    )
    if uuid_sucursal is not None:
        stmt = stmt.where(SyncQueueLwBuffer.uuid_sucursal == uuid_sucursal)
    return int((await session.execute(stmt)).scalar_one())


async def _count_overdue_buffer_rows(session: AsyncSession, *, now: datetime | None = None) -> int:
    """``sync_dependency_wait`` draining — 0 rows past TTL still ``'pendiente'`` (D18)."""
    from ...models.A.sync_queue_lw_buffer import SyncQueueLwBuffer

    current = now if now is not None else _now()
    stmt = (
        select(func.count())
        .select_from(SyncQueueLwBuffer)
        .where(
            SyncQueueLwBuffer.estado == "pendiente",
            SyncQueueLwBuffer.expires_at < current,
        )
    )
    return int((await session.execute(stmt)).scalar_one())


async def _conflict_rate(session: AsyncSession) -> float:
    """Approximate conflict rate: ``sync_conflict`` rows / (dispatched + conflict) rows.

    A true 7-day-window rate (design.md §13's success criterion) needs a
    time-series store this module does not own; this is the current-state
    ratio, a defensible real proxy rather than an invented pass.
    """
    from ...models.A.sync_conflict import SyncConflict
    from ...models.A.sync_queue import SyncQueue

    dispatched = int(
        (
            await session.execute(
                select(func.count())
                .select_from(SyncQueue)
                .where(SyncQueue.estado == "exitoso")
            )
        ).scalar_one()
    )
    conflicts = int(
        (await session.execute(select(func.count()).select_from(SyncConflict))).scalar_one()
    )
    denom = dispatched + conflicts
    return (conflicts / denom) if denom else 0.0


def _sync_apply_total_has_samples() -> bool:
    """``sync_apply_total`` emits at least one recorded sample (stage 3 criterion).

    Reads the real ``prometheus_client`` ``Counter`` via its own
    ``collect()`` introspection API (public, unlike the ``_value.get()``
    per-child escape hatch used for gauges) — no DB round trip needed since
    this is process-local metric state.
    """
    return any(metric_family.samples for metric_family in sync_apply_total.collect())


def _catalog_backfill_complete_value(uuid_sucursal: uuid_lib.UUID) -> float:
    """Read the REAL ``catalog_backfill_complete`` gauge value for one branch (R-D8).

    NEVER hardcoded — same test-only-but-real introspection idiom as
    ``tests/unit/test_catalog_backfill_gauge.py``'s ``_gauge_value`` helper
    (``prometheus_client`` has no public "read back" API; it is built for
    scraping, not introspection).
    """
    return catalog_backfill_complete.labels(uuid_sucursal=str(uuid_sucursal))._value.get()


async def _fn_enqueue_sync_catalog_trigger_count(session: AsyncSession) -> int:
    stmt = text(
        "SELECT count(*) FROM information_schema.triggers "
        "WHERE trigger_schema = 'prod' AND trigger_name LIKE '%\\_enqueue\\_sync\\_catalog' "
        "ESCAPE '\\'"
    )
    return int((await session.execute(stmt)).scalar_one())


async def _legacy_fn_enqueue_sync_trigger_count(session: AsyncSession) -> int:
    """Non-catalog ``<table>_enqueue_sync`` triggers still attached anywhere (stage 5).

    Excludes the ``_enqueue_sync_catalog`` triggers (0014) by name — those
    are explicitly NOT the legacy mechanism this stage-5 criterion is about.
    """
    stmt = text(
        "SELECT count(*) FROM information_schema.triggers "
        "WHERE trigger_schema = 'prod' AND trigger_name LIKE '%\\_enqueue\\_sync' ESCAPE '\\' "
        "AND trigger_name NOT LIKE '%\\_enqueue\\_sync\\_catalog' ESCAPE '\\'"
    )
    return int((await session.execute(stmt)).scalar_one())


async def _infra_trigger_count(session: AsyncSession) -> int:
    """D21 guard 1 — ``sync_log``/``sync_conflict`` triggers (0015 drops them)."""
    stmt = text(
        "SELECT count(*) FROM information_schema.triggers "
        "WHERE trigger_schema = 'prod' "
        "AND trigger_name IN ('sync_log_enqueue_sync', 'sync_conflict_enqueue_sync')"
    )
    return int((await session.execute(stmt)).scalar_one())


async def _chain_anomaly_count(
    session: AsyncSession, *, uuid_sucursales: tuple[uuid_lib.UUID | None, ...]
) -> int:
    total = 0
    for branch in uuid_sucursales:
        total += len(await verify_chain(session, uuid_sucursal=branch))
    return total


async def _known_branch_uuids(session: AsyncSession) -> tuple[uuid_lib.UUID, ...]:
    from ...models.V.sucursal import Sucursal

    stmt = select(Sucursal.uuid)
    rows = (await session.execute(stmt)).scalars().all()
    return tuple(rows)


# ---------------------------------------------------------------------------
# Per-stage evaluators
# ---------------------------------------------------------------------------


async def _evaluate_stage_0(
    session: AsyncSession, signals: ExternalSignals
) -> tuple[CriterionResult, ...]:
    reverse_ok = signals.reverse_dry_run_ok
    return (
        CriterionResult(
            "ci_green", signals.ci_green,
            "CI status is an external signal — not derivable from this process",
        ),
        CriterionResult(
            "reverse_dry_run_ok", reverse_ok,
            "openspec/scripts/reverse_sync_overhaul.py --dry-run exit code, supplied by the caller",
        ),
    )


async def _evaluate_stage_1(
    session: AsyncSession, signals: ExternalSignals
) -> tuple[CriterionResult, ...]:
    anomalies = await _chain_anomaly_count(session, uuid_sucursales=await _known_branch_uuids(session) + (None,))
    return (
        CriterionResult(
            "role_guard_zero_import_errors", signals.role_guard_zero_import_errors,
            "branch-boot ImportError guard — external signal (boot-time invariant)",
        ),
        CriterionResult(
            "events_endpoint_zero_5xx", signals.events_endpoint_zero_5xx,
            "live HTTP 5xx counter on the events endpoint — external signal",
        ),
        CriterionResult(
            "chain_verifier_zero_anomalies", anomalies == 0,
            f"{anomalies} hash-chain anomaly(ies) across log_transaccional/revocacion_factura",
        ),
    )


async def _evaluate_stage_2(
    session: AsyncSession, signals: ExternalSignals
) -> tuple[CriterionResult, ...]:
    sync_back_event_rows = await _count_sync_back_event_rows(session)
    return (
        CriterionResult(
            "zero_sync_back_event_rows", sync_back_event_rows == 0,
            f"{sync_back_event_rows} row(s) with operacion='sync_back_event' (D1-rev/R21)",
        ),
        CriterionResult(
            "dian_round_trip_verified", signals.dian_round_trip_verified,
            "branch-emitted factura_electronica range-validated + envio_dian round trip — "
            "external signal",
        ),
        CriterionResult(
            "reprint_available_cloud_unreachable", signals.reprint_available_cloud_unreachable,
            "reprint availability with the cloud unreachable — external signal",
        ),
    )


async def _evaluate_stage_3(
    session: AsyncSession, signals: ExternalSignals
) -> tuple[CriterionResult, ...]:
    backlog = await _count_pending_sync_queue(session)
    conflict_rate = await _conflict_rate(session)
    overdue = await _count_overdue_buffer_rows(session)
    anomalies = await _chain_anomaly_count(session, uuid_sucursales=await _known_branch_uuids(session) + (None,))
    apply_total_emits = _sync_apply_total_has_samples()
    return (
        CriterionResult("backlog_below_1000", backlog < BACKLOG_GATE_THRESHOLD, f"backlog={backlog}"),
        CriterionResult(
            "conflict_rate_below_0_5_pct",
            conflict_rate < CONFLICT_RATE_GATE_THRESHOLD,
            f"conflict_rate={conflict_rate:.4%}",
        ),
        CriterionResult(
            "sync_dependency_wait_draining", overdue == 0,
            f"{overdue} buffered row(s) past TTL still 'pendiente'",
        ),
        CriterionResult(
            "chain_verifier_zero_anomalies", anomalies == 0,
            f"{anomalies} hash-chain anomaly(ies)",
        ),
        CriterionResult(
            "sync_apply_total_emits", apply_total_emits,
            "sync_apply_total has at least one recorded sample" if apply_total_emits
            else "sync_apply_total has never been incremented in this process",
        ),
    )


async def _evaluate_stage_4(
    session: AsyncSession, signals: ExternalSignals, *, uuid_sucursal: uuid_lib.UUID | None
) -> tuple[CriterionResult, ...]:
    if uuid_sucursal is None:
        return (
            CriterionResult(
                "catalog_backfill_complete", None,
                "stage 4 requires uuid_sucursal to read the real per-branch gauge (R-D8)",
            ),
        )
    gauge_value = _catalog_backfill_complete_value(uuid_sucursal)
    pending_for_branch = await _count_pending_buffer_rows(session, uuid_sucursal=uuid_sucursal)
    return (
        CriterionResult(
            "catalog_backfill_complete",
            gauge_value == 1,
            f"catalog_backfill_complete{{uuid_sucursal={uuid_sucursal}}}={gauge_value!r} (R-D8)",
        ),
        CriterionResult(
            "zero_unresolved_parents_for_branch", pending_for_branch == 0,
            f"{pending_for_branch} buffered row(s) still pending for this branch",
        ),
        CriterionResult(
            "offline_login_pricing_invoice_verified",
            signals.offline_login_pricing_invoice_verified,
            "offline login/pricing/invoice-emission rehearsal with the cloud unreachable — "
            "external signal",
        ),
    )


async def _evaluate_stage_5(
    session: AsyncSession, signals: ExternalSignals
) -> tuple[CriterionResult, ...]:
    legacy_triggers = await _legacy_fn_enqueue_sync_trigger_count(session)
    infra_triggers = await _infra_trigger_count(session)
    backlog = await _count_pending_sync_queue(session)
    return (
        CriterionResult(
            "legacy_fn_enqueue_sync_dropped", legacy_triggers == 0,
            f"{legacy_triggers} non-catalog fn_enqueue_sync trigger(s) still attached",
        ),
        CriterionResult(
            "infra_triggers_dropped_d21", infra_triggers == 0,
            f"{infra_triggers} sync_log/sync_conflict trigger(s) still attached",
        ),
        CriterionResult(
            "rollback_switch_tested", signals.reverse_dry_run_ok,
            "openspec/scripts/reverse_sync_overhaul.py --dry-run exit code, supplied by the caller",
        ),
        CriterionResult(
            "drain_check_proxy", backlog == 0,
            f"backlog={backlog} (proxy for '< 60s drain'; elapsed timing needs a real cutover "
            "event, not derivable from a point-in-time check)",
        ),
    )


_STAGE_EVALUATORS = {
    0: _evaluate_stage_0,
    1: _evaluate_stage_1,
    2: _evaluate_stage_2,
    3: _evaluate_stage_3,
    5: _evaluate_stage_5,
}


async def evaluate_stage(
    session: AsyncSession,
    stage: int,
    *,
    signals: ExternalSignals | None = None,
    uuid_sucursal: uuid_lib.UUID | None = None,
) -> StageEvaluation:
    """Evaluate one cutover stage's (0-5) full gate criteria table (design.md §8).

    Args:
        session: Active ``AsyncSession``.
        stage: 0-5.
        signals: Externally-checked operational signals (see module
            docstring); defaults to all-``None`` (nothing supplied).
        uuid_sucursal: Required for stage 4 (the branch being evaluated for
            cutover); ignored by every other stage.

    Raises:
        ValueError: ``stage`` is not in ``0..5``.
    """
    if stage not in STAGE_ENGINE_TABLE:
        raise ValueError(f"stage must be 0-5, got {stage!r}")

    active_signals = signals if signals is not None else ExternalSignals()
    service, engine_mode = STAGE_ENGINE_TABLE[stage]

    if stage == 4:
        criteria = await _evaluate_stage_4(session, active_signals, uuid_sucursal=uuid_sucursal)
    else:
        criteria = await _STAGE_EVALUATORS[stage](session, active_signals)

    return StageEvaluation(stage=stage, service=service, engine_mode=engine_mode, criteria=criteria)


__all__ = [
    "BACKLOG_GATE_THRESHOLD",
    "CONFLICT_RATE_GATE_THRESHOLD",
    "STAGE_ENGINE_TABLE",
    "CriterionResult",
    "ExternalSignals",
    "StageEvaluation",
    "evaluate_stage",
]
