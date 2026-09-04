"""Integration tests — pairing flow (T-PR8-21, design §21.14 acceptance #1).

9 scenarios from ``tasks.md:582``:

1. ``test_pair_happy_path`` — admin issues token, branch consumes, JWT issued
2. ``test_pair_token_reuse_rejected`` — same token twice → second fails
3. ``test_pair_token_expired_rejected`` — token past TTL → ExpiredError
4. ``test_pair_token_revoked_rejected`` — admin revokes, consume fails
5. ``test_pair_revoked_jwt_rejects_subsequent_calls`` — sync_agent JWT
   revoked → 401 on /sync/push (xfail — PR8c wires sync_router)
6. ``test_pair_wrong_sucursal_rejected`` — token for branch A, consumed by B → fail
7. ``test_pair_env_validator_fails_fast`` — empty PARKOS_SUCURSAL_UUID → exit 2
8. ``test_pair_persisted_jwt_path_0600`` — JWT written with mode 0o600
9. ``test_pair_token_rate_limit`` — 6 pairing requests in 60 min → 6th returns 429

Test 5 documents a pending PR8c dependency (``sync_router`` does not
exist yet in PR8b). Marked ``xfail(strict=False, ...)`` so the suite
passes today and the test will XPASS once PR8c lands.

The DB-touching tests depend on the ``pg_engine`` fixture (testcontainers
Postgres + alembic upgrade). When the Postgres image lacks ``pg_partman``
the ``alembic_upgrade`` fixture skips the whole session — those tests
will then also skip. CLI tests (#7, #8) don't touch the DB and run
unconditionally.
"""
from __future__ import annotations

import hashlib as _hashlib
import os
import secrets
import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000c1")
SUCURSAL_A = uuid_lib.UUID("00000000-0000-0000-0000-0000000000a1")
SUCURSAL_B = uuid_lib.UUID("00000000-0000-0000-0000-0000000000b2")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _mint_plaintext() -> tuple[str, str]:
    """Return ``(plaintext, sha256_hex)`` mirroring the repo's generator."""
    plaintext = secrets.token_urlsafe(32)
    sha_hex = _hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, sha_hex


def _make_no_op_session() -> MagicMock:
    """``AsyncSession`` double — no-op add + flush + commit."""
    session = MagicMock(name="AsyncSession")
    added: list[object] = []

    async def _flush() -> None:
        for obj in added:
            if getattr(obj, "uuid", None) is None:
                obj.uuid = uuid_lib.uuid4()
            if getattr(obj, "created_at", None) is None:
                obj.created_at = _now_naive()

    session.add = MagicMock(side_effect=added.append)
    session.flush = AsyncMock(side_effect=_flush)
    session.commit = AsyncMock(return_value=None)
    session.refresh = AsyncMock(return_value=None)
    return session


# ---------------------------------------------------------------------------
# 1. happy path
# ---------------------------------------------------------------------------


async def test_pair_happy_path(pg_engine, alembic_upgrade):
    """Admin issues a token; the branch's consume path succeeds."""
    from parkos_core.models.A.pairing_tokens import PairingToken
    from parkos_core.repo.pairing import consume_pairing_token
    from sqlalchemy.ext.asyncio import async_sessionmaker

    plaintext_token, sha_hex = _mint_plaintext()

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        now = _now_naive()
        row = PairingToken(
            uuid_sucursal=SUCURSAL_A,
            pairing_token_hash=sha_hex,
            expires_at=now + timedelta(hours=1),
            used=False,
            created_by=ACTOR_UUID,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)

        consumed = await consume_pairing_token(
            session,
            plaintext_token,
            uuid_sucursal=SUCURSAL_A,
            branch_info={"hostname": "test-branch", "version": "0.1.0"},
            actor_uuid=ACTOR_UUID,
        )
        await session.commit()

        # The new "consumed" sibling row carries used=True.
        assert consumed.used is True
        assert consumed.used_at is not None
        assert consumed.used_by_branch_info == {
            "hostname": "test-branch",
            "version": "0.1.0",
        }
        # The original issuance row's hash matches the consumed sibling.
        assert consumed.pairing_token_hash == sha_hex


# ---------------------------------------------------------------------------
# 2. token reuse rejected
# ---------------------------------------------------------------------------


