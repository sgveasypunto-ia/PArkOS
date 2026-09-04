"""Unit tests for ``api/v1/pairing.py`` (T-PR8-20).

Covers the 3 endpoints that PR8b ships (the 4th,
``POST /admin/sucursales/{uuid}/revoke-sync``, is a PR8c stub covered
by a separate test):

- ``POST /admin/pairing-tokens`` happy path (returns plaintext once +
  sha256 hash + uuid + expires_at).
- ``GET  /admin/pairing-tokens/{uuid}`` strips ``pairing_token_hash``
  from the JSON output.
- ``POST /admin/pairing-tokens/{uuid}/revoke`` inserts a
  ``revoked_sync_jwts`` row + returns 204.

Pure-Python FastAPI tests with ``app.dependency_overrides`` so we can
mock ``get_session``, ``get_tenant_ctx``, the issuer guard, the
permission guard, and the rate limiter — no DB, no JWT signing.

The "extend consume to check revoked_sync_jwts" behavior is covered
in ``test_pairing_repo.py::test_revoked_via_revoked_sync_jwts_*`` (the
repo layer is the right place for that check; the endpoint is a thin
wrapper).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from parkos_core.api.deps import get_tenant_ctx
from parkos_core.api.rate_limit_pairing import default_limiter
from parkos_core.api.v1 import pairing as pairing_module
from parkos_core.auth.jwt_issuer_guard import requires_issuer
from parkos_core.auth.permissions import require_permission
from parkos_core.auth.tenancy import TenantContext
from parkos_core.db.engine import get_session

# Import the specific dep instances used in pairing.py — overriding
# the factory result (requires_issuer("admin-")) directly won't match the
# dep instance stored in the router.
_admin_issuer_dep = pairing_module._admin_issuer_dep
_manage_perm_dep = pairing_module._manage_perm_dep

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000c1")
SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000a1")
TOKEN_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000d1")


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_row(
    *,
    uuid: uuid_lib.UUID | None = None,
    used: bool = False,
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
    pairing_token_hash: str = "a" * 64,
    uuid_sucursal: uuid_lib.UUID | None = SUCURSAL_UUID,
    created_by: uuid_lib.UUID | None = ACTOR_UUID,
) -> MagicMock:
    row = MagicMock(name="PairingToken")
    row.uuid = uuid or TOKEN_UUID
    row.fecha_retencion_hasta = _now_naive().date()
    row.created_at = _now_naive()
    row.created_by = created_by
    row.uuid_sucursal = uuid_sucursal
    row.pairing_token_hash = pairing_token_hash
    row.expires_at = expires_at or (_now_naive() + timedelta(hours=24))
    row.used = used
    row.used_at = None
    row.used_by_branch_info = None
    row.revoked_at = revoked_at
    row.revoked_by = None
    return row


@pytest.fixture
def fake_session() -> MagicMock:
    """``AsyncSession`` double — covers add + execute + flush + commit + refresh."""
    session = MagicMock(name="AsyncSession")
    added: list[Any] = []

    result_default = MagicMock(name="Result")
    result_default.scalar_one_or_none = MagicMock(return_value=None)
    session.execute = AsyncMock(return_value=result_default)
    session.add = MagicMock(side_effect=added.append)

    async def _flush() -> None:
        for obj in added:
            if getattr(obj, "uuid", None) is None:
                obj.uuid = uuid_lib.uuid4()
            if getattr(obj, "created_at", None) is None:
                obj.created_at = _now_naive()
            if getattr(obj, "fecha_retencion_hasta", None) is None:
                obj.fecha_retencion_hasta = _now_naive().date()
            if getattr(obj, "sync_status", None) is None:
                obj.sync_status = "pendiente"
            if getattr(obj, "sync_attempts", None) is None:
                obj.sync_attempts = 0

    session.flush = AsyncMock(side_effect=_flush)

    async def _commit() -> None:
        # commit() in SQLAlchemy calls flush() first.
        await _flush()

    session.commit = AsyncMock(side_effect=_commit)
    session.refresh = AsyncMock(return_value=None)
    session.rollback = AsyncMock(return_value=None)
    session.added = added
    return session


@pytest.fixture
def app(fake_session: MagicMock) -> FastAPI:
    """FastAPI app with the pairing router + dependency overrides."""
    app = FastAPI()
    app.include_router(pairing_module.router)

    # Mock every dep the endpoints touch.
    async def _session_override():
        yield fake_session

    async def _tenant_override():
        return TenantContext(
            actor_uuid=ACTOR_UUID,
            actor_rol="admin",
            issuer_prefix="admin-",
            sucursal_uuid=SUCURSAL_UUID,
        )

    async def _issuer_override():
        return {"sub": str(ACTOR_UUID), "iss": "admin-test"}

    async def _perm_override():
        return {"sub": str(ACTOR_UUID), "iss": "admin-test"}

    # Override the SPECIFIC dep instances stored on the router (not the
    # ``requires_issuer("admin-")`` factory call, which returns a new
    # function each time).
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_tenant_ctx] = _tenant_override
    app.dependency_overrides[_admin_issuer_dep] = _issuer_override
    app.dependency_overrides[_manage_perm_dep] = _perm_override

    # The endpoint also depends on ``default_limiter.check`` directly;
    # reset the limiter for each test so the bucket is fresh.
    default_limiter.reset()

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /admin/pairing-tokens
# ---------------------------------------------------------------------------


class TestIssuePairingToken:
    def test_returns_plaintext_once_plus_sha256_hash(
        self, client: TestClient, fake_session: MagicMock
    ):
        """Happy-path 201 — plaintext + sha256 + uuid + expires_at."""
        resp = client.post(
            "/admin/pairing-tokens",
            json={"uuid_sucursal": str(SUCURSAL_UUID), "ttl_hours": 24},
            headers={"X-Sucursal-Context": str(SUCURSAL_UUID)},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()

        # Plaintext returned ONCE.
        assert "token" in body
        assert len(body["token"]) == 43
        # Hash is the canonical 64-char hex.
        assert len(body["pairing_token_hash"]) == 64
        assert all(c in "0123456789abcdef" for c in body["pairing_token_hash"])
        # The hash in the response matches the persisted row's hash.
        assert len(fake_session.added) == 1
        assert body["pairing_token_hash"] == fake_session.added[0].pairing_token_hash
        # expires_at + ttl_hours shape.
        assert body["ttl_hours"] == 24
        assert "expires_at" in body
        # UUID surfaced.
        assert uuid_lib.UUID(body["pairing_token_uuid"])

    def test_rejects_invalid_ttl(self, client: TestClient):
        resp = client.post(
            "/admin/pairing-tokens",
            json={"uuid_sucursal": str(SUCURSAL_UUID), "ttl_hours": 0},
            headers={"X-Sucursal-Context": str(SUCURSAL_UUID)},
        )
        assert resp.status_code == 422

        resp = client.post(
            "/admin/pairing-tokens",
            json={"uuid_sucursal": str(SUCURSAL_UUID), "ttl_hours": 9999},
            headers={"X-Sucursal-Context": str(SUCURSAL_UUID)},
        )
        assert resp.status_code == 422

    def test_rate_limit_6th_returns_429(self, client: TestClient):
        """6th request within the hour returns 429."""
        for _ in range(5):
            r = client.post(
                "/admin/pairing-tokens",
                json={"uuid_sucursal": str(SUCURSAL_UUID)},
                headers={"X-Sucursal-Context": str(SUCURSAL_UUID)},
            )
            assert r.status_code == 201, r.text
        # 6th call → rate limit.
        r = client.post(
            "/admin/pairing-tokens",
            json={"uuid_sucursal": str(SUCURSAL_UUID)},
            headers={"X-Sucursal-Context": str(SUCURSAL_UUID)},
        )
        assert r.status_code == 429
        assert r.json()["detail"]["error"] == "pairing_token_rate_limited"


# ---------------------------------------------------------------------------
# GET /admin/pairing-tokens/{uuid}
# ---------------------------------------------------------------------------


class TestReadPairingToken:
    def test_returns_metadata_strips_hash(
        self, client: TestClient, fake_session: MagicMock
    ):
        row = _make_row(uuid=TOKEN_UUID, used=False)
        fake_session.execute = AsyncMock(
            return_value=_result_with_scalar(row)
        )

        resp = client.get(
            f"/admin/pairing-tokens/{TOKEN_UUID}",
            headers={"X-Sucursal-Context": str(SUCURSAL_UUID)},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # Audit fields exposed.
        assert body["uuid"] == str(TOKEN_UUID)
        assert body["uuid_sucursal"] == str(SUCURSAL_UUID)
        assert body["used"] is False
        # pairing_token_hash is NOT in the public shape.
        assert "pairing_token_hash" not in body

    def test_404_when_not_found(self, client: TestClient, fake_session: MagicMock):
        fake_session.execute = AsyncMock(
            return_value=_result_with_scalar(None)
        )

        resp = client.get(
            f"/admin/pairing-tokens/{uuid_lib.uuid4()}",
            headers={"X-Sucursal-Context": str(SUCURSAL_UUID)},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/pairing-tokens/{uuid}/revoke
# ---------------------------------------------------------------------------


class TestRevokePairingToken:
    def test_inserts_revoked_sync_jwt_row_returns_204(
        self, client: TestClient, fake_session: MagicMock
    ):
        row = _make_row(uuid=TOKEN_UUID)
        fake_session.execute = AsyncMock(
            return_value=_result_with_scalar(row)
        )

        resp = client.post(
            f"/admin/pairing-tokens/{TOKEN_UUID}/revoke",
            headers={"X-Sucursal-Context": str(SUCURSAL_UUID)},
        )
        assert resp.status_code == 204, resp.text
        # The endpoint INSERTs a RevokedSyncJwt row.
        assert len(fake_session.added) == 1
        revoked = fake_session.added[0]
        # Architectural deviation: revocation goes through
        # ``revoked_sync_jwts`` (the inmutable trigger blocks UPDATE on
        # ``pairing_tokens``).
        assert revoked.jwt_kid == f"pairing_token:{TOKEN_UUID}"
        assert revoked.jwt_uuid == str(TOKEN_UUID)
        assert revoked.revoked_by == ACTOR_UUID
        assert revoked.motivo.startswith("admin_revoked_at_")

    def test_404_when_not_found(self, client: TestClient, fake_session: MagicMock):
        fake_session.execute = AsyncMock(
            return_value=_result_with_scalar(None)
        )

        resp = client.post(
            f"/admin/pairing-tokens/{uuid_lib.uuid4()}/revoke",
            headers={"X-Sucursal-Context": str(SUCURSAL_UUID)},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/sucursales/{uuid}/revoke-sync (PR8c wire-up)
# ---------------------------------------------------------------------------


class TestRevokeSync:
    """PR8c replaces the PR8b 501 stub with the real ``revoke_jwt`` call.

    The admin POSTs ``{jwt_kid, jwt_uuid}`` in the body; the endpoint
    inserts a ``revoked_sync_jwts`` row scoped to the branch. The
    sync-router's ``is_revoked`` lookup catches the revocation on the
    next ``POST /sync/push`` / ``/pull`` / ``/heartbeat`` (returns 401
    with ``{"error": "sync_jwt_revoked"}``). Duplicates are idempotent
    — ``revoke_jwt`` returns ``None`` and the endpoint still answers
    204.
    """

    def _make_app(self, fake_session: MagicMock) -> FastAPI:
        app = FastAPI()
        app.include_router(pairing_module.router)
        app.include_router(pairing_module.sync_revoke_router)

        async def _session_override():
            yield fake_session

        async def _tenant_override():
            return TenantContext(
                actor_uuid=ACTOR_UUID,
                actor_rol="admin",
                issuer_prefix="admin-",
                sucursal_uuid=SUCURSAL_UUID,
            )

        async def _issuer_override():
            return {"sub": str(ACTOR_UUID), "iss": "admin-test"}

        async def _perm_override():
            return {"sub": str(ACTOR_UUID), "iss": "admin-test"}

        app.dependency_overrides[get_session] = _session_override
        app.dependency_overrides[get_tenant_ctx] = _tenant_override
        app.dependency_overrides[_admin_issuer_dep] = _issuer_override
        app.dependency_overrides[_manage_perm_dep] = _perm_override
        return app

    def test_returns_204_and_inserts_revoked_sync_jwt_row(
        self, fake_session: MagicMock
    ) -> None:
        """Happy path — body carries kid + jwt_uuid, endpoint inserts a
        ``revoked_sync_jwts`` row + commits + returns 204.
        """
        app = self._make_app(fake_session)
        c = TestClient(app)
        resp = c.post(
            f"/admin/sucursales/{SUCURSAL_UUID}/revoke-sync",
            headers={"X-Sucursal-Context": str(SUCURSAL_UUID)},
            json={"jwt_kid": "sync-agent-cloud", "jwt_uuid": "00000000-0000-0000-0000-000000000aaa"},
        )
        assert resp.status_code == 204, resp.text
        # One ``revoked_sync_jwts`` row INSERTed.
        assert len(fake_session.added) == 1
        row = fake_session.added[0]
        assert row.jwt_kid == "sync-agent-cloud"
        assert row.jwt_uuid == "00000000-0000-0000-0000-000000000aaa"
        assert row.revoked_by == ACTOR_UUID
        # expires_at is server-set to now + 24h (JWT_OVERLAP_HOURS).
        # The fake_session's flush() populates missing attributes, but
        # the endpoint sets expires_at explicitly — verify it landed.
        assert row.expires_at is not None

    def test_returns_204_on_duplicate_revocation(
        self, fake_session: MagicMock
    ) -> None:
        """Duplicate revocations are idempotent — the UK violation in
        ``revoke_jwt`` is swallowed and the endpoint still answers 204.
        """
        from parkos_core.repo.revoked_sync_jwt import revoke_jwt as real_revoke_jwt

        async def _fake_revoke_jwt(*args, **kwargs):
            return None  # duplicate — UK violation swallowed

        # Patch the symbol the endpoint imported, so the call returns
        # None (the "duplicate" branch).
        import parkos_core.api.v1.pairing as _pairing

        original = _pairing.revoke_jwt
        _pairing.revoke_jwt = _fake_revoke_jwt  # type: ignore[assignment]
        try:
            app = self._make_app(fake_session)
            c = TestClient(app)
            resp = c.post(
                f"/admin/sucursales/{SUCURSAL_UUID}/revoke-sync",
                headers={"X-Sucursal-Context": str(SUCURSAL_UUID)},
                json={"jwt_kid": "k1", "jwt_uuid": "j1"},
            )
            assert resp.status_code == 204
        finally:
            _pairing.revoke_jwt = original

    def test_rejects_missing_body(self, fake_session: MagicMock) -> None:
        """Missing body → 422 from Pydantic (jwt_kid + jwt_uuid required)."""
        app = self._make_app(fake_session)
        c = TestClient(app)
        resp = c.post(
            f"/admin/sucursales/{SUCURSAL_UUID}/revoke-sync",
            headers={"X-Sucursal-Context": str(SUCURSAL_UUID)},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result_with_scalar(value: Any) -> MagicMock:
    """Build a ``Result`` double whose ``scalar_one_or_none`` returns ``value``."""
    result = MagicMock(name="Result")
    result.scalar_one_or_none = MagicMock(return_value=value)
    return result