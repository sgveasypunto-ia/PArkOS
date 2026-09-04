"""Server clock + branch clock-skew validation (T-PR8-03).

Per design §21.3 (JWT ``issued_at_branch`` validation) and §21.8
(hash-chain verifier ordering), the sync transport rejects requests
whose JWT ``issued_at_branch`` claim drifts more than
``MAX_SKEW_SECONDS`` from the cloud server's wall clock. Branches with a
broken NTP sync drift unboundedly; rejecting them prevents:

- Replay attacks where a branch with a buggy clock issues a token with
  ``issued_at_branch`` far in the past or future.
- Hash-chain verifier false-positives: cloud verifies the per-branch
  chain in ``sync_timestamp`` order; a branch running 5 min ahead
  produces entries that look like out-of-order arrivals.

The skew check intentionally uses naive UTC on both sides — Postgres
stores ``timestamp without time zone`` (see ``0001_initial_schema.py``
``created_at``, ``sync_timestamp``, ``log_transaccional.timestamp_evento``)
so DST/offset arithmetic is irrelevant.

Cites §21.3 JWT specifics (``issued_at_branch`` validation), §21.8
hash-chain verifier ordering, §21.7 exit-code contract for boundary
errors.
"""
from __future__ import annotations

from datetime import UTC, datetime

#: Maximum absolute clock drift (seconds) accepted between the branch
#: ``issued_at_branch`` and the server's ``server_now()`` before the
#: request is rejected with :class:`ClockSkewError`.
#:
#: 60 s = NTP-friendly tolerance: a healthy NTP-synced branch drifts well
#: under 1 s; 60 s absorbs transient outages and short-lived NTP sync
#: restarts without blocking legitimate traffic.
MAX_SKEW_SECONDS: int = 60


class ClockSkewError(Exception):
    """Raised when ``abs(skew) > MAX_SKEW_SECONDS``.

    Carries the branch-issued and server-side timestamps so the
    middleware layer can render a structured error response (or sync
    worker can log the drift for ops review).
    """

    def __init__(self, branch_issued_at: datetime, server_now: datetime, skew_seconds: int) -> None:
        self.branch_issued_at = branch_issued_at
        self.server_now = server_now
        self.skew_seconds = skew_seconds
        super().__init__(
            f"clock skew {skew_seconds}s exceeds MAX_SKEW_SECONDS="
            f"{MAX_SKEW_SECONDS} (branch={branch_issued_at.isoformat()}, "
            f"server={server_now.isoformat()})"
        )


def server_now() -> datetime:
    """Return the server's current wall clock as naive UTC.

    Mirrors the ``_now_naive()`` pattern from :mod:`parkos_core.runtime.env`:
    return the instant with second-resolution and no tzinfo so direct
    comparison against Postgres ``timestamp without time zone`` columns
    (``log_transaccional.timestamp_evento``, ``sync_queue.timestamp_evento``,
    etc.) is unambiguous. The branching actor (``branch``) also uses naive
    UTC (the JWT serializer strips tzinfo), so the comparison stays on
    the same axis.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def clock_skew_seconds(branch_issued_at: datetime) -> int:
    """Return the integer second-delta between ``branch_issued_at`` and now.

    Positive means branch is AHEAD of server (branch clock fast);
    negative means branch is BEHIND (branch clock slow). The caller
    decides what to do with the value — :meth:`validate_skew` raises
    :class:`ClockSkewError` when the magnitude exceeds
    ``MAX_SKEW_SECONDS``.

    Args:
        branch_issued_at: Naive UTC datetime from the JWT
            ``issued_at_branch`` claim. Timezone-aware datetimes are
            accepted and normalized to naive UTC — defense in depth
            against a hostile branch that adds tzinfo to confuse drift
            arithmetic.

    Returns:
        Integer second-delta ``server_now - branch_issued_at``.
    """
    server = server_now()
    # Normalize tz-aware inputs to naive UTC. ``astimezone`` without an
    # arg rebases to the local tz; we explicitly use ``tzinfo=utc`` to
    # force UTC, regardless of the caller's local zone.
    if branch_issued_at.tzinfo is not None:
        branch_issued_at = branch_issued_at.astimezone(UTC).replace(tzinfo=None)
    return int((server - branch_issued_at).total_seconds())


def validate_skew(branch_issued_at: datetime) -> int:
    """Validate skew against :data:`MAX_SKEW_SECONDS`, raising if exceeded.

    Convenience wrapper used by ``sync_router`` middleware: returns the
    skew on success, raises :class:`ClockSkewError` (with both
    timestamps) when out of bounds. The middleware maps the exception
    to ``401 sync_jwt_clock_skew`` with the structured payload.
    """
    skew = clock_skew_seconds(branch_issued_at)
    if abs(skew) > MAX_SKEW_SECONDS:
        raise ClockSkewError(
            branch_issued_at=branch_issued_at,
            server_now=server_now(),
            skew_seconds=skew,
        )
    return skew


__all__ = [
    "MAX_SKEW_SECONDS",
    "ClockSkewError",
    "clock_skew_seconds",
    "server_now",
    "validate_skew",
]
