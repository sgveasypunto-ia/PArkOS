"""MIGRATION 0042 -- ingreso.consecutivo column + ingreso_consecutivo_contador [A] counter table.

Revision ID: 0042_add_ingreso_consecutivo
Revises: 0041_seed_configuracion_tolerancias
Create Date: 2026-09-22

**Scope.** HU-INGRESO-SIN-PLACA backend foundation (REQ-OPS-191..193 + REQ-OPS-040
modified). Two schema changes:

  1. ``prod.ingreso ADD COLUMN consecutivo VARCHAR(20) NULL`` -- nullable for
     backward compat with existing carro/moto rows (50k+ in production).
     Defense in depth via partial UK
     ``CREATE UNIQUE INDEX uq_ingreso_consecutivo_partial
       ON prod.ingreso (uuid_sucursal, uuid_tipo_vehiculo, consecutivo)
       WHERE consecutivo IS NOT NULL``
     (R1, R5 from exploration.md). The partial UK only applies when
     ``consecutivo IS NOT NULL``; legacy rows are unaffected.

  2. New ``[A]``-class table ``prod.ingreso_consecutivo_contador`` carrying
     ``ultimo_consecutivo`` per ``(uuid_sucursal, uuid_tipo_vehiculo)``.
     Server-side counter for ingresos sin placa (bici, patineta).
     REVOKE UPDATE/DELETE on ``rol_app`` + BEFORE UPDATE OR DELETE trigger
     carve-out that only permits UPDATE on the
     ``(ultimo_consecutivo, last_event_uuid)`` pair -- the SAME defense in
     depth pattern as ``prod.idempotency_keys`` (PR2, REQ-OP-04). Per
     ``openspec/config.yaml`` ``rules.tasks``, REVOKE + trigger live in
     the SAME migration.

The counter is intentionally NOT wired into ``prod.fn_enqueue_sync`` --
counter rows are local-only operational state per branch, never
propagated to the cloud. If a future PR needs to enqueue counter
mutations, the existing ``IF TG_TABLE_NAME = 'sync_queue' THEN RETURN NEW;
END IF;`` guard in ``fn_enqueue_sync()`` is the precedent for a similar
exclusion; design §3.1 mentioned ``fn_enqueue_sync_catalog`` but that
function only fires on the 18 [V] catalog tables (0014_add_catalog_triggers
migration), NOT on [A] tables, so the exclusion there is unnecessary.

**Idempotency.** Both ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` and
``CREATE INDEX IF NOT EXISTS`` are PG-native idempotent operations. The
table CREATE wraps in a DO block that checks ``pg_class`` first so a
replay doesn't fail on the second ``CREATE TABLE``. The CHECK constraint
also wraps in DO; the trigger function is ``CREATE OR REPLACE``. Reversion
order: drop trigger -> drop function -> drop index -> drop column ->
drop table.

Refs: REQ-OPS-191, REQ-OPS-192, REQ-OPS-193
"""
from __future__ import annotations

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0042_add_ingreso_consecutivo"
down_revision = "0041_seed_configuracion_tolerancias"
branch_labels = None
depends_on = None


