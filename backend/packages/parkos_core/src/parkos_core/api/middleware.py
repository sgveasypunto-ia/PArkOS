"""HTTP middlewares (REQ-OP-04 + design §8).

PR2 ships the full :class:`IdempotencyKeyMiddleware`:

  - Reads the ``Idempotency-Key`` request header.
  - Hashes ``sha256(issuer + ":" + key)`` — the issuer prefix scopes the
    key per JWT issuer (``admin-``, ``operador-``, ``sync-agent-``) so
    two callers using the same UUID string don't collide.
  - On a hit within the 24h TTL: replay the cached response (status,
    body, headers) with ``Idempotent-Replay: true``; a different request
    (body/path/method) under the same key is a 409 ``idempotency_key_conflict``.
  - On a hit past the TTL: treated as a fresh request (handler runs, no
    persist: the append-only UK keeps the stale row).
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
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
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


# Responses larger than this are streamed through untouched and never
# persisted: the replay cache is a JSONB column, not a blob store.
MAX_PERSIST_BODY_BYTES = 256 * 1024

# Paths that must never be cached/replayed by the generic layer:
#   * ``/auth/`` and ``/sync/``: responses carry tokens/credentials (login,
#     refresh, pairing) and sync keeps its own single-use / in-memory cache.
#   * ``.../subscripciones/{uuid}/renovar``: the handler replays on its own
#     (``repo.idempotency.guard``) and refreshes the FE outcome on replay.
_SELF_MANAGED_PATH_RE = re.compile(r"/(?:auth|sync)/|/subscripciones/[^/]+/renovar/?$")

# Outcomes that describe the CALLER's momentary state rather than the
# operation: caching them would make a legitimate retry (fresh token, after
# the rate-limit window) replay the failure.
_NON_CACHEABLE_STATUS = frozenset({401, 403, 408, 429})

# Hop-by-hop / per-connection / secret headers are never stored.
_VOLATILE_HEADERS = frozenset(
    {"content-length", "transfer-encoding", "connection", "keep-alive", "date", "server", "set-cookie"}
)


def _is_self_managed_path(path: str) -> bool:
    return _SELF_MANAGED_PATH_RE.search(path) is not None


def _is_cacheable_status(status: int) -> bool:
    """Persist only non-5xx outcomes that are about the operation itself."""
    return status < 500 and status not in _NON_CACHEABLE_STATUS


def _serialize_body(raw: bytes, content_type: str) -> tuple[str, Any]:
    """Return ``(kind, body)`` for the JSONB envelope, or raise ValueError.

    ``kind`` is ``empty`` / ``json`` / ``text``. Non-UTF-8 payloads are not
    representable in JSONB and raise (the caller then skips persistence).
    """
    if not raw:
        return "empty", None
    text = raw.decode("utf-8")  # UnicodeDecodeError is a ValueError
    if "json" in content_type.lower():
        try:
            return "json", json.loads(text)
        except json.JSONDecodeError:
            pass
    return "text", text


def _storable_headers(headers: Any) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in _VOLATILE_HEADERS}


async def _chain_chunks(chunks: list[bytes], rest: Any):
    for chunk in chunks:
        yield chunk
    while True:
        try:
            chunk = await rest.__anext__()
        except StopAsyncIteration:
            return
        yield chunk


async def _drain_response(response: Any) -> tuple[Response, bytes | None]:
    """Consume a streamed downstream response and rebuild an equivalent one.

    ``BaseHTTPMiddleware.call_next`` hands back a streaming response with no
    ``.body``. We read ``body_iterator`` up to ``MAX_PERSIST_BODY_BYTES``:

    * within the cap -> a plain :class:`Response` (same status, same raw
      headers incl. repeated ones) and the full body bytes for persistence;
    * over the cap -> a :class:`StreamingResponse` that replays the chunks
      already read and then the rest of the iterator (memory stays bounded),
      and ``None`` meaning "do not persist".
    """
    iterator = response.body_iterator.__aiter__()
    chunks: list[bytes] = []
    size = 0
    overflow = False
    while True:
        try:
            chunk = await iterator.__anext__()
        except StopAsyncIteration:
            break
        chunk = chunk.encode("utf-8") if isinstance(chunk, str) else bytes(chunk)
        chunks.append(chunk)
        size += len(chunk)
        if size > MAX_PERSIST_BODY_BYTES:
            overflow = True
            break

    if overflow:
        rebuilt: Response = StreamingResponse(
            _chain_chunks(chunks, iterator),
            status_code=response.status_code,
            background=getattr(response, "background", None),
        )
        rebuilt.raw_headers = list(response.raw_headers)
        return rebuilt, None

    body = b"".join(chunks)
    rebuilt = Response(
        content=body,
        status_code=response.status_code,
        background=getattr(response, "background", None),
    )
    rebuilt.raw_headers = list(response.raw_headers)
    return rebuilt, body


def _replay_response(cached: Any) -> Response:
    """Rebuild the stored response (status, body, headers) for a replay."""
    envelope = cached.response_body if isinstance(cached.response_body, dict) else {}
    body = envelope.get("body")
    kind = envelope.get("kind") or ("empty" if body is None else "json")
    headers = {
        k: v
        for k, v in (envelope.get("headers") or {}).items()
        if k.lower() != "content-length"
    }
    headers["Idempotent-Replay"] = "true"
    status = cached.response_status or 200
    if kind == "empty":
        headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
        return Response(status_code=status, headers=headers)
    if kind == "text":
        return Response(content=body, status_code=status, headers=headers)
    return JSONResponse(status_code=status, content=body, headers=headers)


async def _caller_scope(request: Request) -> tuple[str, str] | None:
    """Return ``(issuer, subject)`` scoping the key, or ``None`` to bypass.

    The route's auth dependency runs AFTER this middleware, so
    ``request.state.jwt_claims`` is never populated yet. When a bearer token
    is sent we verify it here; if it does not verify we bypass idempotency
    entirely and let the route answer 401 (a replay must never be served to
    a caller that failed authentication).
    """
    if not request.headers.get("Authorization"):
        return "anonymous", ""
    from ..auth.jwt_issuer_guard import verify_jwt  # local import: avoid cycles

    try:
        await verify_jwt(request)
    except Exception:  # noqa: BLE001 - any auth failure => bypass
        return None
    claims = getattr(request.state, "jwt_claims", None) or {}
    return _issuer_for_request(request), str(claims.get("sub", ""))


class IdempotencyKeyMiddleware(BaseHTTPMiddleware):
    """Replay cached responses for repeated ``Idempotency-Key`` requests.

    Per design §8: GET, OPTIONS, and any request without the header is
    a pass-through. POST/PUT/PATCH/DELETE with the header consult
    ``prod.idempotency_keys`` before invoking the route handler.

    * Same key + same request (method, path, body) within 24h -> the stored
      response with ``Idempotent-Replay: true``; the handler does not run.
    * Same key + different request -> 409 ``idempotency_key_conflict``.
    * Expired key -> a NEW request (handler runs; the append-only UK keeps
      the stale row, so nothing is persisted).
    * Only non-5xx, operation-level outcomes are persisted.
    """

    async def dispatch(self, request: Request, call_next):
        raw_key = request.headers.get("Idempotency-Key")
        request.state.idempotency_key = raw_key
        if not raw_key or _is_self_managed_path(request.url.path):
            return await call_next(request)

        scope = await _caller_scope(request)
        if scope is None:
            return await call_next(request)
        issuer, subject = scope
        key_hash = _hash_idempotency_key(
            issuer, f"{subject}:{raw_key}" if subject else raw_key
        )
        request.state.idempotency_key_hash = key_hash
        request.state.idempotency_key_issuer = issuer

        body_hash = _hash_request_body(await request.body())

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
                    # An expired key is a NEW request, never a permanent 410.
                    # ``idempotency_keys`` is append-only with UK (issuer,
                    # key_hash), so the stale row can neither be updated nor
                    # re-inserted: run the handler and do not persist.
                    logger.info(
                        "idempotency_key_expired_passthrough",
                        extra={"issuer": issuer, "path": request.url.path},
                    )
                    return await call_next(request)

                stored_hash = getattr(cached, "request_body_hash", None)
                stored_path = getattr(cached, "path", None)
                stored_method = getattr(cached, "method", None)
                if (
                    (stored_hash is not None and stored_hash != body_hash)
                    or (stored_path is not None and stored_path != request.url.path)
                    or (stored_method is not None and stored_method != request.method)
                ):
                    return JSONResponse(
                        status_code=409,
                        content={"detail": {"error": "idempotency_key_conflict"}},
                        headers={"Cache-Control": "no-store"},
                    )

                logger.debug(
                    "idempotency_key_replay",
                    extra={
                        "issuer": issuer,
                        "path": request.url.path,
                        "cached_status": cached.response_status,
                    },
                )
                return _replay_response(cached)

            # First time — pass through, then persist on response.
            downstream = await call_next(request)
            if not hasattr(downstream, "body_iterator"):
                return downstream
            response, raw_body = await _drain_response(downstream)

            if raw_body is None or not _is_cacheable_status(response.status_code):
                return response

            try:
                kind, body = _serialize_body(
                    raw_body, response.headers.get("content-type", "")
                )
                session.add(
                    IdempotencyKeys(
                        issuer=issuer,
                        key_hash=key_hash,
                        method=request.method,
                        path=request.url.path,
                        request_body_hash=body_hash,
                        response_status=response.status_code,
                        response_body={
                            "kind": kind,
                            "body": body,
                            "headers": _storable_headers(response.headers),
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