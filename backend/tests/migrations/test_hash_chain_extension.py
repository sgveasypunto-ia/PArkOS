"""test_hash_chain_extension.py — REQ-16 + REQ-X4 (chain extension on append).

PR2 tests the ``hash_chain.append`` helper against the live DB:

  1. Inserting the FIRST row for a ``uuid_sucursal`` writes a row whose
     ``hash_anterior`` equals ``sha256(b"genesis:" + uuid_sucursal_bytes).hexdigest()``.
  2. Inserting a SECOND row for the same tenant writes a row whose
     ``hash_anterior`` equals the FIRST row's ``hash_actual``.
  3. The chain grows monotonically (each new ``hash_actual`` differs
     from the prior one — a trivial collision would be a serious bug).

The companion unit test ``tests/unit/test_hash_chain.py`` exercises the
same paths against a per-test fixture; this migration test exercises
them against the production schema with the DB-side chain trigger
``prod.fn_extend_hash_chain()`` enabled.

PR6 note: these tests INSERT directly via raw ``psycopg`` SQL, bypassing
``repo/hash_chain.py``'s Python-side genesis-row auto-bootstrap entirely
(nothing here ever calls that helper) — so each test seeds its own genesis
row via ``seed_hash_chain_genesis_row_sync`` (mirrors the exact trigger
escape valve ``repo.hash_chain._ensure_genesis_row`` uses) before exercising
the trigger's OWN chain-extension math. ``uuid_sucursal`` is a REAL seeded
branch (``seeded_sucursal_uuid``) rather than a bare ``uuid_lib.uuid4()`` —
the ``AFTER INSERT`` outbox trigger (``fn_enqueue_sync``) enqueues into
``prod.sync_queue``, whose ``uuid_sucursal`` carries a real FK to
``prod.sucursal``.
"""
from __future__ import annotations

import uuid as uuid_lib

from tests.conftest import seed_hash_chain_genesis_row_sync


async def test_first_row_uses_genesis_anchor(
    pg_dsn: str, seeded_sucursal_uuid: uuid_lib.UUID
) -> None:
    """The first row for a uuid_sucursal has ``hash_anterior = genesis_hash``."""
    import hashlib

    import psycopg

    sucursal = seeded_sucursal_uuid
    expected_anchor = hashlib.sha256(b"genesis:" + str(sucursal).encode()).hexdigest()
    seed_hash_chain_genesis_row_sync(pg_dsn, sucursal)

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO prod.log_transaccional "
            "(uuid_sucursal, accion, tabla_afectada, uuid_registro_afectado, timestamp_evento) "
            "VALUES (%s, %s, %s, %s, NOW()) RETURNING hash_anterior",
            (sucursal, "chain_test_first", "log_transaccional", uuid_lib.uuid4()),
        )
        row = await cur.fetchone()
        await conn.commit()

        assert row is not None
        assert row[0] == expected_anchor, (
            f"first row hash_anterior={row[0]!r} != expected {expected_anchor!r}"
        )


async def test_second_row_links_to_first(
    pg_dsn: str, seeded_sucursal_uuid: uuid_lib.UUID
) -> None:
    """The second row's ``hash_anterior`` matches the first row's ``hash_actual``."""
    import psycopg

    sucursal = seeded_sucursal_uuid
    seed_hash_chain_genesis_row_sync(pg_dsn, sucursal)

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        # Insert the first row and capture its hash_actual.
        await cur.execute(
            "INSERT INTO prod.log_transaccional "
            "(uuid_sucursal, accion, tabla_afectada, uuid_registro_afectado, timestamp_evento) "
            "VALUES (%s, %s, %s, %s, NOW()) RETURNING hash_actual",
            (sucursal, "chain_first", "log_transaccional", uuid_lib.uuid4()),
        )
        first = await cur.fetchone()
        await conn.commit()
        assert first is not None
        first_hash_actual = first[0]

        # Insert the second row.
        await cur.execute(
            "INSERT INTO prod.log_transaccional "
            "(uuid_sucursal, accion, tabla_afectada, uuid_registro_afectado, timestamp_evento) "
            "VALUES (%s, %s, %s, %s, NOW()) RETURNING hash_anterior, hash_actual",
            (sucursal, "chain_second", "log_transaccional", uuid_lib.uuid4()),
        )
        second = await cur.fetchone()
        await conn.commit()
        assert second is not None
        second_anterior, second_actual = second

        assert second_anterior == first_hash_actual, (
            f"second.hash_anterior={second_anterior!r} != first.hash_actual={first_hash_actual!r}"
        )
        assert second_actual is not None
        assert second_actual != first_hash_actual


async def test_chain_grows_monotonically(
    pg_dsn: str, seeded_sucursal_uuid: uuid_lib.UUID
) -> None:
    """A 5-row chain produces 5 distinct ``hash_actual`` values."""
    import psycopg

    sucursal = seeded_sucursal_uuid
    seed_hash_chain_genesis_row_sync(pg_dsn, sucursal)

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        seen_hashes: set[str] = set()
        for i in range(5):
            await cur.execute(
                "INSERT INTO prod.log_transaccional "
                "(uuid_sucursal, accion, tabla_afectada, uuid_registro_afectado, timestamp_evento) "
                "VALUES (%s, %s, %s, %s, NOW() + (%s * INTERVAL '1 millisecond')) "
                "RETURNING hash_actual",
                (
                    sucursal,
                    f"chain_grow_{i}",
                    "log_transaccional",
                    uuid_lib.uuid4(),
                    i,
                ),
            )
            row = await cur.fetchone()
            assert row is not None
            seen_hashes.add(row[0])

        await conn.commit()

        # 5 distinct hashes — no collisions across the chain.
        assert len(seen_hashes) == 5, (
            f"expected 5 distinct hashes, got {len(seen_hashes)}"
        )
