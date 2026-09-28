"""Cursor advance and health escalation for ``job_sync_sucursal``.

THE DEFECT THIS PINS
--------------------
The pull watermark advanced whenever ``unresolved == 0``. A row that raised
INSIDE its batch — a foreign key whose parent had not arrived yet — was not
"unresolved" by that definition, so the watermark moved past it and the row
was never re-delivered. Combined with a batch that was rolled back wholesale
by the first failing row, the node re-fetched the same 103 rows 522 times,
landed none of them, and reported healthy.

Two invariants are pinned here:

* the watermark must not advance past a row that failed this cycle, and
* the node must report itself degraded once it has failed enough cycles in
  a row, so ``/healthz`` stops saying ``ok`` while it is consuming nothing.
"""
from __future__ import annotations

import uuid
from typing import Any, ClassVar

import pytest
import structlog
from parkos_core.jobs import sync_sucursal as mod
from parkos_core.jobs.sync_sucursal import SyncSucursalWorker


class _Recorder:
    """Captures ``set_seq`` calls without a database."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def set_seq(self, _session, *, uuid_sucursal, ultimo_seq) -> None:
        self.calls.append({"uuid_sucursal": uuid_sucursal, "ultimo_seq": ultimo_seq})


def _worker(recorder: _Recorder, uuid_sucursal: uuid.UUID | None) -> SyncSucursalWorker:
    """A worker with only the attributes the helpers under test touch.

    Built via ``__new__`` rather than the real constructor: the constructor
    opens a session and reads env, none of which these guards involve, and
    requiring a database to test a watermark decision would make the test
    useless in exactly the environment where the watermark matters.
    """
    del recorder  # the fixture already patched the module-level helper
    worker = SyncSucursalWorker.__new__(SyncSucursalWorker)
    worker.uuid_sucursal = uuid_sucursal
    worker._session = None
    worker.log = structlog.get_logger()
    return worker


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    rec = _Recorder()
    monkeypatch.setattr(mod, "sync_cursor_helpers", rec)
    return rec


# ---------------------------------------------------------------------------
# The watermark
# ---------------------------------------------------------------------------


async def test_a_clean_batch_advances_the_cursor(recorder: _Recorder) -> None:
    worker = _worker(recorder, uuid.uuid4())
    await worker._persist_pull_cursor(next_seq=42, unresolved=0, failed=0)
    assert len(recorder.calls) == 1
    assert recorder.calls[0]["ultimo_seq"] == 42


async def test_a_failed_row_freezes_the_cursor(recorder: _Recorder) -> None:
    """The core regression: a poison row must be re-delivered, not skipped."""
    worker = _worker(recorder, uuid.uuid4())
    await worker._persist_pull_cursor(next_seq=42, unresolved=0, failed=1)
    assert recorder.calls == [], "the watermark advanced past a row that failed"


async def test_an_unresolved_row_freezes_the_cursor(recorder: _Recorder) -> None:
    """Pre-existing guard, pinned so the ``failed`` addition cannot drop it."""
    worker = _worker(recorder, uuid.uuid4())
    await worker._persist_pull_cursor(next_seq=42, unresolved=1, failed=0)
    assert recorder.calls == []


async def test_no_branch_uuid_means_no_cursor_write(recorder: _Recorder) -> None:
    """``uuid_sucursal`` is NOT NULL; the legacy constructor passes None."""
    worker = _worker(recorder, None)
    await worker._persist_pull_cursor(next_seq=42, unresolved=0, failed=0)
    assert recorder.calls == []


# ---------------------------------------------------------------------------
# Health escalation
# ---------------------------------------------------------------------------


class _Spec:
    """Only ``.name`` is read — by the log line naming the offending table."""

    def __init__(self, name: str) -> None:
        self.name = name


class _Batch:
    def __init__(self, failed: int = 0, buffered: int = 0) -> None:
        self.failed = [
            (_Spec("permisos_usuario"), {}, "fk_violation:fk_permisos_usuario_uuid_permiso")
        ] * failed
        self.buffered = [None] * buffered
        self.applied = []


class _Clean:
    failed: ClassVar[list] = []
    buffered: ClassVar[list] = []
    applied: ClassVar[list] = []


def _health_worker() -> SyncSucursalWorker:
    worker = SyncSucursalWorker.__new__(SyncSucursalWorker)
    worker.log = structlog.get_logger()
    worker._consecutive_apply_failures = 0
    worker._last_apply_error = None
    return worker


def test_health_is_ok_before_the_threshold() -> None:
    worker = _health_worker()
    assert worker.sync_health()["ok"] is True


def test_health_degrades_once_the_threshold_is_reached() -> None:
    worker = _health_worker()
    threshold = worker.APPLY_FAILURE_DEGRADED_THRESHOLD
    for _ in range(threshold - 1):
        worker._record_apply_outcome(_Batch(failed=1))
        assert worker.sync_health()["ok"] is True, "degraded too early"
    worker._record_apply_outcome(_Batch(failed=1))
    report = worker.sync_health()
    assert report["ok"] is False
    assert report["consecutive_apply_failures"] == threshold


def test_a_single_clean_cycle_resets_the_streak() -> None:
    """Flapping must not latch the node into a permanent degraded state."""
    worker = _health_worker()
    worker._record_apply_outcome(_Batch(failed=1))
    worker._record_apply_outcome(_Clean())
    assert worker._consecutive_apply_failures == 0
    assert worker.sync_health()["ok"] is True


def test_the_report_carries_the_failing_constraint() -> None:
    """The label is the actionable token: the CONSTRAINT name, not row data."""
    worker = _health_worker()
    worker._record_apply_outcome(_Batch(failed=1))
    report = worker.sync_health()
    assert report["last_apply_error"] == (
        "fk_violation:fk_permisos_usuario_uuid_permiso"
    )


def test_health_report_is_wired_to_the_http_provider() -> None:
    """``WorkerRunner`` asks the subclass for its report; it must not be None.

    A subclass that forgot to override ``health_report`` would silently
    degrade to a constant 200 — the exact original defect.
    """
    worker = _health_worker()
    assert callable(worker.health_report)
    assert worker.health_report()["ok"] is True


def test_a_whole_batch_raise_counts_as_a_failure() -> None:
    """``apply_batch`` isolates per-row errors; a fault OUTSIDE it escapes.

    A node wedging on every cycle must not report healthy — that is the
    failure mode this change exists to end, and it is a different code path
    from the per-row one.
    """
    worker = _health_worker()
    for _ in range(worker.APPLY_FAILURE_DEGRADED_THRESHOLD):
        worker._note_batch_failure(RuntimeError("ordering exploded"))
    assert worker.sync_health()["ok"] is False
    assert worker.sync_health()["last_apply_error"] == "RuntimeError"


def test_an_empty_pulled_batch_clears_the_streak() -> None:
    """A cycle with nothing to apply is a CLEAN cycle.

    Without this, a node that degraded during an incident stays 503 for as
    long as the cloud sends no further changes, which reads as a permanent
    outage long after the divergence was fixed.
    """
    worker = _health_worker()
    worker._consecutive_apply_failures = 5
    worker._last_apply_error = "fk_violation:x"
    worker._note_clean_cycle()
    assert worker.sync_health()["ok"] is True
    assert worker._last_apply_error is None


def test_a_batch_failure_tolerates_a_missing_spec() -> None:
    """``_note_batch_failure`` has no spec, so the tables set must survive it.

    ``_record_apply_outcome`` reads ``spec.name`` for its log line; a whole
    batch failure has no spec, and the log must not be the thing that
    raises.
    """
    worker = _health_worker()
    worker._record_apply_outcome(_Batch(failed=1))  # has a spec
    worker._note_batch_failure(ValueError("boom"))  # has none
    assert worker.sync_health()["consecutive_apply_failures"] == 2
