"""test_hash_chain_genesis.py — REQ-16 + REQ-X4 (SC-12-A-HASH-CHAIN).

Verifies the hash-chain genesis invariant after ``alembic upgrade head``:

  - There must be AT LEAST one row in ``prod.log_transaccional`` with
    ``accion = 'inicialización'`` — that's the genesis row. The 0001
    migration declares the genesis row insertion is "NOT inserted at
    migration time" (see the comment in ``0001_initial_schema.py``); it is
    the application's responsibility on first login. We check the row
    exists when the test fixture (or the local smoke check in
    ``apply_migration.py``) inserted it.

  - The genesis row's ``hash_anterior`` and ``hash_actual`` must equal the
    canonical SHA-256 of ``b'genesis:' + uuid_sucursal_bytes``. For the
    global (uuid_sucursal IS NULL) genesis row, that's the SHA-256 of
    ``b'genesis:NULL'``.

The test does NOT insert the genesis row itself — that would violate the
"hash chain genesis is app-owned" invariant. If the genesis row is
absent, the test fails with a clear message pointing at the app-side
``repo/hash_chain.py`` helper (PR2) and at the manual workaround in
``apply_migration.py`` (lines 173-190).
"""
from __future__ import annotations

import hashlib

import pytest

_XFAIL_GENESIS = pytest.mark.xfail(
    reason=(
        "Bloqueado hasta PR6 (hash-chain genesis-row bootstrap) — "
        "openspec/changes/sync-overhaul/tasks.md PR6"
    ),
    strict=True,
)


@_XFAIL_GENESIS
async def test_genesis_row_exists(pg_dsn: str) -> None:
    """At least one ``log_transaccional`` row with ``accion='inicialización'``.

    The row is normally inserted by the application on first login (PR2's
    ``repo/hash_chain.append()``). The smoke verifier in
    ``backend/scripts/apply_migration.py`` inserts a fallback row when the
    migration finishes — that's the path this test exercises.
    """
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT count(*) FROM prod.log_transaccional "
            "WHERE accion = 'inicialización'"
        )
        count = (await cur.fetchone())[0]
        assert count >= 1, (
            "hash-chain genesis row missing — the application must insert "
            "one 'inicialización' row in log_transaccional on first login "
            "(see repo/hash_chain.py in PR2). The local smoke verifier "
            "(apply_migration.py) inserts a fallback row when running the "
            "migration in isolation."
        )


@_XFAIL_GENESIS
async def test_genesis_row_hash_matches(pg_dsn: str) -> None:
    """Genesis row's ``hash_anterior`` and ``hash_actual`` match SHA-256
    of ``b'genesis:' + uuid_sucursal_bytes`` (canonical genesis anchor).
    """
    import psycopg

    expected_null_anchor = hashlib.sha256(b"genesis:NULL").hexdigest()

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT hash_anterior, hash_actual, uuid_sucursal "
            "FROM prod.log_transaccional "
            "WHERE accion = 'inicialización' "
            "ORDER BY timestamp_evento NULLS FIRST, uuid "
            "LIMIT 1"
        )
        row = await cur.fetchone()
        assert row is not None, "genesis row missing"
        hash_anterior, hash_actual, _uuid_sucursal = row
        # The first genesis row is the global (uuid_sucursal IS NULL) anchor.
        assert hash_anterior == expected_null_anchor, (
            f"genesis hash_anterior mismatch: "
            f"got '{hash_anterior}', expected '{expected_null_anchor}'"
        )
        assert hash_actual == expected_null_anchor, (
            f"genesis hash_actual mismatch: "
            f"got '{hash_actual}', expected '{expected_null_anchor}'"
        )


async def test_hash_chain_function_exists(pg_dsn: str) -> None:
    """The ``fn_extend_hash_chain`` trigger function must exist in the DB.

    Verifies the function — without it, every subsequent ``log_transaccional``
    INSERT would skip the chain extension. The trigger is added by
    ``0001_initial_schema.py``.
    """
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT 1 FROM pg_proc p "
            "JOIN pg_namespace n ON p.pronamespace = n.oid "
            "WHERE n.nspname = 'prod' AND p.proname = 'fn_extend_hash_chain'"
        )
        row = await cur.fetchone()
        assert row is not None, (
            "prod.fn_extend_hash_chain() is missing — log_transaccional chain "
            "extension will not work. Check 0001_initial_schema.py trigger "
            "creation block."
        )