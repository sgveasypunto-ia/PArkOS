"""test_a_inmutable.py — SC-10-A-INMUTABLE-DB.

12 fixtures (one per [A] table) verify that:

  1. INSERT into the table succeeds (the row exists afterwards).
  2. UPDATE on that row raises an exception whose message contains
     ``<TABLE>_INMUTABLE`` (the BEFORE UPDATE OR DELETE trigger fires).
  3. DELETE on that row raises the same exception.

``sync_queue`` is the carved-out [A] table (design §12) — its UPDATE/DELETE
test is skipped with a clear message so the test count drops to 11 effective
tests but the parametrization is preserved at 12 for future-proofing.

The fixture ``table_set_a`` in ``conftest.py`` carries the canonical 11
[REVOKE'd + inmutable] [A] table list. We parametrize over that list plus a
synthetic ``sync_queue`` entry marked ``skip=True`` so adding the sync_queue
harness in PR2 is a one-line change.
"""
from __future__ import annotations

import pytest

# (table_name, skip?)
_A_TABLES: tuple = (
    ("salidas", False),
    ("factura_detalle", False),
    ("factura_impuestos", False),
    ("factura_otros_cobros", False),
    ("factura_pagos", False),
    ("revocacion_factura", False),
    ("caja", False),
    ("arqueo", False),
    ("sync_log", False),
    ("sync_conflict", False),
    pytest.param(
        "log_transaccional",
        False,
        marks=pytest.mark.xfail(
            reason=(
                "Bloqueado hasta PR6 (hash-chain genesis-row bootstrap) — "
                "openspec/changes/sync-overhaul/tasks.md PR6"
            ),
            strict=True,
        ),
    ),
    ("sync_queue", True),  # carve-out — UPDATE/DELETE allowed on the 4 whitelisted cols
)


@pytest.mark.parametrize(("table_name", "carve_out"), _A_TABLES)
async def test_a_table_insert_succeeds(
    pg_dsn: str,
    table_name: str,
    carve_out: bool,
) -> None:
    """INSERT into each [A] table must succeed.

    The test relies on the table-specific schema to satisfy the INSERT — we
    fill the minimum required columns (uuid, fecha_retencion_hasta when the
    table is partitioned by it, plus enough business fields to satisfy the
    NOT NULL constraints). The hash-chain trigger will compute the chain
    value for ``log_transaccional`` automatically; for all other tables the
    INSERT is a plain row write.
    """
    import psycopg

    if carve_out:
        pytest.skip(f"{table_name} is carved-out from inmutability (design §12)")

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(f"SELECT count(*) FROM prod.{table_name}")
        before = (await cur.fetchone())[0]

        # All [A] tables accept (uuid, fecha_retencion_hasta). Most have
        # additional required columns; for the partitioned-by-retention
        # tables the retention column is the partition key.
        insert_sql = (
            f"INSERT INTO prod.{table_name} (uuid, fecha_retencion_hasta) "
            f"VALUES (gen_random_uuid(), CURRENT_DATE) "
            f"RETURNING uuid"
        )
        try:
            await cur.execute(insert_sql)
            row_uuid = (await cur.fetchone())[0]
        except psycopg.errors.NotNullViolation as exc:
            # Some tables need extra business columns. The error message
            # guides future PRs that own those tables.
            pytest.fail(
                f"{table_name} requires extra NOT NULL columns for INSERT: {exc}"
            )

        assert row_uuid is not None, f"INSERT into {table_name} returned no row"
        await cur.execute(f"SELECT count(*) FROM prod.{table_name}")
        after = (await cur.fetchone())[0]
        assert after == before + 1, (
            f"{table_name}: count went {before} → {after}, expected +1"
        )


@pytest.mark.parametrize(("table_name", "carve_out"), _A_TABLES)
async def test_a_table_update_blocked(
    pg_dsn: str,
    table_name: str,
    carve_out: bool,
) -> None:
    """UPDATE on a [A] table row must raise ``<TABLE>_INMUTABLE``.

    Inserts a row first (via the helper from the previous test pattern), then
    attempts an UPDATE. The BEFORE UPDATE OR DELETE trigger raises
    ``RAISE EXCEPTION ... USING ERRCODE = '42501'`` (``insufficient_privilege``
    — see every ``fn_<table>_inmutable()`` function in
    ``0001_initial_schema.py``), which psycopg surfaces as
    :class:`psycopg.errors.InsufficientPrivilege`, not the generic
    :class:`psycopg.errors.RaiseException` (that class corresponds to the
    default ``P0001`` code, used only when no ``ERRCODE`` is given). We
    assert the error message contains the table-specific tag.

    ``sync_status`` is the column mutated here (not ``estado``) because it is
    the one column every ``[A]`` table carries via ``AppendOnlyBase``'s
    ``SyncMixin`` — most ``[A]`` tables (all but ``log_transaccional``) have
    no ``estado`` column at all.
    """
    import psycopg

    if carve_out:
        pytest.skip(f"{table_name} is carved-out from inmutability (design §12)")

    expected_tag = f"{table_name.upper()}_INMUTABLE"

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        # Seed a row in its own transaction so the UPDATE sees it.
        await cur.execute(
            f"INSERT INTO prod.{table_name} (uuid, fecha_retencion_hasta) "
            f"VALUES (gen_random_uuid(), CURRENT_DATE) RETURNING uuid"
        )
        row_uuid = (await cur.fetchone())[0]
        await conn.commit()

        # New transaction for the UPDATE — the trigger raises RAISE EXCEPTION.
        try:
            await cur.execute(
                f"UPDATE prod.{table_name} SET sync_status = 'error' "
                f"WHERE uuid = %s",
                (row_uuid,),
            )
            await conn.commit()
        except psycopg.errors.InsufficientPrivilege as exc:
            msg = str(exc)
            assert expected_tag in msg, (
                f"{table_name}: trigger raised but missing tag; "
                f"expected '{expected_tag}' in '{msg}'"
            )
        else:
            pytest.fail(
                f"{table_name}: UPDATE succeeded but trigger should have blocked it"
            )


@pytest.mark.parametrize(("table_name", "carve_out"), _A_TABLES)
async def test_a_table_delete_blocked(
    pg_dsn: str,
    table_name: str,
    carve_out: bool,
) -> None:
    """DELETE on a [A] table row must raise ``<TABLE>_INMUTABLE``.

    Symmetric to ``test_a_table_update_blocked`` — same trigger, different
    DML verb. Verified for every [A] table except ``sync_queue`` (carve-out).
    Same ``InsufficientPrivilege`` exception class as the UPDATE case — the
    trigger raises with ``ERRCODE = '42501'`` regardless of the DML verb.
    """
    import psycopg

    if carve_out:
        pytest.skip(f"{table_name} is carved-out from inmutability (design §12)")

    expected_tag = f"{table_name.upper()}_INMUTABLE"

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            f"INSERT INTO prod.{table_name} (uuid, fecha_retencion_hasta) "
            f"VALUES (gen_random_uuid(), CURRENT_DATE) RETURNING uuid"
        )
        row_uuid = (await cur.fetchone())[0]
        await conn.commit()

        try:
            await cur.execute(
                f"DELETE FROM prod.{table_name} WHERE uuid = %s",
                (row_uuid,),
            )
            await conn.commit()
        except psycopg.errors.InsufficientPrivilege as exc:
            msg = str(exc)
            assert expected_tag in msg, (
                f"{table_name}: trigger raised but missing tag; "
                f"expected '{expected_tag}' in '{msg}'"
            )
        else:
            pytest.fail(
                f"{table_name}: DELETE succeeded but trigger should have blocked it"
            )