"""Server-side helpers for the sync router (PR8c, T-PR8-15).

Distinct from the client-side :class:`SyncHttpClient` in
:mod:`parkos_core.sync.transport` (PR9, T-PR9-02). This module is consumed
by :mod:`parkos_core.api.v1.sync_router` to enforce idempotency + rate
limits + clock-skew checks on the ``/sync/*`` surface.

Three primitives ship here:

- :class:`SyncIdempotencyCache` — process-local LRU keyed by
  ``(issuer, subject, x_request_id)``. Same shape as PR7's
  :class:`parkos_core.api.middleware.IdempotencyKeyMiddleware` but in-memory
  only and TTL-based (no DB roundtrip per request).
- :class:`RateLimit` — per-(issuer, subject) token-bucket limiter.
  Defaults per ``tasks.md:576``: push=60/min, pull=120/min,
  heartbeat=10/min, rotate_jwt=1/min. The router instantiates one
  per endpoint with the appropriate ``per_minute``.
- :func:`check_iat_branch_skew` / :func:`extract_subject_from_jwt` —
  JWT-claim helpers for the sync-router endpoints (the spec uses the
  ``iat_branch`` claim to detect branch clock drift per §21.3).

Why in-memory only (not Redis):

- The /sync/* path runs on a single FastAPI worker per process; the
  operator chooses the deployment topology. A Redis-backed variant is
  a follow-up if the cloud team moves to multi-instance behind a load
  balancer.
- The bucket state is small (10k entries for the cache, dozens of
  (issuer, subject) pairs for the limiter); per-process memory cost is
  negligible.
- The 5-min cache TTL + 60-sec rate-limit window absorb retry storms
  without blocking legitimate traffic.

Cites §21.9 (Idempotency + Rate limits), §21.3 (issued_at_branch skew),
§21.14 acceptance #15-16.
"""
from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..runtime.clock import ClockSkewError, clock_skew_seconds, server_now


class SyncRateLimitedError(Exception):
    """Raised when a (issuer, subject) bucket exceeds its per-minute budget.

    The endpoint maps this to HTTP 429 with a structured detail + the
    ``Retry-After`` header carrying ``retry_after_seconds``.
    """

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"sync_rate_limited: retry_after={retry_after_seconds}s"
        )


# ---------------------------------------------------------------------------
# Idempotency cache
# ---------------------------------------------------------------------------


@dataclass
class _CacheEntry:
    """One cached response (status, body) with the naive-UTC insertion time."""

    status: int
    body: dict[str, Any]
    stored_at: datetime  # naive UTC


class SyncIdempotencyCache:
    """In-memory LRU keyed by ``(issuer, subject, x_request_id)``.

    Per request: the handler calls :meth:`get` first; if it returns a
    non-``None`` tuple, that tuple is replayed with the ``Idempotent-Replay:
    true`` header. If it returns ``None``, the handler executes, then calls
    :meth:`put` to register the response.

    Args:
        maxsize: Maximum entries to retain (LRU eviction past this).
            Default 10_000 per spec §21.9.
        ttl_seconds: How long a cached entry remains valid. Default
            300s (5 min) per spec §21.9.

    Thread safety: the cache is mutated from FastAPI handlers running on
    a single asyncio event loop. Under CPython the dict ``get/set`` is
    atomic against the GIL, so no explicit lock is needed. If a future
    worker moves the cache to a thread pool, switch to ``asyncio.Lock``
    or move state to Redis.
    """

    def __init__(self, maxsize: int = 10_000, ttl_seconds: int = 300) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be >= 1")
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[tuple[str, str, str], _CacheEntry] = OrderedDict()

    def _now(self) -> datetime:
        return server_now()

    def get(
        self, issuer: str, subject: str, x_request_id: str
    ) -> tuple[int, dict[str, Any]] | None:
        """Return the cached ``(status, body)`` for ``(issuer, subject, x_request_id)``.

        ``None`` when no entry exists OR the entry is older than
        ``ttl_seconds``. Expired entries are evicted lazily on access
        (no background sweeper).
        """
        key = (issuer, subject, x_request_id)
        entry = self._cache.get(key)
        if entry is None:
            return None
        elapsed = (self._now() - entry.stored_at).total_seconds()
        if elapsed > self.ttl_seconds:
            # TTL expired — drop it + tell caller there's nothing to replay.
            self._cache.pop(key, None)
            return None
        # Touch for LRU semantics: the read counts as a "use".
        self._cache.move_to_end(key)
        return (entry.status, entry.body)

    def put(
        self,
        issuer: str,
        subject: str,
        x_request_id: str,
        status: int,
        body: dict[str, Any],
    ) -> bool:
        """Store ``(status, body)`` for the key.

        Returns:
            ``True`` if the key was already present in the cache
            (i.e. this PUT is replacing an entry that the same caller
            is calling again). ``False`` if the key was new (this PUT
            is the FIRST time the response was stored).

        The contract lets callers distinguish a fresh write from a
        replay. In practice the router doesn't need the return value —
        it always stores the response on first call; the SECOND
        call's :meth:`get` returns the cached entry and the handler
        short-circuits without calling :meth:`put` again. The return
        is exposed for tests + future debugging.
        """
        key = (issuer, subject, x_request_id)
        already_present = key in self._cache
        entry = _CacheEntry(status=status, body=body, stored_at=self._now())
        if already_present:
            # Refresh: drop the old timestamp + move to MRU end.
            self._cache.move_to_end(key)
            self._cache[key] = entry
        else:
            self._cache[key] = entry
            # LRU eviction: drop the oldest entry until we're at maxsize.
            while len(self._cache) > self.maxsize:
                self._cache.popitem(last=False)
        return already_present

    def reset(self) -> None:
        """Clear the cache (test helper; never called in production)."""
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


