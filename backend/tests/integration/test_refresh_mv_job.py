"""test_refresh_mv_job.py -- HU-F1.5 / REQ-OPS-033.

TDD RED -> GREEN coverage for the ``RefreshMvOcupacionWorker`` cycle.

Pattern mirrors the precedent ``test_sync_sucursal_scenarios.py``:
mock the ``AsyncSession`` with ``unittest.mock.AsyncMock`` so the test
exercises ONLY the worker's ``cycle()`` body -- no live DB needed, no
``PARKOS_DOCKER_TEST`` gate.

H9 (2026-10): the worker connects as the app role, which does NOT own
``prod.mv_ocupacion_diaria``, so a direct ``REFRESH MATERIALIZED VIEW``
failed with "must be owner of materialized view" on both branches. The
refresh now goes through the SECURITY DEFINER helper
``prod.refresh_mv_ocupacion_diaria()`` (migration 0045), exactly like the
``/operacion`` API handlers do.

  T1 -- cycle_normal: ``cycle()`` calls the helper + ``commit()`` +
       ``asyncio.sleep(refresh_interval_s)``. Never a direct REFRESH.

  T2 -- cycle_failure: when the helper raises, the worker rolls back,
       logs ``refresh_mv_ocupacion_failed`` and does NOT fall back to a
       direct ``REFRESH`` (it would fail again for a non-owner role).

Both tests additionally assert:

  - The worker never raises (the cycle must return normally even on
    fallback failure -- RIESGO-SUC-02 accepted).
  - Log records do NOT contain ``pgcode`` / ``repr(exc)`` -- only
    ``exception_class``. R6 mitigation.
  - ``WorkerRunner`` base is untouched (``worker_base_intact`` CI
    gate, enforced by ``git diff`` separately).
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


def _make_mock_session(*, side_effects: list | None = None) -> AsyncSession:
    """Build an ``AsyncMock`` session whose ``.execute(...)`` and
    ``.commit()`` / ``.rollback()`` are pre-wired with optional
    side effects for the ``session.execute`` calls (the test feeds
    either a success path or a failure-then-success sequence)."""
    from unittest.mock import AsyncMock, MagicMock

    session = MagicMock(spec=AsyncSession)
    if side_effects is None:
        session.execute = AsyncMock(return_value=MagicMock())
    else:
        session.execute = AsyncMock(side_effect=side_effects)
    session.commit = AsyncMock(return_value=None)
    session.rollback = AsyncMock(return_value=None)
    return session


def _patch_sleep(monkeypatch: pytest.MonkeyPatch, captured: list[float]) -> None:
    """Replace ``parkos_core.jobs.refresh_mv_ocupacion.asyncio.sleep``
    so the test does not block on the real sleep. Each call appends
    the requested sleep duration to ``captured`` for assertions."""

    async def _fake_sleep(seconds: float) -> None:
        captured.append(float(seconds))

    monkeypatch.setattr(
        "parkos_core.jobs.refresh_mv_ocupacion.asyncio.sleep",
        _fake_sleep,
    )


# ---------------------------------------------------------------------------
# T1 -- cycle_normal
# ---------------------------------------------------------------------------

REFRESH_HELPER_SQL = "SELECT prod.refresh_mv_ocupacion_diaria()"


def _worker_not_fresh(session: AsyncSession):  # type: ignore[no-untyped-def]
    """Build a worker whose freshness guard (REQ-OPS-133) reports "stale"
    so ``cycle()`` reaches the refresh step with a mocked session."""
    from parkos_core.jobs.refresh_mv_ocupacion import RefreshMvOcupacionWorker

    worker = RefreshMvOcupacionWorker(session=session, refresh_interval_s=10)

    async def _not_fresh() -> bool:
        return False

    worker._is_mv_fresh = _not_fresh  # type: ignore[method-assign]
    return worker


async def test_cycle_normal_calls_security_definer_helper_then_sleeps(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """``cycle()`` refreshes via ``prod.refresh_mv_ocupacion_diaria()``
    (never a direct REFRESH), commits, and sleeps ``refresh_interval_s``."""
    captured_sleep: list[float] = []
    _patch_sleep(monkeypatch, captured_sleep)

    session = _make_mock_session()
    worker = _worker_not_fresh(session)
    with caplog.at_level(logging.DEBUG, logger="parkos_core.jobs.refresh_mv_ocupacion"):
        await worker.cycle()

    execute_calls = session.execute.await_args_list
    assert [str(c.args[0]) for c in execute_calls] == [REFRESH_HELPER_SQL], (
        f"cycle MUST call only the SECURITY DEFINER helper; got "
        f"{[str(c.args[0]) for c in execute_calls]!r}"
    )
    assert session.commit.await_count == 1
    assert session.rollback.await_count == 0
    assert captured_sleep == [10.0]
    assert any(
        rec.message == "refresh_mv_ocupacion_cycle_ok" for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# T2 -- cycle_failure (no direct-REFRESH fallback)
# ---------------------------------------------------------------------------


async def test_cycle_helper_failure_logs_and_does_not_fall_back_to_direct_refresh(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """If the helper raises, the worker rolls back, logs
    ``refresh_mv_ocupacion_failed`` (exception class only, R6) and returns
    normally; it never issues a direct ``REFRESH MATERIALIZED VIEW``."""
    captured_sleep: list[float] = []
    _patch_sleep(monkeypatch, captured_sleep)

    fake_exc = RuntimeError("must be owner of materialized view")
    session = _make_mock_session(side_effects=[fake_exc])
    worker = _worker_not_fresh(session)
    with caplog.at_level(
        logging.WARNING, logger="parkos_core.jobs.refresh_mv_ocupacion"
    ):
        await worker.cycle()  # KD-5: MUST NOT raise

    execute_calls = session.execute.await_args_list
    assert [str(c.args[0]) for c in execute_calls] == [REFRESH_HELPER_SQL]
    assert not any(
        "REFRESH MATERIALIZED VIEW" in str(c.args[0]) for c in execute_calls
    )
    assert session.commit.await_count == 0
    assert session.rollback.await_count == 1
    assert captured_sleep == [10.0]

    failed = [r for r in caplog.records if r.message == "refresh_mv_ocupacion_failed"]
    assert len(failed) == 1
    assert failed[0].exception_class == "RuntimeError"  # type: ignore[attr-defined]

    for rec in caplog.records:
        rendered = rec.getMessage() + " " + str(rec.__dict__)
        assert "pgcode" not in rendered

    # JB1: the line now carries the (sanitized) message so operators can see
    # the cause; it was blind before and hid a SQL syntax error.
    assert "must be owner" in failed[0].error  # type: ignore[attr-defined]


def test_sanitize_error_redacts_credentials_and_truncates() -> None:
    from parkos_core.jobs.refresh_mv_ocupacion import sanitize_error

    out = sanitize_error(
        RuntimeError("connect postgresql+asyncpg://user:s3cret@host/db failed " + "x" * 900)
    )
    assert "s3cret" not in out and "user:" not in out
    assert "***@host" in out
    assert len(out) <= 300


async def test_health_degrades_after_consecutive_failures_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[float] = []
    _patch_sleep(monkeypatch, captured)
    session = _make_mock_session(side_effects=[RuntimeError("boom")] * 3 + [MagicMock()])
    worker = _worker_not_fresh(session)
    assert worker.health_report()["ok"] is True
    for _ in range(3):
        await worker.cycle()
    report = worker.health_report()
    assert report["ok"] is False
    assert report["consecutive_failures"] == 3
    assert report["last_error_class"] == "RuntimeError"
    await worker.cycle()  # success
    assert worker.health_report()["ok"] is True


# ---------------------------------------------------------------------------
# T3 -- freshness guard: never-analyzed MV is STALE (D1)
# ---------------------------------------------------------------------------


def _session_returning_seconds(seconds):  # type: ignore[no-untyped-def]
    """Session whose stats lookup returns one row ``(seconds,)``."""
    from unittest.mock import AsyncMock, MagicMock

    session = MagicMock(spec=AsyncSession)
    result = MagicMock()
    result.first.return_value = (seconds,)
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.parametrize(
    ("seconds", "expected_fresh"),
    [
        (None, False),  # never analyzed: must be refreshed, NOT skipped forever
        (5.0, True),  # analyzed moments ago: inside the REQ-OPS-133 window
        (3600.0, False),  # analyzed long ago: refresh
    ],
)
async def test_is_mv_fresh_treats_never_analyzed_as_stale(
    seconds: float | None, expected_fresh: bool
) -> None:
    from parkos_core.jobs.refresh_mv_ocupacion import RefreshMvOcupacionWorker

    worker = RefreshMvOcupacionWorker(
        session=_session_returning_seconds(seconds), refresh_interval_s=10
    )
    assert await worker._is_mv_fresh() is expected_fresh


async def test_is_mv_fresh_sql_does_not_coalesce_missing_analyze_to_now() -> None:
    """``coalesce(last_analyze, now())`` made a never-analyzed MV look 0s old
    (fresh forever). The query must leave NULL as NULL."""
    from parkos_core.jobs.refresh_mv_ocupacion import RefreshMvOcupacionWorker

    session = _session_returning_seconds(None)
    await RefreshMvOcupacionWorker(session=session)._is_mv_fresh()
    sql = str(session.execute.await_args_list[0].args[0])
    after_coalesce = sql.lower().split("coalesce", 1)[1]
    assert "now()" not in after_coalesce
    assert "pg_stat_get_last_autoanalyze_time" in sql


async def test_cycle_refreshes_when_mv_was_never_analyzed() -> None:
    """End-to-end on the cycle: NULL stats -> the helper IS invoked."""
    from unittest.mock import AsyncMock, MagicMock

    from parkos_core.jobs.refresh_mv_ocupacion import RefreshMvOcupacionWorker

    stats = MagicMock()
    stats.first.return_value = (None,)
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock(side_effect=[stats, MagicMock()])
    session.commit = AsyncMock(return_value=None)
    session.rollback = AsyncMock(return_value=None)
    captured: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        captured.append(float(seconds))

    import parkos_core.jobs.refresh_mv_ocupacion as mod

    orig = mod.asyncio.sleep
    mod.asyncio.sleep = _fake_sleep  # type: ignore[assignment]
    try:
        await RefreshMvOcupacionWorker(session=session, refresh_interval_s=10).cycle()
    finally:
        mod.asyncio.sleep = orig  # type: ignore[assignment]
    assert [str(c.args[0]) for c in session.execute.await_args_list][-1] == REFRESH_HELPER_SQL
    assert session.commit.await_count == 1


__all__ = [
    "test_cycle_helper_failure_logs_and_does_not_fall_back_to_direct_refresh",
    "test_cycle_normal_calls_security_definer_helper_then_sleeps",
]
