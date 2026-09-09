"""test_sync_queue_mark_dispatched.py — T-PR2-000 regression coverage.

Pre-existing bug (found during PR1's ``check_sync_queue_carveout.py`` draft,
deferred to PR2): ``ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS`` was missing
``sync_timestamp`` even though both ``mark_dispatched`` and
``mark_in_progress`` always stamp it, so both helpers unconditionally raised
:class:`SyncQueueStateError` whenever actually called.

This file has two layers of proof:

  1. A DB-free reproduction against the private column validator
     (:func:`_validate_update_columns`) — the exact root cause, fast, no
     testcontainers needed. This is the RED test: it fails against the
     pre-fix 4-column whitelist and passes against the fixed 5-column one.
  2. DB-backed acceptance tests (``pg_engine`` / ``alembic_upgrade``
     fixtures, mirroring ``test_sync_queue.py``'s existing style) proving
     ``mark_dispatched`` / ``mark_in_progress`` succeed end-to-end against a
     seeded ``sync_queue`` row, plus the ``mark_failed`` regression case
     (T-PR2-000's third acceptance bullet: ``mark_failed`` only touches
     already-whitelisted columns and must stay unaffected).
"""
from __future__ import annotations

import uuid as uuid_lib

from parkos_core.repo.sync_queue import (
    ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS,
    _validate_update_columns,
    enqueue,
    mark_dispatched,
    mark_failed,
    mark_in_progress,
)


def test_sync_timestamp_is_whitelisted() -> None:
    """``sync_timestamp`` is part of the update whitelist (T-PR2-000)."""
    assert "sync_timestamp" in ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS


def test_mark_dispatched_column_set_does_not_raise() -> None:
    """The exact column set ``mark_dispatched`` passes must validate clean.

    This reproduces the bug at its root: before T-PR2-000,
    ``_validate_update_columns`` raised ``SyncQueueStateError`` here because
    ``sync_timestamp`` was not in the whitelist.
    """
    _validate_update_columns(
        {
            "estado": "exitoso",
            "sync_timestamp": None,
            "next_retry_at": None,
            "ultimo_error": None,
        }
    )  # must not raise


def test_mark_in_progress_column_set_does_not_raise() -> None:
    """The exact column set ``mark_in_progress`` passes must validate clean."""
    _validate_update_columns({"estado": "en_progreso", "sync_timestamp": None})  # must not raise


def test_mark_failed_column_set_unaffected() -> None:
    """``mark_failed`` never touches ``sync_timestamp`` — regression case.

    T-PR2-000's third acceptance bullet: the fix must not change
    ``mark_failed``'s already-whitelisted column set
    (``intentos``/``next_retry_at``/``ultimo_error``/``estado``).
    """
    _validate_update_columns(
        {
            "estado": "pendiente",
            "intentos": 1,
            "next_retry_at": None,
            "ultimo_error": "boom",
        }
    )  # must not raise — unchanged behavior


async def test_mark_dispatched_succeeds_against_seeded_row(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """``mark_dispatched`` succeeds end-to-end against a seeded row (DB-backed)."""
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

        # Must not raise SyncQueueStateError (the pre-T-PR2-000 bug).
        await mark_dispatched(session, row_uuid)
        await session.commit()
        await session.refresh(row)

        assert row.estado == "exitoso"
        assert row.sync_timestamp is not None


async def test_mark_in_progress_succeeds_against_seeded_row(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """``mark_in_progress`` succeeds end-to-end against a seeded row (DB-backed)."""
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

        # Must not raise SyncQueueStateError (the pre-T-PR2-000 bug).
        await mark_in_progress(session, row_uuid)
        await session.commit()
        await session.refresh(row)

        assert row.estado == "en_progreso"


async def test_mark_failed_still_succeeds_after_the_fix(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """``mark_failed`` is unaffected by the whitelist extension (DB-backed regression)."""
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

        await mark_failed(session, row_uuid, "unaffected by T-PR2-000")
        await session.commit()
        await session.refresh(row)

        assert row.estado == "pendiente"
        assert row.intentos == 1
        assert row.ultimo_error == "unaffected by T-PR2-000"
