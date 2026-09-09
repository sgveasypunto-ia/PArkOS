"""sync/cutover/dual_protocol.py — ``/sync/hello`` response builder
(T-PR11-003, REQ-CUT-003, REQ-CUT-004, D11).

The dual-protocol handshake is the mechanism that lets a branch decide,
on every ``/sync/hello`` call, whether to run the legacy applier or the
catalog-driven ``SyncMotor`` applier — WITHOUT requiring every branch to
upgrade in lockstep with the cloud (D11's whole point). This module builds
the response body; the actual endpoint
(``parkos_core.api.v1.sync_router::sync_hello``) is a thin wrapper around
:func:`build_sync_hello_response`.

Branch-side consumption (auto-detect table, REQ-CUT-005) is PR12's
``jobs/sync_sucursal.py`` wiring (T-PR12-007) — this module only ships the
cloud-side response builder + the shared constants PR12 will consume
(``BRANCH_CACHE_TTL_SECONDS``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ...runtime import engine_flag

#: REQ-CUT-004: the branch MUST cache the ``/sync/hello`` response for this
#: many seconds to avoid hammering the cloud (PR12 consumes this constant).
BRANCH_CACHE_TTL_SECONDS = 300

#: REQ-CUT-003 / R-D6: 14 calendar days of dual-protocol grace once the
#: cloud reaches stage 3 (``PARKOS_SYNC_ENGINE=catalog``).
GRACE_PERIOD_DAYS = 14

#: REQ-CUT-005: the minimum branch semver allowed to use the catalog
#: applier; a branch below this stays on the legacy applier + logs
#: ``WARN catalog_too_new``.
DEFAULT_MIN_BRANCH_VERSION = "1.5.0"

#: Engine modes from which the BRANCH-facing protocol is "catalog".
#: ``catalog_admin``/``catalog_dian`` are cloud-internal staging (stages
#: 1-2, REQ-CUT-006) that do not yet change what a branch should do — only
#: stage 3 (``catalog``) and stage 4 (``catalog_branch``) flip the
#: branch-facing protocol advertised here.
_CATALOG_PROTOCOL_ENGINE_MODES: frozenset[engine_flag.EngineMode] = frozenset(
    {engine_flag.EngineMode.CATALOG, engine_flag.EngineMode.CATALOG_BRANCH}
)


@dataclass(frozen=True)
class SyncHelloResponse:
    """The ``/sync/hello`` response body (REQ-CUT-004's exact shape).

    ``grace_until`` is ``None`` iff ``protocol_version == "legacy"`` — a
    branch still on the legacy protocol has no grace-period clock running
    against it yet.
    """

    protocol_version: str  # "legacy" | "catalog"
    min_branch_version: str
    grace_until: str | None  # ISO-8601, tz-aware
    catalog_revision: str


def _catalog_revision() -> str:
    """Git SHA of the catalog at deploy time (REQ-CUT-004).

    Deploy-time injected via ``PARKOS_CATALOG_REVISION`` — wiring this into
    a real CI/deploy pipeline is explicitly out of scope here (mirrors
    T-PR11-004's identical "actual CI wiring is a deploy-pipeline concern"
    carve-out for ``check_drain.py``). ``"unknown"`` when unset (e.g. local
    dev without the env var set).
    """
    return os.environ.get("PARKOS_CATALOG_REVISION", "unknown")


def build_sync_hello_response(
    *,
    engine: engine_flag.EngineMode | None = None,
    min_branch_version: str = DEFAULT_MIN_BRANCH_VERSION,
    now: datetime | None = None,
) -> SyncHelloResponse:
    """Build the ``/sync/hello`` response body (REQ-CUT-003, REQ-CUT-004).

    Args:
        engine: Override the current ``PARKOS_SYNC_ENGINE`` reading
            (tests); defaults to ``engine_flag.get_engine()``.
        min_branch_version: Override the advertised minimum branch semver.
        now: Override "current time" for a deterministic ``grace_until``
            (tests); defaults to ``datetime.now(UTC)``.
    """
    mode = engine if engine is not None else engine_flag.get_engine()
    protocol_version = "catalog" if mode in _CATALOG_PROTOCOL_ENGINE_MODES else "legacy"

    grace_until: str | None = None
    if protocol_version == "catalog":
        current = now if now is not None else datetime.now(UTC)
        grace_until = (current + timedelta(days=GRACE_PERIOD_DAYS)).isoformat()

    return SyncHelloResponse(
        protocol_version=protocol_version,
        min_branch_version=min_branch_version,
        grace_until=grace_until,
        catalog_revision=_catalog_revision(),
    )


__all__ = [
    "BRANCH_CACHE_TTL_SECONDS",
    "DEFAULT_MIN_BRANCH_VERSION",
    "GRACE_PERIOD_DAYS",
    "SyncHelloResponse",
    "build_sync_hello_response",
]
