"""Unit tests for ``repo.pairing`` (T-PR8-19).

Covers:

- :func:`generate_pairing_token` produces 43-char base64url plaintext
  + 64-char hex hash.
- :func:`hash_pairing_token` is deterministic + matches ``generate_pairing_token``.
- :func:`create_pairing_token` writes ONLY the SHA-256 hash (never the
  plaintext) and returns a :class:`PairingTokenRead` carrying the
  hash + uuid + expires_at + audit fields.
- :func:`consume_pairing_token` happy path.
- :func:`consume_pairing_token` with wrong plaintext → NotFoundError.
- :func:`consume_pairing_token` with expired plaintext → ExpiredError.
- :func:`consume_pairing_token` concurrent session wins → ConsumedError.
- :func:`find_active_pairing_token` returns the row when active, None
  when revoked (via revoked_sync_jwts).

Pure Python + ``unittest.mock``. No DB. The tests stub ``AsyncSession``
following the dian-conftest pattern (``session.execute`` returns a
``Result`` double whose ``scalar_one_or_none`` is per-call configured;
``session.add`` appends to a ``session.added`` list; ``flush`` + ``refresh``
are ``AsyncMock`` that stamp server-defaulted columns).
"""
from __future__ import annotations

import hashlib
import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000a1")
ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000b1")
ISSUED_HASH = "a" * 64


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_pairing_row(
    *,
    uuid: uuid_lib.UUID | None = None,
    used: bool = False,
    used_at: datetime | None = None,
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
    uuid_sucursal: uuid_lib.UUID | None = SUCURSAL_UUID,
    pairing_token_hash: str = ISSUED_HASH,
    created_at: datetime | None = None,
    created_by: uuid_lib.UUID | None = None,
) -> MagicMock:
    """Build a ``PairingToken`` row double carrying only the fields the repo reads."""
    row = MagicMock(name="PairingToken")
    row.uuid = uuid or uuid_lib.uuid4()
    row.fecha_retencion_hasta = _now_naive().date()
    row.created_at = created_at or _now_naive()
    row.created_by = created_by
    row.uuid_sucursal = uuid_sucursal
    row.pairing_token_hash = pairing_token_hash
    row.expires_at = expires_at or (_now_naive() + timedelta(hours=24))
    row.used = used
    row.used_at = used_at
    row.used_by_branch_info = None
    row.revoked_at = revoked_at
    row.revoked_by = None
    return row


