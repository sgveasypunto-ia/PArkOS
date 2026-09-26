"""``POST /sync/push`` must APPLY its rows, not just claim it did.

REGRESSION SUITE for the real defect found on live Docker (2026-09-26).
``sync_push`` shipped in PR8c as an auth/cache/rate-limit plumbing harness
and returned a HARDCODED ``status="applied"`` for every incoming row
without ever touching the database::

    # PR9 will iterate ``payload.rows`` against the conflict-resolution
    # applier; PR8c returns applied=true on all rows so the auth +
    # rate-limit + cache plumbing is verified end-to-end.
    results = [_PushResponseRow(..., status="applied", ...) for row in payload.rows]

The ``session: AsyncSession = Depends(get_session)`` parameter was
accepted and never used. PR9 shipped the worker and the motor but never
wired THIS endpoint to it.

The 207 contract was broken at BOTH ends:

- **Server** never applied anything and answered ``{"results": [...]}``.
- **Client** (``sync_sucursal._handle_push_response``) parsed
  ``body["success_uuids"]`` / ``body["accepted"]`` — keys this endpoint
  never returned — and then intersected them against ``row.uuid`` (the
  ``sync_queue`` row uuid) while the receiver reports ``uuid_registro``
  (the business row uuid). Two different namespaces, so the intersection
  was empty for every row and the whole batch would have been marked
  ``rejected_by_cloud`` forever.

Both halves are fixed to correlate by INDEX, the convention
``_push_and_handle_catalog`` already uses.

THE CONTRACT pinned here, one test per clause:

1. Rows are handed to ``SyncMotor.apply_row`` (real application).
2. A row the motor did not apply is NEVER reported ``applied``.
3. An unrecognized ``tabla`` is reported, never silently dropped
   (REQ-CUT-015's "never a silent drop").
4. A ``pg_partman`` child-partition name resolves to its parent catalog
   entry, otherwise the 8 partitioned tables fail ``unknown_table`` forever.
5. Echo suppression is enabled once per transaction before any apply.
6. The batch is ordered dependency-aware.
7. Response rows align index-for-index with request order.
8. If ``session.commit()`` fails the request does NOT return 207, so the
   sender never records a delivery that did not happen.
9. An exception mid-batch rolls the transaction back.

Distinct from ``test_sync_router.py`` (auth/idempotency/rate-limit) and
``test_sync_transport.py`` (the client transport).
"""

from __future__ import annotations

import uuid as uuid_lib
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from parkos_core.api.v1 import sync_router as sr
from parkos_core.api.v1.sync_router import (
    _IDEMPOTENCY,
    _RATE_LIMIT_PUSH,
    _sync_agent_claims,
)
from parkos_core.api.v1.sync_router import (
    router as sync_router_obj,
)
from parkos_core.sync.motor.apply_result import ApplyResult

SUBJECT_UUID = uuid_lib.UUID("22222222-2222-2222-2222-222222222222")
SUCURSAL_UUID = uuid_lib.UUID("11111111-1111-1111-1111-111111111111")


def _claims() -> dict[str, Any]:
    return {
        "iss": "sync-agent-cloud",
        "sub": str(SUBJECT_UUID),
        "jti": "test-jti-push-applier",
        "scope": "branch",
        "sucursal": str(SUCURSAL_UUID),
    }


class _Recorder:
    """Records every ``apply_row`` call and replays scripted outcomes.

    ``outcomes`` maps a table name to what the motor should do for it:
    ``"APPLIED"`` (the default for any table not listed), ``"CONFLICT"``,
    ``"RETRY"``, or ``"raise"``.
    """

    def __init__(self, outcomes: dict[str, str] | None = None) -> None:
        self.outcomes = outcomes or {}
        self.calls: list[tuple[str, dict[str, Any], str | None]] = []

    async def apply_row(
        self,
        session: Any,
        spec: Any,
        payload: dict[str, Any],
        *,
        actor_uuid: Any = None,
    ) -> ApplyResult:
        self.calls.append((spec.name, payload, str(actor_uuid)))
        outcome = self.outcomes.get(spec.name, "APPLIED")
        if outcome == "raise":
            raise RuntimeError(f"motor exploded on {spec.name}")
        if outcome == "APPLIED":
            return ApplyResult(status="APPLIED")
        if outcome == "CONFLICT":
            return ApplyResult(status="CONFLICT", reason="divergent")
        if outcome == "RETRY":
            return ApplyResult(status="RETRY", reason="parent_missing")
        raise AssertionError(f"unhandled scripted outcome {outcome!r}")

    @property
    def tables(self) -> list[str]:
        return [c[0] for c in self.calls]


