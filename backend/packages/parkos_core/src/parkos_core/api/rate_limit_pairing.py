"""In-memory pairing-token rate limiter (T-PR8-13, REQ-OP-04, design §21.3).

Cloud-only defense against admin-side brute-force issuance of pairing
tokens. Per spec §21.3, the budget is 5 admin issuances per hour per
``actor_uuid``; the 6th within the window raises
:class:`PairingTokenRateLimitedError` and the API returns 429.

Why in-memory (not Redis):

- Single-process cloud admin app behind a single ingress (the operator
  chooses the deployment topology; this PR ships the MVP and a Redis
  adapter is a v1.1 follow-up).
- The rate-limit state is per-``actor_uuid`` — small fixed memory.
- The 1-hour reset cadence absorbs accidental over-issuance (operator
  types twice in a row) without blocking legitimate re-pairs.

Clock-driven: the limiter holds ``(tokens_remaining, last_reset_at)``
per actor and resets when ``now - last_reset_at >= 3600s``. The clock
  source is :func:`runtime.clock.server_now` (naive UTC) so test code
  can stub the clock in isolation.

Thread safety: the limiter is mutated from FastAPI handlers that run
on a single asyncio event loop. Under CPython the dict ``get/set`` is
atomic against the GIL, so no explicit lock is needed. If a future
worker moves the limiter to a thread pool, switch to ``asyncio.Lock``
or move state to Redis.
"""
from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass
from datetime import datetime

from ..runtime.clock import server_now


@dataclass
class _Bucket:
    """Per-actor rate-limit bucket."""

    tokens_remaining: int
    last_reset_at: datetime


class PairingTokenRateLimitedError(Exception):
    """Raised when an actor exceeds the 5/hour issuance budget.

    The endpoint maps this to HTTP 429 with a structured detail.
    """

    def __init__(self, actor_uuid: uuid_lib.UUID, limit: int, window_s: int) -> None:
        self.actor_uuid = actor_uuid
        self.limit = limit
        self.window_s = window_s
        super().__init__(
            f"pairing_token_rate_limited: actor={actor_uuid} "
            f"limit={limit}/{window_s}s"
        )


class PairingTokenRateLimiter:
    """Token-bucket rate limiter for ``POST /admin/pairing-tokens``.

    Usage as a FastAPI dependency::

        limiter = PairingTokenRateLimiter()

        @router.post(..., dependencies=[Depends(limiter.check)])
        async def issue(...):

    Args:
        max_per_hour: Maximum issuances per hour (default 5, per spec).
        window_seconds: Window length (default 3600).
    """

    def __init__(self, max_per_hour: int = 5, window_seconds: int = 3600) -> None:
        if max_per_hour < 1:
            raise ValueError("max_per_hour must be >= 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be >= 1")
        self.max_per_hour = max_per_hour
        self.window_seconds = window_seconds
        self._buckets: dict[uuid_lib.UUID, _Bucket] = {}

    def _now(self) -> datetime:
        return server_now()

    def check(self, actor_uuid: uuid_lib.UUID) -> None:
        """Deduct a token for ``actor_uuid`` or raise :class:`PairingTokenRateLimitedError`.

        Called from the FastAPI dependency chain on every
        ``POST /admin/pairing-tokens`` request. On reset (window
        elapsed), the bucket refills to ``max_per_hour`` and a token is
        deducted; the actor gets a fresh budget.
        """
        now = self._now()
        bucket = self._buckets.get(actor_uuid)
        if bucket is None or (now - bucket.last_reset_at).total_seconds() >= self.window_seconds:
            # Reset (first call OR window elapsed). Refill and deduct 1.
            self._buckets[actor_uuid] = _Bucket(
                tokens_remaining=self.max_per_hour - 1,
                last_reset_at=now,
            )
            return
        if bucket.tokens_remaining <= 0:
            raise PairingTokenRateLimitedError(
                actor_uuid=actor_uuid,
                limit=self.max_per_hour,
                window_s=self.window_seconds,
            )
        bucket.tokens_remaining -= 1

    def reset(self) -> None:
        """Clear the bucket map (test helper; never called in production)."""
        self._buckets.clear()


# Module-level singleton wired as a FastAPI dependency in
# ``api/v1/pairing.py``. Importing this module multiple times returns
# the same limiter instance — the bucket state survives across requests
# for the lifetime of the process.
default_limiter = PairingTokenRateLimiter()


__all__ = [
    "PairingTokenRateLimitedError",
    "PairingTokenRateLimiter",
    "default_limiter",
]