@dataclass
class _RateBucket:
    """Per-(issuer, subject) token-bucket state."""

    tokens_remaining: int
    last_reset_at: datetime  # naive UTC


class RateLimit:
    """Per-(issuer, subject) token-bucket rate limiter for /sync/*.

    Defaults (router wires one instance per endpoint, passing the
    spec's ``per_minute``):

    - push=60/min
    - pull=120/min
    - heartbeat=10/min
    - rotate_jwt=1/min

    Args:
        per_minute: Maximum requests per 60-second window per
            (issuer, subject) pair.

    Raises:
        SyncRateLimitedError: with ``retry_after_seconds`` set to the
            seconds until the bucket resets.
    """

    def __init__(self, *, per_minute: int) -> None:
        if per_minute < 1:
            raise ValueError("per_minute must be >= 1")
        self.per_minute = per_minute
        self._window_seconds = 60
        self._buckets: dict[tuple[str, str], _RateBucket] = {}

    def _now(self) -> datetime:
        return server_now()

    def check(self, issuer: str, subject: str) -> None:
        """Deduct one token from the (issuer, subject) bucket.

        On the first call OR after the bucket resets, refill to
        ``per_minute`` and deduct 1 (the caller is admitted). When the
        bucket is empty (all tokens spent within the 60-second window),
        raise :class:`SyncRateLimitedError` carrying the seconds
        remaining until the next reset.
        """
        now = self._now()
        key = (issuer, subject)
        bucket = self._buckets.get(key)
        if bucket is None or (now - bucket.last_reset_at).total_seconds() >= self._window_seconds:
            # Reset (first call OR window elapsed). Refill and deduct 1.
            self._buckets[key] = _RateBucket(
                tokens_remaining=self.per_minute - 1,
                last_reset_at=now,
            )
            return
        if bucket.tokens_remaining <= 0:
            # Window hasn't reset yet. Compute the seconds until reset.
            elapsed = (now - bucket.last_reset_at).total_seconds()
            retry_after = max(1, int(self._window_seconds - elapsed))
            raise SyncRateLimitedError(retry_after_seconds=retry_after)
        bucket.tokens_remaining -= 1

    def reset(self) -> None:
        """Clear the bucket map (test helper; never called in production)."""
        self._buckets.clear()


# ---------------------------------------------------------------------------
# JWT-claim helpers
# ---------------------------------------------------------------------------


def extract_subject_from_jwt(claims: dict[str, Any]) -> str:
    """Return the JWT ``sub`` claim as a string.

    Sync-agent JWTs use the JWT subject (``sub``) as the rate-limit
    bucket key (NOT ``uuid_sucursal``). The branch's uuid is carried in
    the ``sucursal`` claim; ``sub`` is the sync-agent identity (which
    for branch-side tokens is the branch uuid; for cloud-side tokens
    it's the cloud service account uuid).
    """
    sub = claims.get("sub")
    if not sub:
        raise KeyError("JWT claims missing required 'sub' claim")
    return str(sub)


