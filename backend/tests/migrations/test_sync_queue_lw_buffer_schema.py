"""test_sync_queue_lw_buffer_schema.py — T-PR8-001 acceptance for migration
``0012_add_sync_queue_lw_buffer.py`` (design.md §2 Issue #2/#8).

Verifies the table, REVOKE, inmutable trigger, both indexes, and the
``pg_partman`` parent all exist after ``alembic upgrade head``.
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest
from sqlalchemy import text


async def test_sync_queue_lw_buffer_table_exists(pg_engine, alembic_upgrade) -> None:
    async with pg_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'prod' AND table_name = 'sync_queue_lw_buffer'"
                )
            )
        ).scalars().all()
    assert rows == ["sync_queue_lw_buffer"]


async def test_sync_queue_lw_buffer_columns(pg_engine, alembic_upgrade) -> None:
    """The literal T-PR8-001 column set (plus ultimo_error + audit/sync columns)."""
    async with pg_engine.connect() as conn:
        columns = (
            await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'prod' AND table_name = 'sync_queue_lw_buffer'"
                )
            )
        ).scalars().all()

    expected = {
        "uuid",
        "uuid_sucursal",
        "tabla",
        "uuid_registro",
        "tabla_padre",
        "uuid_padre",
        "datos",
        "estado",
        "buffered_at",
        "expires_at",
        "ultimo_error",
        "created_at",
        "created_by",
        "sync_status",
        "sync_timestamp",
        "sync_attempts",
    }
    assert expected.issubset(set(columns)), f"missing columns: {expected - set(columns)}"


async def test_sync_queue_lw_buffer_revoked(pg_dsn: str, alembic_upgrade) -> None:
    """``rol_app`` must NOT have UPDATE/DELETE on ``sync_queue_lw_buffer``."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT has_table_privilege('rol_app', 'prod.sync_queue_lw_buffer', 'UPDATE')"
        )
        can_update = (await cur.fetchone())[0]
        await cur.execute(
            "SELECT has_table_privilege('rol_app', 'prod.sync_queue_lw_buffer', 'DELETE')"
        )
        can_delete = (await cur.fetchone())[0]
    # Carve-out (design §12's sync_queue precedent, see 0012's own module
    # docstring "Carve-out, not a blanket [A] REVOKE"): UPDATE is ALLOWED —
    # the drain/TTL-sweep workers flip estado/ultimo_error after insert.
    # DELETE stays blocked — a buffered row is NEVER deleted (T-PR8-008).
    assert can_update is True
    assert can_delete is False


async def test_sync_queue_lw_buffer_delete_blocked(pg_dsn: str, alembic_upgrade) -> None:
    """DELETE raises ``SYNC_QUEUE_LW_BUFFER_INMUTABLE``; UPDATE succeeds."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        row_uuid = uuid_lib.uuid4()
        parent_uuid = uuid_lib.uuid4()
        await cur.execute(
            """
            INSERT INTO prod.sync_queue_lw_buffer
                (uuid, tabla, uuid_registro, tabla_padre, uuid_padre, datos, expires_at)
            VALUES
                (%s, 'factura_detalle', %s, 'facturas', %s, '{}'::jsonb,
                 NOW() + INTERVAL '24 hours')
            """,
            (row_uuid, row_uuid, parent_uuid),
        )
        await conn.commit()

        # UPDATE succeeds — required by the drain (estado='aplicado') and
        # the TTL sweep (estado='fallido', ultimo_error=...).
        await cur.execute(
            "UPDATE prod.sync_queue_lw_buffer SET estado = 'aplicado' WHERE uuid = %s",
            (row_uuid,),
        )
        await conn.commit()

        with pytest.raises(
            psycopg.errors.InsufficientPrivilege, match="SYNC_QUEUE_LW_BUFFER_INMUTABLE"
        ):
            await cur.execute(
                "DELETE FROM prod.sync_queue_lw_buffer WHERE uuid = %s",
                (row_uuid,),
            )
        await conn.rollback()


async def test_sync_queue_lw_buffer_parent_partial_index(pg_engine, alembic_upgrade) -> None:
    async with pg_engine.connect() as conn:
        definition = (
            await conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'ix_sync_queue_lw_buffer_parent'"
                )
            )
        ).scalar_one()
    assert "tabla_padre" in definition
    assert "uuid_padre" in definition
    assert "pendiente" in definition


async def test_sync_queue_lw_buffer_expires_at_index(pg_engine, alembic_upgrade) -> None:
    async with pg_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE indexname = 'ix_sync_queue_lw_buffer_expires_at'"
                )
            )
        ).scalars().all()
    assert rows == ["ix_sync_queue_lw_buffer_expires_at"]


async def test_sync_queue_lw_buffer_partman_parent_registered(pg_dsn: str, alembic_upgrade) -> None:
    """``pg_partman`` parent registered with a 1-day interval (T-PR8-001)."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT partition_interval FROM partman.part_config "
            "WHERE parent_table = 'prod.sync_queue_lw_buffer'"
        )
        row = await cur.fetchone()
    assert row is not None, "prod.sync_queue_lw_buffer is not registered in partman.part_config"
    assert row[0] == "1 day"
