"""Tests for ``repo.idempotency`` TTL handling.

Covers:

- ``guard`` honors ``expires_at`` — expired entries are treated as fresh.
- ``guard`` replays future entries.
- ``store_response`` defaults to 24h TTL (``expires_at = now + 86400``).
- ``store_response`` honors a custom ``ttl_seconds``.
"""
from __future__ import annotations

import hashlib
import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from parkos_core.models.A.idempotency_keys import IdempotencyKeys
from parkos_core.repo.idempotency import (
    IdempotencyGuardResult,
    guard,
    store_response,
)

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000010")
ENDPOINT = "/api/v1/auth/login"
IDEM_KEY = "ttl-key"


def _session_with_existing_entry(
    *,
    request_body_hash: str,
    expires_at: datetime,
) -> AsyncMock:
    """Mock ``AsyncSession`` whose ``execute`` returns a cached entry.

    The result object is ``MagicMock`` (NOT ``AsyncMock``) because
    ``scalar_one_or_none()`` is called synchronously by ``guard``.
    """
    session = AsyncMock()
    session.add = MagicMock()
    entry = MagicMock(spec=IdempotencyKeys)
    entry.path = ENDPOINT
    entry.key_hash = hashlib.sha256(IDEM_KEY.encode("utf-8")).hexdigest()
    entry.method = "POST"
    entry.request_body_hash = request_body_hash
    entry.response_status = 200
    entry.response_body = {"ok": True}
    entry.expires_at = expires_at
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=entry)
    session.execute.return_value = result
    return session


class TestGuardTTLBehavior:
    """``guard`` honors the ``expires_at`` SQL filter on cached entries."""

    async def test_expired_entry_is_treated_as_fresh(self):
        """``expires_at`` in the past → SQL filter excludes it → ``None`` returned."""
        session = AsyncMock()
        empty = MagicMock()
        empty.scalar_one_or_none = MagicMock(return_value=None)
        session.execute.return_value = empty

        result = await guard(
            session,
            endpoint=ENDPOINT,
            idempotency_key=IDEM_KEY,
            request_body=b'{"x":1}',
            actor_uuid=ACTOR_UUID,
        )
        assert result is None

    async def test_future_entry_is_replay(self):
        """``expires_at`` in the future → cached entry returned as replay."""
        request_body = b'{"x":1}'
        body_hash = hashlib.sha256(request_body).hexdigest()
        future = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
        session = _session_with_existing_entry(
            request_body_hash=body_hash,
            expires_at=future,
        )

        result = await guard(
            session,
            endpoint=ENDPOINT,
            idempotency_key=IDEM_KEY,
            request_body=request_body,
            actor_uuid=ACTOR_UUID,
        )
        assert isinstance(result, IdempotencyGuardResult)
        assert result.is_replay is True
        assert result.status == 200
        # JSONB dict ``{"ok": True}`` re-encoded with compact separators.
        assert result.body == b'{"ok":true}'


class TestStoreResponseTTLDeltas:
    """``store_response`` computes ``expires_at = now + ttl_seconds``."""

    async def test_default_ttl_is_24_hours(self):
        session = AsyncMock()
        session.add = MagicMock()

        before = datetime.now(UTC).replace(tzinfo=None)
        await store_response(
            session,
            endpoint=ENDPOINT,
            idempotency_key=IDEM_KEY,
            request_body=b'{}',
            actor_uuid=ACTOR_UUID,
            response_status=200,
            response_body=b'{}',
        )
        after = datetime.now(UTC).replace(tzinfo=None)

        added = session.add.call_args.args[0]
        # ``expires_at`` must fall between ``before + 24h`` and ``after + 24h``.
        # Tolerance accounts for the few microseconds between the two ``now``
        # calls (both naive UTC, matching the DB column convention).
        assert before + timedelta(seconds=86400) <= added.expires_at
        assert added.expires_at <= after + timedelta(seconds=86400)

    async def test_custom_ttl_one_hour(self):
        """``ttl_seconds=3600`` produces ``expires_at ≈ now + 3600``."""
        session = AsyncMock()
        session.add = MagicMock()

        before = datetime.now(UTC).replace(tzinfo=None)
        await store_response(
            session,
            endpoint=ENDPOINT,
            idempotency_key=IDEM_KEY,
            request_body=b'{}',
            actor_uuid=ACTOR_UUID,
            response_status=200,
            response_body=b'{}',
            ttl_seconds=3600,
        )
        after = datetime.now(UTC).replace(tzinfo=None)

        added = session.add.call_args.args[0]
        assert before + timedelta(seconds=3600) <= added.expires_at
        assert added.expires_at <= after + timedelta(seconds=3600)

    async def test_custom_ttl_one_minute(self):
        """``ttl_seconds=60`` produces ``expires_at ≈ now + 60``."""
        session = AsyncMock()
        session.add = MagicMock()

        before = datetime.now(UTC).replace(tzinfo=None)
        await store_response(
            session,
            endpoint=ENDPOINT,
            idempotency_key=IDEM_KEY,
            request_body=b'{}',
            actor_uuid=ACTOR_UUID,
            response_status=200,
            response_body=b'{}',
            ttl_seconds=60,
        )
        after = datetime.now(UTC).replace(tzinfo=None)

        added = session.add.call_args.args[0]
        assert before + timedelta(seconds=60) <= added.expires_at
        assert added.expires_at <= after + timedelta(seconds=60)