def check_iat_branch_skew(
    claims: dict[str, Any],
    *,
    max_skew_seconds: int = 60,
) -> None:
    """Validate ``iat_branch`` claim against the server clock.

    Per §21.3 (JWT specifics): the branch stamps ``iat_branch`` on every
    sync call so the cloud detects clock drift early. The cloud compares
    ``server_now() - iat_branch``; if the absolute delta exceeds
    ``max_skew_seconds`` (default 60s, NTP-friendly), the request is
    rejected with :class:`ClockSkewError`.

    No-claim behavior: when ``iat_branch`` is missing from the JWT, the
    helper is a silent pass-through (PR8b tokens don't carry the claim
    yet; PR9 rotates tokens to include it). This keeps backward compat
    with existing tokens while letting PR8c surface drift on new ones.

    Args:
        claims: Decoded JWT claims dict (from :func:`verify_token`).
        max_skew_seconds: Maximum absolute drift tolerated. Per spec §21.3
            default 60s.

    Raises:
        ClockSkewError: with branch_issued_at, server_now, and skew_seconds.
    """
    raw = claims.get("iat_branch")
    if raw is None:
        # No claim present — back-compat pass-through. PR9 tokens will
        # include it; older tokens skip the check.
        return

    branch_dt = _coerce_iat_branch(raw)
    skew = clock_skew_seconds(branch_dt)
    if abs(skew) > max_skew_seconds:
        raise ClockSkewError(
            branch_issued_at=branch_dt,
            server_now=server_now(),
            skew_seconds=skew,
        )


def _coerce_iat_branch(raw: Any) -> datetime:
    """Coerce an ``iat_branch`` claim value to a naive UTC datetime.

    Accepts:
    - ``datetime`` (tz-aware → rebased to UTC + tzinfo stripped)
    - ``int`` / ``float`` (unix epoch seconds, fractional OK)
    - ``str`` (ISO 8601, with or without trailing ``Z``)

    Anything else raises ``ClockSkewError`` with skew=0 — the request
    is rejected as malformed rather than silently passed through (an
    attacker shouldn't get a free pass by sending a bogus iat_branch).
    """
    if isinstance(raw, datetime):
        branch_dt = raw
        if branch_dt.tzinfo is not None:
            branch_dt = branch_dt.astimezone(UTC).replace(tzinfo=None)
        return branch_dt

    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(int(raw), tz=UTC).replace(tzinfo=None)

    if isinstance(raw, str):
        # ISO 8601 with optional trailing 'Z' (RFC 3339 UTC designator).
        # Python 3.13's ``fromisoformat`` accepts the trailing 'Z' natively.
        try:
            branch_dt = datetime.fromisoformat(raw)
        except ValueError as e:
            raise ClockSkewError(
                branch_issued_at=server_now(),
                server_now=server_now(),
                skew_seconds=0,
            ) from e
        if branch_dt.tzinfo is not None:
            branch_dt = branch_dt.astimezone(UTC).replace(tzinfo=None)
        return branch_dt

    raise ClockSkewError(
        branch_issued_at=server_now(),
        server_now=server_now(),
        skew_seconds=0,
    )


def decode_jwt_header_kid(token: str) -> str:
    """Decode the JWT header and return its ``kid`` claim.

    Used by the sync router to (a) populate the ``is_revoked`` lookup
    and (b) compute the new JWT's ``kid`` during rotate-jwt. The header
    is base64url-decoded WITHOUT signature verification; the caller's
    :func:`verify_jwt` dependency handles that. This helper is purely
    informational.

    Args:
        token: The raw JWT string (``header.payload.signature``).

    Returns:
        The ``kid`` claim from the header.

    Raises:
        ValueError: if the token is malformed or the header doesn't
            carry a ``kid`` claim.
    """
    if not isinstance(token, str) or token.count(".") != 2:
        raise ValueError("malformed_jwt")
    header_b64 = token.split(".", 1)[0]
    try:
        # Restore base64url padding (JWT strips it; b64decode needs it).
        from base64 import urlsafe_b64decode

        padding = "=" * (-len(header_b64) % 4)
        raw = urlsafe_b64decode(header_b64 + padding)
        header = json.loads(raw)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"jwt_header_decode_failed: {e}") from e
    kid = header.get("kid")
    if not isinstance(kid, str):
        raise TypeError("jwt_header_missing_kid")
    return kid


__all__ = [
    "RateLimit",
    "SyncIdempotencyCache",
    "SyncRateLimitedError",
    "check_iat_branch_skew",
    "decode_jwt_header_kid",
    "extract_subject_from_jwt",
]