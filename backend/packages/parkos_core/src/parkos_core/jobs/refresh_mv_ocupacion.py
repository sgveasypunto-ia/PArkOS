"""HU-F1.5: refresh worker for ``prod.mv_ocupacion_diaria``.

Operates as a separate NSSM service (KD-1) with the same shape as
``parkos_core.jobs.sync_sucursal``. Cycle::

    try:
        SELECT prod.refresh_mv_ocupacion_diaria()   # SECURITY DEFINER (0045)
    except Exception:
        rollback + log error refresh_mv_ocupacion_failed
    asyncio.sleep(refresh_interval_s)  # default 10s

The helper runs ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` as the MV owner
(requires the UNIQUE INDEX, KD-2). The worker's app role is not the owner,
so it must never issue ``REFRESH`` directly.

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
import re
import sys
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .runner import WorkerRunner

logger = logging.getLogger("parkos_core.jobs.refresh_mv_ocupacion")


_URL_CREDENTIALS = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)[^/@\s]+@", re.IGNORECASE)
_MAX_ERROR_CHARS = 300


def sanitize_error(exc: BaseException) -> str:
    """Message safe for log aggregation: URL credentials masked, truncated."""
    return _URL_CREDENTIALS.sub(r"\g<scheme>***@", str(exc))[:_MAX_ERROR_CHARS]


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
    # returns NULL for a never-analyzed relation; NULL is treated as
    # stale (refresh), only a timestamp within the window skips. 60s is
    # wide enough to absorb the migration's own CONCURRENTLY-on-fresh-
    # MV race window without being so wide that a real operator-driven
    # CREATE-OR-REPLACE during a maintenance window is hidden.
    FRESH_MV_SKIP_WINDOW_S = 60
    # ``/healthz`` turns 503 after this many consecutive failed refreshes, so
    # Docker no longer reports a job that never refreshes anything as healthy.
    FAILURE_DEGRADED_THRESHOLD = 3

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
        self._consecutive_failures = 0
        self._last_error_class: str | None = None
        self._last_error: str | None = None

    def health_report(self) -> dict[str, Any]:
        """Logical health for ``/healthz``: 503 while refreshes keep failing."""
        return {
            "ok": self._consecutive_failures < self.FAILURE_DEGRADED_THRESHOLD,
            "consecutive_failures": self._consecutive_failures,
            "degraded_threshold": self.FAILURE_DEGRADED_THRESHOLD,
            "last_error_class": self._last_error_class,
            "last_error": self._last_error,
        }

    def _note_failure(self, where: str, exc: Exception) -> None:
        self._consecutive_failures += 1
        self._last_error_class = type(exc).__name__
        self._last_error = sanitize_error(exc)
        logger.error(
            "refresh_mv_ocupacion_failed",
            extra={
                "event": "refresh_mv_ocupacion_failed",
                "stage": where,
                "exception_class": self._last_error_class,
                "error": self._last_error,
                "consecutive_failures": self._consecutive_failures,
            },
        )

    async def _is_mv_fresh(self) -> bool:
        """Return True iff ``prod.mv_ocupacion_diaria`` was created or
        last analyzed within ``FRESH_MV_SKIP_WINDOW_S`` seconds.

        Uses the analyze timestamps as a proxy for "recently touched".
        A NULL timestamp (the MV was NEVER analyzed) means "age
        unknown", which is STALE, not fresh: the previous
        ``coalesce(..., now())`` made such an MV look 0s old forever, so
        the job never refreshed an empty MV (defect D1). The refresh
        helper is a no-op when the MV is missing and raises when it is
        unpopulated (logged, retried next cycle), so refreshing is safe.
        """
        try:
            row = (
                await self._session.execute(
                    text(
                        "SELECT "
                        "extract(epoch from (now() - "
                        "  coalesce(pg_stat_get_last_analyze_time(c.oid), "
                        "           pg_stat_get_last_autoanalyze_time(c.oid)"
                        "))) AS seconds_since_analyze "
                        "FROM pg_class c "
                        "JOIN pg_namespace n ON c.relnamespace = n.oid "
                        "WHERE n.nspname = 'prod' AND c.relname = "
                        "  'mv_ocupacion_diaria'"
                    )
                )
            ).first()
        except Exception as exc:  # noqa: BLE001 -- never block on stats lookup
            # The failed statement aborted the transaction: without a rollback
            # the refresh that follows dies with InFailedSQLTransactionError.
            await self._session.rollback()
            self._note_failure("stats_lookup", exc)
            return False
        if row is None:
            return False
        seconds = row[0]
        if seconds is None:
            return False
        return float(seconds) < self.FRESH_MV_SKIP_WINDOW_S

    async def cycle(self) -> None:
        """One REFRESH pass + interval sleep. Always idempotent.

        Calls the SECURITY DEFINER helper ``prod.refresh_mv_ocupacion_diaria()``
        (migration 0045), which owns the ``REFRESH ... CONCURRENTLY``. The
        worker connects as the app role, which does NOT own the MV, so a
        direct ``REFRESH MATERIALIZED VIEW`` fails with "must be owner of
        materialized view mv_ocupacion_diaria" -- there is deliberately no
        direct-REFRESH fallback. On failure the session is rolled back and
        the next cycle retries (KD-5: never crash the loop).
        """
        # REQ-OPS-133: skip the first cycle on a freshly-created MV to
        # avoid the CONCURRENTLY-on-not-yet-committed-MV race. After
        # the skip window elapses (default 60s) the next cycle does a
        # normal refresh, which is the established production behavior.
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
                text("SELECT prod.refresh_mv_ocupacion_diaria()")
            )
            await self._session.commit()
            logger.debug(
                "refresh_mv_ocupacion_cycle_ok",
                extra={"event": "refresh_mv_ocupacion_cycle_ok"},
            )
        except Exception as exc:  # noqa: BLE001 -- KD-5: log, do not crash
            # exception class + sanitized message (credentials masked,
            # truncated); never the DSN or pgcode.
            await self._session.rollback()
            self._note_failure("refresh", exc)
        else:
            self._consecutive_failures = 0
            self._last_error_class = None
            self._last_error = None
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
