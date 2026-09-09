"""Auto-discovery of active branches from the local DB (T-PR9-05).

The cloud-side ``job_sync_cloud`` worker needs the list of branches that
are currently active so it can drive the catalog-driven apply loop and
walk each branch's hash chain. This module is the canonical source of
that list.

The query (per design §21.5 + tasks.md T-PR9-05):

    SELECT s.* FROM prod.sucursal s
    WHERE s.uuid IN (
        SELECT DISTINCT uuid_sucursal FROM prod.sync_log
        WHERE timestamp_evento > NOW() - INTERVAL '7 days'
        UNION
        SELECT DISTINCT uuid_sucursal FROM prod.pairing_tokens
        WHERE used = true AND used_at > NOW() - INTERVAL '30 days'
    )

A branch is "active" when it has either recent sync activity (last 7
days — heartbeat) OR a recent successful pairing (last 30 days). The
two windows are different because heartbeat is cheap to emit and proves
the branch is alive, while pairing only happens once at bootstrap and is
a much weaker long-term signal.

External registry (PARKOS_REGISTRY_URL): the spec allows an external
HTTP registry as an alternative source of truth. That integration is
out-of-PR9b scope (deferred per tasks.md T-PR9-05); this module ships
DB-only.

Caching: the discoverable branch set changes slowly (a new branch comes
online or goes offline at most a few times per day). The
:class:`BranchCache` keeps the result in memory for
``PARKOS_SYNC_VERIFY_INTERVAL_S / 12`` seconds (default 5 minutes per
the spec) so the worker's per-cycle query is a cheap dict lookup
instead of a round-trip to the DB.

Why per-row sequence goes on the branch (not here): the per-row ``seq``
that :class:`~parkos_core.sync.conflict_resolver.ConflictResolver`
validates lives on the destination [V] tables, not on the branch
master. This module only knows which branches exist + their endpoint
URLs; the seq lookup is owned by the conflict resolver and the
worker that wires its concrete overrides (PR9c scope).

Cites §21.5 (Auto-discovery), T-PR9-05, AGENTS.md §1 (audit columns on
every row — ``sucursal`` [V] row carries ``created_at`` + ``vigente_*
`` for bi-temporal versioning; the discovery query joins on ``uuid``,
NOT on ``vigente_hasta``, so we always see the LATEST version of the
branch master).
"""
from __future__ import annotations

import datetime as dt
import uuid as uuid_lib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.pairing_tokens import PairingToken
from ..models.A.sync_log import SyncLog
from ..models.V.sucursal import Sucursal


@dataclass(frozen=True)
class BranchEndpoint:
    """One active branch, as seen by the cloud-side worker.

    Attributes:
        uuid_sucursal: Branch PK.
        nombre: Latest branch name from ``prod.sucursal.nombre`` (best-effort;
            a closed branch keeps its name on the closed version per bi-temporal).
        endpoint_url: Branch API base URL. Sourced from the cloud-side
            pairing row's ``used_by_branch_info->>'endpoint_url'`` so we
            never have to query the branch to ask for its URL. Empty string
            when the branch has no used pairing row (degraded state — the
            worker logs and skips).
        last_heartbeat_at: Most recent ``sync_log.timestamp_evento`` for
            this branch. ``None`` when the branch is known only via a
            pairing row (no heartbeat yet).
    """

    uuid_sucursal: uuid_lib.UUID
    nombre: str
    endpoint_url: str
    last_heartbeat_at: dt.datetime | None


def _utcnow_naive() -> dt.datetime:
    """Naive UTC ``NOW()`` matching the schema's ``DateTime(timezone=False)``."""
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


