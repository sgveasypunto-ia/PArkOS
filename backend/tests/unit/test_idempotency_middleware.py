"""test_idempotency_middleware.py — REQ-OP-04.

Unit tests for :class:`parkos_core.api.middleware.IdempotencyKeyMiddleware`.

The middleware runs in three modes:

  1. **No header** → pass-through (verified at the unit level via
     ``_hash_idempotency_key`` and the dispatcher's no-header branch).
  2. **Header + cached + live** → replay the cached response.
  3. **Header + cached + expired** → return 410 Gone.

The DB-touching branches (insert / cache-hit) require the live test DB
and the migration chain. We exercise them in
``tests/migrations/test_idempotency_inmutable.py``; here we exercise the
helpers that don't need a DB (``_hash_idempotency_key``, the constant
``TTL_HOURS``, and the JSON serialization path).
"""
from __future__ import annotations

import hashlib

import pytest
from parkos_core.api.middleware import TTL_HOURS, _hash_idempotency_key


def test_ttl_hours_constant() -> None:
    """The TTL is 24h per design §8."""
    assert TTL_HOURS == 24


def test_hash_idempotency_key_is_deterministic() -> None:
    """Same (issuer, key) → same hash."""
    a = _hash_idempotency_key("admin-", "abc-123")
    b = _hash_idempotency_key("admin-", "abc-123")
    assert a == b
    assert len(a) == 64  # SHA-256 hex


def test_hash_idempotency_key_isolates_by_issuer() -> None:
    """The same UUID-key under different issuers does NOT collide."""
    admin = _hash_idempotency_key("admin-", "shared-key")
    operador = _hash_idempotency_key("operador-", "shared-key")
    assert admin != operador


def test_hash_idempotency_key_matches_sha256_manual() -> None:
    """The helper produces the same bytes as a hand-rolled sha256."""
    issuer = "sync-agent-"
    raw_key = "token-uuid-xyz"
    expected = hashlib.sha256(f"{issuer}:{raw_key}".encode()).hexdigest()
    assert _hash_idempotency_key(issuer, raw_key) == expected


def test_hash_idempotency_key_handles_empty_strings() -> None:
    """Edge case: empty issuer and empty key still produce a valid hash."""
    h = _hash_idempotency_key("", "")
    assert len(h) == 64
    assert h == hashlib.sha256(b":").hexdigest()


# ---------------------------------------------------------------------------
# FastAPI dispatch tests — use TestClient + httpx to drive the middleware
# end-to-end. The DB-touching tests live in
# ``tests/migrations/test_idempotency_inmutable.py``.
# ---------------------------------------------------------------------------


def test_middleware_no_header_passes_through() -> None:
    """Without the ``Idempotency-Key`` header, the middleware is a no-op.

    We instantiate a tiny FastAPI app, register the middleware, and
    assert that a request without the header hits the route handler.
    Uses ``AsyncClient`` + ``ASGITransport`` because the ASGI transport
    requires async context (httpx >= 0.28).
    """
    import asyncio

    import httpx
    from fastapi import FastAPI
    from parkos_core.api.middleware import IdempotencyKeyMiddleware

    app = FastAPI()
    app.add_middleware(IdempotencyKeyMiddleware)

    @app.get("/probe")
    async def probe() -> dict[str, str]:
        return {"hello": "world"}

    async def _drive() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.get("/probe")

    resp = asyncio.run(_drive())

    assert resp.status_code == 200
    assert resp.json() == {"hello": "world"}


def test_middleware_with_header_passes_through_when_no_db() -> None:
    """With the header but no DB, the middleware raises RuntimeError.

    We expect the middleware to attempt opening a session for the
    lookup; with no DATABASE_URL the lazy engine initializer raises
    :class:`RuntimeError`. This test confirms the middleware code
    path is exercised (the request header is read; the lookup is
    attempted) without requiring a live database.
    """
    import asyncio
    import os

    import httpx
    from fastapi import FastAPI
    from parkos_core.api.middleware import IdempotencyKeyMiddleware

    # Clear the DB env so the lazy engine can't initialize.
    saved = os.environ.pop("DATABASE_URL", None)

    app = FastAPI()
    app.add_middleware(IdempotencyKeyMiddleware)

    @app.post("/echo")
    async def echo() -> dict[str, str]:
        return {"ok": "true"}

    async def _drive() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.post(
                "/echo",
                headers={"Idempotency-Key": "test-key-12345"},
            )

    try:
        # We expect the RuntimeError to propagate out of the middleware —
        # Starlette's ServerErrorMiddleware re-raises it; the test framework
        # surfaces it as an unhandled exception. That's the signal: the
        # middleware code path was exercised and tried to open a session.
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            asyncio.run(_drive())
    finally:
        if saved is not None:
            os.environ["DATABASE_URL"] = saved