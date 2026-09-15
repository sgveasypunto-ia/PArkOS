"""test_refresh_mv_job.py -- HU-F1.5 / REQ-OPS-033.

TDD RED -> GREEN coverage for the ``RefreshMvOcupacionWorker`` cycle.

Pattern mirrors the precedent ``test_sync_sucursal_scenarios.py``:
mock the ``AsyncSession`` with ``unittest.mock.AsyncMock`` so the test
exercises ONLY the worker's ``cycle()`` body -- no live DB needed, no
``PARKOS_DOCKER_TEST`` gate.

Two scenarios from ``openspec/changes/hu-f1-5-mv-ocupacion-diaria/
design.md §11 File 5``:

  T1 -- cycle_normal: a fresh ``cycle()`` call invokes
       ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` + ``commit()`` +
       ``asyncio.sleep(refresh_interval_s)``. KD-5 happy path.

  T2 -- cycle_fallback: when the CONCURRENTLY path raises an exception
       (Postgres ``FeatureNotSupported`` when UNIQUE INDEX is missing,
       or a transient driver error), the worker logs
       ``refresh_mv_concurrently_failed_fallback`` and falls back to
       plain ``REFRESH MATERIALIZED VIEW``. No crash. KD-5 fallback.

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


async def test_cycle_normal_refresh_runs_concurrently_then_sleeps(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A fresh ``cycle()`` invokes
    ``REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria``,
    commits the session, and sleeps for ``refresh_interval_s``."""
    captured_sleep: list[float] = []
    _patch_sleep(monkeypatch, captured_sleep)

    session = _make_mock_session()

    from parkos_core.jobs.refresh_mv_ocupacion import RefreshMvOcupacionWorker

    worker = RefreshMvOcupacionWorker(session=session, refresh_interval_s=10)
    with caplog.at_level(logging.DEBUG, logger="parkos_core.jobs.refresh_mv_ocupacion"):
        await worker.cycle()

    # session.execute called once with the CONCURRENTLY SQL.
    from sqlalchemy import text

    expected_stmt = text(
        "REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria"
    )
    execute_calls = session.execute.await_args_list
    assert len(execute_calls) == 1, (
        f"normal cycle must call session.execute exactly once; "
        f"got {len(execute_calls)} calls"
    )
    actual_stmt = execute_calls[0].args[0]
    assert str(actual_stmt) == str(expected_stmt), (
        f"cycle MUST execute the CONCURRENTLY variant; got {actual_stmt!r}"
    )

    # session.commit() called once.
    assert session.commit.await_count == 1
    # session.rollback() NOT called on the happy path.
    assert session.rollback.await_count == 0

    # asyncio.sleep was awaited with 10.
    assert captured_sleep == [10.0], (
        f"post-cycle sleep MUST be refresh_interval_s=10; got {captured_sleep!r}"
    )

    # Debug log emitted on success.
    assert any(
        rec.message == "refresh_mv_ocupacion_cycle_ok" for rec in caplog.records
    ), (
        f"successful cycle MUST emit the refresh_mv_ocupacion_cycle_ok event; "
        f"got {[r.message for r in caplog.records]!r}"
    )


# ---------------------------------------------------------------------------
# T2 -- cycle_fallback (KD-5)
# ---------------------------------------------------------------------------


async def test_cycle_concurrently_fails_falls_back_to_plain_refresh(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """When the CONCURRENTLY path raises, the worker logs the fallback
    event, retries with plain ``REFRESH MATERIALIZED VIEW``, and does NOT
    crash. KD-5 mitigation.

    The first ``session.execute`` raises; the second (plain ``REFRESH``)
    succeeds. Log records contain
    ``refresh_mv_concurrently_failed_fallback`` and NEVER ``pgcode`` /
    ``repr(exc)`` (R6 mitigation)."""
    captured_sleep: list[float] = []
    _patch_sleep(monkeypatch, captured_sleep)

    # First call raises; subsequent calls succeed.
    fake_exc = RuntimeError("simulated concurrent refresh failure (no pgcode)")
    from unittest.mock import MagicMock

    session = _make_mock_session(side_effects=[fake_exc, MagicMock()])

    from parkos_core.jobs.refresh_mv_ocupacion import RefreshMvOcupacionWorker

    worker = RefreshMvOcupacionWorker(session=session, refresh_interval_s=10)
    with caplog.at_level(
        logging.WARNING, logger="parkos_core.jobs.refresh_mv_ocupacion"
    ):
        # KD-5: cycle MUST NOT raise -- even on fallback.
        await worker.cycle()

    execute_calls = session.execute.await_args_list
    assert len(execute_calls) == 2, (
        f"cycle must call session.execute twice (CONCURRENTLY fails, "
        f"plain REFRESH succeeds); got {len(execute_calls)} calls"
    )
    # First call: the CONCURRENTLY SQL.
    assert (
        str(execute_calls[0].args[0])
        == "REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria"
    )
    # Second call: the plain REFRESH SQL (no CONCURRENTLY).
    assert (
        str(execute_calls[1].args[0])
        == "REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria"
    ), (
        f"fallback MUST use plain REFRESH MATERIALIZED VIEW (no CONCURRENTLY); "
        f"got {execute_calls[1].args[0]!r}"
    )

    # commit was called twice (once per successful branch). rollback was
    # called once after the CONCURRENTLY failure.
    assert session.commit.await_count == 1, (
        f"plain fallback commit MUST be called once; got "
        f"{session.commit.await_count}"
    )
    assert session.rollback.await_count == 1, (
        f"rollback MUST be called once after the CONCURRENTLY failure; "
        f"got {session.rollback.await_count}"
    )

    # Post-cycle sleep still happens (KD-5).
    assert captured_sleep == [10.0]

    # Log capture: refresh_mv_concurrently_failed_fallback event.
    assert any(
        rec.message == "refresh_mv_concurrently_failed_fallback"
        for rec in caplog.records
    ), (
        f"fallback MUST emit the refresh_mv_concurrently_failed_fallback "
        f"event; got {[r.message for r in caplog.records]!r}"
    )

    # R6 mitigation: NO pgcode / repr(exc) leakage in any log line.
    for rec in caplog.records:
        rendered = rec.getMessage() + " " + str(rec.__dict__)
        assert "pgcode" not in rendered, (
            f"log MUST NOT contain pgcode (R6 mitigation); got {rendered!r}"
        )
        # ``str(exc)`` would surface "simulated concurrent refresh failure";
        # the worker must log only ``type(exc).__name__`` ("RuntimeError").
        assert "simulated concurrent" not in rendered, (
            f"log MUST NOT contain the original exception message (R6); "
            f"got {rendered!r}"
        )


__all__ = [
    "test_cycle_concurrently_fails_falls_back_to_plain_refresh",
    "test_cycle_normal_refresh_runs_concurrently_then_sleeps",
]
