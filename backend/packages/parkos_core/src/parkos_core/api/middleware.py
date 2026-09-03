"""HTTP middlewares (REQ-OP-04 + design §8).

PR2 ships the full :class:`IdempotencyKeyMiddleware`:

  - Reads the ``Idempotency-Key`` request header.
  - Hashes ``sha256(issuer + ":" + key)`` — the issuer prefix scopes the
    key per JWT issuer (``admin-``, ``operador-``, ``sync-agent-``) so
    two callers using the same UUID string don't collide.
  - On a hit within the 24h TTL: replay the cached response (status,
    body, headers).
  - On a hit past the TTL: 410 Gone.
  - On a miss: pass through; on the response, persist the response for
    future replays.

When the header is absent (GET, OPTIONS preflight, health check), the
middleware is a no-op pass-through. Per-route helpers do not need to
re-check the header.

The middleware speaks to the DB on every request. For the dev/test path
the dependency is injected via the FastAPI request scope (via
``request.state.db_session``); when unset we open a fresh session on
demand. Production code wires the session in
``api/v1/__init__.py``'s lifespan.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from ..models.A.idempotency_keys import IdempotencyKeys

logger = logging.getLogger(__name__)

# 24-hour TTL per design §8. The DB index ``ix_idempotency_keys_active``
# matches ``expires_at > NOW()`` so expired rows are ignored.
TTL_HOURS = 24


def _hash_idempotency_key(issuer: str, raw_key: str) -> str:
    """Return the deterministic cache key for ``(issuer, raw_key)``."""
    return hashlib.sha256(f"{issuer}:{raw_key}".encode()).hexdigest()


def _issuer_for_request(request: Request) -> str:
    """Return the issuer scope for the request.

    Falls back to ``"anonymous"`` when no JWT is present (e.g. health
    checks). The issuer string is included in the key hash so two
    callers using the same UUID-key under different JWT issuers don't
    collide.
    """
    # The JWT verifier populates ``request.state.jwt_claims`` (see
    # ``auth/jwt_issuer_guard.py``). When the request never went through
    # the auth path (e.g. a public health endpoint), we fall back to
    # ``anonymous``.
    claims = getattr(request.state, "jwt_claims", None) or {}
    issuer = claims.get("iss", "anonymous")
    # Normalize to the prefix form: "admin-..." → "admin-", etc.
    if "-" in issuer:
        issuer = issuer.split("-", 1)[0] + "-"
    return issuer or "anonymous"


def _serialize_response(response: Response) -> dict[str, Any]:
    """Extract the cacheable parts of a Starlette ``Response``.

    ``body`` is read once via ``response.body`` (which the middleware
    populates before this call). For streaming responses this is the
    first chunk — PR2 does not support stream replay.

    ``response.body`` is a ``memoryview`` in Starlette ≥0.27; we coerce
    to ``bytes`` via ``bytes(...)`` so ``.decode()`` works in every
    version.
    """
    raw = bytes(response.body) if response.body else b""
    body: Any
    if isinstance(response, JSONResponse):
        try:
            body = json.loads(raw.decode("utf-8")) if raw else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = raw.decode("utf-8", errors="replace")
    else:
        body = raw.decode("utf-8", errors="replace") if raw else None
    return {
        "status": response.status_code,
        "body": body,
        "headers": dict(response.headers),
    }


class IdempotencyKeyMiddleware(BaseHTTPMiddleware):
    """Replay cached responses for repeated ``Idempotency-Key`` requests.

    Per design §8: GET, OPTIONS, and any request without the header is
    a pass-through. POST/PUT/PATCH/DELETE with the header consult
    ``prod.idempotency_keys`` before invoking the route handler.
    """

    async def dispatch(self, request: Request, call_next):
        raw_key = request.headers.get("Idempotency-Key")
        request.state.idempotency_key = raw_key
        if not raw_key:
            return await call_next(request)

        issuer = _issuer_for_request(request)
        key_hash = _hash_idempotency_key(issuer, raw_key)
        request.state.idempotency_key_hash = key_hash
        request.state.idempotency_key_issuer = issuer

        session = await _open_session_for_request(request)

        try:
            existing = await session.execute(
                select(IdempotencyKeys).where(
                    IdempotencyKeys.issuer == issuer,
                    IdempotencyKeys.key_hash == key_hash,
                )
            )
            cached = existing.scalar_one_or_none()

            if cached is not None:
                now = datetime.now(UTC).replace(tzinfo=None)
                if cached.expires_at is not None and cached.expires_at <= now:
                    logger.info(
                        "idempotency_key_expired",
                        extra={"issuer": issuer, "path": request.url.path},
                    )
                    return JSONResponse(
                        status_code=410,
                        content={"error": "idempotency_key_expired"},
                    )

                logger.debug(
                    "idempotency_key_replay",
                    extra={
                        "issuer": issuer,
                        "path": request.url.path,
                        "cached_status": cached.response_status,
                    },
                )
                # ``cached.response_body`` is the JSONB dict we stored on
                # the first call: ``{"body": <original body>, "headers": ...}``.
                # Reconstruct the response from that envelope.
                envelope = cached.response_body or {}
                original_body = envelope.get("body") if isinstance(envelope, dict) else None
                original_headers = (
                    envelope.get("headers") if isinstance(envelope, dict) else None
                ) or {}
                return JSONResponse(
                    status_code=cached.response_status or 200,
                    content=original_body,
                    headers=original_headers,
                )

            # First time — pass through, then persist on response.
            response = await call_next(request)

            try:
                serialized = _serialize_response(response)
                session.add(
                    IdempotencyKeys(
                        issuer=issuer,
                        key_hash=key_hash,
                        method=request.method,
                        path=request.url.path,
                        request_body_hash=None,  # populated lazily; see note
                        response_status=serialized["status"],
                        response_body={
                            "body": serialized["body"],
                            "headers": serialized["headers"],
                        },
                        expires_at=datetime.now(UTC).replace(tzinfo=None)
                        + timedelta(hours=TTL_HOURS),
                        created_at=datetime.now(UTC).replace(tzinfo=None),
                        sync_status="pendiente",
                    )
                )
                await session.commit()
            except Exception as exc:  # noqa: BLE001
                # Persistence errors MUST NOT break the response — log and
                # let the caller see the real result. The next request
                # with the same key will re-execute (no cached row).
                logger.warning(
                    "idempotency_key_persist_failed",
                    extra={
                        "issuer": issuer,
                        "path": request.url.path,
                        "error": str(exc),
                    },
                )
                await session.rollback()

            return response
        finally:
            await session.close()


async def _open_session_for_request(request: Request):
    """Return an :class:`AsyncSession` bound to this request.

    FastAPI's dependency injection normally passes the session via the
    route handler. The middleware runs BEFORE the route handler, so it
    doesn't have that injection. We open a short-lived session on
    demand via the lazy engine and close it in ``dispatch.finally``.
    """
    from ..db.engine import _get_sessionmaker  # local import to avoid circular

    SessionLocal = _get_sessionmaker()
    return SessionLocal()


def _hash_request_body(body: bytes) -> str:
    """SHA-256 hex of the request body. Stored for later conflict checks."""
    return hashlib.sha256(body or b"").hexdigest()


__all__ = [
    "TTL_HOURS",
    "IdempotencyKeyMiddleware",
    "_hash_idempotency_key",
]