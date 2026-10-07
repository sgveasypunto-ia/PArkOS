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

    fake_exc = RuntimeError("must be owner of materialized view (no pgcode)")
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
        assert "must be owner" not in rendered, (
            f"log MUST NOT contain the original exception message (R6); "
            f"got {rendered!r}"
        )


__all__ = [
    "test_cycle_helper_failure_logs_and_does_not_fall_back_to_direct_refresh",
    "test_cycle_normal_calls_security_definer_helper_then_sleeps",
]
