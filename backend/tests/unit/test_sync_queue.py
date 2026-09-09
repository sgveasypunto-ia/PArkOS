"""test_sync_queue.py — REQ-14-A-SYNC-FACADE + SC-13-A-SYNC-QUEUE-MARK-DISPATCHED.

Unit tests for :mod:`parkos_core.repo.sync_queue`.

Verifies:

  1. ``enqueue`` inserts with default priority (10 for inserts, 0 for
     everything else).
  2. ``mark_dispatched`` / ``mark_in_progress`` / ``mark_failed`` set
     the right column values.
  3. The exponential backoff schedule is honored:
     1m → 5m → 30m → 2h → 12h → 24h max.
  4. The column whitelist is enforced — any attempt to update a
     non-whitelisted column raises :class:`SyncQueueStateError`.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

import pytest
from parkos_core.repo.sync_queue import (
    ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS,
    BACKOFF_SCHEDULE,
    SyncQueueStateError,
    enqueue,
    list_pending,
    mark_dispatched,
    mark_failed,
    mark_in_progress,
    next_retry_delay,
)


def test_allowed_columns_constant() -> None:
    """The whitelist has exactly the five expected columns (T-PR2-000).

    ``sync_timestamp`` joined the whitelist in T-PR2-000 — without it,
    ``mark_dispatched``/``mark_in_progress`` always raised
    ``SyncQueueStateError`` because both stamp ``sync_timestamp`` on every
    call.
    """
    assert frozenset(
        {"estado", "intentos", "next_retry_at", "ultimo_error", "sync_timestamp"}
    ) == ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS


def test_backoff_schedule_shape() -> None:
    """The schedule is monotonic non-decreasing and capped at 24h."""
    assert len(BACKOFF_SCHEDULE) == 6
    assert BACKOFF_SCHEDULE[0] == timedelta(minutes=1)
    assert BACKOFF_SCHEDULE[1] == timedelta(minutes=5)
    assert BACKOFF_SCHEDULE[2] == timedelta(minutes=30)
    assert BACKOFF_SCHEDULE[3] == timedelta(hours=2)
    assert BACKOFF_SCHEDULE[4] == timedelta(hours=12)
    assert BACKOFF_SCHEDULE[5] == timedelta(hours=24)
    # Monotonic non-decreasing.
    for i in range(1, len(BACKOFF_SCHEDULE)):
        assert BACKOFF_SCHEDULE[i] >= BACKOFF_SCHEDULE[i - 1]


def test_next_retry_delay_clamping() -> None:
    """``next_retry_delay`` clamps to the cap for high attempt counts."""
    assert next_retry_delay(0) == timedelta(minutes=1)
    assert next_retry_delay(1) == timedelta(minutes=5)
    assert next_retry_delay(2) == timedelta(minutes=30)
    assert next_retry_delay(3) == timedelta(hours=2)
    assert next_retry_delay(4) == timedelta(hours=12)
    assert next_retry_delay(5) == timedelta(hours=24)
    assert next_retry_delay(50) == timedelta(hours=24)  # cap
    assert next_retry_delay(-1) == timedelta(minutes=1)  # clamp to first


async def test_enqueue_default_priority_for_insert(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """``operacion='insert'`` gets priority 10 (highest)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        row = await enqueue(
            session,
            operacion="insert",
            tabla="log_transaccional",
            uuid_registro=uuid_lib.uuid4(),
            datos={"accion": "test"},
            uuid_sucursal=seeded_sucursal_uuid,
        )
        await session.commit()

        assert row.prioridad == 10
        assert row.estado == "pendiente"
        assert row.intentos == 0


async def test_enqueue_default_priority_for_non_insert(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """Non-insert operations default to priority 0."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        for op in ("update", "delete", "compensate"):
            row = await enqueue(
                session,
                operacion=op,  # type: ignore[arg-type]
                tabla="sync_queue",
                uuid_registro=uuid_lib.uuid4(),
                datos={},
                uuid_sucursal=seeded_sucursal_uuid,
            )
            assert row.prioridad == 0, f"{op} should default to priority 0"
        await session.commit()


async def test_mark_dispatched(pg_engine, alembic_upgrade, seeded_sucursal_uuid) -> None:
    """``mark_dispatched`` flips ``estado='exitoso'`` and stamps ``sync_timestamp``."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        row = await enqueue(
            session,
            operacion="insert",
            tabla="sync_queue",
            uuid_registro=uuid_lib.uuid4(),
            datos={},
            uuid_sucursal=seeded_sucursal_uuid,
        )
        await session.commit()
        row_uuid = row.uuid

        await mark_dispatched(session, row_uuid)
        await session.commit()
        await session.refresh(row)

        assert row.estado == "exitoso"
        assert row.sync_timestamp is not None