PG_UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    """Schema change: ADD COLUMN + partial UK + counter table + REVOKE + trigger."""
    op.execute("CREATE SCHEMA IF NOT EXISTS prod;")

    # =========================================================================
    # 1) prod.ingreso.consecutivo (nullable ADD COLUMN + partial UK)
    # =========================================================================
    op.execute(
        "ALTER TABLE prod.ingreso "
        "ADD COLUMN IF NOT EXISTS consecutivo VARCHAR(20) NULL;"
    )

    # Partial UK defense in depth (R1/R5): reject duplicate consecutivos in
    # the same (sucursal, tipo) namespace IF the helper ever races (the
    # helper is the primary defense via SELECT ... FOR UPDATE; this UK is
    # the catch-all at DB level).
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ingreso_consecutivo_partial
            ON prod.ingreso (uuid_sucursal, uuid_tipo_vehiculo, consecutivo)
            WHERE consecutivo IS NOT NULL;
        """
    )

    # =========================================================================
    # 2) prod.ingreso_consecutivo_contador ([A] counter table)
    # =========================================================================
    # Idempotent CREATE TABLE -- check pg_class first so a replay is a no-op.
    op.execute(
        """
        DO $$
        DECLARE
            _n_table bigint;
        BEGIN
            SELECT count(*) INTO _n_table
                FROM pg_catalog.pg_class
                WHERE relname='ingreso_consecutivo_contador'
                  AND relnamespace='prod'::regnamespace;
            IF _n_table IS NULL OR _n_table = 0 THEN
                CREATE TABLE prod.ingreso_consecutivo_contador (
                    -- IdMixin
                    uuid            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    -- AuditMixin
                    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
                    created_by      UUID,
                    -- SyncMixin
                    sync_status     VARCHAR(16) DEFAULT 'pendiente',
                    sync_timestamp  TIMESTAMP,
                    sync_attempts   INTEGER     DEFAULT 0,
                    -- VersionedMixin (bi-temporal; counter has close+insert
                    -- semantics for the version lifecycle, even though
                    -- there's typically only one vigente row per
                    -- (sucursal, tipo) pair)
                    vigente_desde   TIMESTAMP   DEFAULT NOW(),
                    vigente_hasta   TIMESTAMP,
                    estado          VARCHAR(16) NOT NULL DEFAULT 'activo',
                    -- RetentionMixin (DIAN 5-year default per AGENTS.md §1;
                    -- conservative default for an operational table per
                    -- DEC-INCOME-01)
                    fecha_retencion_hasta DATE,
                    -- Business columns
                    uuid_sucursal        UUID NOT NULL
                        REFERENCES prod.sucursal(uuid),
                    uuid_tipo_vehiculo   UUID NOT NULL
                        REFERENCES prod.tipos_vehiculo(uuid),
                    ultimo_consecutivo   INTEGER NOT NULL DEFAULT 0,
                    last_event_uuid      UUID,
                    -- Bi-temporal UK mirrors [V] convention: version is
                    -- part of identity (per AGENTS.md §2).
                    UNIQUE (uuid_sucursal, uuid_tipo_vehiculo, vigente_desde),
                    CHECK (
                        ultimo_consecutivo >= 0
                        AND ultimo_consecutivo < 1000000
                    )
                );
                RAISE NOTICE '0042: prod.ingreso_consecutivo_contador created';
            ELSE
                RAISE NOTICE '0042: prod.ingreso_consecutivo_contador already '
                             'present (count=%), no-op', _n_table;
            END IF;
        END $$;
        """
    )

    # =========================================================================
    # 3) REVOKE + trigger (per config.yaml rules.tasks, same migration)
    # =========================================================================
    op.execute("REVOKE UPDATE, DELETE ON prod.ingreso_consecutivo_contador FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.ingreso_consecutivo_contador TO rol_app;")

    # Trigger function with the operational UPDATE carve-out (REQ-OPS-193):
    # only (ultimo_consecutivo, last_event_uuid) may be UPDATEd by rol_app
    # to advance the counter. DELETE is unconditionally rejected.
    # Pattern mirrors prod.idempotency_keys_inmutable (PR2) and
    # prod.revoked_sync_jwts_inmutable (PR2).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prod.fn_ingreso_consecutivo_contador_carveout()
        RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            is_carveout BOOLEAN := false;
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                -- Carve-out: only (ultimo_consecutivo, last_event_uuid,
                -- sync_status, sync_timestamp, sync_attempts) may change.
                -- All other columns MUST be byte-identical to OLD.
                IF (
                    OLD.uuid_sucursal      IS NOT DISTINCT FROM NEW.uuid_sucursal
                    AND OLD.uuid_tipo_vehiculo IS NOT DISTINCT FROM NEW.uuid_tipo_vehiculo
                    AND OLD.created_at      IS NOT DISTINCT FROM NEW.created_at
                    AND OLD.created_by      IS NOT DISTINCT FROM NEW.created_by
                    AND OLD.vigente_desde   IS NOT DISTINCT FROM NEW.vigente_desde
                    AND OLD.vigente_hasta   IS NOT DISTINCT FROM NEW.vigente_hasta
                    AND OLD.estado          IS NOT DISTINCT FROM NEW.estado
                    AND OLD.uuid            IS NOT DISTINCT FROM NEW.uuid
                    AND OLD.fecha_retencion_hasta IS NOT DISTINCT FROM NEW.fecha_retencion_hasta
                ) THEN
                    is_carveout := true;
                END IF;
                IF NOT is_carveout THEN
                    RAISE EXCEPTION
                        'INGRESO_CONSECUTIVO_CONTADOR_IMMUTABLE: '
                        'only (ultimo_consecutivo, last_event_uuid, '
                        'sync_status, sync_timestamp, sync_attempts) '
                        'may be UPDATEd on prod.ingreso_consecutivo_contador'
                        USING ERRCODE = '42501',
                              HINT = 'counter is append-only modulo '
                                     'carve-out columns; corrections must '
                                     'close+insert a new version.';
                END IF;
            ELSE
                -- DELETE is forbidden unconditionally.
                RAISE EXCEPTION
                    'INGRESO_CONSECUTIVO_CONTADOR_IMMUTABLE: '
                    'DELETE is forbidden on prod.ingreso_consecutivo_contador'
                    USING ERRCODE = '42501',
                          HINT = 'counter is append-only; close+insert a new '
                                 'version instead of DELETE.';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ingreso_consecutivo_contador_inmutable
            BEFORE UPDATE OR DELETE ON prod.ingreso_consecutivo_contador
            FOR EACH ROW EXECUTE FUNCTION
                prod.fn_ingreso_consecutivo_contador_carveout();
        """
    )


def downgrade() -> None:
    """Reverse: drop trigger + function + index + column + table."""
    # Order matters: drop dependents first (trigger -> function -> index ->
    # column -> table). PG 14+ auto-drops triggers with the table, but
    # explicit ordering is portable and readable.
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ingreso_consecutivo_contador_inmutable "
        "ON prod.ingreso_consecutivo_contador;"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS prod.fn_ingreso_consecutivo_contador_carveout();"
    )
    # Restore grants on the counter before DROP (the trigger would otherwise
    # block DROP indirectly via FKs, though DROP TABLE bypasses triggers).
    op.execute("GRANT UPDATE, DELETE ON prod.ingreso_consecutivo_contador TO rol_app;")
    op.execute("DROP TABLE IF EXISTS prod.ingreso_consecutivo_contador CASCADE;")
    op.execute("DROP INDEX IF EXISTS prod.uq_ingreso_consecutivo_partial;")
    op.execute(
        "ALTER TABLE prod.ingreso DROP COLUMN IF EXISTS consecutivo CASCADE;"
    )


__all__ = ["downgrade", "upgrade"]