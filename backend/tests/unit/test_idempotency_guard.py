"""Tests for ``repo.idempotency.guard`` + ``store_response`` (REQ-OP-04, SC-OP-02).

Verifies the single-execution semantics required by the middleware:

- Missing ``Idempotency-Key`` header raises ``IdempotencyKeyRequiredError``.
- First call returns ``None`` (caller proceeds).
- Replay with SAME key + SAME body returns cached response with
  ``is_replay=True``.
- Replay with SAME key + DIFFERENT body raises
  ``IdempotencyConflictError``.
- Expired entries (past ``expires_at``) are treated as fresh.

Also verifies ``store_response`` SHA-256 hashing and ORM column mapping
(``path`` / ``key_hash`` / ``request_body_hash`` / ``response_status`` /
``response_body`` JSONB).
"""
from __future__ import annotations

import hashlib
import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock

from parkos_core.models.A.idempotency_keys import IdempotencyKeys
from parkos_core.repo.idempotency import (
    IdempotencyConflictError,
    IdempotencyGuardResult,
    IdempotencyKeyRequiredError,
    guard,
    store_response,
)

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000001")
ENDPOINT = "/api/v1/auth/login"
IDEM_KEY = "test-key-abc123"
REQUEST_BODY = b'{"username":"alice","password":"hunter2"}'
RESPONSE_BODY = b'{"id":"abc","token":"xyz"}'


def _make_session() -> AsyncMock:
    """Mock ``AsyncSession`` — ``add`` is sync, ``execute`` is async."""
    session = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    return session


def _result_scalar(row: MagicMock | None) -> MagicMock:
    """Wrap a row in a ``Result``-shaped mock with ``scalar_one_or_none``.

    Uses ``MagicMock`` (NOT ``AsyncMock``) because ``scalar_one_or_none()``
    is invoked synchronously by ``guard`` — making the result async would
    return a coroutine instead of the row.
    """
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=row)
    return result


def _existing_entry(
    *,
    request_body_hash: str,
    response_status: int = 200,
    response_body: dict | None = None,
) -> MagicMock:
    """Build a mock that mimics an existing ``IdempotencyKeys`` row."""
    entry = MagicMock(spec=IdempotencyKeys)
    entry.path = ENDPOINT
    entry.key_hash = hashlib.sha256(IDEM_KEY.encode("utf-8")).hexdigest()
    entry.method = "POST"
    entry.request_body_hash = request_body_hash
    entry.response_status = response_status
    entry.response_body = response_body if response_body is not None else {"id": "abc"}
    return entry


class TestGuardMissingKey:
    """``Idempotency-Key`` header required on POST (REQ-OP-04)."""

    async def test_empty_key_raises(self):
        session = _make_session()
        try:
            await guard(
                session,
                endpoint=ENDPOINT,
                idempotency_key="",
                request_body=REQUEST_BODY,
                actor_uuid=ACTOR_UUID,
            )
        except IdempotencyKeyRequiredError:
            return
        raise AssertionError("IdempotencyKeyRequiredError was not raised")


class TestGuardNoExistingEntry:
    """No cached entry → caller proceeds (returns ``None``)."""

    async def test_returns_none_when_no_row_found(self):
        session = _make_session()
        session.execute.return_value = _result_scalar(None)

        result = await guard(
            session,
            endpoint=ENDPOINT,
            idempotency_key=IDEM_KEY,
            request_body=REQUEST_BODY,
            actor_uuid=ACTOR_UUID,
        )
        assert result is None


class TestGuardReplaySameBody:
    """Cached entry with SAME body hash → replay with ``is_replay=True``."""

    async def test_returns_idempotency_guard_result(self):
        session = _make_session()
        body_hash = hashlib.sha256(REQUEST_BODY).hexdigest()
        existing = _existing_entry(
            request_body_hash=body_hash,
            response_status=201,
            response_body={"id": "abc"},
        )
        session.execute.return_value = _result_scalar(existing)

        result = await guard(
            session,
            endpoint=ENDPOINT,
            idempotency_key=IDEM_KEY,
            request_body=REQUEST_BODY,
            actor_uuid=ACTOR_UUID,
        )

        assert isinstance(result, IdempotencyGuardResult)
        assert result.is_replay is True
        assert result.status == 201
        # response_body (dict) is JSON-encoded with compact separators
        # (``separators=(",", ":")``) so the cached bytes are
        # ``b'{"id":"abc"}'`` (no whitespace).
        assert result.body == b'{"id":"abc"}'


class TestGuardConflictDifferentBody:
    """Cached entry with DIFFERENT body hash → 409 ``IdempotencyConflictError``."""

    async def test_raises_conflict(self):
        session = _make_session()
        existing = _existing_entry(
            # Stored hash is for a DIFFERENT body than what we send now.
            request_body_hash="0" * 64,
            response_status=201,
            response_body={"id": "abc"},
        )
        session.execute.return_value = _result_scalar(existing)

        try:
            await guard(
                session,
                endpoint=ENDPOINT,
                idempotency_key=IDEM_KEY,
                # Different body from the one that produced the cached hash
                request_body=b'{"username":"bob"}',
                actor_uuid=ACTOR_UUID,
            )
        except IdempotencyConflictError:
            return
        raise AssertionError("IdempotencyConflictError was not raised")


