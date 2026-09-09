"""test_catalog_triggers_schema.py — T-PR10-001 acceptance for migration
``0014_add_catalog_triggers.py`` (design.md §4, REQ-CAT-004, REQ-CAT-012).

Verifies ``fn_enqueue_sync_catalog()`` fires an ``AFTER INSERT`` on each of
the 18 ``[V]`` tables that had no sync trigger before this migration
(D8-rev), and that ``prioridad`` is written as the constant tie-break value
``1`` (REQ-CAT-012, D18) — never used for cross-table ordering.
"""
from __future__ import annotations

import pytest
from parkos_core.sync.catalog.entries.sync_entries_v import SYNC_ENTRIES_V
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

# The 8 [V] tables that already had an AFTER INSERT fn_enqueue_sync()
# trigger in 0001_initial_schema.py (all of them have a physical
# uuid_sucursal column) — everything else in SYNC_ENTRIES_V is one of the
# 18 tables 0014_add_catalog_triggers.py newly covers.
_ALREADY_TRIGGERED = frozenset(
    {
        "configuracion_tolerancias",
        "configuracion_seguridad",
        "resolucion_facturacion",
        "usuarios_sucursal",
        "documentos",
        "tarifas_sucursal",
        "cantidad_vehiculos_sucursal",
        "subscripciones_cliente",
    }
)

_NEWLY_TRIGGERED_ENTRIES = [
    entry for entry in SYNC_ENTRIES_V if entry.name not in _ALREADY_TRIGGERED
]

assert len(_NEWLY_TRIGGERED_ENTRIES) == 18, (
    f"expected 18 newly-triggered [V] tables (REQ-CAT-004), got {len(_NEWLY_TRIGGERED_ENTRIES)}"
)


@pytest.mark.parametrize(
    "entry",
    _NEWLY_TRIGGERED_ENTRIES,
    ids=[e.name for e in _NEWLY_TRIGGERED_ENTRIES],
)
async def test_insert_enqueues_sync_queue_row(
    entry, pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    """An INSERT into each of the 18 tables enqueues exactly one sync_queue row."""
    async with pg_engine.connect() as conn:
        before = (await conn.execute(text("SELECT count(*) FROM prod.sync_queue"))).scalar_one()

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = v_fixture_factory.build(entry.model_cls)
        session.add(row)
        await session.commit()

    async with pg_engine.connect() as conn:
        after = (await conn.execute(text("SELECT count(*) FROM prod.sync_queue"))).scalar_one()
        assert after == before + 1, (
            f"expected exactly +1 sync_queue row for {entry.name!r}, got {after - before}"
        )

        result = await conn.execute(
            text(
                "SELECT tabla, prioridad, uuid_sucursal FROM prod.sync_queue "
                "ORDER BY created_at DESC LIMIT 1"
            )
        )
        tabla, prioridad, uuid_sucursal = result.one()

    assert tabla == entry.name
    # REQ-CAT-012/D18: priority is a constant intra-level tie-break value,
    # never a cross-table ordering criterion — SyncCatalogEntry.priority
    # defaults to 1 for every [V] entry (none override it).
    assert prioridad == 1
    # None of these 18 tables has a physical uuid_sucursal column
    # (has_uuid_sucursal=False for all of them) — the trigger must resolve
    # this to NULL (global, all_branches scope) rather than raising.
    assert not entry.has_uuid_sucursal
    assert uuid_sucursal is None


async def test_fn_enqueue_sync_catalog_exists(pg_dsn: str, alembic_upgrade) -> None:
    """``prod.fn_enqueue_sync_catalog()`` is present after the migration."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT prosrc FROM pg_proc p "
            "JOIN pg_namespace n ON p.pronamespace = n.oid "
            "WHERE n.nspname = 'prod' AND p.proname = 'fn_enqueue_sync_catalog'"
        )
        row = await cur.fetchone()
    assert row is not None, "prod.fn_enqueue_sync_catalog() is missing"
    assert "uuid_sucursal" in row[0]