def _make_session(
    *,
    existing: MagicMock | None = None,
    locked: MagicMock | None = None,
    revoked_subquery_returns_none: bool = True,
) -> MagicMock:
    """Mock ``AsyncSession`` wired for the consume-pairing-token call shape.

    ``session.execute`` returns ``session._next_result`` so tests can
    stage the lookup + lock results independently.

    The ``revoked_sync_jwt.is_revoked`` subquery is also called via
    ``session.execute``; we set ``_next_result`` to a list of 3 entries
    that the repo consumes in order. The last entry is the revoke-check
    result (None when not revoked, the uuid otherwise).
    """
    session = MagicMock(name="AsyncSession")
    added: list[Any] = []

    # Stage results. consume_pairing_token's execute calls (in order):
    #  1. base_stmt — existing row check
    #  2. is_revoked subquery — None / uuid
    #  3. lock_stmt — SKIP LOCKED claim
    revoke_result = MagicMock(name="RevokedResult")
    revoke_result.scalar_one_or_none = MagicMock(
        return_value=None if revoked_subquery_returns_none else uuid_lib.uuid4()
    )

    results: list[MagicMock] = []
    base_result = MagicMock(name="BaseResult")
    base_result.scalar_one_or_none = MagicMock(return_value=existing)
    results.append(base_result)

    results.append(revoke_result)

    lock_result = MagicMock(name="LockResult")
    lock_result.scalar_one_or_none = MagicMock(return_value=locked)
    results.append(lock_result)

    async def _execute_side_effect(*args: Any, **kwargs: Any):
        if not results:
            raise AssertionError("session.execute called too many times")
        return results.pop(0)

    session.execute = AsyncMock(side_effect=_execute_side_effect)
    session.add = MagicMock(side_effect=added.append)

    async def _flush() -> None:
        for obj in added:
            if getattr(obj, "uuid", None) is None:
                obj.uuid = uuid_lib.uuid4()
            if getattr(obj, "created_at", None) is None:
                obj.created_at = _now_naive()
            # fecha_retencion_hasta is server-defaulted to current_date()
            # — the real flush would populate it; the mock matches.
            if getattr(obj, "fecha_retencion_hasta", None) is None:
                obj.fecha_retencion_hasta = _now_naive().date()
            # sync_status is server-defaulted to 'pendiente'.
            if getattr(obj, "sync_status", None) is None:
                obj.sync_status = "pendiente"
            # sync_attempts is server-defaulted to 0.
            if getattr(obj, "sync_attempts", None) is None:
                obj.sync_attempts = 0

    session.flush = AsyncMock(side_effect=_flush)
    session.commit = AsyncMock(return_value=None)
    session.rollback = AsyncMock(return_value=None)
    session.refresh = AsyncMock(return_value=None)
    session.added = added
    return session


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestGeneratePairingToken:
    def test_returns_tuple(self):
        from parkos_core.repo.pairing import generate_pairing_token

        plaintext, sha = generate_pairing_token()
        assert isinstance(plaintext, str)
        assert isinstance(sha, str)

    def test_plaintext_is_43_chars(self):
        """``secrets.token_urlsafe(32)`` yields a 43-char URL-safe string."""
        from parkos_core.repo.pairing import generate_pairing_token

        plaintext, _ = generate_pairing_token()
        assert len(plaintext) == 43

    def test_hash_is_64_char_hex(self):
        """SHA-256 hex digest is exactly 64 chars [0-9a-f]."""
        from parkos_core.repo.pairing import generate_pairing_token

        _, sha = generate_pairing_token()
        assert len(sha) == 64
        assert all(c in "0123456789abcdef" for c in sha)

    def test_hash_matches_plaintext(self):
        from parkos_core.repo.pairing import generate_pairing_token, hash_pairing_token

        plaintext, sha = generate_pairing_token()
        assert sha == hash_pairing_token(plaintext)

    def test_two_calls_produce_distinct_values(self):
        """Cryptographic RNG — collisions are vanishingly unlikely."""
        from parkos_core.repo.pairing import generate_pairing_token

        p1, h1 = generate_pairing_token()
        p2, h2 = generate_pairing_token()
        assert p1 != p2
        assert h1 != h2


class TestHashPairingToken:
    def test_deterministic(self):
        from parkos_core.repo.pairing import hash_pairing_token

        s = "abc123def456"
        assert hash_pairing_token(s) == hash_pairing_token(s)

    def test_matches_hashlib_sha256_hex(self):
        from parkos_core.repo.pairing import hash_pairing_token

        s = "hello-world-pairing-token"
        assert hash_pairing_token(s) == hashlib.sha256(s.encode()).hexdigest()


# ---------------------------------------------------------------------------
# create_pairing_token
# ---------------------------------------------------------------------------


class TestCreatePairingToken:
    @pytest.mark.asyncio
    async def test_writes_sha256_only_never_plaintext(self):
        """The DB row carries the hash + uuid + expires_at — NEVER the plaintext."""
        from parkos_core.repo.pairing import create_pairing_token

        session = _make_session()
        await create_pairing_token(
            session,
            uuid_sucursal=SUCURSAL_UUID,
            actor_uuid=ACTOR_UUID,
        )

        # One row added.
        assert len(session.added) == 1
        row = session.added[0]
        # Hash is populated (64-char hex).
        assert len(row.pairing_token_hash) == 64
        assert all(c in "0123456789abcdef" for c in row.pairing_token_hash)
        # ``token`` is NOT a column on the model — the plaintext was
        # generated, used to compute the hash, and discarded. We
        # assert the row's own attributes do not include `` plaintext``.
        assert not hasattr(row, "plaintext") or row.plaintext is None

    @pytest.mark.asyncio
    async def test_returns_pairing_token_read(self):
        """The return shape is ``PairingTokenRead`` with hash + expires_at."""
        from parkos_core.repo.pairing import create_pairing_token

        session = _make_session()
        result = await create_pairing_token(
            session,
            uuid_sucursal=SUCURSAL_UUID,
            actor_uuid=ACTOR_UUID,
        )

        # Read shape — hash populated, expires_at = now+24h, used=false.
        assert result.pairing_token_hash == session.added[0].pairing_token_hash
        assert result.used is False
        assert result.revoked_at is None
        delta = result.expires_at - result.created_at
        # 24h ± a few seconds (clock skew in test runner).
        assert abs(delta.total_seconds() - 86400) < 5

    @pytest.mark.asyncio
    async def test_custom_ttl(self):
        from parkos_core.repo.pairing import create_pairing_token

        session = _make_session()
        result = await create_pairing_token(
            session,
            uuid_sucursal=SUCURSAL_UUID,
            ttl_hours=1,
            actor_uuid=ACTOR_UUID,
        )
        delta = result.expires_at - result.created_at
        assert abs(delta.total_seconds() - 3600) < 5

    @pytest.mark.asyncio
    async def test_optional_uuid_sucursal(self):
        """Pre-branch tokens carry ``uuid_sucursal=NULL``."""
        from parkos_core.repo.pairing import create_pairing_token

        session = _make_session()
        result = await create_pairing_token(
            session,
            uuid_sucursal=None,
            actor_uuid=ACTOR_UUID,
        )
        assert result.uuid_sucursal is None