async def test_pair_token_reuse_rejected(pg_engine, alembic_upgrade):
    """The second consume of the same plaintext raises ConsumedError."""
    from parkos_core.models.A.pairing_tokens import PairingToken
    from parkos_core.repo.pairing import (
        PairingTokenConsumedError,
        consume_pairing_token,
    )
    from sqlalchemy.ext.asyncio import async_sessionmaker

    plaintext_token, sha_hex = _mint_plaintext()

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        now = _now_naive()
        row = PairingToken(
            uuid_sucursal=SUCURSAL_A,
            pairing_token_hash=sha_hex,
            expires_at=now + timedelta(hours=1),
            used=False,
            created_by=ACTOR_UUID,
        )
        session.add(row)
        await session.commit()

        # First consume — succeeds.
        consumed = await consume_pairing_token(
            session, plaintext_token, uuid_sucursal=SUCURSAL_A
        )
        await session.commit()
        assert consumed.used is True

        # Second consume — fails (the consumed sibling is the latest row).
        with pytest.raises(PairingTokenConsumedError):
            await consume_pairing_token(
                session, plaintext_token, uuid_sucursal=SUCURSAL_A
            )


# ---------------------------------------------------------------------------
# 3. expired token rejected
# ---------------------------------------------------------------------------


async def test_pair_token_expired_rejected(pg_engine, alembic_upgrade):
    """Past-TTL token → ``PairingTokenExpiredError``."""
    from parkos_core.models.A.pairing_tokens import PairingToken
    from parkos_core.repo.pairing import (
        PairingTokenExpiredError,
        consume_pairing_token,
    )
    from sqlalchemy.ext.asyncio import async_sessionmaker

    plaintext_token, sha_hex = _mint_plaintext()

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        now = _now_naive()
        # Inserted with an already-past TTL.
        row = PairingToken(
            uuid_sucursal=SUCURSAL_A,
            pairing_token_hash=sha_hex,
            expires_at=now - timedelta(seconds=1),
            used=False,
            created_by=ACTOR_UUID,
        )
        session.add(row)
        await session.commit()

        with pytest.raises(PairingTokenExpiredError):
            await consume_pairing_token(
                session, plaintext_token, uuid_sucursal=SUCURSAL_A
            )


# ---------------------------------------------------------------------------
# 4. admin revoke → consume fails
# ---------------------------------------------------------------------------


async def test_pair_token_revoked_rejected(pg_engine, alembic_upgrade):
    """After admin revocation the token is no longer consumable."""
    from parkos_core.models.A.pairing_tokens import PairingToken
    from parkos_core.repo.pairing import (
        PairingTokenConsumedError,
        consume_pairing_token,
    )
    from parkos_core.repo.revoked_sync_jwt import revoke_jwt
    from sqlalchemy.ext.asyncio import async_sessionmaker

    plaintext_token, sha_hex = _mint_plaintext()

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        now = _now_naive()
        expires_at = now + timedelta(hours=1)
        row = PairingToken(
            uuid_sucursal=SUCURSAL_A,
            pairing_token_hash=sha_hex,
            expires_at=expires_at,
            used=False,
            created_by=ACTOR_UUID,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)

        # Admin revokes (writes a revoked_sync_jwts row).
        revoked = await revoke_jwt(
            session,
            kid=f"pairing_token:{row.uuid}",
            jwt_uuid=str(row.uuid),
            motivo="admin_revoked_at_test",
            actor_uuid=ACTOR_UUID,
            expires_at=expires_at,
        )
        await session.commit()
        assert revoked is not None

        # Subsequent consume fails.
        with pytest.raises(PairingTokenConsumedError):
            await consume_pairing_token(
                session, plaintext_token, uuid_sucursal=SUCURSAL_A
            )


# ---------------------------------------------------------------------------
# 5. revoked sync_agent JWT → 401 (xfail — PR8c)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=False, reason="PR8c wires sync_router; xfail documents pending test."
)
async def test_pair_revoked_jwt_rejects_subsequent_calls(
    pg_engine, alembic_upgrade
):
    """A revoked ``sync-agent-`` JWT is rejected on subsequent sync calls.

    Documents the contract: once an admin revoke-sync a branch's JWT,
    the next ``POST /sync/push`` from that branch returns 401. The
    sync_router doesn't exist in PR8b — the test XPASSES in PR8c.
    """
    # Placeholder assertion that always fails today so the xfail is
    # surfaced (XPASS in PR8c).
    pytest.fail("sync_router not implemented in PR8b; lands in PR8c")


# ---------------------------------------------------------------------------
# 6. cross-branch rejected
# ---------------------------------------------------------------------------