async def discover_active_branches(
    session: AsyncSession,
    *,
    min_heartbeat_age_days: int = 7,
    min_pairing_age_days: int = 30,
) -> list[BranchEndpoint]:
    """Return branches with recent sync activity or recent successful pairing.

    The query is two ``SELECT DISTINCT uuid_sucursal`` statements UNIONed
    together and joined against ``prod.sucursal`` for the human-readable
    name. Endpoints come from the most-recent used ``pairing_tokens`` row
    per branch (``used_by_branch_info->>'endpoint_url'``).

    Args:
        session: Active ``AsyncSession`` (caller commits).
        min_heartbeat_age_days: Window for the ``sync_log`` heartbeat filter.
            Default 7 per spec.
        min_pairing_age_days: Window for the ``pairing_tokens`` filter.
            Default 30 per spec.

    Returns:
        Deduplicated list of :class:`BranchEndpoint` ordered by
        ``uuid_sucursal`` (deterministic for cache-diffing).
    """
    now = _utcnow_naive()
    threshold_heartbeat = now - dt.timedelta(days=min_heartbeat_age_days)
    threshold_pairing = now - dt.timedelta(days=min_pairing_age_days)

    # 1. UUIDs from recent sync_log activity.
    sync_uuids_stmt = (
        select(SyncLog.uuid_sucursal)
        .where(SyncLog.timestamp_evento.is_not(None))
        .where(SyncLog.timestamp_evento >= threshold_heartbeat)
        .distinct()
    )

    # 2. UUIDs from recent successful pairing. ``used=True`` is the
    #    ``prod.pairing_tokens.used`` boolean (set when a branch first
    #    pairs); ``used_at`` carries the timestamp.
    pair_uuids_stmt = (
        select(PairingToken.uuid_sucursal)
        .where(PairingToken.used.is_(True))
        .where(PairingToken.used_at.is_not(None))
        .where(PairingToken.used_at >= threshold_pairing)
        .distinct()
    )

    # 3. UNION the two UUID streams. SQLAlchemy 2.0 ``select(...).union(...)``
    #    returns a ``CompoundSelect`` we can wrap as a subquery for the
    #    downstream join against ``prod.sucursal``.
    uuid_union = sync_uuids_stmt.union(pair_uuids_stmt).subquery()

    stmt = (
        select(
            Sucursal.uuid,
            Sucursal.nombre,
        )
        .select_from(Sucursal)
        .join(uuid_union, uuid_union.c.uuid_sucursal == Sucursal.uuid)
        .order_by(Sucursal.uuid)
    )
    result = await session.execute(stmt)
    rows = result.all()

    # 4. For each UUID, fetch the latest used pairing_tokens row's
    #    ``used_by_branch_info->>'endpoint_url'``. One SELECT per branch is
    #    fine — discover_active_branches runs at most every 5 min.
    endpoints: list[BranchEndpoint] = []
    for row in rows:
        uuid_sucursal = row.uuid
        nombre = row.nombre or ""

        pair_stmt = (
            select(
                PairingToken.used_by_branch_info,
                PairingToken.used_at,
            )
            .where(PairingToken.uuid_sucursal == uuid_sucursal)
            .where(PairingToken.used.is_(True))
            .order_by(PairingToken.used_at.desc())
            .limit(1)
        )
        pair_row = (await session.execute(pair_stmt)).first()
        endpoint_url = ""
        if pair_row is not None and pair_row.used_by_branch_info:
            endpoint_url = str(pair_row.used_by_branch_info.get("endpoint_url", "") or "")

        # 5. Most recent heartbeat — subquery keeps it to one row.
        hb_stmt = (
            select(SyncLog.timestamp_evento)
            .where(SyncLog.uuid_sucursal == uuid_sucursal)
            .where(SyncLog.timestamp_evento.is_not(None))
            .order_by(SyncLog.timestamp_evento.desc())
            .limit(1)
        )
        hb_row = (await session.execute(hb_stmt)).first()
        last_heartbeat_at = hb_row.timestamp_evento if hb_row is not None else None

        endpoints.append(
            BranchEndpoint(
                uuid_sucursal=uuid_sucursal,
                nombre=nombre,
                endpoint_url=endpoint_url,
                last_heartbeat_at=last_heartbeat_at,
            )
        )

    return endpoints


# Re-export the UUID alias so callers that already imported
# ``UUID as PG_UUID`` from sqlalchemy.dialects.postgresql don't get a
# surprise. (The module imports it for type clarity in the
# discovery statement; keeping the symbol here means the typechecker
# stays happy even if the import is later removed.)
_ = PG_UUID  # type: ignore[misc]


class BranchCache:
    """In-memory TTL cache for branch discovery.

    The cloud worker calls :meth:`get` once per cycle; if the cached
    result is older than ``ttl_seconds`` (default 300s = 5 min, per
    spec), a fresh ``discover_active_branches`` runs.

    Thread safety: ``get`` mutates ``_cached_at`` + ``_cache`` from the
    asyncio loop's single thread; under CPython's GIL a concurrent
    in-flight ``get`` may both decide to refresh — the second one wins,
    which is fine (same query, same result).
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be >= 1")
        self.ttl_seconds = ttl_seconds
        self._cached_at: dt.datetime | None = None
        self._cache: list[BranchEndpoint] = []

    @property
    def cached_at(self) -> dt.datetime | None:
        """Naive UTC timestamp of the last successful refresh, or ``None``."""
        return self._cached_at

    def invalidate(self) -> None:
        """Force the next :meth:`get` to refresh.

        Useful when the operator just paired a new branch and wants the
        worker to discover it on the next cycle without waiting for the
        TTL to expire.
        """
        self._cached_at = None
        self._cache = []

    async def get(
        self,
        session: AsyncSession,
        *,
        min_heartbeat_age_days: int = 7,
        min_pairing_age_days: int = 30,
    ) -> list[BranchEndpoint]:
        """Return the cached result if fresh; else refresh + return.

        Args:
            session: Active ``AsyncSession`` (caller commits).
            min_heartbeat_age_days: Passed through to
                :func:`discover_active_branches`.
            min_pairing_age_days: Same.
        """
        now = _utcnow_naive()
        if self._cached_at is None or (now - self._cached_at).total_seconds() > self.ttl_seconds:
            self._cache = await discover_active_branches(
                session,
                min_heartbeat_age_days=min_heartbeat_age_days,
                min_pairing_age_days=min_pairing_age_days,
            )
            self._cached_at = now
        return list(self._cache)


__all__ = [
    "BranchCache",
    "BranchEndpoint",
    "discover_active_branches",
]
