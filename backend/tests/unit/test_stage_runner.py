"""test_stage_runner.py — T-PR14-001 acceptance for ``cutover/stage_runner.py``.

Req: REQ-CUT-006, REQ-CUT-007 · Design: §8 · Depends on: PR13.

Exercises all 6 stages against a real testcontainers Postgres (``pg_session``)
plus the real ``prometheus_client`` metric objects — no hardcoded pass for
stage 4's ``catalog_backfill_complete`` gate (the literal T-PR14-001
acceptance criterion).
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest
from parkos_core.sync.cutover.stage_runner import (
    ExternalSignals,
    StageEvaluation,
    evaluate_stage,
)
from parkos_core.sync.observability.metrics import (
    catalog_backfill_complete,
    sync_apply_total,
)
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Stage table / evaluation shape
# ---------------------------------------------------------------------------


async def test_invalid_stage_raises(pg_session: AsyncSession) -> None:
    with pytest.raises(ValueError):
        await evaluate_stage(pg_session, 6)
    with pytest.raises(ValueError):
        await evaluate_stage(pg_session, -1)


async def test_stage_evaluation_passed_is_false_when_any_criterion_unknown(
    pg_session: AsyncSession,
) -> None:
    """No signals supplied — every external criterion is None (unknown) — never a pass."""
    evaluation = await evaluate_stage(pg_session, 0)
    assert isinstance(evaluation, StageEvaluation)
    assert evaluation.passed is False
    assert any(c.passed is None for c in evaluation.criteria)


async def test_stage_0_passes_when_externals_supplied(pg_session: AsyncSession) -> None:
    evaluation = await evaluate_stage(
        pg_session, 0, signals=ExternalSignals(ci_green=True, reverse_dry_run_ok=True)
    )
    assert evaluation.passed is True


# ---------------------------------------------------------------------------
# Stage 1 — chain verifier (real, DB-backed)
# ---------------------------------------------------------------------------


async def test_stage_1_chain_verifier_reflects_real_db_state(pg_session: AsyncSession) -> None:
    """The gate's chain-verifier criterion mirrors ``motor.verify_chain``'s REAL output —
    not a hardcoded pass. Computed independently rather than asserted as an
    a-priori "clean DB" (this test may run inside the full suite, after
    OTHER tests' own deliberate hash-chain-break fixtures have already
    committed real, intentional anomalies for their own purposes — see this
    file's own module docstring and the PR14 apply report's "Issues Found"
    section)."""
    from parkos_core.models.V.sucursal import Sucursal
    from parkos_core.sync.motor.verify_chain import verify_chain
    from sqlalchemy import select

    branches = (await pg_session.execute(select(Sucursal.uuid))).scalars().all()
    expected_anomalies = 0
    for branch in (*branches, None):
        expected_anomalies += len(await verify_chain(pg_session, uuid_sucursal=branch))

    evaluation = await evaluate_stage(
        pg_session,
        1,
        signals=ExternalSignals(role_guard_zero_import_errors=True, events_endpoint_zero_5xx=True),
    )
    chain_criterion = next(
        c for c in evaluation.criteria if c.name == "chain_verifier_zero_anomalies"
    )
    assert chain_criterion.passed == (expected_anomalies == 0)
    assert evaluation.passed == (expected_anomalies == 0)


# ---------------------------------------------------------------------------
# Stage 2 — zero sync_back_event rows (D1-rev/R21) — real DB check
# ---------------------------------------------------------------------------


async def test_stage_2_passes_with_zero_sync_back_event_rows(pg_session: AsyncSession) -> None:
    evaluation = await evaluate_stage(
        pg_session,
        2,
        signals=ExternalSignals(
            dian_round_trip_verified=True, reprint_available_cloud_unreachable=True
        ),
    )
    criterion = next(c for c in evaluation.criteria if c.name == "zero_sync_back_event_rows")
    assert criterion.passed is True
    assert evaluation.passed is True


async def test_stage_2_fails_when_a_sync_back_event_row_exists(pg_session: AsyncSession) -> None:
    """A residual row with the withdrawn operacion value fails the gate (D1-rev/R21).

    ``repo.sync_queue.enqueue``'s ``Operacion`` Literal only accepts the 4
    live values at the type-checker level; a stray legacy client posting
    the withdrawn value straight to the DB is exactly the residual-garbage
    case this gate exists to catch, so the row is constructed directly
    (bypassing the Python-side type hint, which cannot stop a raw DB write).
    """
    from datetime import UTC, datetime

    from parkos_core.models.A.sync_queue import SyncQueue

    row = SyncQueue(
        uuid_sucursal=None,
        operacion="sync_back_event",
        tabla="factura_electronica",
        uuid_registro=uuid_lib.uuid4(),
        datos={"seq": 1},
        prioridad=0,
        estado="pendiente",
        intentos=0,
        created_at=datetime.now(UTC).replace(tzinfo=None),
        sync_status="pendiente",
    )
    pg_session.add(row)
    await pg_session.flush()

    evaluation = await evaluate_stage(pg_session, 2)
    criterion = next(c for c in evaluation.criteria if c.name == "zero_sync_back_event_rows")
    assert criterion.passed is False
    assert evaluation.passed is False


# ---------------------------------------------------------------------------
# Stage 3 — backlog / conflict-rate / dependency-wait / chain / apply_total
# ---------------------------------------------------------------------------


async def test_stage_3_real_criteria_pass_on_clean_db(pg_session: AsyncSession) -> None:
    # sync_apply_total must show at least one recorded sample (real Counter read).
    sync_apply_total.labels(
        status="APPLIED", tabla="clientes", uuid_sucursal=str(uuid_lib.uuid4()), audit_class="V"
    ).inc()

    # The chain-verifier criterion mirrors REAL DB state (see
    # test_stage_1_chain_verifier_reflects_real_db_state's docstring) —
    # computed independently rather than assumed clean, since this test may
    # run inside the full suite after other tests' own deliberate
    # hash-chain-break fixtures have committed real anomalies.
    from parkos_core.models.V.sucursal import Sucursal
    from parkos_core.sync.motor.verify_chain import verify_chain
    from sqlalchemy import select

    branches = (await pg_session.execute(select(Sucursal.uuid))).scalars().all()
    expected_anomalies = 0
    for branch in (*branches, None):
        expected_anomalies += len(await verify_chain(pg_session, uuid_sucursal=branch))

    evaluation = await evaluate_stage(pg_session, 3)
    by_name = {c.name: c for c in evaluation.criteria}
    assert by_name["backlog_below_1000"].passed is True
    assert by_name["conflict_rate_below_0_5_pct"].passed is True
    assert by_name["sync_dependency_wait_draining"].passed is True
    assert by_name["chain_verifier_zero_anomalies"].passed == (expected_anomalies == 0)
    assert by_name["sync_apply_total_emits"].passed is True
    assert evaluation.passed == (expected_anomalies == 0)


# ---------------------------------------------------------------------------
# Stage 4 — REAL catalog_backfill_complete gauge (T-PR14-001's literal
# acceptance criterion: never a hardcoded pass)
# ---------------------------------------------------------------------------


async def test_stage_4_requires_uuid_sucursal(pg_session: AsyncSession) -> None:
    evaluation = await evaluate_stage(pg_session, 4, uuid_sucursal=None)
    criterion = next(c for c in evaluation.criteria if c.name == "catalog_backfill_complete")
    assert criterion.passed is None
    assert evaluation.passed is False


async def test_stage_4_gate_reads_real_gauge_not_hardcoded(pg_session: AsyncSession) -> None:
    """The gauge defaults to 0 for a branch never observed — the gate must fail, not pass."""
    unseen_branch = uuid_lib.uuid4()
    evaluation = await evaluate_stage(pg_session, 4, uuid_sucursal=unseen_branch)
    criterion = next(c for c in evaluation.criteria if c.name == "catalog_backfill_complete")
    assert criterion.passed is False
    assert "0.0" in criterion.detail or "0" in criterion.detail


async def test_stage_4_gate_passes_once_the_real_gauge_is_set(pg_session: AsyncSession) -> None:
    branch = uuid_lib.uuid4()
    catalog_backfill_complete.labels(uuid_sucursal=str(branch)).set(1)

    evaluation = await evaluate_stage(
        pg_session, 4, uuid_sucursal=branch,
        signals=ExternalSignals(offline_login_pricing_invoice_verified=True),
    )
    criterion = next(c for c in evaluation.criteria if c.name == "catalog_backfill_complete")
    assert criterion.passed is True
    assert evaluation.passed is True


# ---------------------------------------------------------------------------
# Stage 5 — trigger-drop checks (real DB introspection)
# ---------------------------------------------------------------------------


async def test_stage_5_infra_triggers_already_dropped_by_migration_0015(
    pg_session: AsyncSession,
) -> None:
    """0015_drop_infra_triggers.py already dropped sync_log/sync_conflict triggers."""
    evaluation = await evaluate_stage(
        pg_session, 5, signals=ExternalSignals(reverse_dry_run_ok=True)
    )
    by_name = {c.name: c for c in evaluation.criteria}
    assert by_name["infra_triggers_dropped_d21"].passed is True


async def test_stage_5_legacy_triggers_still_present_before_actual_cutover(
    pg_session: AsyncSession,
) -> None:
    """Legacy fn_enqueue_sync triggers on the 26 [V]/other [A] tables are NOT dropped by
    any migration in this repo (design.md §12: dropped only at real stage-5 cutover, an
    operational action, not a migration) — the gate correctly reports this as not-yet-done."""
    evaluation = await evaluate_stage(pg_session, 5)
    by_name = {c.name: c for c in evaluation.criteria}
    assert by_name["legacy_fn_enqueue_sync_dropped"].passed is False
    assert evaluation.passed is False