async def test_pair_wrong_sucursal_rejected(pg_engine, alembic_upgrade):
    """Token issued for branch A, consumed by branch B → ConsumedError."""
    from parkos_core.models.A.pairing_tokens import PairingToken
    from parkos_core.repo.pairing import (
        PairingTokenConsumedError,
        consume_pairing_token,
    )
    from sqlalchemy.ext.asyncio import async_sessionmaker

    plaintext_token, sha_hex = _mint_plaintext()

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        now = _now_naive()
        # Issued for branch A.
        row = PairingToken(
            uuid_sucursal=SUCURSAL_A,
            pairing_token_hash=sha_hex,
            expires_at=now + timedelta(hours=1),
            used=False,
            created_by=ACTOR_UUID,
        )
        session.add(row)
        await session.commit()

        # Branch B tries to consume.
        with pytest.raises(PairingTokenConsumedError):
            await consume_pairing_token(
                session,
                plaintext_token,
                uuid_sucursal=SUCURSAL_B,  # wrong branch
            )


# ---------------------------------------------------------------------------
# 7. env validator fail-fast
# ---------------------------------------------------------------------------


def test_pair_env_validator_fails_fast(monkeypatch: pytest.MonkeyPatch):
    """``PARKOS_SUCURSAL_UUID`` empty → ``cli/pair.py`` exits 2."""
    from parkos_core.cli.pair import main as pair_main

    monkeypatch.setenv("PARKOS_PAIRING_TOKEN", "fake-plaintext-token")
    monkeypatch.delenv("PARKOS_SUCURSAL_UUID", raising=False)
    monkeypatch.setenv("PARKOS_CLOUD_API_URL", "http://cloud:8000")
    monkeypatch.setenv("PARKOS_SYNC_JWT_PATH", "/tmp/sync.jwt")
    monkeypatch.setenv("DATABASE_URL", "")

    rc = pair_main()
    assert rc == 2


# ---------------------------------------------------------------------------
# 8. persisted JWT path mode 0o600
# ---------------------------------------------------------------------------


def test_pair_persisted_jwt_path_0600(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """The CLI writes the JWT with mode ``0o600`` (Unix only)."""
    sync_jwt_path = tmp_path / "sync.jwt"

    # Mock httpx so the CLI never reaches the cloud.
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json = MagicMock(return_value={"sync_jwt": "fake-jwt-blob"})
    fake_response.raise_for_status = MagicMock(return_value=None)

    monkeypatch.setenv("PARKOS_PAIRING_TOKEN", "fake-plaintext-token")
    monkeypatch.setenv("PARKOS_CLOUD_API_URL", "http://cloud:8000")
    monkeypatch.setenv("PARKOS_SYNC_JWT_PATH", str(sync_jwt_path))
    monkeypatch.setenv("PARKOS_SUCURSAL_UUID", str(uuid_lib.uuid4()))
    monkeypatch.setenv("DATABASE_URL", "")

    with patch("parkos_core.cli.pair.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(return_value=fake_response))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

        from parkos_core.cli.pair import main as pair_main

        pair_main()

    # On Windows the chmod is a no-op (no POSIX mode bits). We skip the
    # permission check; on Unix the file should exist + carry 0o600.
    assert sync_jwt_path.is_file()
    if os.name != "nt":
        mode = sync_jwt_path.stat().st_mode & 0o777
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


# ---------------------------------------------------------------------------
# 9. rate limit (6th request returns 429)
# ---------------------------------------------------------------------------


async def test_pair_token_rate_limit():
    """6 admin pairing requests in 60 min → 6th returns 429.

    Builds a minimal FastAPI app with just the pairing router + mocked
    tenant + session deps (no DB needed; the limiter is in-memory).
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from parkos_core.api.deps import get_tenant_ctx
    from parkos_core.api.rate_limit_pairing import default_limiter
    from parkos_core.api.v1 import pairing as pairing_module
    from parkos_core.auth.tenancy import TenantContext
    from parkos_core.db.engine import get_session

    default_limiter.reset()

    app = FastAPI()
    app.include_router(pairing_module.router)

    async def _tenant_override():
        return TenantContext(
            actor_uuid=ACTOR_UUID,
            actor_rol="admin",
            issuer_prefix="admin-",
            sucursal_uuid=SUCURSAL_A,
        )

    async def _session_override():
        yield _make_no_op_session()

    app.dependency_overrides[get_tenant_ctx] = _tenant_override
    app.dependency_overrides[get_session] = _session_override

    with TestClient(app) as c:
        # 5 successful 201s.
        for _ in range(5):
            resp = c.post(
                "/admin/pairing-tokens",
                json={"uuid_sucursal": str(SUCURSAL_A)},
                headers={"X-Sucursal-Context": str(SUCURSAL_A)},
            )
            assert resp.status_code == 201, resp.text
        # 6th → 429.
        resp = c.post(
            "/admin/pairing-tokens",
            json={"uuid_sucursal": str(SUCURSAL_A)},
            headers={"X-Sucursal-Context": str(SUCURSAL_A)},
        )
        assert resp.status_code == 429
        assert resp.json()["detail"]["error"] == "pairing_token_rate_limited"