def _build_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    outcomes: dict[str, str] | None = None,
    commit_error: BaseException | None = None,
) -> tuple[TestClient, _Recorder, MagicMock]:
    """App with a fake session and a real ``SyncMotor`` whose apply is stubbed.

    ``engine_flag.get_engine()`` is stubbed rather than ``SyncMotor``
    itself, so the genuine ``SyncMotor`` object is still constructed and
    only ``apply_row`` is replaced.
    """
    session = MagicMock(name="AsyncSession")
    session.commit = AsyncMock(side_effect=commit_error)
    session.rollback = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    application = FastAPI()
    application.include_router(sync_router_obj)
    from parkos_core.db.engine import get_session

    application.dependency_overrides[get_session] = lambda: session
    application.dependency_overrides[_sync_agent_claims] = _claims

    monkeypatch.setattr(sr.engine_flag, "get_engine", lambda: MagicMock())
    monkeypatch.setattr(sr.apply_guard, "enable_echo_suppression", AsyncMock(return_value=None))
    recorder = _Recorder(outcomes)
    monkeypatch.setattr(sr.SyncMotor, "apply_row", recorder.apply_row)

    return TestClient(application, raise_server_exceptions=False), recorder, session


def _row(
    tabla: str = "alerta",
    *,
    seq: int = 1,
    datos: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tabla": tabla,
        "uuid_registro": str(uuid_lib.uuid4()),
        "seq": seq,
        "datos": datos if datos is not None else {"tipo_alerta": "hash_chain_anomaly"},
    }


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    _IDEMPOTENCY.reset()
    _RATE_LIMIT_PUSH.reset()


# ---------------------------------------------------------------------------
# 1. The row is actually applied.
# ---------------------------------------------------------------------------


def test_push_applies_row_through_sync_motor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The row must reach ``apply_row`` with its real payload."""
    c, motor, _ = _build_client(monkeypatch)
    datos = {"tipo_alerta": "hash_chain_anomaly", "descripcion": "x"}

    resp = c.post("/sync/push", json={"rows": [_row(datos=datos)]})

    assert resp.status_code == 207
    assert motor.tables == ["alerta"], "push never handed the row to the motor"
    assert motor.calls[0][1] == datos
    assert motor.calls[0][2] == str(SUBJECT_UUID)
    assert resp.json()["results"][0]["status"] == "applied"


# ---------------------------------------------------------------------------
# 2. THE CONTRACT: never report ``applied`` for a row that was not applied.
# ---------------------------------------------------------------------------


def test_push_reports_conflict_not_applied_when_motor_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A conflicting row reports ``conflict`` — never ``applied``.

    This is the exact shape of the original defect: a row the receiver
    did not accept reported back as delivered.
    """
    c, _, _ = _build_client(monkeypatch, outcomes={"alerta": "CONFLICT"})

    resp = c.post("/sync/push", json={"rows": [_row()]})

    assert resp.status_code == 207
    assert resp.json()["results"][0]["status"] == "conflict"


def test_push_reports_retry_parent_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    c, _, _ = _build_client(monkeypatch, outcomes={"alerta": "RETRY"})

    resp = c.post("/sync/push", json={"rows": [_row()]})

    assert resp.json()["results"][0]["status"] == "retry_parent_missing"


# ---------------------------------------------------------------------------
# 3. Unknown table: reported, never dropped, never applied.
# ---------------------------------------------------------------------------


def test_push_unknown_table_is_reported_never_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c, motor, _ = _build_client(monkeypatch)

    resp = c.post("/sync/push", json={"rows": [_row(tabla="tabla_fantasma")]})

    assert resp.status_code == 207
    result = resp.json()["results"][0]
    assert result["status"] == "unknown_table", (
        f"expected explicit unknown_table, got {result['status']!r} (must never be a silent drop)"
    )
    assert motor.calls == [], "an unknown table must never reach the motor"


# ---------------------------------------------------------------------------
# 4. pg_partman child-partition names resolve to their parent entry.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("partitioned", "parent"),
    [
        ("log_transaccional_p_current", "log_transaccional"),
        ("log_transaccional_p20260926", "log_transaccional"),
        ("salidas_default", "salidas"),
    ],
)
def test_push_resolves_partman_partition_name_to_parent(
    monkeypatch: pytest.MonkeyPatch, partitioned: str, parent: str
) -> None:
    """``{parent}_p_current`` / ``_default`` must apply via the parent spec.

    The enqueue trigger stamps ``TG_TABLE_NAME`` with the PHYSICAL
    partition, so every row from the 8 partitioned tables arrives
    suffixed. Without ``resolve_catalog_name`` they all fail
    ``unknown_table`` forever.
    """
    c, motor, _ = _build_client(monkeypatch)

    resp = c.post("/sync/push", json={"rows": [_row(tabla=partitioned)]})

    assert resp.status_code == 207
    assert resp.json()["results"][0]["status"] == "applied"
    assert motor.tables == [parent]


