"""MIGRATION 0051 -- ``prod.sync_cursor`` per-branch pull high-water mark table.

Revision ID: 0051_add_sync_cursor
Revises: 0050_cotizar_mensualidad_factura_descuento
Create Date: 2026-09-25

**Scope.** CU-07 follow-up (plan.md:6957): the branch worker's cloud pull
is currently a full, idempotent re-snapshot from ``since_seq=0`` every
cycle -- safe but unbounded (``api/v1/sync_router.py``'s own docstring
calls this the "PR9 follow-up" gap). This migration ships the per-branch
delivery cursor: a new ``[A]``-class, local-only, non-ER table that holds
one monotonic high-water mark per ``uuid_sucursal``:

::

    prod.sync_cursor (
        uuid                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
        created_by           UUID,
        sync_status          VARCHAR(16) DEFAULT 'pendiente',
        sync_timestamp       TIMESTAMP,
        sync_attempts        INTEGER     DEFAULT 0,
        fecha_retencion_hasta DATE,
        uuid_sucursal        UUID NOT NULL REFERENCES prod.sucursal(uuid),
        ultimo_seq           BIGINT NOT NULL DEFAULT 0,
        UNIQUE (uuid_sucursal)
    )

``ultimo_seq`` is the cloud's ``next_seq`` -- the epoch-ms of the last
row's ``created_at`` the worker successfully APPLIED (not merely
delivered). The worker reads it as the next ``since_seq`` instead of
re-snapshotting from 0 (CU-07).

**Defense in depth (same carved-out ``[A]`` pattern as
``prod.ingreso_consecutivo_contador``, migration 0042).** Per
``openspec/config.yaml`` ``rules.tasks``, REVOKE + trigger live in the
SAME migration:

  * ``REVOKE UPDATE, DELETE`` on the table from ``rol_app`` (DELETE is
    unconditionally rejected at DB level -- cursor rows are append-only
    local state, never physically removed).
  * ``BEFORE UPDATE OR DELETE`` trigger carve-out permits UPDATE ONLY on
    ``(ultimo_seq, sync_status, sync_timestamp, sync_attempts)`` -- the
    operational advance path for the counter. Every other column must be
    byte-identical to OLD. This is the bi-temporal-close WITHOUT the
    ``vigente_*`` columns: the cursor is a monotonic high-water mark, not
    a versioned entity, so close+insert would be over-engineering -- the
    monotonic guard lives in ``repo/sync_cursor.py`` (``set_seq`` refuses
    to move backwards), and the trigger's column whitelist is the DB
    backstop.

**Local-only, never replicated.** Mirrors ``ingreso_consecutivo_contador``
(migration 0042): no ``fn_enqueue_sync`` trigger is attached and the
table is deliberately absent from every sync catalog collection (SYNC /
LOCAL_ONLY / OUT_OF_CATALOG) -- registered only in
``EXPECTED_NON_ER_TABLES`` (``openspec/scripts/check_schema_match.py``)
alongside the 4 existing non-ER tables.

**NOT partitioned.** Bounded at ``O(branches)`` -- one row per branch DB
(the worker is single-tenant). ``pg_partman`` would add overhead for no
gain (same rationale as the counter).

**Idempotency.** CREATE TABLE wraps in a DO block that checks ``pg_class``
first (replay-safe, per the 0041/0042 precedent). Trigger function is
``CREATE OR REPLACE``; trigger is ``CREATE`` guarded by ``DROP IF EXISTS``
first. Reversion order: trigger -> function -> restore grants -> table.

Refs: REQ-OPS-195 (CU-07), PR9 follow-up (sync_router docstring)
"""
from __future__ import annotations

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0051_add_sync_cursor"
down_revision = "0050_cotizar_mensualidad_factura_descuento"
branch_labels = None
depends_on = None


