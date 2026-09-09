"""test_drop_infra_triggers_schema.py — T-PR10-002 acceptance for migration
``0015_drop_infra_triggers.py`` (D21 guard 1, design.md §4 / §11).

Verifies an INSERT into ``prod.sync_log`` / ``prod.sync_conflict`` produces
NO ``sync_queue`` row after ``0015`` drops their ``fn_enqueue_sync``
trigger — both are out-of-catalog infrastructure tables
(``catalog/out_of_catalog.py::OUT_OF_CATALOG``) and must never themselves
be replicated.
"""
from __future__ import annotations

import uuid as uuid_lib


async def test_sync_log_insert_produces_no_sync_queue_row(pg_dsn: str, alembic_upgrade) -> None:
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute("SELECT count(*) FROM prod.sync_queue")
        before = (await cur.fetchone())[0]

        await cur.execute("INSERT INTO prod.sync_log (uuid) VALUES (%s)", (uuid_lib.uuid4(),))
        await conn.commit()

        await cur.execute("SELECT count(*) FROM prod.sync_queue")
        after = (await cur.fetchone())[0]

    assert after == before, f"expected no new sync_queue row from sync_log, got +{after - before}"


async def test_sync_conflict_insert_produces_no_sync_queue_row(
    pg_dsn: str, alembic_upgrade
) -> None:
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute("SELECT count(*) FROM prod.sync_queue")
        before = (await cur.fetchone())[0]

        await cur.execute("INSERT INTO prod.sync_conflict (uuid) VALUES (%s)", (uuid_lib.uuid4(),))
        await conn.commit()

        await cur.execute("SELECT count(*) FROM prod.sync_queue")
        after = (await cur.fetchone())[0]

    assert after == before, (
        f"expected no new sync_queue row from sync_conflict, got +{after - before}"
    )


async def test_enqueue_sync_trigger_dropped_from_both_tables(pg_dsn: str, alembic_upgrade) -> None:
    """Neither table carries a ``<table>_enqueue_sync`` trigger anymore."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT c.relname, t.tgname FROM pg_trigger t "
            "JOIN pg_class c ON t.tgrelid = c.oid "
            "JOIN pg_namespace n ON c.relnamespace = n.oid "
            "WHERE n.nspname = 'prod' AND c.relname IN ('sync_log', 'sync_conflict') "
            "AND t.tgname LIKE '%_enqueue_sync' AND NOT t.tgisinternal"
        )
        rows = await cur.fetchall()
    assert rows == [], f"expected no enqueue_sync triggers left on sync_log/sync_conflict: {rows}"


async def test_fn_enqueue_sync_function_still_exists(pg_dsn: str, alembic_upgrade) -> None:
    """``fn_enqueue_sync()`` itself is NOT dropped — the other 28 tables still use it."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT prosrc FROM pg_proc p "
            "JOIN pg_namespace n ON p.pronamespace = n.oid "
            "WHERE n.nspname = 'prod' AND p.proname = 'fn_enqueue_sync'"
        )
        row = await cur.fetchone()
    assert row is not None, (
        "prod.fn_enqueue_sync() must survive 0015 — 28 other tables still use it "
        "until stage 5 of the cutover (design.md §12 Rollback)"
    )
