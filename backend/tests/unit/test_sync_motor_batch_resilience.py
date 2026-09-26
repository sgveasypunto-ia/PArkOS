"""Batch-apply resilience: one bad row must not poison the whole batch.

THE DEFECT THIS PINS
--------------------
``SyncMotor.apply_batch`` applied every row inside the caller's single
SAVEPOINT. A row whose foreign-key parent is absent therefore raised
``ForeignKeyViolationError``, which rolled back the enclosing transaction
and discarded every OTHER row in the batch with it.

Measured live: the branch worker retried the same 103-row batch 522 times
over 11 hours, applied none of it, and reported ``healthy``. Nothing in the
worker distinguished "this node is alive" from "this node is consuming its
changes".

``apply_batch`` now wraps each row in its own SAVEPOINT and reports
failures in ``BatchResult.failed`` instead of raising.

These are unit tests with a stub session and a stubbed ``apply_row``: the
savepoint semantics under test are SQLAlchemy's, and the thing being
verified here is that the motor ISOLATES rather than propagates — which is
observable without a database.
"""
from __future__ import annotations

from typing import Any

from parkos_core.sync.motor.sync_motor import (
    BatchResult,
    SyncMotor,
    describe_apply_error,
)


class _FakeApplyResult:
    def __init__(self, status: str = "APPLIED", reason: str | None = None) -> None:
        self.status = status
        self.reason = reason
        self.row_uuid = None


class _FakeNested:
    """Stand-in for ``session.begin_nested()``.

    Entering a savepoint is a recovery point: it models the ROLLBACK that
    clears an aborted transaction, which is the second of the two properties
    that make per-row isolation possible.

    The FIRST property - a failed statement aborts the transaction - is
    modelled by the row applier in the test itself, not here. Modelling it
    here would tie the fake to the code under test: a version of
    ``apply_batch`` that never opened a savepoint would also never trip the
    abort flag, and the test would pass against the very defect it exists to
    catch.
    """

    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeNested:
        self._session.savepoints += 1
        self._session.aborted = False
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeSession:
    def __init__(self) -> None:
        self.savepoints = 0
        self.aborted = False

    def begin_nested(self) -> _FakeNested:
        return _FakeNested(self)

    def fail_statement(self) -> None:
        """Model a statement that errored: the transaction is now aborted."""
        self.aborted = True


def _real(name: str):
    """A real catalogue entry.

    ``SyncCatalogEntry`` validates that ``name`` equals the model's
    ``__tablename__``, so the entries must be the genuine ones rather than
    hand-built stand-ins - otherwise the batch under test is not a batch the
    motor would ever be handed.
    """
    from parkos_core.sync.catalog.dependency_graph import SYNC_CATALOG

    for entry in SYNC_CATALOG:
        if entry.name == name:
            return entry
    raise AssertionError(f"{name!r} is not in the sync catalogue")


def _motor() -> SyncMotor:
    from parkos_core.runtime import engine_flag

    return SyncMotor(engine=engine_flag.EngineMode.CATALOG_BRANCH)


class _FKViolation(Exception):
    """Shaped like SQLAlchemy's wrapper around asyncpg's error."""

    def __init__(self) -> None:
        orig = Exception("insert or update on table permisos_usuario violates "
                         "foreign key constraint fk_permisos_usuario_uuid_permiso")
        orig.diag = type("Diag", (), {"constraint_name": "fk_permisos_usuario_uuid_permiso"})()
        orig.sqlstate = "23503"
        self.orig = orig


async def test_one_failing_row_does_not_discard_the_rest(monkeypatch: Any) -> None:
    """The core regression: 2 good rows survive 1 FK violation.

    Before the fix this raised out of ``apply_batch`` and the caller's
    savepoint rolled back all three.
    """
    motor = _motor()
    session = _FakeSession()
    good, bad, also_good = _real("usuarios"), _real("permisos"), _real("permisos_usuario")

    seen: list[str] = []

    async def fake_apply_row(session, spec, payload, **_kw):
        assert not session.aborted, (
            "a statement ran on an aborted transaction: this row was applied "
            "without a savepoint to roll back to"
        )
        seen.append(spec.name)
        if spec.name == "usuarios":
            session.fail_statement()
            raise _FKViolation()
        return _FakeApplyResult()

    monkeypatch.setattr(motor, "apply_row", fake_apply_row)

    result = await motor.apply_batch(
        session, [(good, {}), (bad, {}), (also_good, {})], actor_uuid=None  # type: ignore[arg-type]
    )

    attempted = set(seen)
    assert attempted == {"usuarios", "permisos", "permisos_usuario"}, (
        "the failing row must not stop later rows"
    )
    assert len(result.applied) == 2
    assert len(result.failed) == 1
    assert result.failed[0][0].name == "usuarios"


async def test_failure_reason_names_the_constraint(monkeypatch: Any) -> None:
    """The label must be actionable AND must not echo row data.

    asyncpg's message embeds every bound parameter; logging ``str(exc)``
    is what produced 522 near-identical lines re-emitting the row.
    """
    motor = _motor()
    session = _FakeSession()
    spec = _real("permisos_usuario")

    async def fake_apply_row(*_a, **_kw):
        raise _FKViolation()

    monkeypatch.setattr(motor, "apply_row", fake_apply_row)

    result = await motor.apply_batch(
        session, [(spec, {})], actor_uuid=None  # type: ignore[arg-type]
    )

    assert len(result.failed) == 1
    reason = result.failed[0][2]
    assert reason == "fk_violation:fk_permisos_usuario_uuid_permiso"
    assert "INSERT INTO" not in reason


def test_describe_apply_error_falls_back_without_an_orm_wrapper() -> None:
    """A bare exception must still yield a short, stable label."""
    assert describe_apply_error(ValueError("boom")) == "ValueError"


def test_batch_result_failed_defaults_empty() -> None:
    """Back-compat: a clean batch reports no failures."""
    assert BatchResult().failed == []
