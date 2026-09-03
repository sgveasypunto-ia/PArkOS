"""test_revokes_active.py — REQ-X5.

Asserts ``rol_app`` does NOT have UPDATE or DELETE privileges on any of
the 11 [A] tables that should be REVOKE'd. ``sync_queue`` is excluded per
the design §12 carve-out (it intentionally grants UPDATE/DELETE for the
sync queue worker).

We use ``has_table_privilege('rol_app', 'prod.<table>', 'UPDATE')`` — the
same predicate the canonical ``check_schema_match.py`` verifier uses. If
the predicate returns ``true`` for any of the 11 tables, the migration's
``REVOKE`` step was incomplete and CI fails.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def a_tables_to_verify() -> list[str]:
    """11 [A] tables that MUST have UPDATE/DELETE REVOKE'd from rol_app."""
    return [
        "salidas",
        "factura_detalle",
        "factura_impuestos",
        "factura_otros_cobros",
        "factura_pagos",
        "revocacion_factura",
        "caja",
        "arqueo",
        "sync_log",
        "sync_conflict",
        "log_transaccional",
    ]


@pytest.mark.parametrize(
    "table_name",
    [
        "salidas",
        "factura_detalle",
        "factura_impuestos",
        "factura_otros_cobros",
        "factura_pagos",
        "revocacion_factura",
        "caja",
        "arqueo",
        "sync_log",
        "sync_conflict",
        "log_transaccional",
    ],
)
async def test_rol_app_cannot_update_a_table(pg_dsn: str, table_name: str) -> None:
    """``rol_app`` must NOT have UPDATE privilege on the [A] table."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT has_table_privilege('rol_app', %s, 'UPDATE')",
            (f"prod.{table_name}",),
        )
        can_update = (await cur.fetchone())[0]
        assert can_update is False, (
            f"{table_name}: REVOKE failed — rol_app still has UPDATE privilege"
        )


@pytest.mark.parametrize(
    "table_name",
    [
        "salidas",
        "factura_detalle",
        "factura_impuestos",
        "factura_otros_cobros",
        "factura_pagos",
        "revocacion_factura",
        "caja",
        "arqueo",
        "sync_log",
        "sync_conflict",
        "log_transaccional",
    ],
)
async def test_rol_app_cannot_delete_a_table(pg_dsn: str, table_name: str) -> None:
    """``rol_app`` must NOT have DELETE privilege on the [A] table."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT has_table_privilege('rol_app', %s, 'DELETE')",
            (f"prod.{table_name}",),
        )
        can_delete = (await cur.fetchone())[0]
        assert can_delete is False, (
            f"{table_name}: REVOKE failed — rol_app still has DELETE privilege"
        )


async def test_sync_queue_has_update_delete(pg_dsn: str) -> None:
    """``sync_queue`` MUST retain UPDATE/DELETE for the worker carve-out.

    Defensive positive test — if a future migration accidentally REVOKEs
    ``sync_queue``, the sync worker breaks and this test catches it.
    """
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT has_table_privilege('rol_app', 'prod.sync_queue', 'UPDATE')"
        )
        can_update = (await cur.fetchone())[0]
        await cur.execute(
            "SELECT has_table_privilege('rol_app', 'prod.sync_queue', 'DELETE')"
        )
        can_delete = (await cur.fetchone())[0]
        assert can_update is True, (
            "sync_queue: UPDATE privilege missing — sync worker cannot mark dispatched"
        )
        assert can_delete is True, (
            "sync_queue: DELETE privilege missing — purge worker cannot clean up"
        )