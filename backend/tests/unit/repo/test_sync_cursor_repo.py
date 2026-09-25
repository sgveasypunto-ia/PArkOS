"""test_sync_cursor_repo.py — CU-07 pull-cursor persistence helpers.

Unit tests for ``repo.sync_cursor.get_seq`` / ``set_seq`` exercised
against a REAL Postgres container (same rule as
``test_repo_ingreso_consecutivo.py``: the row lock + monotonic guard are
exactly what a mock would hide).

Scenarios:

  T1 -- ``get_seq`` returns ``0`` for an unknown sucursal (never crashed).
  T2 -- ``set_seq`` INSERTs the first row and later reads persist.
  T3 -- monotonic: a lower ``ultimo_seq`` is a no-op (draw in place).
  T4 -- ``get_seq`` stays branch-scoped (two sucursales, two cursors).
  T5 -- advances within one session commit as a single transaction.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

import pytest
from parkos_core.models.V.empresa import Empresa
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.repo import sync_cursor
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seed_empresa(pg_engine: AsyncEngine) -> uuid_lib.UUID:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre=f"Empresa cursor {empresa_uuid.hex[:6]}",
                nit=f"900{empresa_uuid.hex[:6]}",
                mensaje_bienvenida="hi",
                mensaje_salida="bye",
                regimen="comun",
                vigente_desde=_now(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now(),
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.commit()
        return empresa_uuid


async def _seed_sucursal(
    pg_engine: AsyncEngine, *, uuid_empresa: uuid_lib.UUID
) -> uuid_lib.UUID:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal_uuid = uuid_lib.uuid4()
        session.add(
            Sucursal(
                uuid=sucursal_uuid,
                uuid_empresa=uuid_empresa,
                uuid_tipo_sucursal=None,
                nombre=f"Suc cursor {sucursal_uuid.hex[:6]}",
                prefijo_nombre=f"S{sucursal_uuid.hex[:4]}",
                ciudad="Bogota",
                direccion="Calle cursor 1",
                telefono="+57111",
                horario="24/7",
                vigente_desde=_now(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now(),
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
        return sucursal_uuid


@pytest.fixture
async def seeded_sucursal(pg_engine: AsyncEngine, pg_dsn: str) -> uuid_lib.UUID:
    """Clean + seed one sucursal row (FK parent for the cursor row)."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE prod.sync_cursor, prod.sucursal, prod.empresa CASCADE")
        conn.commit()
    empresa_uuid = await _seed_empresa(pg_engine)
    return await _seed_sucursal(pg_engine, uuid_empresa=empresa_uuid)


@pytest.mark.asyncio
async def test_get_seq_unknown_sucursal_returns_zero(
    pg_engine: AsyncEngine, seeded_sucursal: uuid_lib.UUID
) -> None:
    """T1: no cursor row yet -> ``0`` (full resnapshot semantics)."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        seq = await sync_cursor.get_seq(session, uuid_sucursal=seeded_sucursal)
        assert seq == 0


@pytest.mark.asyncio
async def test_set_seq_inserts_first_row_and_persists(
    pg_engine: AsyncEngine, seeded_sucursal: uuid_lib.UUID
) -> None:
    """T2: first write INSERTs the row; a fresh session reads it back."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        persisted = await sync_cursor.set_seq(
            session, uuid_sucursal=seeded_sucursal, ultimo_seq=1750
        )
        assert persisted == 1750
        await session.commit()
    async with Session() as session:
        seq = await sync_cursor.get_seq(session, uuid_sucursal=seeded_sucursal)
        assert seq == 1750


@pytest.mark.asyncio
async def test_set_seq_monotonic_draw_is_noop(
    pg_engine: AsyncEngine, seeded_sucursal: uuid_lib.UUID
) -> None:
    """T3: a lower ``ultimo_seq`` never moves the watermark backwards."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await sync_cursor.set_seq(
            session, uuid_sucursal=seeded_sucursal, ultimo_seq=5000
        )
        await session.commit()
    async with Session() as session:
        persisted = await sync_cursor.set_seq(
            session, uuid_sucursal=seeded_sucursal, ultimo_seq=1000
        )
        await session.commit()
        assert persisted == 5000, "monotonic guard regressed the watermark"
        seq = await sync_cursor.get_seq(session, uuid_sucursal=seeded_sucursal)
        assert seq == 5000


@pytest.mark.asyncio
async def test_cursors_are_branch_scoped(
    pg_engine: AsyncEngine, seeded_sucursal: uuid_lib.UUID
) -> None:
    """T4: two sucursales hold independent watermarks."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await sync_cursor.set_seq(
            session, uuid_sucursal=seeded_sucursal, ultimo_seq=100
        )
        await session.commit()
    async with Session() as session:
        other = await _seed_sucursal(
            pg_engine, uuid_empresa=(await _seed_empresa(pg_engine))
        )
        await sync_cursor.set_seq(session, uuid_sucursal=other, ultimo_seq=200)
        await session.commit()
        assert await sync_cursor.get_seq(session, uuid_sucursal=seeded_sucursal) == 100
        assert await sync_cursor.get_seq(session, uuid_sucursal=other) == 200


@pytest.mark.asyncio
async def test_set_seq_advance_in_single_transaction(
    pg_engine: AsyncEngine, seeded_sucursal: uuid_lib.UUID
) -> None:
    """T5: set_seq + commit persists the advance atomically with the batch
    that called it (the worker commits cursor + applied rows together)."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await sync_cursor.set_seq(
            session, uuid_sucursal=seeded_sucursal, ultimo_seq=250
        )
        await sync_cursor.set_seq(
            session, uuid_sucursal=seeded_sucursal, ultimo_seq=251
        )
        await session.commit()
    async with Session() as session:
        assert (
            await sync_cursor.get_seq(session, uuid_sucursal=seeded_sucursal) == 251
        )