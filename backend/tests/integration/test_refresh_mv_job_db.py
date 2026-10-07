"""JB1: el job de refresco ejecuta su SQL REAL contra Postgres.

Los tests de ``test_refresh_mv_job.py`` mockean la sesion, por eso un
parentesis sin cerrar en ``_is_mv_fresh`` (syntax error near "AS") llego al
stack: el job fallaba en cada ciclo y la MV nunca se refrescaba. Aqui se
ejecutan ``_is_mv_fresh`` y ``cycle`` completos contra la DB de testcontainers.
"""
from __future__ import annotations

import asyncio
import logging

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

import parkos_core.jobs.refresh_mv_ocupacion as mod
from parkos_core.jobs.refresh_mv_ocupacion import RefreshMvOcupacionWorker

_HELPER = "SELECT prod.refresh_mv_ocupacion_diaria()"


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    captured: list[float] = []

    async def _fake(seconds: float) -> None:
        captured.append(float(seconds))

    monkeypatch.setattr(mod.asyncio, "sleep", _fake)
    return captured


class _HelperCalls:
    """Proxy de sesion: cuenta las llamadas al helper y puede hacer que la
    primera falle con un error REAL de Postgres (aborta la transaccion)."""

    def __init__(self, session, *, fail_first_helper: bool = False) -> None:
        self._s = session
        self.helper_calls = 0
        self._fail = fail_first_helper

    async def execute(self, stmt, *a, **kw):
        if str(stmt) == _HELPER:
            self.helper_calls += 1
            if self._fail:
                self._fail = False
                return await self._s.execute(text("SELECT 1/0"))
        return await self._s.execute(stmt, *a, **kw)

    def __getattr__(self, name):
        return getattr(self._s, name)


async def _set_analyzed(pg_engine, *, analyzed: bool) -> None:
    """Deja la MV sin analizar (None) o recien analizada."""
    async with pg_engine.connect() as conn:
        if analyzed:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(text("ANALYZE prod.mv_ocupacion_diaria"))


async def test_is_mv_fresh_real_sql_executes_without_syntax_error(
    pg_engine, alembic_upgrade
) -> None:
    """El SQL real no puede fallar: antes lanzaba ``syntax error at or near AS``."""
    async with async_sessionmaker(pg_engine)() as session:
        worker = RefreshMvOcupacionWorker(session=session)
        result = await worker._is_mv_fresh()
        # Si el SQL fallara, la transaccion queda abortada y esto lanza.
        await session.execute(text("SELECT 1"))
    assert isinstance(result, bool)
    assert worker.health_report()["consecutive_failures"] == 0, worker.health_report()


async def test_is_mv_fresh_true_right_after_analyze(pg_engine, alembic_upgrade) -> None:
    await _set_analyzed(pg_engine, analyzed=True)
    fresh = False
    for _ in range(20):  # los stats de Postgres se publican con un pequeno retraso
        async with async_sessionmaker(pg_engine)() as session:
            fresh = await RefreshMvOcupacionWorker(session=session)._is_mv_fresh()
        if fresh:
            break
        await asyncio.sleep(0.25)
    assert fresh is True


async def test_cycle_skips_when_mv_is_fresh(
    pg_engine, alembic_upgrade, no_sleep
) -> None:
    async with async_sessionmaker(pg_engine)() as session:
        proxy = _HelperCalls(session)
        worker = RefreshMvOcupacionWorker(session=proxy, refresh_interval_s=10)
        worker._is_mv_fresh = _always(True)  # type: ignore[method-assign]
        await worker.cycle()
    assert proxy.helper_calls == 0
    assert no_sleep == [10.0]


async def test_cycle_refreshes_when_stale(pg_engine, alembic_upgrade, no_sleep) -> None:
    async with async_sessionmaker(pg_engine)() as session:
        proxy = _HelperCalls(session)
        worker = RefreshMvOcupacionWorker(session=proxy, refresh_interval_s=10)
        worker._is_mv_fresh = _always(False)  # type: ignore[method-assign]
        await worker.cycle()
    assert proxy.helper_calls == 1
    assert worker.health_report()["ok"] is True


async def test_cycle_real_never_analyzed_path_calls_helper(
    pg_engine, alembic_upgrade, no_sleep
) -> None:
    """Ciclo completo SIN stubs: stats reales -> el helper real se ejecuta
    (cualquier MV que no se analizo en los ultimos 60 s se refresca)."""
    async with async_sessionmaker(pg_engine)() as session:
        proxy = _HelperCalls(session)
        worker = RefreshMvOcupacionWorker(session=proxy, refresh_interval_s=10)
        fresh = await worker._is_mv_fresh()
        await worker.cycle()
    assert proxy.helper_calls == (0 if fresh else 1)


async def test_error_rolls_back_and_next_cycle_succeeds(
    pg_engine, alembic_upgrade, no_sleep, caplog: pytest.LogCaptureFixture
) -> None:
    async with async_sessionmaker(pg_engine)() as session:
        proxy = _HelperCalls(session, fail_first_helper=True)
        worker = RefreshMvOcupacionWorker(session=proxy, refresh_interval_s=10)
        worker._is_mv_fresh = _always(False)  # type: ignore[method-assign]
        with caplog.at_level(logging.ERROR, logger=mod.logger.name):
            await worker.cycle()  # falla (division by zero real) -> rollback
            failed_report = worker.health_report()
            await worker.cycle()  # sin rollback previo esto fallaria con InFailedSQLTransaction
    assert proxy.helper_calls == 2
    failed = [r for r in caplog.records if r.message == "refresh_mv_ocupacion_failed"]
    assert len(failed) == 1, [r.message for r in caplog.records]
    assert failed[0].exception_class  # type: ignore[attr-defined]
    assert "division by zero" in failed[0].error  # type: ignore[attr-defined]
    assert failed_report["consecutive_failures"] == 1
    assert worker.health_report()["ok"] is True
    assert worker.health_report()["consecutive_failures"] == 0


async def test_stats_lookup_failure_rolls_back_so_refresh_still_runs(
    pg_engine, alembic_upgrade, no_sleep
) -> None:
    """Si la consulta de stats falla se hace rollback (antes quedaba la
    transaccion abortada y el refresh siguiente fallaba)."""

    class _BadStats(_HelperCalls):
        async def execute(self, stmt, *a, **kw):
            if "pg_stat_get_last_analyze_time" in str(stmt):
                return await self._s.execute(text("SELECT 1/0"))
            return await super().execute(stmt, *a, **kw)

    async with async_sessionmaker(pg_engine)() as session:
        proxy = _BadStats(session)
        worker = RefreshMvOcupacionWorker(session=proxy, refresh_interval_s=10)
        await worker.cycle()
    assert proxy.helper_calls == 1
    assert worker.health_report()["ok"] is True


def _always(value: bool):
    async def _f() -> bool:
        return value

    return _f
