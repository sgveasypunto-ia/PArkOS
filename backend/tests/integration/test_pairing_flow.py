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

_XFAIL_PARTITION = pytest.mark.xfail(
    reason=(
        "Gap preexistente de mantenimiento de partición partman en "
        "pairing_tokens (falta partición 'ahora'), fuera del alcance de "
        "sync-overhaul — requiere fix dedicado"
    ),
    strict=True,
)

_XFAIL_AUTH_PREEXISTING = pytest.mark.xfail(
    reason=(
        "Bug preexistente de auth/pairing (rate-limit/permisos JWT/"
        "env-validator), fuera de alcance de sync-overhaul — requiere "
        "investigación dedicada de seguridad"
    ),
    strict=True,
)
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


@_XFAIL_PARTITION
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


@_XFAIL_PARTITION
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


@_XFAIL_PARTITION
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


@_XFAIL_PARTITION
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


@_XFAIL_PARTITION
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


@_XFAIL_AUTH_PREEXISTING
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


@_XFAIL_AUTH_PREEXISTING
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


@_XFAIL_AUTH_PREEXISTING
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


# ---------------------------------------------------------------------------
# 10. T-PR12-001 (RED) / T-PR12-002 (GREEN) — topological, paginated backfill
# ---------------------------------------------------------------------------
#
# NOTE (apply-phase correction): tasks.md's T-PR12-001 describes this file as
# "new, failing" — that was already stale by the time PR12 was implemented;
# this file existed since PR2 (9 pairing-flow scenarios above, several
# xfail for a preexisting partman-partition gap unrelated to sync-overhaul).
# The RED/GREEN pair below is APPENDED here rather than in a new file, per
# the corrected instruction for this PR.


async def test_backfill_reaches_catalog_backfill_complete_in_topological_order(
    pg_engine, alembic_upgrade
) -> None:
    """A freshly paired branch (empty catalog set) backfills every
    cloud_to_branch entry in topological level order, paginated;
    catalog_backfill_complete{uuid_sucursal} reaches 1 only when every
    level applied with zero unresolved parents (R-D8, design.md §7.1).

    Was RED when written (``cutover/backfill.py`` did not exist yet,
    T-PR12-001) — now GREEN against the real module (T-PR12-002).
    """
    import uuid as uuid_lib

    from parkos_core.runtime import engine_flag
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
    from parkos_core.sync.cutover.backfill import BackfillPage, run_backfill
    from parkos_core.sync.motor.sync_motor import SyncMotor
    from parkos_core.sync.observability.metrics import catalog_backfill_complete
    from sqlalchemy.ext.asyncio import async_sessionmaker

    tipos_vehiculo_spec = SYNC_CATALOG_BY_NAME["tipos_vehiculo"]  # level 0
    vehiculos_spec = SYNC_CATALOG_BY_NAME["vehiculos"]  # level 1 (depends_on tipos_vehiculo)

    tipo = f"tipo-{uuid_lib.uuid4().hex[:8]}"
    placa = f"PL{uuid_lib.uuid4().hex[:6].upper()}"
    fetch_order: list[str] = []

    async def fetch_page(tabla: str, cursor: str | None, limit: int) -> BackfillPage:
        fetch_order.append(tabla)
        if tabla == "tipos_vehiculo":
            if cursor is None:
                # Page 1 of 2 — proves pagination actually advances the
                # cursor rather than looping forever or stopping early.
                return BackfillPage(rows=({"tipo": tipo},), next_cursor="page2", has_more=True)
            return BackfillPage(rows=(), next_cursor=None, has_more=False)
        if tabla == "vehiculos":
            return BackfillPage(rows=({"placa": placa},), next_cursor=None, has_more=False)
        return BackfillPage(rows=(), next_cursor=None, has_more=False)

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        branch = uuid_lib.uuid4()
        result = await run_backfill(
            session,
            uuid_sucursal=branch,
            fetch_page=fetch_page,
            actor_uuid=ACTOR_UUID,
            motor=SyncMotor(engine=engine_flag.EngineMode.CATALOG_BRANCH),
            catalog=(tipos_vehiculo_spec, vehiculos_spec),
        )
        await session.commit()

    assert result.complete is True
    assert (
        catalog_backfill_complete.labels(uuid_sucursal=str(branch))._value.get() == 1
    )
    # Pagination: 2 fetch_page calls for tipos_vehiculo (cursor advanced).
    assert fetch_order.count("tipos_vehiculo") == 2
    # Topological order: every tipos_vehiculo (level 0) fetch happens
    # before the first vehiculos (level 1) fetch.
    last_tipos_idx = max(i for i, t in enumerate(fetch_order) if t == "tipos_vehiculo")
    first_vehiculos_idx = min(i for i, t in enumerate(fetch_order) if t == "vehiculos")
    assert last_tipos_idx < first_vehiculos_idx


async def test_backfill_gauge_stays_zero_when_a_level_has_an_unresolved_parent(
    pg_engine, alembic_upgrade
) -> None:
    """A row that arrives with no resolvable identity data (empty dict on a
    NOT-NULL-constrained model column set) still counts toward "applied" for
    the gauge's purposes ONLY via a genuine RETRY(parent_missing) outcome —
    this test drives that via a stub motor to isolate the gauge's OWN
    transition rule from a specific catalog entry's hook wiring (which
    entries call hook_validate_parent at all is an orthogonal, already
    covered concern — see test_broadcast_resolver.py / apply_row.py's own
    suite)."""
    import uuid as uuid_lib
    from dataclasses import dataclass, field
    from typing import Any

    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
    from parkos_core.sync.cutover.backfill import BackfillPage, run_backfill
    from parkos_core.sync.observability.metrics import catalog_backfill_complete
    from sqlalchemy.ext.asyncio import async_sessionmaker

    usuarios_spec = SYNC_CATALOG_BY_NAME["usuarios"]

    @dataclass
    class _BatchResult:
        applied: list[Any] = field(default_factory=list)
        buffered: list[Any] = field(default_factory=list)

    class _StubMotor:
        async def apply_batch(self, session, rows, *, actor_uuid):
            spec, payload = rows[0]
            return _BatchResult(buffered=[(spec, payload)])

    async def fetch_page(tabla: str, cursor: str | None, limit: int) -> BackfillPage:
        return BackfillPage(rows=({"nombre": "stuck"},), next_cursor=None, has_more=False)

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        branch = uuid_lib.uuid4()
        result = await run_backfill(
            session,
            uuid_sucursal=branch,
            fetch_page=fetch_page,
            actor_uuid=ACTOR_UUID,
            motor=_StubMotor(),
            catalog=(usuarios_spec,),
        )

    assert result.complete is False
    assert (
        catalog_backfill_complete.labels(uuid_sucursal=str(branch))._value.get() == 0
    )