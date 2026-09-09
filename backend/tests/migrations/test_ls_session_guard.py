"""test_ls_session_guard.py — SC-42-S-LS-SESSION-GUARD.

Two fixtures (``login``, ``sesion``) verify that updating ``estado`` on an
[L-S] table requires a co-transactional ``log_transaccional`` INSERT.

For each table:

  1. INSERT a row with ``estado='exitoso'`` (login) or ``estado='abierta'``
     (sesion — both spellings are accepted by the trigger pattern in the
     canonical ``fn_<table>_ls_session_guard()``).
  2. Attempt UPDATE ``estado='cerrado'`` WITHOUT prior log row → expect
     ``LOG_TRANSACCIONAL_REQUIRED`` in the error message.
  3. INSERT a ``log_transaccional`` row referencing the [L-S] row's uuid
     in the SAME transaction.
  4. UPDATE → expect success.

The two tests run in their own connections (each step opens a new TX) so
the trigger's "same TX" check is observable across calls.
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest

_LS_TABLES = ("login", "sesion")

_XFAIL_GENESIS = pytest.mark.xfail(
    reason=(
        "Bloqueado hasta PR6 (hash-chain genesis-row bootstrap) — "
        "openspec/changes/sync-overhaul/tasks.md PR6"
    ),
    strict=True,
)


@pytest.mark.parametrize("table_name", _LS_TABLES)
async def test_ls_update_requires_log(
    pg_dsn: str,
    table_name: str,
) -> None:
    """Without a co-transactional ``log_transaccional`` row, the UPDATE
    must be rejected with ``LOG_TRANSACCIONAL_REQUIRED``.

    The guard trigger raises with ``ERRCODE = '42501'``
    (``insufficient_privilege``, ``0001_initial_schema.py``), which psycopg
    surfaces as :class:`psycopg.errors.InsufficientPrivilege` — not the
    generic :class:`psycopg.errors.RaiseException` (``P0001``, the default
    for a plain ``RAISE EXCEPTION`` with no explicit code).
    """
    import psycopg

    row_uuid = uuid_lib.uuid4()

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        # Step 1: INSERT a fresh row for this test.
        await cur.execute(
            f"INSERT INTO prod.{table_name} (uuid, estado, "
            f"vigente_desde, vigente_hasta, created_at, sync_status) "
            f"VALUES (%s, %s, NOW(), NULL, NOW(), 'pendiente')",
            (row_uuid, "exitoso"),
        )
        await conn.commit()

        # Step 2: UPDATE without log row — trigger must reject.
        try:
            await cur.execute(
                f"UPDATE prod.{table_name} SET estado = 'cerrado' "
                f"WHERE uuid = %s",
                (row_uuid,),
            )
            await conn.commit()
        except psycopg.errors.InsufficientPrivilege as exc:
            msg = str(exc)
            assert "LOG_TRANSACCIONAL_REQUIRED" in msg, (
                f"{table_name}: trigger raised but missing tag; "
                f"got '{msg[:200]}'"
            )
        else:
            pytest.fail(
                f"{table_name}: UPDATE succeeded without prior log row — guard missing"
            )


@_XFAIL_GENESIS
@pytest.mark.parametrize("table_name", _LS_TABLES)
async def test_ls_update_with_log_succeeds(
    pg_dsn: str,
    table_name: str,
) -> None:
    """With a co-transactional ``log_transaccional`` row, the UPDATE must succeed.

    Pattern: INSERT log row FIRST in the SAME transaction, then UPDATE the
    [L-S] row. The trigger walks the trigger-scoped ``log_transaccional``
    rows; seeing one, it allows the UPDATE.
    """
    import psycopg

    row_uuid = uuid_lib.uuid4()

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        # Seed the [L-S] row.
        await cur.execute(
            f"INSERT INTO prod.{table_name} (uuid, estado, "
            f"vigente_desde, vigente_hasta, created_at, sync_status) "
            f"VALUES (%s, %s, NOW(), NULL, NOW(), 'pendiente')",
            (row_uuid, "exitoso"),
        )
        await conn.commit()

        # New TX: insert log + UPDATE in the same TX.
        await cur.execute(
            "INSERT INTO prod.log_transaccional (uuid, fecha_retencion_hasta, "
            "uuid_registro_afectado, tabla_afectada, accion, timestamp_evento) "
            "VALUES (gen_random_uuid(), CURRENT_DATE, %s, %s, %s, NOW())",
            (row_uuid, table_name, f"{table_name}_update"),
        )
        await cur.execute(
            f"UPDATE prod.{table_name} SET estado = 'cerrado' WHERE uuid = %s",
            (row_uuid,),
        )
        await conn.commit()

        await cur.execute(
            f"SELECT estado FROM prod.{table_name} WHERE uuid = %s",
            (row_uuid,),
        )
        row = await cur.fetchone()
        assert row is not None
        assert row[0] == "cerrado", (
            f"{table_name}: UPDATE with log row did not apply (estado={row[0]})"
        )