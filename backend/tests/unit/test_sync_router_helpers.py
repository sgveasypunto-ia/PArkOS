"""Unit tests for ``sync.router_helpers`` (PR8c, T-PR8-22).

The server-side helpers consumed by :mod:`parkos_core.api.v1.sync_router`:

- :class:`SyncIdempotencyCache` — in-memory LRU keyed by
  ``(issuer, subject, x_request_id)`` with TTL-based eviction.
- :class:`RateLimit` — per-(issuer, subject) token-bucket limiter that
  raises :class:`SyncRateLimitedError` with ``retry_after_seconds`` when
  exhausted.
- :func:`extract_subject_from_jwt` — pulls ``sub`` claim.
- :func:`check_iat_branch_skew` — validates JWT ``iat_branch`` claim
  against :func:`server_now`; raises :class:`ClockSkewError` when
  drift exceeds 60s.

Distinct from ``tests/unit/test_sync_transport.py`` (PR9, T-PR9-02)
which exercises the CLIENT-side ``SyncHttpClient``.

All tests stub :func:`server_now` via ``monkeypatch`` so they're
deterministic and don't depend on wall-clock arithmetic.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from parkos_core.runtime.clock import ClockSkewError
from parkos_core.sync.router_helpers import (
    RateLimit,
    SyncIdempotencyCache,
    SyncRateLimitedError,
    check_iat_branch_skew,
    decode_jwt_header_kid,
    extract_subject_from_jwt,
)

# ---------------------------------------------------------------------------
# Clock helpers
# ---------------------------------------------------------------------------


def _frozen_now(monkeypatch: pytest.MonkeyPatch, iso: str = "2026-09-03T12:00:00") -> datetime:
    """Patch ``server_now`` to return a fixed naive-UTC instant.

    Two patches are needed because ``router_helpers`` does
    ``from ..runtime.clock import server_now`` (binding a separate
    reference in its namespace for the cache's internal clock) AND
    uses ``clock_skew_seconds`` (which references ``server_now`` in its
    own module scope at call time). Patch both names so every clock
    read returns the frozen instant.
    """
    dt = datetime.fromisoformat(iso).replace(tzinfo=None)
    monkeypatch.setattr("parkos_core.sync.router_helpers.server_now", lambda: dt)
    monkeypatch.setattr("parkos_core.runtime.clock.server_now", lambda: dt)
    return dt


# ---------------------------------------------------------------------------
# SyncIdempotencyCache
# ---------------------------------------------------------------------------


class TestSyncIdempotencyCache:
    """``(issuer, subject, x_request_id)`` LRU with TTL eviction."""

    def test_get_on_empty_cache_returns_none(self) -> None:
        cache = SyncIdempotencyCache(maxsize=10, ttl_seconds=60)
        assert cache.get("sync-agent-", "sub-1", "req-1") is None

    def test_put_then_get_returns_cached_entry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _frozen_now(monkeypatch)
        cache = SyncIdempotencyCache(maxsize=10, ttl_seconds=60)
        cache.put("sync-agent-", "sub-1", "req-1", 207, {"results": [{"x": 1}]})
        cached = cache.get("sync-agent-", "sub-1", "req-1")
        assert cached is not None
        assert cached[0] == 207
        assert cached[1] == {"results": [{"x": 1}]}

    def test_cache_expires_after_ttl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        base = _frozen_now(monkeypatch)
        cache = SyncIdempotencyCache(maxsize=10, ttl_seconds=60)
        cache.put("sync-agent-", "sub-1", "req-1", 207, {"a": 1})

        # Advance the clock past the TTL.
        later = base + timedelta(seconds=61)
        monkeypatch.setattr(
            "parkos_core.sync.router_helpers.server_now", lambda: later
        )
        assert cache.get("sync-agent-", "sub-1", "req-1") is None
        assert len(cache) == 0  # expired entry evicted on access

    def test_lru_evicts_oldest_at_maxsize(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _frozen_now(monkeypatch)
        cache = SyncIdempotencyCache(maxsize=3, ttl_seconds=600)
        cache.put("i", "s", "r1", 200, {"k": 1})
        cache.put("i", "s", "r2", 200, {"k": 2})
        cache.put("i", "s", "r3", 200, {"k": 3})
        # Insert a 4th — oldest (r1) should evict.
        cache.put("i", "s", "r4", 200, {"k": 4})
        assert cache.get("i", "s", "r1") is None
        assert cache.get("i", "s", "r2") is not None
        assert cache.get("i", "s", "r3") is not None
        assert cache.get("i", "s", "r4") is not None
        assert len(cache) == 3

    def test_different_x_request_id_for_same_issuer_subject_independent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _frozen_now(monkeypatch)
        cache = SyncIdempotencyCache(maxsize=10, ttl_seconds=60)
        cache.put("sync-agent-", "sub-1", "req-1", 200, {"x": 1})
        cache.put("sync-agent-", "sub-1", "req-2", 200, {"x": 2})

        assert cache.get("sync-agent-", "sub-1", "req-1") == (200, {"x": 1})
        assert cache.get("sync-agent-", "sub-1", "req-2") == (200, {"x": 2})

    def test_put_returns_false_first_call_true_on_replace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``put`` returns ``True`` iff the key was already present."""
        _frozen_now(monkeypatch)
        cache = SyncIdempotencyCache(maxsize=10, ttl_seconds=60)
        assert cache.put("i", "s", "r", 200, {"a": 1}) is False  # fresh insert
        assert cache.put("i", "s", "r", 201, {"a": 2}) is True  # replaced

    def test_constructor_validates_args(self) -> None:
        with pytest.raises(ValueError):
            SyncIdempotencyCache(maxsize=0)
        with pytest.raises(ValueError):
            SyncIdempotencyCache(ttl_seconds=0)


# ---------------------------------------------------------------------------
# RateLimit
# ---------------------------------------------------------------------------


class TestRateLimit:
    """Per-(issuer, subject) token bucket."""

    def test_first_n_pass_then_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _frozen_now(monkeypatch)
        limiter = RateLimit(per_minute=3)
        # 3 calls fit the bucket; the 4th raises.
        limiter.check("sync-agent-", "subject-1")
        limiter.check("sync-agent-", "subject-1")
        limiter.check("sync-agent-", "subject-1")
        with pytest.raises(SyncRateLimitedError) as exc_info:
            limiter.check("sync-agent-", "subject-1")
        # retry_after_seconds is bounded by the window's remaining time.
        assert 1 <= exc_info.value.retry_after_seconds <= 60

    def test_bucket_refills_after_window(self, monkeypatch: pytest.MonkeyPatch) -> None:
        base = _frozen_now(monkeypatch)
        limiter = RateLimit(per_minute=2)
        limiter.check("i", "s")  # refill to 1
        limiter.check("i", "s")  # refill to 0
        with pytest.raises(SyncRateLimitedError):
            limiter.check("i", "s")

        # Advance past the 60s window.
        monkeypatch.setattr(
            "parkos_core.sync.router_helpers.server_now",
            lambda: base + timedelta(seconds=61),
        )
        # Bucket refilled — call passes.
        limiter.check("i", "s")

    def test_independent_buckets_per_issuer_subject(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _frozen_now(monkeypatch)
        limiter = RateLimit(per_minute=1)
        limiter.check("sync-agent-", "branch-a")
        # Same issuer, different subject — independent bucket.
        limiter.check("sync-agent-", "branch-b")
        # First bucket is exhausted; second call from branch-a raises.
        with pytest.raises(SyncRateLimitedError):
            limiter.check("sync-agent-", "branch-a")

    def test_retry_after_seconds_approximates_remaining_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base = _frozen_now(monkeypatch)
        limiter = RateLimit(per_minute=1)
        limiter.check("i", "s")
        # Advance 30s into the window.
        monkeypatch.setattr(
            "parkos_core.sync.router_helpers.server_now",
            lambda: base + timedelta(seconds=30),
        )
        with pytest.raises(SyncRateLimitedError) as exc_info:
            limiter.check("i", "s")
        # 60s window - 30s elapsed = 30s remaining.
        assert 25 <= exc_info.value.retry_after_seconds <= 35

    def test_constructor_rejects_invalid_per_minute(self) -> None:
        with pytest.raises(ValueError):
            RateLimit(per_minute=0)


# ---------------------------------------------------------------------------
# JWT-claim helpers
# ---------------------------------------------------------------------------


class TestExtractSubjectFromJwt:
    def test_returns_sub_claim(self) -> None:
        claims: dict[str, Any] = {"sub": "00000000-0000-0000-0000-000000000abc"}
        assert extract_subject_from_jwt(claims) == "00000000-0000-0000-0000-000000000abc"

    def test_missing_sub_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            extract_subject_from_jwt({})


class TestCheckIatBranchSkew:
    def test_no_skew_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        now = _frozen_now(monkeypatch)
        # Branch stamped ``iat_branch`` exactly at ``server_now`` — zero skew.
        claims = {"iat_branch": now.isoformat()}
        check_iat_branch_skew(claims)  # no exception

    def test_positive_skew_above_max_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        now = _frozen_now(monkeypatch)
        branch_dt = now - timedelta(seconds=120)  # branch 120s behind
        claims = {"iat_branch": branch_dt.isoformat()}
        with pytest.raises(ClockSkewError) as exc_info:
            check_iat_branch_skew(claims)
        # skew is positive (server ahead of branch) per clock_skew_seconds.
        assert exc_info.value.skew_seconds >= 60

    def test_negative_skew_below_max_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        now = _frozen_now(monkeypatch)
        # Branch 120s ahead of server — negative skew.
        branch_dt = now + timedelta(seconds=120)
        claims = {"iat_branch": branch_dt.isoformat()}
        with pytest.raises(ClockSkewError) as exc_info:
            check_iat_branch_skew(claims)
        assert exc_info.value.skew_seconds <= -60

    def test_missing_iat_branch_is_silent_pass_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Back-compat: PR8b-era tokens omit ``iat_branch`` — no exception."""
        _frozen_now(monkeypatch)
        # Must NOT raise — see module docstring.
        check_iat_branch_skew({})

    def test_skew_at_boundary_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Skew of exactly 60s is at the boundary (not greater) — passes."""
        now = _frozen_now(monkeypatch)
        branch_dt = now - timedelta(seconds=60)
        claims = {"iat_branch": branch_dt.isoformat()}
        check_iat_branch_skew(claims)  # no exception

    def test_unix_epoch_int_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        now = _frozen_now(monkeypatch)
        epoch = int(now.replace(tzinfo=UTC).timestamp())
        claims = {"iat_branch": epoch}
        check_iat_branch_skew(claims)  # no exception

    def test_z_suffix_iso8601_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        now = _frozen_now(monkeypatch)
        iso_with_z = now.isoformat() + "Z"
        claims = {"iat_branch": iso_with_z}
        check_iat_branch_skew(claims)  # no exception


# ---------------------------------------------------------------------------
# decode_jwt_header_kid
# ---------------------------------------------------------------------------


class TestDecodeJwtHeaderKid:
    def test_decodes_kid_from_real_jwt(self) -> None:
        # Build a real JWT via issue_token so the header format matches.
        from parkos_core.auth.tokens import issue_token

        token = issue_token(
            subject_uuid=uuid_lib.uuid4(),
            issuer="sync-agent-test",
            claims={},
            expires_in=60,
        )
        kid = decode_jwt_header_kid(token)
        assert kid.startswith("sync-agent-")

    def test_malformed_token_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            decode_jwt_header_kid("not.a.jwt")
        with pytest.raises(ValueError):
            decode_jwt_header_kid("")
