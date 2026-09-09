"""test_seq_lookup_index_schema.py — T-PR7-003 acceptance for migration
``0011_add_seq_lookup_indexes.py`` (D4).

Verifies the partial index backing ``ReadLocalSeq``'s ``seq_via_datos``
strategy exists after ``alembic upgrade head``, is scoped to
``estado IN ('exitoso', 'pendiente')``, and is built on ``prod.sync_queue``
— the already-applied ``0001_initial_schema.py`` table, unmodified by this
migration (only the index is added).
"""
from __future__ import annotations

from sqlalchemy import text


async def test_seq_lookup_index_exists(pg_engine, alembic_upgrade) -> None:
    async with pg_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'prod' "
                    "AND indexname = 'ix_sync_queue_seq_lookup'"
                )
            )
        ).scalars().all()

    assert rows == ["ix_sync_queue_seq_lookup"]


async def test_seq_lookup_index_is_on_sync_queue(pg_engine, alembic_upgrade) -> None:
    async with pg_engine.connect() as conn:
        tablename = (
            await conn.execute(
                text(
                    "SELECT tablename FROM pg_indexes "
                    "WHERE indexname = 'ix_sync_queue_seq_lookup'"
                )
            )
        ).scalar_one()

    assert tablename == "sync_queue"


async def test_seq_lookup_index_is_partial_on_estado(pg_engine, alembic_upgrade) -> None:
    async with pg_engine.connect() as conn:
        definition = (
            await conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'ix_sync_queue_seq_lookup'"
                )
            )
        ).scalar_one()

    assert "estado" in definition
    assert "exitoso" in definition
    assert "pendiente" in definition


async def test_seq_lookup_index_covers_tabla_uuid_registro_and_seq(
    pg_engine, alembic_upgrade
) -> None:
    async with pg_engine.connect() as conn:
        definition = (
            await conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'ix_sync_queue_seq_lookup'"
                )
            )
        ).scalar_one()

    assert "tabla" in definition
    assert "uuid_registro" in definition
    assert "datos" in definition
    assert "seq" in definition