# ---------------------------------------------------------------------------
# consume_pairing_token
# ---------------------------------------------------------------------------


class TestConsumePairingTokenHappyPath:
    @pytest.mark.asyncio
    async def test_returns_consumed_row(self):
        from parkos_core.repo.pairing import (
            consume_pairing_token,
            generate_pairing_token,
        )

        plaintext, sha = generate_pairing_token()
        existing = _make_pairing_row(
            used=False,
            expires_at=_now_naive() + timedelta(hours=1),
            pairing_token_hash=sha,
        )
        locked = _make_pairing_row(
            used=False,
            expires_at=_now_naive() + timedelta(hours=1),
            pairing_token_hash=sha,
        )
        session = _make_session(existing=existing, locked=locked)

        await consume_pairing_token(
            session,
            plaintext,
            uuid_sucursal=SUCURSAL_UUID,
            branch_info={"hostname": "test"},
        )

        # Two adds: the original issuance (from session.execute's load)
        # is NOT added again; only the new consumed sibling is added.
        # (the magic mocks' ``add`` was called only once via consume.)
        assert len(session.added) == 1
        consumed = session.added[0]
        assert consumed.used is True
        assert consumed.used_at is not None
        assert consumed.used_by_branch_info == {"hostname": "test"}


class TestConsumePairingTokenFailures:
    @pytest.mark.asyncio
    async def test_wrong_token_raises_not_found(self):
        from parkos_core.repo.pairing import (
            PairingTokenNotFoundError,
            consume_pairing_token,
        )

        session = _make_session(existing=None, locked=None)
        with pytest.raises(PairingTokenNotFoundError):
            await consume_pairing_token(
                session,
                "wrong-token-plaintext",
                uuid_sucursal=SUCURSAL_UUID,
            )

    @pytest.mark.asyncio
    async def test_expired_token_raises_expired_error(self):
        from parkos_core.repo.pairing import (
            PairingTokenExpiredError,
            consume_pairing_token,
            generate_pairing_token,
        )

        plaintext, sha = generate_pairing_token()
        existing = _make_pairing_row(
            used=False,
            expires_at=_now_naive() - timedelta(seconds=1),  # already expired
            pairing_token_hash=sha,
        )
        session = _make_session(existing=existing, locked=None)
        with pytest.raises(PairingTokenExpiredError):
            await consume_pairing_token(
                session, plaintext, uuid_sucursal=SUCURSAL_UUID
            )

    @pytest.mark.asyncio
    async def test_already_used_raises_consumed_error(self):
        from parkos_core.repo.pairing import (
            PairingTokenConsumedError,
            consume_pairing_token,
            generate_pairing_token,
        )

        plaintext, sha = generate_pairing_token()
        existing = _make_pairing_row(
            used=True,  # already consumed (consumed sibling is latest)
            pairing_token_hash=sha,
        )
        session = _make_session(existing=existing, locked=None)
        with pytest.raises(PairingTokenConsumedError):
            await consume_pairing_token(
                session, plaintext, uuid_sucursal=SUCURSAL_UUID
            )

    @pytest.mark.asyncio
    async def test_revoked_via_revoked_sync_jwts_raises_consumed_error(self):
        """When ``is_revoked`` returns True the consume fails (revoked gate)."""
        from parkos_core.repo.pairing import (
            PairingTokenConsumedError,
            consume_pairing_token,
            generate_pairing_token,
        )

        plaintext, sha = generate_pairing_token()
        existing = _make_pairing_row(
            used=False,
            expires_at=_now_naive() + timedelta(hours=1),
            pairing_token_hash=sha,
        )
        # is_revoked returns a non-None uuid → revocation active.
        session = _make_session(
            existing=existing, locked=None, revoked_subquery_returns_none=False
        )
        with pytest.raises(PairingTokenConsumedError):
            await consume_pairing_token(
                session, plaintext, uuid_sucursal=SUCURSAL_UUID
            )

    @pytest.mark.asyncio
    async def test_cross_branch_raises_consumed_error(self):
        """Token issued for branch A, consumed by branch B → ConsumedError (no info leak)."""
        from parkos_core.repo.pairing import (
            PairingTokenConsumedError,
            consume_pairing_token,
            generate_pairing_token,
        )

        plaintext, sha = generate_pairing_token()
        other_sucursal = uuid_lib.UUID("00000000-0000-0000-0000-0000000000cc")
        existing = _make_pairing_row(
            used=False,
            uuid_sucursal=other_sucursal,  # issued for branch B
            expires_at=_now_naive() + timedelta(hours=1),
            pairing_token_hash=sha,
        )
        session = _make_session(existing=existing, locked=None)
        with pytest.raises(PairingTokenConsumedError):
            await consume_pairing_token(
                session,
                plaintext,
                uuid_sucursal=SUCURSAL_UUID,  # branch A consumes
            )

    @pytest.mark.asyncio
    async def test_concurrent_session_wins_raises_consumed_error(self):
        """Another session holds the SKIP LOCKED → the second consume fails."""
        from parkos_core.repo.pairing import (
            PairingTokenConsumedError,
            consume_pairing_token,
            generate_pairing_token,
        )

        plaintext, sha = generate_pairing_token()
        existing = _make_pairing_row(
            used=False,
            expires_at=_now_naive() + timedelta(hours=1),
            pairing_token_hash=sha,
        )
        # lock_stmt's scalar_one_or_none returns None → another session won.
        session = _make_session(existing=existing, locked=None)
        with pytest.raises(PairingTokenConsumedError):
            await consume_pairing_token(
                session, plaintext, uuid_sucursal=SUCURSAL_UUID
            )


