"""Idempotency-Key helpers (REQ-OP-04, design §4.7).

The middleware layer (``api/middleware.py::IdempotencyKeyMiddleware``)
inspects the ``Idempotency-Key`` header on POST requests and calls these
helpers to enforce single-execution semantics:

- First call with a given key: caller proceeds + calls ``store_response``.
- Replay with the SAME key + SAME body: returns cached response + flag
  ``is_replay=True`` (caller sends ``Idempotent-Replay: true`` header).
- Replay with the SAME key + DIFFERENT body: ``IdempotencyConflictError``
  (409 Conflict).
- Missing key on POST: ``IdempotencyKeyRequiredError`` (400).

TTL: 24 hours by default (``ttl_seconds=86400``). After expiry the entry
is treated as fresh (re-INSERT allowed).

ORM column mapping (defense in depth — see PR2 ``models/A/idempotency_keys.py``):

- Public ``endpoint`` parameter → ORM column ``path`` (String(512))
- Public ``request_payload_hash`` (computed) → ORM column
  ``request_body_hash`` (CHAR(64))
- Public ``response_body: bytes`` → ORM column ``response_body`` (JSONB
  dict) — bytes are JSON-decoded on store, JSON-encoded on retrieval.
- ``method`` is hardcoded to ``"POST"`` (middleware only enforces POST).
- ``issuer`` is left NULL (future PR adds issuer-scoped keys).
"""
from __future__ import annotations

import hashlib
import json
import uuid as uuid_lib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.idempotency_keys import IdempotencyKeys


class IdempotencyError(Exception):
    """Base class for idempotency-related errors."""


class IdempotencyKeyRequiredError(IdempotencyError):
    """Raised when a POST handler receives no ``Idempotency-Key`` header."""


class IdempotencyConflictError(IdempotencyError):
    """Raised when a key is reused with a DIFFERENT request body."""


@dataclass
class IdempotencyGuardResult:
    """Result of :func:`guard` when a non-expired cached entry is found."""

    is_replay: bool
    status: int
    body: bytes


def _now_naive() -> datetime:
    """Naive UTC ``datetime`` matching the DB ``DateTime(timezone=False)`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def _hash_key(idempotency_key: str) -> str:
    """SHA-256 hash the raw key (never store the raw key in the DB)."""
    return hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()


def _hash_payload(request_body: bytes) -> str:
    """SHA-256 hash of the request body for key/body-mismatch detection."""
    return hashlib.sha256(request_body).hexdigest()


def _decode_response_body(body: bytes) -> dict:
    """Decode ``bytes`` to a ``dict`` for the JSONB ``response_body`` column.

    Falls back to a ``{"raw_text": ...}`` wrapper if the bytes aren't
    valid JSON (defense in depth — middleware should always send JSON).
    """
    if not body:
        return {}
    try:
        decoded = json.loads(body.decode("utf-8"))
        if isinstance(decoded, dict):
            return decoded
        return {"data": decoded}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"raw_text": body.decode("utf-8", errors="replace")}


def _encode_response_body(body: dict | None) -> bytes:
    """Encode the JSONB dict back to ``bytes`` for the caller's replay response."""
    if body is None:
        return b""
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


async def guard(
    session: AsyncSession,
    *,
    endpoint: str,
    idempotency_key: str,
    request_body: bytes,
    actor_uuid: uuid_lib.UUID,
) -> IdempotencyGuardResult | None:
    """Look up a cached idempotency entry for the given key + endpoint.

    Args:
        session: Active ``AsyncSession`` (caller commits).
        endpoint: Logical endpoint identifier (e.g. ``"/api/v1/auth/login"``).
            Stored in the ORM's ``path`` column.
        idempotency_key: Raw ``Idempotency-Key`` header value (hashed before
            lookup; never stored verbatim).
        request_body: Raw request body bytes — hashed for body-mismatch
            detection.
        actor_uuid: JWT subject (audit actor; not used for lookup but kept
            in the signature for API symmetry with :func:`store_response`).

    Returns:
        ``None`` if no cached entry exists (caller should proceed + call
        :func:`store_response` after the handler succeeds).
        :class:`IdempotencyGuardResult` if a non-expired entry exists with
        the SAME request body hash.

    Raises:
        :class:`IdempotencyKeyRequiredError` if ``idempotency_key`` is empty.
        :class:`IdempotencyConflictError` if a non-expired entry exists
        with a DIFFERENT request body hash (key reuse with different payload).
    """
    if not idempotency_key:
        raise IdempotencyKeyRequiredError(
            "Idempotency-Key header is required on POST"
        )

    key_hash = _hash_key(idempotency_key)
    now = _now_naive()

    stmt = select(IdempotencyKeys).where(
        IdempotencyKeys.path == endpoint,
        IdempotencyKeys.key_hash == key_hash,
        IdempotencyKeys.expires_at > now,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is None:
        return None  # No cached entry — caller proceeds.

    payload_hash = _hash_payload(request_body)
    if existing.request_body_hash != payload_hash:
        raise IdempotencyConflictError(
            f"Idempotency-Key {idempotency_key!r} reused with different request body"
        )

    return IdempotencyGuardResult(
        is_replay=True,
        status=existing.response_status if existing.response_status is not None else 200,
        body=_encode_response_body(existing.response_body),
    )


async def store_response(
    session: AsyncSession,
    *,
    endpoint: str,
    idempotency_key: str,
    request_body: bytes,
    actor_uuid: uuid_lib.UUID,
    response_status: int,
    response_body: bytes,
    ttl_seconds: int = 86400,
) -> IdempotencyKeys:
    """Cache the response for future replays.

    Called by the middleware AFTER the handler succeeds. The row is
    append-only (``REVOKE UPDATE, DELETE`` + ``BEFORE UPDATE OR DELETE``
    trigger enforce immutability — see migration ``0002``).

    Args:
        session: Active ``AsyncSession`` (caller commits).
        endpoint: Logical endpoint identifier (mapped to ORM ``path``).
        idempotency_key: Raw ``Idempotency-Key`` header value (hashed
            before storage).
        request_body: Raw request body bytes (hashed before storage).
        actor_uuid: JWT subject — stored in ``created_by``.
        response_status: HTTP status code to replay.
        response_body: Raw response body bytes — JSON-decoded for the
            JSONB column.
        ttl_seconds: Seconds until the entry expires (default 24h).

    Returns:
        The newly created :class:`IdempotencyKeys` row (not yet committed).
    """
    now = _now_naive()
    expires_at = now + timedelta(seconds=ttl_seconds)

    key_hash = _hash_key(idempotency_key)
    payload_hash = _hash_payload(request_body)
    body_dict = _decode_response_body(response_body)

    row = IdempotencyKeys(
        path=endpoint,
        key_hash=key_hash,
        method="POST",  # middleware only enforces POST
        request_body_hash=payload_hash,
        response_status=response_status,
        response_body=body_dict,
        expires_at=expires_at,
        created_at=now,
        created_by=actor_uuid,
    )
    session.add(row)
    return row


__all__ = [
    "IdempotencyConflictError",
    "IdempotencyError",
    "IdempotencyGuardResult",
    "IdempotencyKeyRequiredError",
    "guard",
    "store_response",
]