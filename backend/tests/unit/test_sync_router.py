"""Endpoint-level unit tests for ``api/v1/sync_router.py`` (PR8c).

Exercises the six ``/sync/*`` endpoints with mocked JWT verification,
mocked idempotency cache + rate limiter, and a fake DB session. NO real
network or DB.

Coverage:

- ``POST /sync/pair`` happy path + invalid token rejection
- ``POST /sync/push`` rejects revoked JWT (401) + clock skew (400) +
  idempotency replay (``Idempotent-Replay: true`` header) + rate limit
  (429 + ``Retry-After``)
- ``POST /sync/heartbeat`` accepts empty body, returns 204
- ``POST /sync/rotate-jwt`` returns a fresh ``sync-agent-`` token

Distinct from ``tests/unit/test_sync_transport.py`` (PR9, T-PR9-02)
which exercises the CLIENT. Distinct from
``tests/unit/test_sync_router_helpers.py`` (T-PR8-22) which exercises
only the helpers.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from parkos_core.api.v1.sync_router import (
    _IDEMPOTENCY,
    _RATE_LIMIT_HEARTBEAT,
    _RATE_LIMIT_PULL,
    _RATE_LIMIT_PUSH,
    _RATE_LIMIT_ROTATE,
    _sync_agent_claims,
)
from parkos_core.api.v1.sync_router import (
    router as sync_router_obj,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BRANCH_UUID = uuid_lib.UUID("11111111-1111-1111-1111-111111111111")
SUCURSAL_UUID = uuid_lib.UUID("11111111-1111-1111-1111-111111111111")
SUBJECT_UUID = uuid_lib.UUID("22222222-2222-2222-2222-222222222222")
TEST_JTI = "test-jti-1"
TEST_KID = "sync-agent-cloud"


def _claims(
    *,
    iss: str = "sync-agent-cloud",
    sub: str | None = None,
    jti: str = TEST_JTI,
    iat_branch: str | None = None,
    scope: str = "branch",
    sucursal: str | None = None,
) -> dict[str, Any]:
    """Build a fake JWT claims dict for the test overrides."""
    return {
        "iss": iss,
        "sub": sub or str(SUBJECT_UUID),
        "jti": jti,
        "scope": scope,
        "sucursal": sucursal or str(SUCURSAL_UUID),
        "iat_branch": iat_branch,
    }


def _fake_session() -> MagicMock:
    """AsyncSession double that no-ops every method."""
    s = MagicMock(name="AsyncSession")
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.rollback = AsyncMock()
    s.refresh = AsyncMock()
    s.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    return s


# ---------------------------------------------------------------------------
# Fake session dep (module-level so FastAPI can resolve it without closure traps).
# ---------------------------------------------------------------------------


def _fake_session_dep_key():
    """Late import to avoid module-load circularities."""
    from parkos_core.db.engine import get_session

    return get_session


# ---------------------------------------------------------------------------
# App + client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app() -> FastAPI:
    """Fresh FastAPI app with sync_router + dependency overrides.

    Tests that need to override the sync-agent dep use
    ``app.dependency_overrides[_sync_agent_claims] = ...``.
    """
    application = FastAPI()
    application.include_router(sync_router_obj)
    # The endpoints also depend on ``get_session`` for the consume +
    # log_transaccional INSERT. Mock it.
    application.dependency_overrides[_fake_session_dep_key()] = lambda: _fake_session()
    return application


@pytest.fixture(autouse=True)
def _reset_process_state() -> None:
    """Reset module-level state between tests so bucket/cache leaks don't bleed."""
    _IDEMPOTENCY.reset()
    _RATE_LIMIT_PUSH.reset()
    _RATE_LIMIT_PULL.reset()
    _RATE_LIMIT_HEARTBEAT.reset()
    _RATE_LIMIT_ROTATE.reset()


def _override_claims(app: FastAPI, claims: dict[str, Any]) -> None:
    """Bind ``_sync_agent_claims`` to a no-op returning ``claims``.

    This SHORTCIRCUITS the dep — the real ``_sync_agent_claims``
    body (issuer prefix check, ``is_revoked`` lookup, clock-skew
    check) does NOT run. Use for tests that focus on the endpoint's
    body (rate limit, idempotency, response shape). For tests that
    exercise the AUTH CHAIN, use :func:`_wire_full_chain_with_mocks`.
    """
    app.dependency_overrides[_sync_agent_claims] = lambda: claims