# ---------------------------------------------------------------------------
# find_active_pairing_token
# ---------------------------------------------------------------------------


class TestFindActivePairingToken:
    @pytest.mark.asyncio
    async def test_returns_row_when_active(self):
        from parkos_core.repo.pairing import (
            find_active_pairing_token,
            generate_pairing_token,
        )

        plaintext, sha = generate_pairing_token()
        row = _make_pairing_row(
            used=False,
            expires_at=_now_naive() + timedelta(hours=1),
            pairing_token_hash=sha,
        )
        session = _make_session(existing=row, revoked_subquery_returns_none=True)
        result = await find_active_pairing_token(session, plaintext)
        assert result is row

    @pytest.mark.asyncio
    async def test_returns_none_when_revoked(self):
        from parkos_core.repo.pairing import (
            find_active_pairing_token,
            generate_pairing_token,
        )

        plaintext, sha = generate_pairing_token()
        row = _make_pairing_row(
            used=False,
            expires_at=_now_naive() + timedelta(hours=1),
            pairing_token_hash=sha,
        )
        # is_revoked returns non-None → token is revoked.
        session = _make_session(
            existing=row, revoked_subquery_returns_none=False
        )
        result = await find_active_pairing_token(session, plaintext)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_expired(self):
        from parkos_core.repo.pairing import (
            find_active_pairing_token,
            generate_pairing_token,
        )

        plaintext, _sha = generate_pairing_token()
        # No row matches because expires_at filter excludes it.
        session = _make_session(existing=None)
        result = await find_active_pairing_token(session, plaintext)
        assert result is None