class TestGuardExpiredEntry:
    """Expired entries are filtered out by the ``expires_at > now`` SQL clause."""

    async def test_treated_as_fresh(self):
        # When the row's ``expires_at`` is in the past, the SQL WHERE filter
        # ``expires_at > now`` excludes it and ``scalar_one_or_none`` returns
        # ``None``. The guard then returns ``None`` (caller proceeds).
        session = _make_session()
        session.execute.return_value = _result_scalar(None)

        result = await guard(
            session,
            endpoint=ENDPOINT,
            idempotency_key=IDEM_KEY,
            request_body=REQUEST_BODY,
            actor_uuid=ACTOR_UUID,
        )
        assert result is None


class TestStoreResponseHappyPath:
    """``store_response`` persists a fresh ``IdempotencyKeys`` row."""

    async def test_session_add_called_with_idempotency_keys(self):
        session = _make_session()
        await store_response(
            session,
            endpoint=ENDPOINT,
            idempotency_key=IDEM_KEY,
            request_body=REQUEST_BODY,
            actor_uuid=ACTOR_UUID,
            response_status=200,
            response_body=RESPONSE_BODY,
        )
        session.add.assert_called_once()
        added = session.add.call_args.args[0]
        assert isinstance(added, IdempotencyKeys)

    async def test_key_hash_is_sha256_of_raw_key(self):
        """``key_hash`` is SHA-256 of the raw key, never the raw key itself."""
        session = _make_session()
        await store_response(
            session,
            endpoint=ENDPOINT,
            idempotency_key="abc123",
            request_body=b'{}',
            actor_uuid=ACTOR_UUID,
            response_status=200,
            response_body=b'{}',
        )
        added = session.add.call_args.args[0]
        expected = hashlib.sha256(b"abc123").hexdigest()
        assert added.key_hash == expected
        # Defensive: raw key MUST NOT leak into the ORM column
        assert added.key_hash != "abc123"

    async def test_request_body_hash_is_sha256(self):
        """``request_body_hash`` is SHA-256 of the raw request body bytes."""
        session = _make_session()
        await store_response(
            session,
            endpoint=ENDPOINT,
            idempotency_key=IDEM_KEY,
            request_body=REQUEST_BODY,
            actor_uuid=ACTOR_UUID,
            response_status=200,
            response_body=b'{}',
        )
        added = session.add.call_args.args[0]
        assert added.request_body_hash == hashlib.sha256(REQUEST_BODY).hexdigest()

    async def test_path_status_method_propagated(self):
        session = _make_session()
        await store_response(
            session,
            endpoint="/api/v1/caja/sesion",
            idempotency_key=IDEM_KEY,
            request_body=b'{}',
            actor_uuid=ACTOR_UUID,
            response_status=418,
            response_body=b'{"teapot":true}',
        )
        added = session.add.call_args.args[0]
        assert added.path == "/api/v1/caja/sesion"
        assert added.response_status == 418
        assert added.method == "POST"
        # JSONB column gets the DECODED dict, not raw bytes.
        assert added.response_body == {"teapot": True}

    async def test_actor_uuid_and_created_at_propagated(self):
        """``created_by`` + ``created_at`` flow into the new row (audit columns)."""
        session = _make_session()
        await store_response(
            session,
            endpoint=ENDPOINT,
            idempotency_key=IDEM_KEY,
            request_body=b'{}',
            actor_uuid=ACTOR_UUID,
            response_status=200,
            response_body=b'{}',
        )
        added = session.add.call_args.args[0]
        assert added.created_by == ACTOR_UUID
        assert added.created_at is not None


class TestStoreResponseBodyDecoding:
    """``response_body`` bytes are JSON-decoded into a dict for the JSONB column."""

    async def test_json_bytes_become_dict(self):
        session = _make_session()
        await store_response(
            session,
            endpoint=ENDPOINT,
            idempotency_key=IDEM_KEY,
            request_body=b'{}',
            actor_uuid=ACTOR_UUID,
            response_status=200,
            response_body=b'{"foo":"bar","baz":42}',
        )
        added = session.add.call_args.args[0]
        assert added.response_body == {"foo": "bar", "baz": 42}

    async def test_invalid_json_falls_back_to_raw_text_wrapper(self):
        """Non-JSON bytes are wrapped as ``{"raw_text": ...}`` (defense in depth)."""
        session = _make_session()
        raw = b"not-json-at-all"
        await store_response(
            session,
            endpoint=ENDPOINT,
            idempotency_key=IDEM_KEY,
            request_body=b'{}',
            actor_uuid=ACTOR_UUID,
            response_status=200,
            response_body=raw,
        )
        added = session.add.call_args.args[0]
        assert added.response_body == {"raw_text": "not-json-at-all"}