# ---------------------------------------------------------------------------
# 5. Echo suppression is enabled once, before any apply.
# ---------------------------------------------------------------------------


def test_push_enables_echo_suppression_once_per_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c, _, session = _build_client(monkeypatch)

    c.post("/sync/push", json={"rows": [_row(), _row(seq=2)]})

    enable = sr.apply_guard.enable_echo_suppression
    assert isinstance(enable, AsyncMock)
    assert enable.await_count == 1, "echo suppression must be set once per request"
    assert enable.await_args is not None
    assert enable.await_args.args[0] is session


# ---------------------------------------------------------------------------
# 6. Dependency-aware ordering (parent before child).
# ---------------------------------------------------------------------------


def test_push_orders_batch_dependency_aware(monkeypatch: pytest.MonkeyPatch) -> None:
    """A child row sent BEFORE its parent must still apply after it.

    Sending order is the sender's ``list_pending`` order, which is not
    dependency-aware. Applying in wire order aborted whole batches with
    ``ForeignKeyViolationError`` because the loop shared one transaction.
    """
    c, motor, _ = _build_client(monkeypatch)
    child = _row(tabla="factura_detalle", seq=1)
    parent = _row(tabla="facturas", seq=9)

    resp = c.post("/sync/push", json={"rows": [child, parent]})

    assert resp.status_code == 207
    assert motor.tables.index("facturas") < motor.tables.index("factura_detalle"), (
        f"child applied before parent: {motor.tables}"
    )
    # Index correspondence with the request must survive the reordering.
    assert [r["status"] for r in resp.json()["results"]] == ["applied", "applied"]


# ---------------------------------------------------------------------------
# 7. Response rows align index-for-index with the request.
# ---------------------------------------------------------------------------


def test_push_results_align_with_request_order(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [_row(seq=i) for i in range(1, 6)]
    sent = [r["uuid_registro"] for r in rows]

    c, _, _ = _build_client(monkeypatch)
    body = c.post("/sync/push", json={"rows": rows}).json()

    assert [r["uuid_registro"] for r in body["results"]] == sent


# ---------------------------------------------------------------------------
# 8. Commit failure must NOT produce a 207 (the false-success guard).
# ---------------------------------------------------------------------------


def test_push_commit_failure_does_not_return_207(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed commit must surface as an error, never as ``applied``.

    The sender marks queue rows dispatched on a 2xx/207. If a commit
    failure still returned 207, the queue would record delivery for rows
    that were never persisted.
    """
    c, _, session = _build_client(monkeypatch, commit_error=RuntimeError("commit failed"))

    resp = c.post("/sync/push", json={"rows": [_row()]})

    assert resp.status_code != 207, (
        "a failed commit returned 207 — the sender would mark the row delivered"
    )
    assert resp.status_code >= 500
    session.rollback.assert_awaited()


# ---------------------------------------------------------------------------
# 9. Mid-batch exception rolls the transaction back.
# ---------------------------------------------------------------------------


def test_push_rolls_back_when_apply_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    c, _, session = _build_client(monkeypatch, outcomes={"alerta": "raise"})

    resp = c.post("/sync/push", json={"rows": [_row()]})

    assert resp.status_code >= 500
    session.rollback.assert_awaited()
    session.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# Guards on the response vocabulary itself.
# ---------------------------------------------------------------------------


def test_push_mixed_batch_reports_each_row_own_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c, motor, _ = _build_client(monkeypatch, outcomes={"alerta": "CONFLICT", "clientes": "APPLIED"})

    resp = c.post(
        "/sync/push",
        json={"rows": [_row(tabla="alerta"), _row(tabla="clientes", seq=2)]},
    )

    # Response order follows the REQUEST, even though the motor applied
    # them dependency-ordered (clientes is a [V] parent, so it applies
    # first regardless of wire order).
    assert [r["status"] for r in resp.json()["results"]] == ["conflict", "applied"]
    assert sorted(motor.tables) == ["alerta", "clientes"]


def test_push_commits_exactly_once_after_applying_everything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c, _, session = _build_client(monkeypatch)

    c.post("/sync/push", json={"rows": [_row(), _row(seq=2), _row(seq=3)]})

    session.commit.assert_awaited_once()


def test_push_empty_batch_commits_and_returns_no_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c, motor, _ = _build_client(monkeypatch)

    resp = c.post("/sync/push", json={"rows": []})

    assert resp.status_code == 207
    assert resp.json()["results"] == []
    assert motor.calls == []
