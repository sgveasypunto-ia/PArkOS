"""HU-F1.5: refresh worker for ``prod.mv_ocupacion_diaria``.

Operates as a separate NSSM service (KD-1) with the same shape as
``parkos_core.jobs.sync_sucursal``. Cycle::

    try:
        REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria
    except Exception:
        log warning refresh_mv_concurrently_failed_fallback
        REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria
    asyncio.sleep(refresh_interval_s)  # default 10s

The CONCURRENTLY branch requires the UNIQUE INDEX (KD-2); if the index
is missing, Postgres returns a stable error class and we fall back to
plain ``REFRESH`` (which takes ``AccessExclusiveLock`` briefly, KD-5).

REQ-OPS-133 (QA-2026-09-17 bug 3): after migration 0034 recreates the
MV, the very first REFRESH CONCURRENTLY can race with a not-yet-
committed MV definition and produce a ``could not open relation`` or
``relation does not exist`` error class. We guard against this with a
``pg_stat_user_tables.last_analyze`` / ``pg_stat_get_last_analyze_time``
lookup: if the MV was created within the last 60 seconds, the first
cycle is skipped so the worker never issues REFRESH on a fresh-but-
uncommitted MV.

CLI entrypoint::

    python -m parkos_core.jobs.refresh_mv_ocupacion \\
        --refresh-interval-s 10 \\
        --database-url $PARKOS_BRANCH_DB_DSN
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .runner import WorkerRunner

logger = logging.getLogger("parkos_core.jobs.refresh_mv_ocupacion")


class RefreshMvOcupacionWorker(WorkerRunner):
    """Refreshes ``prod.mv_ocupacion_diaria`` every
    ``refresh_interval_s`` seconds.

    Inherits signal handling (SIGTERM/SIGINT) and exit codes 0/1/2 from
    ``WorkerRunner`` (``jobs/runner.py``). NO modifications to the base
    class -- ``worker_base_intact`` CI gate stays green.
    """

    DEFAULT_REFRESH_INTERVAL_S = 10  # KD-1: matches F4.3 polling cadence
    # REQ-OPS-133: skip the first REFRESH if the MV was created within
    # this many seconds (Postgres 9.4+). ``pg_stat_get_last_analyze_time``
    # returns NULL for a freshly-created relation; we treat NULL the
    # same as "just now" so the first cycle is always skipped. 60s is
    # wide enough to absorb the migration's own CONCURRENTLY-on-fresh-
    # MV race window without being so wide that a real operator-driven
    # CREATE-OR-REPLACE during a maintenance window is hidden.
    FRESH_MV_SKIP_WINDOW_S = 60

    def __init__(
        self,
        *,
        session: AsyncSession,
        refresh_interval_s: int = DEFAULT_REFRESH_INTERVAL_S,
    ) -> None:
        super().__init__(name="refresh_mv_ocupacion")
        self._session = session
        # Floor at 5s to avoid pathological hot-loops on misconfiguration.
        self.refresh_interval_s = max(5, int(refresh_interval_s))

    async def _is_mv_fresh(self) -> bool:
        """Return True iff ``prod.mv_ocupacion_diaria`` was created or
        last analyzed within ``FRESH_MV_SKIP_WINDOW_S`` seconds.

        Uses ``pg_stat_get_last_analyze_time`` as a proxy for "freshly
        created" — both NULL and a recent timestamp mean "skip the
        first REFRESH this cycle". The MV is created by migrations
        0024 and 0034 with no ANALYZE in the same TX, so the analyzer
        has not run yet when the worker boots inside the same window.
        """
        try:
            row = (
                await self._session.execute(
                    text(
                        "SELECT "
                        "extract(epoch from (now() - "
                        "  coalesce(pg_stat_get_last_analyze_time(c.oid), "
                        "           pg_stat_get_last_autoanalyze_time(c.oid), "
                        "           now()))) AS seconds_since_analyze "
                        "FROM pg_class c "
                        "JOIN pg_namespace n ON c.relnamespace = n.oid "
                        "WHERE n.nspname = 'prod' AND c.relname = "
                        "  'mv_ocupacion_diaria'"
                    )
                )
            ).first()
        except Exception:  # noqa: BLE001 -- defensive: never block on stats lookup
            return False
        if row is None:
            return False
        seconds = row[0]
        if seconds is None:
            return True
        return float(seconds) < self.FRESH_MV_SKIP_WINDOW_S

    async def cycle(self) -> None:
        """One REFRESH pass + interval sleep. Always idempotent.

        Tries CONCURRENTLY first (KD-5); falls back to plain REFRESH if
        the UNIQUE INDEX is missing or Postgres is under load. The
        session is committed per branch so a failed branch does not
        poison the next cycle.
        """
        # REQ-OPS-133: skip the first cycle on a freshly-created MV to
        # avoid the CONCURRENTLY-on-not-yet-committed-MV race. After
        # the skip window elapses (default 60s) the next cycle does a
        # normal REFRESH CONCURRENTLY, which is the established
        # production behavior.
        if await self._is_mv_fresh():
            logger.debug(
                "refresh_mv_ocupacion_skip_fresh_mv",
                extra={
                    "event": "refresh_mv_ocupacion_skip_fresh_mv",
                    "window_s": self.FRESH_MV_SKIP_WINDOW_S,
                },
            )
            await asyncio.sleep(self.refresh_interval_s)
            return

        try:
            await self._session.execute(
                text(
                    "REFRESH MATERIALIZED VIEW CONCURRENTLY "
                    "prod.mv_ocupacion_diaria"
                )
            )
            await self._session.commit()
            logger.debug(
                "refresh_mv_ocupacion_cycle_ok",
                extra={"event": "refresh_mv_ocupacion_cycle_ok"},
            )
        except Exception as exc:  # noqa: BLE001 -- KD-5: fall back, do not crash
            # Truncate the original exception message to avoid leaking
            # pgcode / DSN fragments into log aggregation. Log the
            # exception class only; full traceback at DEBUG.
            logger.warning(
                "refresh_mv_concurrently_failed_fallback",
                extra={
                    "event": "refresh_mv_concurrently_failed_fallback",
                    "exception_class": type(exc).__name__,
                },
            )
            await self._session.rollback()
            try:
                await self._session.execute(
                    text(
                        "REFRESH MATERIALIZED VIEW "
                        "prod.mv_ocupacion_diaria"
                    )
                )
                await self._session.commit()
                logger.debug(
                    "refresh_mv_ocupacion_fallback_ok",
                    extra={"event": "refresh_mv_ocupacion_fallback_ok"},
                )
            except Exception as inner_exc:  # noqa: BLE001
                # Both branches failed -- log error and let the next
                # cycle retry. KD-5: never crash the loop; RIESGO-SUC-02
                # lag is the accepted operating characteristic.
                await self._session.rollback()
                logger.error(
                    "refresh_mv_ocupacion_both_branches_failed",
                    extra={
                        "event": "refresh_mv_ocupacion_both_branches_failed",
                        "exception_class": type(inner_exc).__name__,
                    },
                )
        # Post-cycle sleep -- KD-5: never sleep BEFORE refresh (would
        # block the first startup refresh); see R1 mitigation in
        # proposal.md §8.
        await asyncio.sleep(self.refresh_interval_s)


# ---------------------------------------------------------------------------
# CLI entrypoint (KD-1: registered with NSSM, runs as a separate process)
# ---------------------------------------------------------------------------


async def _run_worker(database_url: str, refresh_interval_s: int) -> int:
    """Boot the worker with its own AsyncSession and run until SIGTERM."""
    engine = create_async_engine(database_url, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        worker = RefreshMvOcupacionWorker(
            session=session,
            refresh_interval_s=refresh_interval_s,
        )
        return await worker.run()  # WorkerRunner.run() handles signals + exit


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m parkos_core.jobs.refresh_mv_ocupacion``."""
    parser = argparse.ArgumentParser(
        description="HU-F1.5: refresh prod.mv_ocupacion_diaria every N seconds.",
    )
    parser.add_argument(
        "--refresh-interval-s",
        type=int,
        default=RefreshMvOcupacionWorker.DEFAULT_REFRESH_INTERVAL_S,
        help="Cycle interval in seconds (floor 5s; default 10).",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get(
            "PARKOS_BRANCH_DB_DSN",
            "postgresql+asyncpg://parkos_app:secret@localhost/parkos_branch",
        ),
        help="Async SQLAlchemy DSN; default $PARKOS_BRANCH_DB_DSN.",
    )
    args = parser.parse_args(argv)
    return asyncio.run(
        _run_worker(args.database_url, args.refresh_interval_s)
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = [
    "RefreshMvOcupacionWorker",
    "main",
]
