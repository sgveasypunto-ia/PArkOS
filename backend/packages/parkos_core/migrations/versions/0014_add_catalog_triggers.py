"""add fn_enqueue_sync_catalog() + AFTER INSERT triggers on the 18 previously-untriggered
[V] tables (T-PR10-001, D8-rev, REQ-CAT-004, REQ-CAT-012)

Revision ID: 0014_add_catalog_triggers
Revises: 0013_add_alert_types
Create Date: 2026-09-09 01:00:00.000000

design.md §4 / ADR-002: D8-rev reversed the original "18 [V] tables are
``never_propagated``" decision (an invented "boot snapshot" mechanism that
existed in no requirement, task, or module) — the ER states the opposite
direction for several of these tables, and all 26 ``[V]`` entries now carry
real ``cloud_to_branch``/``bidirectional`` traffic (``entries/sync_entries_v.py``).
This migration is the DB-side half of that reversal: 8 of the 26 ``[V]``
tables already had an ``AFTER INSERT ... fn_enqueue_sync()`` trigger in
``0001_initial_schema.py`` (``configuracion_tolerancias``,
``configuracion_seguridad``, ``resolucion_facturacion``,
``usuarios_sucursal``, ``documentos``, ``tarifas_sucursal``,
``cantidad_vehiculos_sucursal``, ``subscripciones_cliente`` — all of them
happened to already have a physical ``uuid_sucursal`` column). The
remaining 18 never got one (verified by diffing ``SYNC_ENTRIES_V`` against
every ``CREATE TRIGGER %_enqueue_sync`` in ``0001_initial_schema.py`` —
the count matches REQ-CAT-004's "18-table coverage" exactly):

    usuarios, permisos, tipo_persona, tipos_vehiculo, tipo_subscripciones,
    tipo_tarifa, tipo_sucursal, tipo_arqueo, impuestos, otros_cobros,
    costos_servicios, empresa, permisos_usuario, sucursal, clientes,
    clientes_b2b, vehiculos, subscripcion_vehiculos

**Why a NEW function (``fn_enqueue_sync_catalog``) instead of reusing
``fn_enqueue_sync``).** None of these 18 tables has a physical
``uuid_sucursal`` column (``SyncCatalogEntry.has_uuid_sucursal=False`` for
every one of them — verified against ``entries/sync_entries_v.py``).
``fn_enqueue_sync()`` (0001) references ``NEW.uuid_sucursal`` directly,
which is safe ONLY because it was exclusively attached to the 8 tables
above that DO carry that column — PL/pgSQL does not validate ``NEW.<col>``
field access until the trigger actually fires, so attaching the legacy
function AS-IS to any of these 18 tables would raise "record NEW has no
field uuid_sucursal" on the first INSERT. ``fn_enqueue_sync_catalog()``
extracts ``uuid_sucursal`` from ``to_jsonb(NEW)`` instead of a direct
column reference, which is safe whether or not the column physically
exists (``NULL`` when absent — exactly the "global, all_branches" scope
these 18 tables use). This is a genuine, discovered correctness
requirement, not a stylistic preference — reusing ``fn_enqueue_sync`` as
literally written would have broken on the very first INSERT into
``usuarios``.

**``priority`` (D18, REQ-CAT-012).** ``SyncCatalogEntry.priority`` defaults
to ``1`` for all 26 ``[V]`` entries (no entry in ``entries/sync_entries_v.py``
overrides it). ``fn_enqueue_sync_catalog()`` therefore writes a constant
``prioridad=1`` for all 18 tables it covers — the legacy function's
``CASE TG_TABLE_NAME`` special-casing (10 for ``factura_electronica``/
``revocacion_factura``, 5 for ``ingreso``/``salidas``/``factura_pagos``) is
not replicated here because none of these 18 tables ever match those
literals; copying the dead branches would only obscure that this value is
never a cross-table ordering signal (the only cross-table order is the
``depends_on`` topological sort, REQ-CAT-015) — ``prioridad`` is read
exclusively as an intra-level FIFO tie-break by
``repo/sync_queue.py::list_pending`` (D18, R12).

**Recursion guard not needed.** ``fn_enqueue_sync_catalog()`` is never
attached to ``prod.sync_queue`` itself (unlike ``fn_enqueue_sync()``, which
guards against that with an ``IF TG_TABLE_NAME = 'sync_queue'`` early
return) — this function is exclusively wired to the 18 named tables below,
so the guard would be dead code.

Renumbered ``0011`` -> ``0014`` (session decision, re-verified per every
prior renumbering note's own caveat: ``ls migrations/versions/`` showed
``0013_add_alert_types.py`` as the highest applied revision at PR10 start,
exactly as ``0013``'s own note predicted — "next free number for PR9/PR10
is 0014"). ``tasks.md``'s PR10 section originally named this file
``0011_add_catalog_triggers.py``; corrected here (and in ``tasks.md``
itself) to ``0014`` — ``0011``/``0012`` were already used by PR7
(``0011_add_seq_lookup_indexes.py``) and PR8
(``0012_add_sync_queue_lw_buffer.py``).

Pre-flight: ``uv run alembic upgrade --sql 0014_add_catalog_triggers``
reviewed before apply (clean ``CREATE OR REPLACE FUNCTION`` + 18
``CREATE TRIGGER`` statements only, no data-destructive statements).
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0014_add_catalog_triggers"
down_revision = "0013_add_alert_types"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

# The 18 previously-untriggered [V] tables (REQ-CAT-004, D8-rev) — derived
# by diffing SYNC_ENTRIES_V (26 entries) against 0001_initial_schema.py's
# existing "<table>_enqueue_sync" triggers (8 tables already covered).
CATALOG_TRIGGER_TABLES: tuple[str, ...] = (
    "usuarios",
    "permisos",
    "tipo_persona",
    "tipos_vehiculo",
    "tipo_subscripciones",
    "tipo_tarifa",
    "tipo_sucursal",
    "tipo_arqueo",
    "impuestos",
    "otros_cobros",
    "costos_servicios",
    "empresa",
    "permisos_usuario",
    "sucursal",
    "clientes",
    "clientes_b2b",
    "vehiculos",
    "subscripcion_vehiculos",
)

assert len(CATALOG_TRIGGER_TABLES) == 18, (
    f"expected 18 tables (REQ-CAT-004), got {len(CATALOG_TRIGGER_TABLES)}"
)


def upgrade() -> None:
    """Create ``fn_enqueue_sync_catalog()`` + 18 AFTER INSERT triggers (T-PR10-001)."""
    op.execute(_LOCK_TIMEOUT_SQL)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_enqueue_sync_catalog()
        RETURNS trigger AS $$
        DECLARE
            next_seq bigint;
            payload jsonb;
            row_uuid_sucursal uuid;
        BEGIN
            payload := to_jsonb(NEW);
            -- Extract uuid_sucursal from the JSONB payload rather than
            -- referencing NEW.uuid_sucursal directly: none of the 18
            -- tables this function is attached to has a physical
            -- uuid_sucursal column (has_uuid_sucursal=False for all of
            -- them), and PL/pgSQL only validates NEW.<col> field access
            -- at trigger-fire time, not at CREATE FUNCTION time. NULL
            -- here correctly means "global, all_branches scope".
            row_uuid_sucursal := NULLIF(payload->>'uuid_sucursal', '')::uuid;
            SELECT COALESCE(MAX((datos->>'seq')::bigint), 0) + 1 INTO next_seq
              FROM prod.sync_queue
             WHERE uuid_sucursal IS NOT DISTINCT FROM row_uuid_sucursal;
            payload := jsonb_set(payload, '{seq}', to_jsonb(next_seq));
            INSERT INTO prod.sync_queue (
                uuid, uuid_sucursal, operacion, tabla, uuid_registro,
                datos, prioridad, estado, intentos,
                created_at, created_by, sync_status, sync_attempts)
            VALUES (
                gen_random_uuid(),
                row_uuid_sucursal,
                TG_OP,
                TG_TABLE_NAME,
                NEW.uuid,
                payload,
                -- SyncCatalogEntry.priority defaults to 1 for every [V]
                -- entry this trigger covers (REQ-CAT-012, D18) — an
                -- intra-level FIFO tie-break only, never a cross-table
                -- ordering criterion.
                1,
                'pendiente', 0,
                NOW(), NEW.created_by, 'pendiente', 0);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    for table in CATALOG_TRIGGER_TABLES:
        op.execute(f"""
            CREATE TRIGGER {table}_enqueue_sync_catalog
                AFTER INSERT ON prod.{table}
                FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync_catalog();
        """)


def downgrade() -> None:
    """Drop the 18 triggers + ``fn_enqueue_sync_catalog()``."""
    op.execute(_LOCK_TIMEOUT_SQL)

    for table in reversed(CATALOG_TRIGGER_TABLES):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_enqueue_sync_catalog ON prod.{table};")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_enqueue_sync_catalog();")
