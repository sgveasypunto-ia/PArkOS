"""test_mark_failed_backoff_override.py — T-PR9-006.

``repo.sync_queue.mark_failed`` accepts an optional ``backoff_schedule``
override (design.md §2 Issue #9) — passed IN to the function, never
applied by the caller around it (R-D3 carve-out: this module stays the
ONLY place that computes ``next_retry_at`` and issues the UPDATE).
Asserts the DIAN curve is honored when passed, and the general curve is
used when omitted (default, unchanged behavior).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

import pytest
from parkos_core.dian.backoff import DIAN_BACKOFF_SCHEDULE
from parkos_core.models.A.sync_queue import SyncQueue
from parkos_core.repo import sync_queue as sq
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seed_sync_queue_row(
    pg_engine: AsyncEngine, *, uuid_sucursal: uuid_lib.UUID, intentos: int = 0
) -> uuid_lib.UUID:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = SyncQueue(
            uuid_sucursal=uuid_sucursal,
            operacion="insert",
            tabla="factura_electronica",
            uuid_registro=uuid_lib.uuid4(),
            datos={},
            prioridad=10,
            estado="pendiente",
            intentos=intentos,
            created_at=_now(),
            sync_status="pendiente",
        )
        session.add(row)
        await session.commit()
        return row.uuid


@pytest.mark.asyncio
async def test_mark_failed_uses_general_curve_when_no_override(
    pg_engine: AsyncEngine, seeded_sucursal_uuid: uuid_lib.UUID
) -> None:
    sq_uuid = await _seed_sync_queue_row(pg_engine, uuid_sucursal=seeded_sucursal_uuid)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    before = _now()
    async with Session() as session:
        await sq.mark_failed(session, sq_uuid, "boom")
        await session.commit()

    async with Session() as session:
        from sqlalchemy import select

        row = (
            await session.execute(select(SyncQueue).where(SyncQueue.uuid == sq_uuid))
        ).scalar_one()

    assert row.intentos == 1
    # General curve: attempt 0 -> 1 minute (repo.sync_queue.BACKOFF_SCHEDULE[0]).
    delta = row.next_retry_at - before
    assert sq.BACKOFF_SCHEDULE[0] <= delta < sq.BACKOFF_SCHEDULE[1]


@pytest.mark.asyncio
async def test_mark_failed_honors_dian_backoff_override(
    pg_engine: AsyncEngine, seeded_sucursal_uuid: uuid_lib.UUID
) -> None:
    sq_uuid = await _seed_sync_queue_row(pg_engine, uuid_sucursal=seeded_sucursal_uuid)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    before = _now()
    async with Session() as session:
        await sq.mark_failed(
            session, sq_uuid, "dian boom", backoff_schedule=DIAN_BACKOFF_SCHEDULE
        )
        await session.commit()

    async with Session() as session:
        from sqlalchemy import select

        row = (
            await session.execute(select(SyncQueue).where(SyncQueue.uuid == sq_uuid))
        ).scalar_one()

    assert row.intentos == 1
    # DIAN curve: attempt 0 -> 1 minute too, BUT the curve DIVERGES from
    # attempt 2 onward (15m vs 30m) — assert against the DIAN curve
    # specifically, not merely "some 1-minute-ish value".
    delta = row.next_retry_at - before
    assert DIAN_BACKOFF_SCHEDULE[0] <= delta < DIAN_BACKOFF_SCHEDULE[1]


@pytest.mark.asyncio
async def test_mark_failed_dian_curve_diverges_from_general_at_third_attempt(
    pg_engine: AsyncEngine, seeded_sucursal_uuid: uuid_lib.UUID
) -> None:
    """Attempt index 2: general curve waits 30m, DIAN curve waits 15m."""
    sq_uuid = await _seed_sync_queue_row(
        pg_engine, uuid_sucursal=seeded_sucursal_uuid, intentos=2
    )
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    before = _now()
    async with Session() as session:
        await sq.mark_failed(
            session, sq_uuid, "dian boom", backoff_schedule=DIAN_BACKOFF_SCHEDULE
        )
        await session.commit()

    async with Session() as session:
        from sqlalchemy import select

        row = (
            await session.execute(select(SyncQueue).where(SyncQueue.uuid == sq_uuid))
        ).scalar_one()

    delta = row.next_retry_at - before
    assert DIAN_BACKOFF_SCHEDULE[2] <= delta < sq.BACKOFF_SCHEDULE[2]
    assert sq.BACKOFF_SCHEDULE[2] != DIAN_BACKOFF_SCHEDULE[2]


def test_next_retry_delay_schedule_param() -> None:
    """Unit-level (no DB): ``next_retry_delay(schedule=...)`` indexes the override."""
    assert sq.next_retry_delay(0, schedule=DIAN_BACKOFF_SCHEDULE) == DIAN_BACKOFF_SCHEDULE[0]
    assert sq.next_retry_delay(2, schedule=DIAN_BACKOFF_SCHEDULE) == DIAN_BACKOFF_SCHEDULE[2]
    assert sq.next_retry_delay(99, schedule=DIAN_BACKOFF_SCHEDULE) == DIAN_BACKOFF_SCHEDULE[-1]
    # None (default) falls back to the general curve — unchanged behavior.
    assert sq.next_retry_delay(0) == sq.BACKOFF_SCHEDULE[0]
    assert sq.next_retry_delay(0, schedule=None) == sq.BACKOFF_SCHEDULE[0]
