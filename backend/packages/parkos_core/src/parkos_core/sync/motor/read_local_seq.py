"""motor/read_local_seq.py — ``ReadLocalSeq`` seq-lookup dispatcher (T-PR7-001/002, D4).

REQ-MOT-009 (``specs/sync-motor.md``), design.md §2 Issue #4: replaces the
permanent ``None``-returning stub at
``conflict_resolver.py::_read_local_seq`` (T-PR7-004 removes it). Dispatches
``spec.seq_strategy`` to one of four concrete lookups:

| ``seq_strategy`` | Query | Cache |
|---|---|---|
| ``seq_via_datos`` | ``SELECT MAX((datos->>'seq')::bigint) FROM prod.sync_queue WHERE tabla = :name AND uuid_registro = :row_uuid AND uuid_sucursal IS NOT DISTINCT FROM :branch_uuid`` | 5s TTL |
| ``max_timestamp_evento`` | ``SELECT MAX(timestamp_evento) FROM {table} WHERE uuid = :row_uuid`` | none |
| ``max_created_at`` | ``SELECT MAX(created_at) FROM {table} WHERE uuid = :row_uuid`` | none |
| ``none`` | Returns ``None`` immediately | n/a |

Only ``seq_via_datos`` caches — it is the one strategy that reads
``prod.sync_queue`` (a hot, append-heavy table shared by every branch); the
two time-based strategies read an index-backed column directly on the
destination table (design.md's "Load profile": "fast index hit", "0s (no
cache)"), so caching them would only risk staleness with no throughput
benefit. ``none`` short-circuits before any DB access — used by
``validacion_evento`` (the sole ``never_propagated`` entry) and by
``LocalOnlyCatalog`` entries.

A conflict detected earlier in the same batch for the same
``(tabla, uuid_registro)`` key invalidates any cached ``seq_via_datos``
value for that key — the caller passes ``force_refresh=True`` in that case
(design.md Issue #4's "Bypass condition" column); the class does not track
in-batch conflicts itself, since it has no notion of "batch" at all.

Instance-scoped cache (not a module global): a single :class:`ReadLocalSeq`
instance is expected to live for the lifetime of one worker/motor instance
so its cache is actually useful across calls (see
``motor/sync_motor.py::SyncMotor.__init__``); tests construct a fresh
instance per case so no state leaks between them.
"""
from __future__ import annotations

import time
import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import BigInteger, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.A.sync_queue import SyncQueue
from ..catalog.schema import SyncCatalogEntry

# 5s TTL for ``seq_via_datos`` only (design.md §2 Issue #4).
DEFAULT_CACHE_TTL_SECONDS: float = 5.0

_CacheKey = tuple[str, uuid_lib.UUID, uuid_lib.UUID | None]
_CacheEntry = tuple["int | None", float]


class ReadLocalSeqError(ValueError):
    """Raised for a catalog entry with an unknown/unset ``seq_strategy``."""


class ReadLocalSeq:
    """Dispatches ``spec.seq_strategy`` to the concrete local-seq lookup (D4).

    ``hits``/``misses`` count only ``seq_via_datos`` calls (the one cached
    strategy) — design.md §2 Issue #4's "cache hit rate >= 95%" acceptance
    criterion (T-PR7-007) is otherwise unmeasurable from outside the class.
    """

    def __init__(self, *, cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS) -> None:
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[_CacheKey, _CacheEntry] = {}
        self.hits = 0
        self.misses = 0

    async def __call__(
        self,
        session: AsyncSession,
        spec: SyncCatalogEntry,
        uuid_registro: uuid_lib.UUID,
        *,
        branch_uuid: uuid_lib.UUID | None = None,
        force_refresh: bool = False,
    ) -> int | datetime | None:
        """Return the highest locally-known seq for ``(spec.name, uuid_registro)``.

        Return type varies by strategy: ``int | None`` for ``seq_via_datos``,
        ``datetime | None`` for the two time-based strategies, always
        ``None`` for ``none`` — callers compare like-for-like against the
        remote payload's own value for the same strategy (REQ-MOT-009).
        """
        strategy = spec.seq_strategy
        if strategy is None or strategy == "none":
            return None
        if strategy == "seq_via_datos":
            return await self._read_seq_via_datos(
                spec.name, uuid_registro, branch_uuid, session, force_refresh=force_refresh
            )
        if strategy == "max_timestamp_evento":
            return await self._read_column_max(session, spec, uuid_registro, "timestamp_evento")
        if strategy == "max_created_at":
            return await self._read_column_max(session, spec, uuid_registro, "created_at")
        raise ReadLocalSeqError(f"{spec.name}: unknown seq_strategy {strategy!r}")

    async def _read_seq_via_datos(
        self,
        tabla: str,
        uuid_registro: uuid_lib.UUID,
        branch_uuid: uuid_lib.UUID | None,
        session: AsyncSession,
        *,
        force_refresh: bool,
    ) -> int | None:
        key: _CacheKey = (tabla, uuid_registro, branch_uuid)
        now = time.monotonic()
        if not force_refresh:
            cached = self._cache.get(key)
            if cached is not None and (now - cached[1]) < self._cache_ttl_seconds:
                self.hits += 1
                return cached[0]

        self.misses += 1
        stmt = select(func.max(cast(SyncQueue.datos["seq"].astext, BigInteger))).where(
            SyncQueue.tabla == tabla,
            SyncQueue.uuid_registro == uuid_registro,
            SyncQueue.uuid_sucursal.is_not_distinct_from(branch_uuid),
            # Bug found and fixed here (T-PR7-003): neither design.md §2
            # Issue #4 nor specs/sync-motor.md REQ-MOT-009 include this
            # filter in their literal SQL, but ix_sync_queue_seq_lookup
            # (migration 0011) is a PARTIAL index restricted to exactly
            # this predicate — Postgres can only use a partial index when
            # the query WHERE clause provably implies the index predicate,
            # so omitting this filter would silently defeat the index
            # entirely (full scan every call). It is also the semantically
            # correct scope regardless: a 'fallido' row is superseded by a
            # fresh 'pendiente' re-enqueue (repo/sync_queue.py::mark_failed),
            # never the canonical seq source.
            SyncQueue.estado.in_(("exitoso", "pendiente")),
        )
        value = (await session.execute(stmt)).scalar_one_or_none()
        self._cache[key] = (value, now)
        return value

    async def _read_column_max(
        self,
        session: AsyncSession,
        spec: SyncCatalogEntry,
        uuid_registro: uuid_lib.UUID,
        column_name: str,
    ) -> datetime | None:
        model_cls = spec.model_cls
        column = getattr(model_cls, column_name)
        stmt = select(func.max(column)).where(model_cls.uuid == uuid_registro)  # type: ignore[attr-defined]
        return (await session.execute(stmt)).scalar_one_or_none()

    def clear_cache(self) -> None:
        """Test/ops escape hatch — drop every cached entry immediately."""
        self._cache.clear()


__all__ = ["DEFAULT_CACHE_TTL_SECONDS", "ReadLocalSeq", "ReadLocalSeqError"]
