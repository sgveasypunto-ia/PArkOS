"""test_sync_router_wire_status.py — T-PR11-006 (REQ-MOT-005, REQ-CUT-015).

Covers the cloud-side ``/sync/events`` receiver's per-row wire status:

  - ``wire_status_for_apply_result`` — the pure REQ-MOT-005 mapping table
    (``APPLIED`` -> ``applied``, ``CONFLICT`` -> ``conflict``, ``RETRY``
    with ``reason="parent_missing"`` -> ``retry_parent_missing``), plus the
    "never silent" guard for an unexpected ``RETRY`` reason.
  - The full endpoint: a ``tabla``-bearing row is applied through a stubbed
    ``SyncMotor`` and the response reports the exact wire status; an
    unrecognized ``tabla`` reports ``unknown_table`` (never a silent drop);
    a legacy event with no ``tabla`` still reports ``delivered`` (backward
    compatible with the PR8c shape ``test_sync_router.py::TestSyncEvents``
    already asserts).

Distinct from ``tests/unit/test_sync_router.py`` (PR8c, endpoint-level auth
+ rate-limit + idempotency coverage for all six endpoints) — this file is
scoped to the wire-status mapping T-PR11-006 adds.
"""
from __future__ import annotations

import uuid as uuid_lib
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from parkos_core.api.v1 import sync_router
from parkos_core.api.v1.sync_router import (
    _IDEMPOTENCY,
    _RATE_LIMIT_PULL,
    UnmappedApplyStatusError,
    _sync_agent_claims,
    wire_status_for_apply_result,
)
from parkos_core.api.v1.sync_router import (
    router as sync_router_obj,
)
from parkos_core.runtime import engine_flag
from parkos_core.sync.motor.apply_result import ApplyResult

SUBJECT_UUID = uuid_lib.UUID("22222222-2222-2222-2222-222222222222")


# ---------------------------------------------------------------------------
# wire_status_for_apply_result — pure unit coverage (no FastAPI, no DB)
# ---------------------------------------------------------------------------


class TestWireStatusForApplyResult:
    def test_applied_maps_to_applied(self) -> None:
        result = ApplyResult(status="APPLIED", row_uuid=uuid_lib.uuid4())
        assert wire_status_for_apply_result(result) == "applied"

    def test_conflict_maps_to_conflict(self) -> None:
        result = ApplyResult(status="CONFLICT", reason="illegal_state_transition")
        assert wire_status_for_apply_result(result) == "conflict"

    def test_retry_parent_missing_maps_to_retry_parent_missing(self) -> None:
        result = ApplyResult(status="RETRY", reason="parent_missing")
        assert wire_status_for_apply_result(result) == "retry_parent_missing"

    def test_retry_with_unexpected_reason_raises_never_silent(self) -> None:
        """No ratified wire name exists for a RETRY outside parent_missing —
        raising, not guessing or dropping, is the "never silent" contract."""
        result = ApplyResult(status="RETRY", reason="something_else")
        with pytest.raises(UnmappedApplyStatusError):
            wire_status_for_apply_result(result)


# ---------------------------------------------------------------------------
# Endpoint-level: POST /sync/events with a catalog-driven row
# ---------------------------------------------------------------------------


def _claims() -> dict[str, Any]:
    return {
        "iss": "sync-agent-cloud",
        "sub": str(SUBJECT_UUID),
        "jti": "test-jti-wire-status",
        "scope": "branch",
        "sucursal": str(SUBJECT_UUID),
        "iat_branch": None,
    }


def _fake_session() -> MagicMock:
    s = MagicMock(name="AsyncSession")
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.rollback = AsyncMock()
    s.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    return s


def _stub_motor_cls(results: list[ApplyResult]) -> type:
    """Return a ``SyncMotor``-shaped stub class yielding ``results`` in order.

    One instance is constructed per request (``sync_events`` does
    ``SyncMotor(engine=...)`` once per call); ``apply_row`` is called once
    per catalog-driven row in the request, in the order they were declared.
    """
    queue = list(results)

    class _StubSyncMotor:
        def __init__(self, *, engine: engine_flag.EngineMode | None = None) -> None:
            self.engine = engine

        async def apply_row(
            self,
            session: object,
            spec: object,
            payload: dict[str, Any],
            *,
            actor_uuid: uuid_lib.UUID,
            log_tx: bool = True,
        ) -> ApplyResult:
            return queue.pop(0)

    return _StubSyncMotor


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    application.include_router(sync_router_obj)

    def _fake_session_dep_key():
        from parkos_core.db.engine import get_session

        return get_session

    application.dependency_overrides[_fake_session_dep_key()] = lambda: _fake_session()
    application.dependency_overrides[_sync_agent_claims] = lambda: _claims()
    return application


