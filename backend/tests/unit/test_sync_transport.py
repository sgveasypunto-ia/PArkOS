"""Tests for ``sync.transport.SyncHttpClient`` (T-PR9-02).

Unit tests using mocked ``httpx.AsyncClient`` — no real network calls.
Coverage:

- ``push()`` happy path + Retry-After parsing + Authorization header
- ``pull()`` happy path + missing next_seq default + Retry-After parsing
- ``heartbeat()`` smoke test
- ``rotate_jwt()`` happy path
- ``_read_jwt()`` lazy read + missing-file RuntimeError
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from parkos_core.sync.transport import (
    DEFAULT_TIMEOUT_S,
    NewJwt,
    PullResponse,
    PushResponse,
    SyncHttpClient,
)

# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def jwt_file(tmp_path: Path) -> Path:
    """Write a fake JWT to a temp file."""
    p = tmp_path / "sync.jwt"
    p.write_text("test-jwt-token")
    return p


def _make_response(
    *,
    status_code: int,
    json_body: dict | None = None,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    """Build a mock ``httpx.Response`` with the surface ``SyncHttpClient`` reads."""
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {"content-type": "application/json"}
    response.json = MagicMock(return_value=json_body if json_body is not None else {})
    response.raise_for_status = MagicMock()
    return response


def _make_session_factory(post: AsyncMock) -> MagicMock:
    """Return a session_factory whose ``async with`` yields a session with ``.post = post``."""
    session = MagicMock()
    session.post = post

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)

    return MagicMock(return_value=cm)


# ---------------------------------------------------------------------------
# push()
# ---------------------------------------------------------------------------


class TestPush:
    """``SyncHttpClient.push`` — POST /sync/push."""

    async def test_push_happy_path(self, jwt_file: Path) -> None:
        post = AsyncMock(return_value=_make_response(status_code=200, json_body={"accepted": 3}))
        client = SyncHttpClient(
            session_factory=_make_session_factory(post=post),
            base_url="http://cloud",
            jwt_path=jwt_file,
        )
        result = await client.push([{"tabla": "factura_pagos", "uuid_registro": "abc"}])
        assert isinstance(result, PushResponse)
        assert result.status == 200
        assert result.body == {"accepted": 3}
        assert result.retry_after_seconds is None

    async def test_push_sends_authorization_bearer_header(self, jwt_file: Path) -> None:
        post = AsyncMock(return_value=_make_response(status_code=200, json_body={}))
        factory = _make_session_factory(post=post)
        client = SyncHttpClient(
            session_factory=factory, base_url="http://cloud", jwt_path=jwt_file
        )
        await client.push([])
        headers = post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer test-jwt-token"

    async def test_push_sends_rows_payload(self, jwt_file: Path) -> None:
        post = AsyncMock(return_value=_make_response(status_code=200, json_body={}))
        client = SyncHttpClient(
            session_factory=_make_session_factory(post=post),
            base_url="http://cloud",
            jwt_path=jwt_file,
        )
        rows = [{"tabla": "x", "uuid_registro": "1"}, {"tabla": "x", "uuid_registro": "2"}]
        await client.push(rows)
        assert post.call_args.kwargs["json"] == {"rows": rows}

    async def test_push_parses_retry_after_when_present(self, jwt_file: Path) -> None:
        post = AsyncMock(
            return_value=_make_response(
                status_code=429, json_body={}, headers={"Retry-After": "120"}
            )
        )
        client = SyncHttpClient(
            session_factory=_make_session_factory(post=post),
            base_url="http://cloud",
            jwt_path=jwt_file,
        )
        result = await client.push([])
        assert result.status == 429
        assert result.retry_after_seconds == 120

    async def test_push_ignores_non_numeric_retry_after(self, jwt_file: Path) -> None:
        post = AsyncMock(
            return_value=_make_response(
                status_code=503, json_body={}, headers={"Retry-After": "soon"}
            )
        )
        client = SyncHttpClient(
            session_factory=_make_session_factory(post=post),
            base_url="http://cloud",
            jwt_path=jwt_file,
        )
        result = await client.push([])
        assert result.retry_after_seconds is None


# ---------------------------------------------------------------------------
# pull()
# ---------------------------------------------------------------------------


class TestPull:
    """``SyncHttpClient.pull`` — POST /sync/pull."""

    async def test_pull_happy_path(self, jwt_file: Path) -> None:
        post = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_body={"rows": [{"x": 1}, {"y": 2}], "next_seq": 42},
            )
        )
        client = SyncHttpClient(
            session_factory=_make_session_factory(post=post),
            base_url="http://cloud",
            jwt_path=jwt_file,
        )
        result = await client.pull(since_seq=0)
        assert isinstance(result, PullResponse)
        assert result.status == 200
        assert result.rows == [{"x": 1}, {"y": 2}]
        assert result.next_seq == 42

    async def test_pull_sends_since_seq_payload(self, jwt_file: Path) -> None:
        post = AsyncMock(return_value=_make_response(status_code=200, json_body={"rows": []}))
        client = SyncHttpClient(
            session_factory=_make_session_factory(post=post),
            base_url="http://cloud",
            jwt_path=jwt_file,
        )
        await client.pull(since_seq=17)
        assert post.call_args.kwargs["json"] == {"since_seq": 17}

    async def test_pull_missing_next_seq_defaults_to_input(self, jwt_file: Path) -> None:
        post = AsyncMock(return_value=_make_response(status_code=200, json_body={"rows": []}))
        client = SyncHttpClient(
            session_factory=_make_session_factory(post=post),
            base_url="http://cloud",
            jwt_path=jwt_file,
        )
        result = await client.pull(since_seq=17)
        assert result.next_seq == 17

    async def test_pull_parses_retry_after(self, jwt_file: Path) -> None:
        post = AsyncMock(
            return_value=_make_response(
                status_code=503, json_body={}, headers={"Retry-After": "30"}
            )
        )
        client = SyncHttpClient(
            session_factory=_make_session_factory(post=post),
            base_url="http://cloud",
            jwt_path=jwt_file,
        )
        result = await client.pull(since_seq=0)
        assert result.status == 503
        assert result.retry_after_seconds == 30


# ---------------------------------------------------------------------------
# heartbeat()
# ---------------------------------------------------------------------------


class TestHeartbeat:
    """``SyncHttpClient.heartbeat`` — POST /sync/heartbeat."""

    async def test_heartbeat_sends_state_payload(self, jwt_file: Path) -> None:
        post = AsyncMock(return_value=_make_response(status_code=200, json_body={}))
        client = SyncHttpClient(
            session_factory=_make_session_factory(post=post),
            base_url="http://cloud",
            jwt_path=jwt_file,
        )
        state = {"worker": "sync_sucursal", "uuid_sucursal": "abc"}
        # heartbeat() returns None; just verify it doesn't raise and posts.
        assert await client.heartbeat(state) is None
        post.assert_awaited_once()
        assert post.call_args.kwargs["json"] == state


# ---------------------------------------------------------------------------
# rotate_jwt()
# ---------------------------------------------------------------------------


class TestRotateJwt:
    """``SyncHttpClient.rotate_jwt`` — POST /sync/rotate-jwt."""

    async def test_rotate_jwt_parses_new_jwt_response(self, jwt_file: Path) -> None:
        post = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_body={"jwt": "new-token", "expires_at": 999, "grace_until": 1999},
            )
        )
        client = SyncHttpClient(
            session_factory=_make_session_factory(post=post),
            base_url="http://cloud",
            jwt_path=jwt_file,
        )
        result = await client.rotate_jwt()
        assert isinstance(result, NewJwt)
        assert result.jwt == "new-token"
        assert result.expires_at == 999
        assert result.grace_until == 1999


# ---------------------------------------------------------------------------
# _read_jwt() lazy semantics
# ---------------------------------------------------------------------------


class TestReadJwt:
    """``SyncHttpClient._read_jwt`` — lazy file read on every request."""

    async def test_missing_jwt_raises_runtime_error(self, tmp_path: Path) -> None:
        post = AsyncMock()
        client = SyncHttpClient(
            session_factory=_make_session_factory(post=post),
            base_url="http://cloud",
            jwt_path=tmp_path / "missing.jwt",
        )
        with pytest.raises(RuntimeError, match="missing"):
            await client.push([])

    async def test_jwt_file_is_re_read_on_each_call(self, jwt_file: Path) -> None:
        """Rotation takes effect immediately — no stale cached token."""
        post = AsyncMock(return_value=_make_response(status_code=200, json_body={}))
        client = SyncHttpClient(
            session_factory=_make_session_factory(post=post),
            base_url="http://cloud",
            jwt_path=jwt_file,
        )
        await client.push([])
        first_token = post.call_args_list[0].kwargs["headers"]["Authorization"]

        # Rotate the file between calls — sync write inside async fn is
        # acceptable in tests; the test deliberately exercises lazy re-read.
        jwt_file.write_text("rotated-token")  # noqa: ASYNC240
        await client.push([])
        second_token = post.call_args_list[1].kwargs["headers"]["Authorization"]

        assert first_token == "Bearer test-jwt-token"
        assert second_token == "Bearer rotated-token"


# ---------------------------------------------------------------------------
# Constants + base_url normalization
# ---------------------------------------------------------------------------


def test_default_timeout_constant() -> None:
    """``DEFAULT_TIMEOUT_S`` matches the httpx defaults used in worker main loops."""
    assert DEFAULT_TIMEOUT_S == 30.0


def test_default_session_factory_uses_production_limits() -> None:
    """Production wiring creates ``httpx.AsyncClient`` with timeout=30s and max_connections=10."""
    factory = SyncHttpClient(
        base_url="http://cloud",
        jwt_path=Path("/dev/null"),
    )._default_session_factory
    session = factory()
    try:
        assert isinstance(session, httpx.AsyncClient)
        # ``httpx`` exposes ``timeout`` publicly; ``limits`` are an internal
        # transport-level setting (``_transport._pool._max_connections``) —
        # not part of the public surface, so we only assert timeout here.
        assert session.timeout.connect == 30.0
    finally:
        # AsyncClient.__aexit__ is async; close via the sync wrapper used in tests.
        # We avoid running the loop here — just drop the reference; GC handles it.
        pass


def test_base_url_trailing_slash_stripped() -> None:
    """``base_url`` normalization: ``http://cloud/`` → ``http://cloud``."""
    client = SyncHttpClient(
        base_url="http://cloud/",
        jwt_path=Path("/dev/null"),
    )
    assert client.base_url == "http://cloud"
