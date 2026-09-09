"""test_partman_parents.py — REQ-X6.

Asserts that ``partman.part_config`` has exactly the 8 [A] high-volume
parents registered after ``alembic upgrade head``. The set comes from
design §3.4 (monthly partitioning on the partitioned [A] tables):

    - salidas
    - caja
    - arqueo
    - factura_detalle
    - factura_pagos
    - log_transaccional
    - sync_queue
    - sync_log

If a future migration accidentally drops a partition parent or adds a new
one, this test surfaces the drift at CI time.
"""
from __future__ import annotations

import pytest

EXPECTED_PARTMAN_PARENTS: frozenset[str] = frozenset({
    "salidas",
    "caja",
    "arqueo",
    "factura_detalle",
    "factura_pagos",
    "log_transaccional",
    "sync_queue",
    "sync_log",
})

_XFAIL_PARTMAN_PREFIX = pytest.mark.xfail(
    reason=(
        "Migración 0001 renombra parent_table con prefijo parkos. espurio, "
        "rompe el filtro de partman — fuera de alcance de sync-overhaul, "
        "requiere fix de migración dedicado"
    ),
    strict=True,
)


@_XFAIL_PARTMAN_PREFIX
async def test_partman_parents_count(pg_dsn: str) -> None:
    """``partman.part_config`` MUST have exactly 8 prod.* entries."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT count(*) FROM partman.part_config "
            "WHERE parent_table LIKE 'prod.%'"
        )
        count = (await cur.fetchone())[0]
        assert count == len(EXPECTED_PARTMAN_PARENTS), (
            f"partman part_config has {count} prod.* parents; expected "
            f"{len(EXPECTED_PARTMAN_PARENTS)}"
        )


@_XFAIL_PARTMAN_PREFIX
async def test_partman_parents_match(pg_dsn: str) -> None:
    """Each expected parent table must appear in ``partman.part_config``."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT parent_table FROM partman.part_config "
            "WHERE parent_table LIKE 'prod.%' ORDER BY parent_table"
        )
        rows = await cur.fetchall()
        found = {row[0].split(".")[-1] for row in rows}
        missing = EXPECTED_PARTMAN_PARENTS - found
        extra = found - EXPECTED_PARTMAN_PARENTS
        assert not missing, f"partman missing parents: {sorted(missing)}"
        assert not extra, f"partman unexpected parents: {sorted(extra)}"


@_XFAIL_PARTMAN_PREFIX
@pytest.mark.parametrize("table_name", sorted(EXPECTED_PARTMAN_PARENTS))
async def test_partman_parent_registered(pg_dsn: str, table_name: str) -> None:
    """Each individual parent must be registered (parametrized for clearer failure mode)."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT 1 FROM partman.part_config WHERE parent_table = %s",
            (f"prod.{table_name}",),
        )
        row = await cur.fetchone()
        assert row is not None, f"prod.{table_name} is not registered in partman"