@pytest.fixture(autouse=True)
def _reset_process_state(monkeypatch: pytest.MonkeyPatch) -> None:
    _IDEMPOTENCY.reset()
    _RATE_LIMIT_PULL.reset()
    # engine_flag.get_engine() re-reads PARKOS_SYNC_ENGINE and caches for
    # 60s (runtime/engine_flag.py) — set a valid value and clear the cache
    # so each test starts from a known, fresh state regardless of test order.
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
    engine_flag._reset_cache_for_tests()


class TestSyncEventsWireStatus:
    def test_catalog_row_applied_reports_applied(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            sync_router,
            "SyncMotor",
            _stub_motor_cls([ApplyResult(status="APPLIED", row_uuid=uuid_lib.uuid4())]),
        )
        c = TestClient(app)
        resp = c.post(
            "/sync/events",
            json={
                "events": [
                    {
                        "event_type": "catalog_row",
                        "tabla": "factura_pagos",
                        "payload": {"x": 1},
                    }
                ]
            },
        )
        assert resp.status_code == 207, resp.text
        body = resp.json()
        assert body["results"] == [{"event_type": "catalog_row", "status": "applied"}]

    def test_catalog_row_conflict_reports_conflict(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            sync_router,
            "SyncMotor",
            _stub_motor_cls(
                [ApplyResult(status="CONFLICT", reason="illegal_state_transition")]
            ),
        )
        c = TestClient(app)
        resp = c.post(
            "/sync/events",
            json={
                "events": [
                    {"event_type": "catalog_row", "tabla": "factura_pagos", "payload": {}}
                ]
            },
        )
        assert resp.status_code == 207, resp.text
        assert resp.json()["results"] == [{"event_type": "catalog_row", "status": "conflict"}]

    def test_branch_to_cloud_row_missing_parent_reports_retry_parent_missing(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REQ-CUT-015's exact acceptance scenario: a branch_to_cloud row whose
        declared parent is not yet present on the cloud side — never a
        generic failure, never a silent drop."""
        monkeypatch.setattr(
            sync_router,
            "SyncMotor",
            _stub_motor_cls(
                [ApplyResult(status="RETRY", reason="parent_missing")]
            ),
        )
        c = TestClient(app)
        resp = c.post(
            "/sync/events",
            json={
                "events": [
                    {
                        "event_type": "catalog_row",
                        "tabla": "reimpresion_ticket",
                        "payload": {},
                    }
                ]
            },
        )
        assert resp.status_code == 207, resp.text
        assert resp.json()["results"] == [
            {"event_type": "catalog_row", "status": "retry_parent_missing"}
        ]

    def test_unrecognized_tabla_reports_unknown_table_not_silent(
        self, app: FastAPI
    ) -> None:
        """A ``tabla`` outside SYNC_CATALOG_BY_NAME is reported, never dropped."""
        c = TestClient(app)
        resp = c.post(
            "/sync/events",
            json={
                "events": [
                    {"event_type": "catalog_row", "tabla": "not_a_real_table", "payload": {}}
                ]
            },
        )
        assert resp.status_code == 207, resp.text
        assert resp.json()["results"] == [
            {"event_type": "catalog_row", "status": "unknown_table"}
        ]

    def test_legacy_event_without_tabla_still_reports_delivered(
        self, app: FastAPI
    ) -> None:
        """Backward compat: the original PR8c shape is unaffected by T-PR11-006."""
        c = TestClient(app)
        resp = c.post(
            "/sync/events",
            json={"events": [{"event_type": "factus_dispatch_accepted", "payload": {}}]},
        )
        assert resp.status_code == 207, resp.text
        assert resp.json()["results"] == [
            {"event_type": "factus_dispatch_accepted", "status": "delivered"}
        ]

    def test_mixed_batch_maps_each_row_independently(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One request carrying legacy + catalog-driven + unknown rows —
        each row's status is independent of the others (no cross-row leak)."""
        monkeypatch.setattr(
            sync_router,
            "SyncMotor",
            _stub_motor_cls([ApplyResult(status="APPLIED", row_uuid=uuid_lib.uuid4())]),
        )
        c = TestClient(app)
        resp = c.post(
            "/sync/events",
            json={
                "events": [
                    {"event_type": "legacy", "payload": {}},
                    {"event_type": "row", "tabla": "factura_pagos", "payload": {}},
                    {"event_type": "bad", "tabla": "not_a_real_table", "payload": {}},
                ]
            },
        )
        assert resp.status_code == 207, resp.text
        statuses = [r["status"] for r in resp.json()["results"]]
        assert statuses == ["delivered", "applied", "unknown_table"]