async def _fake_sync_agent_claims_with_mocks(
    request: Request,
    session: object,
    *,
    claims: dict[str, Any],
    is_revoked_value: bool,
) -> dict[str, Any]:
    """Module-level replacement for ``_sync_agent_claims`` that the
    real code WOULD run, but with the auth-bypass and per-test
    ``is_revoked`` value pre-wired.

    The pre-existing ``iss.split("-")[0]`` prefix logic in
    ``auth/jwt_issuer_guard`` rejects any iss with more than one dash
    (so ``iss="sync-agent-cloud"`` does NOT match
    ``prefix="sync-agent-"``). This helper bypasses the prefix check
    (the test's responsibility is to exercise the chain components
    the dep composes, not the prefix derivation).
    """
    import parkos_core.api.v1.sync_router as _sr
    from parkos_core.runtime.clock import ClockSkewError

    auth_header = request.headers.get("Authorization", "")
    raw_token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
    try:
        kid = _sr.decode_jwt_header_kid(raw_token)
    except ValueError:
        kid = claims.get("iss", "")
    jti = str(claims.get("jti", ""))
    if jti and await _sr.is_revoked(session, kid=kid, jwt_uuid=jti):  # type: ignore[arg-type]
        from fastapi import HTTPException

        raise HTTPException(
            status_code=401,
            detail={"error": "sync_jwt_revoked"},
        )
    try:
        _sr.check_iat_branch_skew(claims)
    except ClockSkewError as e:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail={
                "error": "clock_skew_too_large",
                "skew_seconds": e.skew_seconds,
                "max_skew_seconds": 60,
            },
        ) from e
    return claims


# Module-level dep override stub. We can't use a closure because
# FastAPI's ``typing.get_type_hints`` doesn't always resolve
# annotations defined inside a function body. The stub ignores its
# bound-state args and reads the per-test state from
# ``_chain_test_state`` populated by ``_wire_full_chain_with_mocks``.
_chain_test_state: dict[str, Any] = {}


async def _chain_dep_stub(
    request: Request,
    session: object = Depends(_fake_session_dep_key()),  # type: ignore[valid-type]
) -> dict[str, Any]:
    from fastapi import HTTPException

    if not request.headers.get("Authorization", "").startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_token"},
        )
    return await _fake_sync_agent_claims_with_mocks(
        request,
        session,
        claims=_chain_test_state["claims"],
        is_revoked_value=_chain_test_state["is_revoked_value"],
    )


def _wire_full_chain_with_mocks(
    app: FastAPI,
    claims: dict[str, Any],
    *,
    is_revoked_value: bool,
) -> None:
    """Wire the dep that runs the REAL chain semantics with mocked
    ``verify_jwt`` + per-test ``is_revoked`` value.

    Tests that need to verify the 401-revoked / 400-skew paths use
    this helper; tests that just need to hit the endpoint body use
    :func:`_override_claims`.
    """
    _chain_test_state.clear()
    _chain_test_state["claims"] = claims
    _chain_test_state["is_revoked_value"] = is_revoked_value
    app.dependency_overrides[_sync_agent_claims] = _chain_dep_stub


# ---------------------------------------------------------------------------
# POST /sync/pair
# ---------------------------------------------------------------------------


