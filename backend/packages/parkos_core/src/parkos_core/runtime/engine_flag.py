"""``PARKOS_SYNC_ENGINE`` parser (T-PR1-008, D22, ADR-001).

Single feature flag governing the sync-overhaul cutover, staged **by
service** (D13), not by engine behaviour. Read by every worker/service at
the top of its loop tick via :func:`get_engine`, validated on first read,
and cached thereafter (re-read every 60 s so a stage flip doesn't require a
process restart).

Exactly five values are accepted — the service-flavoured enum ratified by
D22 (ADR-001 amendment, 2026-09-08). The prior behaviour-flavoured enum
(``catalog_read``, ``catalog_dual``, ``catalog_only``, ``catalog_lite``) is
**withdrawn** and must never parse successfully; the AST guard
``check_engine_flag_values.py`` (PR11) enforces that no withdrawn literal
appears anywhere under ``backend/`` or ``openspec/scripts/``.

| Value            | Stage | Service                     |
|------------------|-------|------------------------------|
| ``legacy``        | 0     | all — **kill switch** (D12) |
| ``catalog_admin``  | 1     | ``api_admin``                |
| ``catalog_dian``   | 2     | ``dian/cloud/dispatcher``    |
| ``catalog``        | 3     | ``jobs/sync_cloud``          |
| ``catalog_branch`` | 4-5   | branch workers                |

Parsing is always **exact-match** against the enum, never a prefix or
``startswith`` test — ``catalog`` must not swallow ``catalog_admin``,
``catalog_dian``, or ``catalog_branch``.
"""

from __future__ import annotations

import os
import time
from enum import StrEnum

# Values withdrawn by the ADR-001 amendment (2026-09-08). Rejected with a
# dedicated message so a stale deploy config fails loudly instead of
# silently falling through to "unrecognized value".
_WITHDRAWN_VALUES: frozenset[str] = frozenset(
    {"catalog_read", "catalog_dual", "catalog_only", "catalog_lite"}
)

# Workers re-read the flag every 60s so a stage transition (e.g.
# catalog_dian -> catalog) doesn't require a process restart.
_CACHE_TTL_SECONDS: float = 60.0


class InvalidEngineModeError(ValueError):
    """Raised when ``PARKOS_SYNC_ENGINE`` is unset or holds an unrecognized value."""


class EngineMode(StrEnum):
    """The five ratified ``PARKOS_SYNC_ENGINE`` values (D22, ADR-001)."""

    LEGACY = "legacy"
    CATALOG_ADMIN = "catalog_admin"
    CATALOG_DIAN = "catalog_dian"
    CATALOG = "catalog"
    CATALOG_BRANCH = "catalog_branch"


_cached: tuple[EngineMode, float] | None = None


def _parse(raw: str | None) -> EngineMode:
    """Exact-match parse; never a prefix/startswith test (ADR-001 Negative consequence)."""
    if raw is None:
        raise InvalidEngineModeError(
            f"PARKOS_SYNC_ENGINE is unset; must be one of {sorted(m.value for m in EngineMode)}"
        )
    if raw in _WITHDRAWN_VALUES:
        raise InvalidEngineModeError(
            f"PARKOS_SYNC_ENGINE={raw!r} was withdrawn by the ADR-001 amendment "
            "(D22, 2026-09-08); it must not be used. Valid values: "
            f"{sorted(m.value for m in EngineMode)}"
        )
    try:
        # Enum value lookup is exact-match by construction — no startswith.
        return EngineMode(raw)
    except ValueError as e:
        raise InvalidEngineModeError(
            f"PARKOS_SYNC_ENGINE={raw!r} is not a recognized value; expected exactly "
            f"one of {sorted(m.value for m in EngineMode)}"
        ) from e


def get_engine() -> EngineMode:
    """Return the current :class:`EngineMode`, parsing+validating on first read.

    Cached for :data:`_CACHE_TTL_SECONDS` (60 s); callers in a long-running
    worker loop naturally pick up a stage transition within one TTL window
    without a restart.

    Raises:
        InvalidEngineModeError: unset, withdrawn, or unrecognized value.
    """
    global _cached
    now = time.monotonic()
    if _cached is not None and (now - _cached[1]) < _CACHE_TTL_SECONDS:
        return _cached[0]

    mode = _parse(os.environ.get("PARKOS_SYNC_ENGINE"))
    _cached = (mode, now)
    return mode


def _reset_cache_for_tests() -> None:
    """Test-only escape hatch: clear the cache so a test can force a fresh env read.

    Production code never calls this — the 60s TTL is the only cache
    invalidation path outside tests.
    """
    global _cached
    _cached = None


__all__ = [
    "EngineMode",
    "InvalidEngineModeError",
    "get_engine",
]
