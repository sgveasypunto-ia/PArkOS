"""A failed cycle must not leave the session in an aborted transaction.

THE DEFECT THIS PINS
--------------------
``self._session`` is owned by ``main()`` for the whole container lifetime --
``cycle()`` only ever called ``commit()``, never ``rollback()``. When a cycle
raised, ``WorkerRunner.run`` logged ``cycle_error``, slept one second and
called ``cycle()`` again on the SAME session, whose transaction was already
aborted by the failed statement.

PostgreSQL then refused every subsequent command in that transaction with::

    InFailedSQLTransactionError: current transaction is aborted,
    commands ignored until end of transaction block

which is exactly what was observed in production: a single real fault
(``InsufficientPrivilegeError`` on ``prod.sync_cursor``) appeared once, and
every cycle after it reported the cascade instead. The worker looked like it
was retrying a live problem while consuming nothing, and the original cause
was unrecoverable from the logs without stopping the container.

The invariant pinned here: after a cycle raises, the session is rolled back,
so the NEXT cycle starts on a usable transaction and a fresh error is
reported if the fault persists.
"""
from __future__ import annotations

from typing import Any

import pytest
import structlog
from parkos_core.jobs.sync_cloud import SyncCloudWorker
from parkos_core.jobs.sync_sucursal import SyncSucursalWorker


class _FakeSession:
    """Records lifecycle calls; can be told to fail like a real aborted one."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.aborted = False

    async def commit(self) -> None:
        self.commits += 1
        self.aborted = False

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.aborted = False

    def fail_statement(self) -> None:
        """Model a statement error: the transaction is now unusable."""
        self.aborted = True

    async def execute(self, *args: Any, **kwargs: Any) -> None:
        if self.aborted:
            raise RuntimeError("current transaction is aborted")
        return None


def _make(cls: type, session: _FakeSession) -> Any:
    """Build a worker with only the attributes ``cycle()`` touches.

    ``__new__`` rather than the constructor: the constructor opens a real
    session and reads env. The wrapper under test does nothing but delegate
    and roll back, so requiring a database here would make the test useless
    in the environment where the bug actually bit.
    """
    worker = cls.__new__(cls)
    worker._session = session
    worker.log = structlog.get_logger()
    return worker


@pytest.fixture
def session() -> _FakeSession:
    return _FakeSession()


# ---------------------------------------------------------------------------
# job_sync_sucursal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sucursal_cycle_rolls_back_when_the_body_raises(
    session: _FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The raise propagates AND the session is left reusable."""
    worker = _make(SyncSucursalWorker, session)

    async def _boom() -> None:
        session.fail_statement()
        raise RuntimeError("InsufficientPrivilegeError: permission denied")

    monkeypatch.setattr(worker, "_run_cycle", _boom)

    with pytest.raises(RuntimeError, match="permission denied"):
        await worker.cycle()

    assert session.rollbacks == 1, "cycle must roll back before re-raising"
    assert session.aborted is False
    # The real error must survive: not swallowed by the rollback handler.
    await session.execute()  # would raise if the transaction were still aborted


@pytest.mark.asyncio
async def test_sucursal_next_cycle_after_a_failure_is_usable(
    session: _FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two consecutive failing cycles report the SAME error, not a cascade.

    This is the behaviour the production logs got wrong: cycle 1 raised the
    real fault, cycle 2 raised ``InFailedSQLTransactionError``. If the
    rollback is removed, the second error differs and this test fails.
    """
    worker = _make(SyncSucursalWorker, session)
    seen: list[str] = []

    async def _always_fails() -> None:
        session.fail_statement()
        raise RuntimeError("permission denied for table sync_cursor")

    async def _spy() -> None:
        # Runs after the rollback: models the next cycle's first query.
        try:
            await session.execute()
        except RuntimeError as exc:  # pragma: no cover - the failure mode
            seen.append(f"cascade:{exc}")

    monkeypatch.setattr(worker, "_run_cycle", _always_fails)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="permission denied"):
            await worker.cycle()
        await _spy()

    assert seen == [], f"second cycle saw a poisoned transaction: {seen}"
    assert session.rollbacks == 2


@pytest.mark.asyncio
async def test_sucursal_failed_rollback_does_not_mask_the_original_error(
    session: _FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rollback that itself fails must not replace the real exception."""

    async def _rollback_raises() -> None:
        raise RuntimeError("connection already closed")

    session.rollback = _rollback_raises  # type: ignore[method-assign]
    worker = _make(SyncSucursalWorker, session)

    async def _boom() -> None:
        raise RuntimeError("the real fault")

    monkeypatch.setattr(worker, "_run_cycle", _boom)

    with pytest.raises(RuntimeError, match="the real fault"):
        await worker.cycle()


@pytest.mark.asyncio
async def test_sucursal_successful_cycle_does_not_roll_back(
    session: _FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No error, no rollback: ``_run_cycle`` owns its own commit."""
    worker = _make(SyncSucursalWorker, session)

    async def _fine() -> None:
        return None

    monkeypatch.setattr(worker, "_run_cycle", _fine)
    await worker.cycle()

    assert session.rollbacks == 0


# ---------------------------------------------------------------------------
# job_sync_cloud -- same long-lived session, same exposure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cloud_cycle_rolls_back_when_the_body_raises(
    session: _FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = _make(SyncCloudWorker, session)

    async def _boom() -> None:
        session.fail_statement()
        raise RuntimeError("cloud fault")

    monkeypatch.setattr(worker, "_run_cycle", _boom)

    with pytest.raises(RuntimeError, match="cloud fault"):
        await worker.cycle()

    assert session.rollbacks == 1
    assert session.aborted is False


def test_cloud_worker_exposes_the_wrapped_body() -> None:
    """Guard the refactor itself: both workers keep ``_run_cycle`` split out."""
    assert callable(getattr(SyncCloudWorker, "_run_cycle", None))
    assert callable(getattr(SyncSucursalWorker, "_run_cycle", None))
    assert SyncCloudWorker.cycle is not SyncCloudWorker._run_cycle
    assert SyncSucursalWorker.cycle is not SyncSucursalWorker._run_cycle