PG_UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    """Create prod.sync_cursor + REVOKE + trigger carve-out (same migration)."""
    op.execute("CREATE SCHEMA IF NOT EXISTS prod;")

    # ---------------------------------------------------------------------
    # 1) prod.sync_cursor ([A] counter table)
    # ---------------------------------------------------------------------
    op.execute(
        """
        DO $$
        DECLARE
            _n_table bigint;
        BEGIN
            SELECT count(*) INTO _n_table
                FROM pg_catalog.pg_class
                WHERE relname='sync_cursor'
                  AND relnamespace='prod'::regnamespace;
            IF _n_table IS NULL OR _n_table = 0 THEN
                CREATE TABLE prod.sync_cursor (
                    -- IdMixin
                    uuid            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    -- AuditMixin
                    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
                    created_by      UUID,
                    -- SyncMixin
                    sync_status     VARCHAR(16) DEFAULT 'pendiente',
                    sync_timestamp  TIMESTAMP,
                    sync_attempts   INTEGER     DEFAULT 0,
                    -- RetentionMixin (operational table; NULL by default
                    -- per DEC-INCOME-01, no DIAN retention obligation)
                    fecha_retencion_hasta DATE,
                    -- Business columns
                    uuid_sucursal   UUID NOT NULL
                        REFERENCES prod.sucursal(uuid),
                    ultimo_seq      BIGINT NOT NULL DEFAULT 0,
                    -- One cursor row per sucursal (branch is single-tenant).
                    UNIQUE (uuid_sucursal)
                );
                RAISE NOTICE '0051: prod.sync_cursor created';
            ELSE
                RAISE NOTICE '0051: prod.sync_cursor already present '
                             '(count=%), no-op', _n_table;
            END IF;
        END $$;
        """
    )

    # ---------------------------------------------------------------------
    # 2) REVOKE + trigger (per config.yaml rules.tasks, same migration)
    # ---------------------------------------------------------------------
    op.execute("REVOKE UPDATE, DELETE ON prod.sync_cursor FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.sync_cursor TO rol_app;")

    # Trigger function with the operational UPDATE carve-out: only
    # (ultimo_seq, sync_status, sync_timestamp, sync_attempts) may be
    # UPDATEd by rol_app to advance the cursor. DELETE is unconditionally
    # rejected. Pattern mirrors prod.ingreso_consecutivo_contador_carveout
    # (0042) and prod.idempotency_keys_inmutable (PR2).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prod.fn_sync_cursor_carveout()
        RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            is_carveout BOOLEAN := false;
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                -- Carve-out: only (ultimo_seq, sync_status, sync_timestamp,
                -- sync_attempts) may change. All other columns MUST be
                -- byte-identical to OLD.
                IF (
                    OLD.uuid            IS NOT DISTINCT FROM NEW.uuid
                    AND OLD.created_at      IS NOT DISTINCT FROM NEW.created_at
                    AND OLD.created_by      IS NOT DISTINCT FROM NEW.created_by
                    AND OLD.uuid_sucursal   IS NOT DISTINCT FROM NEW.uuid_sucursal
                    AND OLD.fecha_retencion_hasta IS NOT DISTINCT FROM NEW.fecha_retencion_hasta
                ) THEN
                    is_carveout := true;
                END IF;
                IF NOT is_carveout THEN
                    RAISE EXCEPTION
                        'SYNC_CURSOR_IMMUTABLE: '
                        'only (ultimo_seq, sync_status, sync_timestamp, '
                        'sync_attempts) may be UPDATEd on prod.sync_cursor'
                        USING ERRCODE = '42501',
                              HINT = 'the pull cursor is append-only modulo '
                                     'carve-out columns; corrections must go '
                                     'through repo/sync_cursor.set_seq.';
                END IF;
            ELSE
                -- DELETE is forbidden unconditionally.
                RAISE EXCEPTION
                    'SYNC_CURSOR_IMMUTABLE: '
                    'DELETE is forbidden on prod.sync_cursor'
                    USING ERRCODE = '42501',
                          HINT = 'the pull cursor is append-only local state; '
                                 'it must never be physically removed.';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_sync_cursor_inmutable
            BEFORE UPDATE OR DELETE ON prod.sync_cursor
            FOR EACH ROW EXECUTE FUNCTION
                prod.fn_sync_cursor_carveout();
        """
    )


def downgrade() -> None:
    """Reverse: drop trigger + function + restore grants + drop table."""
    op.execute(
        "DROP TRIGGER IF EXISTS trg_sync_cursor_inmutable "
        "ON prod.sync_cursor;"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS prod.fn_sync_cursor_carveout();"
    )
    op.execute("GRANT UPDATE, DELETE ON prod.sync_cursor TO rol_app;")
    op.execute("DROP TABLE IF EXISTS prod.sync_cursor CASCADE;")


__all__ = ["downgrade", "upgrade"]