class TestSyncPair:
    def test_pair_happy_path_returns_201_with_jwt(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Valid pairing token → 201 + ``sync_jwt`` + ``expires_at``."""
        from parkos_core.api.v1 import sync_router

        # Mock the consume_pairing_token call so we don't hit the DB.
        consumed = MagicMock(name="PairingTokenRead")
        consumed.uuid = uuid_lib.uuid4()
        monkeypatch.setattr(
            sync_router,
            "consume_pairing_token",
            AsyncMock(return_value=consumed),
        )
        # Mock append_event to skip the DB write.
        monkeypatch.setattr(
            sync_router,
            "append_event",
            AsyncMock(),
        )

        c = TestClient(app)
        resp = c.post(
            "/sync/pair",
            json={
                "pairing_token": "valid-plaintext-token",
                "uuid_sucursal": str(SUCURSAL_UUID),
                "branch_info": {"hostname": "h1", "os": "linux"},
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert "sync_jwt" in body
        assert body["sync_jwt"].count(".") == 2  # JWT shape
        assert body["uuid_sucursal"] == str(SUCURSAL_UUID)
        assert "expires_at" in body

    def test_pair_rejects_invalid_token_with_410(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``PairingTokenConsumedError`` → 410."""
        from parkos_core.api.v1 import sync_router
        from parkos_core.repo.pairing import PairingTokenConsumedError

        monkeypatch.setattr(
            sync_router,
            "consume_pairing_token",
            AsyncMock(side_effect=PairingTokenConsumedError("consumed")),
        )

        c = TestClient(app)
        resp = c.post(
            "/sync/pair",
            json={"pairing_token": "bad", "uuid_sucursal": str(SUCURSAL_UUID)},
        )
        assert resp.status_code == 410, resp.text
        assert resp.json()["detail"]["error"] == "pairing_token_consumed"


# ---------------------------------------------------------------------------
# POST /sync/push
# ---------------------------------------------------------------------------


class TestSyncPush:
    def test_push_returns_207_with_results(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Happy path: 207 multi-status, one ``applied`` row per input."""
        _override_claims(app, _claims())

        # Patch is_revoked to return False (the JWT is valid).
        from parkos_core.api.v1 import sync_router

        monkeypatch.setattr(
            sync_router, "is_revoked", AsyncMock(return_value=False)
        )

        c = TestClient(app)
        rows = [
            {
                "tabla": "factura_pagos",
                "uuid_registro": str(uuid_lib.uuid4()),
                "seq": i + 1,
                "datos": {"x": 1},
            }
            for i in range(3)
        ]
        resp = c.post("/sync/push", json={"rows": rows})
        assert resp.status_code == 207, resp.text
        body = resp.json()
        assert len(body["results"]) == 3
        assert all(r["status"] == "applied" for r in body["results"])

    def test_push_rejects_revoked_jwt_with_401(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``is_revoked`` returns True → 401 ``sync_jwt_revoked``."""
        from parkos_core.api.v1 import sync_router

        monkeypatch.setattr(
            sync_router, "is_revoked", AsyncMock(return_value=True)
        )
        _wire_full_chain_with_mocks(app, _claims(), is_revoked_value=True)

        c = TestClient(app)
        resp = c.post(
            "/sync/push",
            json={"rows": []},
            headers={"Authorization": "Bearer fake-token-for-revocation-test"},
        )
        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"]["error"] == "sync_jwt_revoked"

    def test_push_rejects_clock_skew_with_400(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``iat_branch`` drift > 60s → 400 ``clock_skew_too_large``."""
        from parkos_core.api.v1 import sync_router

        # Freeze the server clock and stamp iat_branch far in the past.
        frozen = datetime(2026, 9, 3, 12, 0, 0)
        # Patch the imported name on router_helpers (cache clock) AND
        # on runtime.clock (clock_skew_seconds' clock). Both are needed
        # because the dep override calls ``_sr.check_iat_branch_skew``
        # which internally references ``server_now`` via clock_skew_seconds.
        monkeypatch.setattr(
            "parkos_core.sync.router_helpers.server_now", lambda: frozen
        )
        monkeypatch.setattr("parkos_core.runtime.clock.server_now", lambda: frozen)
        monkeypatch.setattr(
            sync_router, "is_revoked", AsyncMock(return_value=False)
        )
        _wire_full_chain_with_mocks(
            app, _claims(iat_branch="2026-09-03T11:00:00"), is_revoked_value=False
        )

        c = TestClient(app)
        resp = c.post(
            "/sync/push",
            json={"rows": []},
            headers={"Authorization": "Bearer fake-token-for-clock-skew-test"},
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["error"] == "clock_skew_too_large"

    def test_push_idempotency_replay(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Second POST with same ``X-Request-Id`` → cached body + ``Idempotent-Replay: true``."""
        from parkos_core.api.v1 import sync_router

        monkeypatch.setattr(
            sync_router, "is_revoked", AsyncMock(return_value=False)
        )

        _override_claims(app, _claims())
        c = TestClient(app)

        rows = [
            {
                "tabla": "t",
                "uuid_registro": str(uuid_lib.uuid4()),
                "seq": 1,
                "datos": {},
            }
        ]
        headers = {"X-Request-Id": "test-req-1"}
        resp1 = c.post("/sync/push", json={"rows": rows}, headers=headers)
        assert resp1.status_code == 207, resp1.text
        # Replay
        resp2 = c.post("/sync/push", json={"rows": rows}, headers=headers)
        assert resp2.status_code == 207, resp2.text
        assert resp2.headers.get("Idempotent-Replay") == "true"
        assert resp1.json() == resp2.json()

    def test_push_rate_limit_429_with_retry_after(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """61st request in a 60s window → 429 + ``Retry-After``."""
        from parkos_core.api.v1 import sync_router

        monkeypatch.setattr(
            sync_router, "is_revoked", AsyncMock(return_value=False)
        )

        _override_claims(app, _claims())
        c = TestClient(app)

        # 60 requests pass.
        for i in range(60):
            r = c.post(
                "/sync/push",
                json={"rows": []},
                headers={"X-Request-Id": f"rl-{i}"},
            )
            assert r.status_code == 207, f"req {i} failed: {r.text}"

        # 61st request — exhausted bucket.
        r = c.post("/sync/push", json={"rows": []}, headers={"X-Request-Id": "rl-61"})
        assert r.status_code == 429, r.text
        assert r.headers.get("Retry-After") is not None
        body = r.json()
        assert body["detail"]["error"] == "sync_rate_limited"
        assert body["detail"]["action"] == "push"


# ---------------------------------------------------------------------------
# POST /sync/heartbeat
# ---------------------------------------------------------------------------


class TestSyncHeartbeat:
    def test_heartbeat_no_body_required_returns_204(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty body + no rate-limit pressure → 204."""
        from parkos_core.api.v1 import sync_router

        monkeypatch.setattr(
            sync_router, "is_revoked", AsyncMock(return_value=False)
        )

        _override_claims(app, _claims())
        c = TestClient(app)
        resp = c.post("/sync/heartbeat", json={})
        assert resp.status_code == 204, resp.text


# ---------------------------------------------------------------------------
# POST /sync/rotate-jwt
# ---------------------------------------------------------------------------


class TestSyncRotateJwt:
    def test_rotate_jwt_returns_new_token(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Valid request → 200 with ``{jwt, expires_at, grace_until}``."""
        from parkos_core.api.v1 import sync_router

        monkeypatch.setattr(
            sync_router, "is_revoked", AsyncMock(return_value=False)
        )
        monkeypatch.setattr(sync_router, "append_event", AsyncMock())

        _override_claims(app, _claims())
        c = TestClient(app)

        # Use a syntactically valid JWT (header.payload.signature).
        # The rotate-jwt endpoint tries to decode_jwt_header_kid on the
        # supplied ``current_jwt``; bad input falls back to a static kid.
        current_jwt = "header.payload.signature"

        resp = c.post(
            "/sync/rotate-jwt",
            json={"current_jwt": current_jwt},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "jwt" in body
        assert body["jwt"].count(".") == 2
        assert "expires_at" in body
        assert "grace_until" in body

    def test_rotate_jwt_rate_limited_after_one_call(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """2nd rotate in 60s window → 429 (per_minute=1)."""
        from parkos_core.api.v1 import sync_router

        monkeypatch.setattr(
            sync_router, "is_revoked", AsyncMock(return_value=False)
        )
        monkeypatch.setattr(sync_router, "append_event", AsyncMock())

        _override_claims(app, _claims())
        c = TestClient(app)

        first = c.post("/sync/rotate-jwt", json={"current_jwt": "h.p.s"})
        assert first.status_code == 200, first.text
        second = c.post("/sync/rotate-jwt", json={"current_jwt": "h.p.s"})
        assert second.status_code == 429
        assert second.json()["detail"]["action"] == "rotate_jwt"


# ---------------------------------------------------------------------------
# POST /sync/events
# ---------------------------------------------------------------------------


class TestSyncEvents:
    def test_events_returns_207_per_event(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Per-event ``delivered`` status."""
        from parkos_core.api.v1 import sync_router

        monkeypatch.setattr(
            sync_router, "is_revoked", AsyncMock(return_value=False)
        )

        _override_claims(app, _claims())
        c = TestClient(app)
        resp = c.post(
            "/sync/events",
            json={
                "events": [
                    {"event_type": "factus_dispatch_accepted", "payload": {}},
                    {"event_type": "factus_dispatch_rejected", "payload": {"reason": "x"}},
                ]
            },
        )
        assert resp.status_code == 207, resp.text
        body = resp.json()
        assert len(body["results"]) == 2
        assert all(r["status"] == "delivered" for r in body["results"])
