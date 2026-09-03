"""test_sync_outbox_recursion.py — REQ-X6 + SC-X5.

Verifies that the DB-side ``AFTER INSERT`` trigger
``prod.fn_enqueue_sync()`` does NOT recurse when the source table IS
``prod.sync_queue``. The trigger has an explicit
``IF TG_TABLE_NAME = 'sync_queue' RETURN NULL`` guard that prevents
the recursion that would otherwise happen on every INSERT.

The companion unit test ``tests/unit/test_sync_outbox.py`` documents
the Python-side no-op facade (``repo.sync_outbox.enqueue_sync_row``
always raises); this test verifies the DB-side complement.

Two scenarios:

  1. **No recursion**: an INSERT into ``prod.sync_queue`` creates
     EXACTLY ONE row (not two, not infinite).
  2. **Trigger fires for non-sync_queue**: an INSERT into a non-queue
     ``[A]`` table (``prod.log_transaccional``) creates the source
     row AND a matching ``sync_queue`` row in the same TX.
"""
from __future__ import annotations

import uuid as uuid_lib


async def test_sync_queue_insert_does_not_recurse(pg_dsn: str) -> None:
    """An INSERT into ``prod.sync_queue`` creates exactly one row — no recursion."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        # Baseline count (the partition may already have rows from prior tests).
        await cur.execute("SELECT count(*) FROM prod.sync_queue")
        before = (await cur.fetchone())[0]

        # Direct INSERT into sync_queue — must NOT trigger a second INSERT.
        await cur.execute(
            "INSERT INTO prod.sync_queue "
            "(operacion, tabla, uuid_registro, datos, estado, prioridad) "
            "VALUES (%s, %s, %s, '{}'::jsonb, 'pendiente', 1)",
            (
                "insert",
                "manual_test",
                uuid_lib.uuid4(),
            ),
        )
        await conn.commit()

        await cur.execute("SELECT count(*) FROM prod.sync_queue")
        after = (await cur.fetchone())[0]

        # Exactly +1 — not +2 (no recursion).
        assert after == before + 1, (
            f"expected exactly +1 row, got {after - before} (recursion?)"
        )


async def test_other_a_table_insert_enqueues_sync(pg_dsn: str) -> None:
    """An INSERT into ``prod.log_transaccional`` triggers a sync_queue INSERT."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute("SELECT count(*) FROM prod.sync_queue")
        before = (await cur.fetchone())[0]

        # INSERT into log_transaccional — the DB trigger fires and adds a
        # sync_queue row in the same TX.
        await cur.execute(
            "INSERT INTO prod.log_transaccional "
            "(uuid_sucursal, accion, tabla_afectada, uuid_registro_afectado, timestamp_evento) "
            "VALUES (%s, %s, %s, %s, NOW())",
            (
                uuid_lib.uuid4(),
                "sync_outbox_test",
                "log_transaccional",
                uuid_lib.uuid4(),
            ),
        )
        await conn.commit()

        await cur.execute("SELECT count(*) FROM prod.sync_queue")
        after = (await cur.fetchone())[0]

        # Exactly +1 sync_queue row, attributable to log_transaccional.
        assert after == before + 1, (
            f"expected exactly +1 sync_queue row, got {after - before}"
        )

        await cur.execute(
            "SELECT tabla FROM prod.sync_queue ORDER BY created_at DESC LIMIT 1"
        )
        row = await cur.fetchone()
        assert row is not None
        assert row[0] == "log_transaccional", (
            f"expected tabla='log_transaccional', got {row[0]!r}"
        )


async def test_trigger_function_has_recursion_guard(pg_dsn: str) -> None:
    """The ``fn_enqueue_sync`` function body contains the recursion guard.

    This is a defensive assertion: if a future migration accidentally
    drops the ``IF TG_TABLE_NAME = 'sync_queue' RETURN NULL`` line,
    the previous tests would still pass for a single insert (because
    the test's cleanup is fast enough to avoid the loop). This test
    reads the function source from ``pg_proc`` and asserts the guard
    string is present.
    """
    import psycopg

    expected_guard = "TG_TABLE_NAME = 'sync_queue'"

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT prosrc FROM pg_proc p "
            "JOIN pg_namespace n ON p.pronamespace = n.oid "
            "WHERE n.nspname = 'prod' AND p.proname = 'fn_enqueue_sync'"
        )
        row = await cur.fetchone()
        assert row is not None, (
            "prod.fn_enqueue_sync() is missing — the sync outbox trigger is broken"
        )
        assert expected_guard in row[0], (
            f"prod.fn_enqueue_sync() missing recursion guard ({expected_guard!r}); "
            f"functioning source:\n{row[0]}"
        )