async def test_mark_in_progress(pg_engine, alembic_upgrade, seeded_sucursal_uuid) -> None:
    """``mark_in_progress`` flips ``estado='en_progreso'``."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        row = await enqueue(
            session,
            operacion="insert",
            tabla="sync_queue",
            uuid_registro=uuid_lib.uuid4(),
            datos={},
            uuid_sucursal=seeded_sucursal_uuid,
        )
        await session.commit()
        row_uuid = row.uuid

        await mark_in_progress(session, row_uuid)
        await session.commit()
        await session.refresh(row)

        assert row.estado == "en_progreso"


async def test_mark_failed_increments_intentos(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """``mark_failed`` increments ``intentos`` and sets ``next_retry_at`` per the schedule."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        row = await enqueue(
            session,
            operacion="insert",
            tabla="sync_queue",
            uuid_registro=uuid_lib.uuid4(),
            datos={},
            uuid_sucursal=seeded_sucursal_uuid,
        )
        await session.commit()
        row_uuid = row.uuid

        # First failure → 1m delay, intentos=1
        await mark_failed(session, row_uuid, "first failure")
        await session.commit()
        await session.refresh(row)

        assert row.intentos == 1
        assert row.estado == "pendiente"  # re-queued for retry
        assert row.ultimo_error == "first failure"
        assert row.next_retry_at is not None

        # The next_retry_at should be ~1m from now.
        now = datetime.now(UTC).replace(tzinfo=None)
        delta = row.next_retry_at - now
        # Allow 5s slack for clock drift.
        assert timedelta(seconds=55) < delta < timedelta(seconds=65), (
            f"expected ~60s delay, got {delta}"
        )

        # Second failure → 5m delay, intentos=2
        await mark_failed(session, row_uuid, "second failure")
        await session.commit()
        await session.refresh(row)
        delta = row.next_retry_at - datetime.now(UTC).replace(tzinfo=None)
        assert timedelta(seconds=295) < delta < timedelta(seconds=305)


async def test_list_pending_returns_pending_rows(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """``list_pending`` returns rows with ``estado='pendiente'``, ordered correctly."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        sucursal = seeded_sucursal_uuid
        # Insert 3 rows: priorities 5, 10, 1.
        high = await enqueue(
            session,
            operacion="insert",
            tabla="sync_queue",
            uuid_registro=uuid_lib.uuid4(),
            datos={},
            uuid_sucursal=sucursal,
            prioridad=5,
        )
        top = await enqueue(
            session,
            operacion="insert",
            tabla="sync_queue",
            uuid_registro=uuid_lib.uuid4(),
            datos={},
            uuid_sucursal=sucursal,
            prioridad=10,
        )
        low = await enqueue(
            session,
            operacion="insert",
            tabla="sync_queue",
            uuid_registro=uuid_lib.uuid4(),
            datos={},
            uuid_sucursal=sucursal,
            prioridad=1,
        )
        await session.commit()

        # Mark one as exitoso — it should NOT appear in list_pending.
        await mark_dispatched(session, low.uuid)
        await session.commit()

        rows = await list_pending(session, limit=10, uuid_sucursal=sucursal)
        uuids = [r.uuid for r in rows]
        # Only the two pendiente rows are returned.
        assert high.uuid in uuids
        assert top.uuid in uuids
        assert low.uuid not in uuids
        # Ordered by prioridad DESC.
        assert rows[0].uuid == top.uuid
        assert rows[1].uuid == high.uuid


async def test_whitelist_rejects_forbidden_columns(pg_engine, alembic_upgrade) -> None:
    """A future caller attempting to update ``datos`` directly raises ``SyncQueueStateError``.

    The whitelist lives in :func:`_validate_update_columns` and is also
    visible to the helper API: any helper that accepts extra columns
    MUST validate before issuing the UPDATE. This test asserts the
    invariant by directly poking the validator via ``enqueue`` +
    ``mark_*`` — the helpers themselves don't expose a free-form
    column set, so we test the validator indirectly by checking that
    the helpers refuse to construct invalid state.
    """
    from parkos_core.repo.sync_queue import _validate_update_columns

    # Direct call to the private validator (white-box test).
    with pytest.raises(SyncQueueStateError, match="forbidden"):
        _validate_update_columns({"estado": "exitoso", "datos": {"foo": "bar"}})

    with pytest.raises(SyncQueueStateError, match="forbidden"):
        _validate_update_columns({"uuid_sucursal": uuid_lib.uuid4()})