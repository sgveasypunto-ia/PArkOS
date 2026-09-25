"""test_sync_queue_exhaustion.py — CU-07 BR3, Track 3.

Repo-level tests for the SLA-exhaustion sweep:
``repo.sync_queue.mark_exhausted`` (terminal ``fallido``) and
``repo.sync_queue.list_exhausted`` (pending rows past the 24h
queue-lifetime cap or with intentos >= len(BACKOFF_SCHEDULE)).

Exercised against a REAL Postgres container (same rule as
``test_sync_cursor_repo.py``): the ``estado`` flip + the re-select dedup
are exactly what a mock would hide.

Scenarios:

  T1 -- ``mark_failed`` re-queues (``pendiente`` + future next_retry_at).
  T2 -- ``mark_exhausted`` is terminal: ``fallido``, next_retry_at NULL,
        and ``list_pending`` never returns it again.
  T3 -- ``list_exhausted`` misses young rows (no false positives).
  T4 -- ``list_exhausted`` catches rows past ``EXHAUSTION_MAX_AGE``
        (created_at > 24h, BR3 — FIRST enqueue clock).
  T5 -- ``list_exhausted`` catches rows with intentos >= curve length.
  T6 -- exhausted rows are NOT re-selected after conversion (dedup by
        state — the same event never alerts twice).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

import pytest
from parkos_core.repo import sync_queue as sq
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _enqueue(
    pg_engine: AsyncEngine,
    *,
    tabla: str,
    intentos: int = 0,
    created_at: datetime | None = None,
) -> uuid_lib.UUID:
    """Insert one pending row with a test-controllable attempt count/age."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = await sq.enqueue(
            session,
            operacion="insert",
            tabla=tabla,
            uuid_registro=uuid_lib.uuid4(),
            datos={"test": "row"},
            uuid_sucursal=None,
        )
        # ``enqueue`` lets the DB server_default generate ``uuid``; set it
        # explicitly so the row PK is readable in-process after commit
        # (expire_on_commit=False leaves server-side defaults unloaded).
        row.uuid = uuid_lib.uuid4()
        if intentos:
            row.intentos = intentos
        if created_at is not None:
            row.created_at = created_at
        row_uuid = row.uuid
        await session.commit()
        return row_uuid


@pytest.fixture
def clean_sync_queue(pg_engine: AsyncEngine, pg_dsn: str) -> None:
    """Wipe ``sync_queue`` so each scenario starts from a known state."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE prod.sync_queue CASCADE")
        conn.commit()


@pytest.mark.asyncio
async def test_mark_failed_requeues_not_terminal(
    pg_engine: AsyncEngine, clean_sync_queue: None
) -> None:
    """T1: ``mark_failed`` keeps the row alive for the next retry."""
    row_uuid = await _enqueue(pg_engine, tabla="ingreso")
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await sq.mark_failed(session, row_uuid, "transient")
        await session.commit()
    async with Session() as session:
        stmt = select(sq.SyncQueue).where(sq.SyncQueue.uuid == row_uuid)
        row = (await session.execute(stmt)).scalar_one()
        # Backoff contract: mark_failed re-queues as ``pendiente`` with a
        # FUTURE next_retry_at (1m) — it must NOT be terminal like
        # mark_exhausted. ``list_pending`` correctly hides it mid-backoff.
        assert row.estado == "pendiente"
        assert row.next_retry_at is not None, "mark_failed schedules a retry"


@pytest.mark.asyncio
async def test_mark_exhausted_is_terminal_and_not_picked_again(
    pg_engine: AsyncEngine, clean_sync_queue: None
) -> None:
    """T2: ``mark_exhausted`` → ``fallido``, no next_retry_at, never re-picked."""
    row_uuid = await _enqueue(pg_engine, tabla="ingreso")
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await sq.mark_exhausted(session, row_uuid, "sla exceeded")
        await session.commit()
    async with Session() as session:
        stmt = select(sq.SyncQueue).where(sq.SyncQueue.uuid == row_uuid)
        row = (await session.execute(stmt)).scalar_one()
        assert row.estado == "fallido"
        assert row.next_retry_at is None
        assert row.ultimo_error == "sla exceeded"
        rows = await sq.list_pending(session)
        assert rows == [], "a terminal row must never be re-selected"


@pytest.mark.asyncio
async def test_list_exhausted_misses_young_rows(
    pg_engine: AsyncEngine, clean_sync_queue: None
) -> None:
    """T3: a fresh pending row is not exhausted (no false positives)."""
    await _enqueue(pg_engine, tabla="ingreso")
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        found = await sq.list_exhausted(session)
    assert found == []


@pytest.mark.asyncio
async def test_list_exhausted_catches_rows_older_than_max_age(
    pg_engine: AsyncEngine, clean_sync_queue: None
) -> None:
    """T4: BR3 — a row pending > 24h since FIRST enqueue is exhausted."""
    old = _now() - sq.EXHAUSTION_MAX_AGE - timedelta(minutes=1)
    row_uuid = await _enqueue(pg_engine, tabla="ingreso", created_at=old)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        found = await sq.list_exhausted(session)
    assert [r.uuid for r in found] == [row_uuid]


@pytest.mark.asyncio
async def test_list_exhausted_catches_rows_past_backoff_curve(
    pg_engine: AsyncEngine, clean_sync_queue: None
) -> None:
    """T5: intentos at the curve length is terminal, regardless of age."""
    curve_len = len(sq.BACKOFF_SCHEDULE)
    row_uuid = await _enqueue(pg_engine, tabla="ingreso", intentos=curve_len)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        found = await sq.list_exhausted(session)
    assert [r.uuid for r in found] == [row_uuid]


@pytest.mark.asyncio
async def test_exhausted_rows_are_not_reselected_after_conversion(
    pg_engine: AsyncEngine, clean_sync_queue: None
) -> None:
    """T6: dedup by state — conversion removes the row from the sweep.

    The worker's dedup guarantee: the SAME event never raises a second
    alert because after ``mark_exhausted`` the row leaves
    ``estado='pendiente'`` and the next ``list_exhausted`` can't match it.
    """
    old = _now() - sq.EXHAUSTION_MAX_AGE - timedelta(minutes=1)
    row_uuid = await _enqueue(pg_engine, tabla="ingreso", created_at=old)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        first = await sq.list_exhausted(session)
        assert [r.uuid for r in first] == [row_uuid]
        await sq.mark_exhausted(session, row_uuid, "sla exceeded")
        await session.commit()
    async with Session() as session:
        second = await sq.list_exhausted(session)
    assert second == [], "converted rows must drop out of the next sweep"