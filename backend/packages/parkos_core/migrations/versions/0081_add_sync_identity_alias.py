"""MIGRATION 0081 -- ``prod.sync_identity_alias`` durable cross-cycle identity alias.

Revision ID: 0081_add_sync_identity_alias
Revises: 0080_grant_uuid_usuario_fk_propagation
Create Date: 2026-10-05 00:00:00.000000

**Scope.** D17 follow-up. ``sync.motor.sync_motor.SyncMotor.apply_batch``
already detects the moment ``identity_reconciler`` collapses an arriving
row onto a DIFFERENT local row with the same natural key, recording
``arriving uuid -> resolved uuid`` in an in-memory ``aliases`` dict so a
child row traveling in the SAME batch gets its foreign key rewritten
before it is attempted. That map never survives past the ``return`` of the
one ``apply_batch`` call that built it.

Real defect confirmed live (qa/integracion-admin-sucursal, 2026-10-05): a
branch's own pre-pairing-seeded ``tipos_vehiculo`` row ``moto`` reconciled
the cloud's ``moto`` onto itself as a no-op DURING PAIRING -- a no-op
reconciliation never calls ``repo.versioned.close_and_insert`` (see
``motor/apply_row.py``'s ``reconciliation == "noop"`` branch), so the
arriving cloud uuid was NEVER written anywhere locally. A
``cantidad_vehiculos_sucursal`` cupo naming that same cloud uuid, admin
-configured weeks later, arrived in its OWN, separate pull cycle -- a
fresh ``apply_batch`` call with a fresh, empty ``aliases`` dict -- and
failed ``fk_violation:fk_cantidad_vehiculos_sucursal_uuid_tipo_vehiculo``
every cycle, forever, holding the branch ``degraded``.

This migration ships the durable backing store for that same mapping::

    prod.sync_identity_alias (
        uuid                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
        created_by           UUID,
        sync_status          VARCHAR(16) DEFAULT 'pendiente',
        sync_timestamp       TIMESTAMP,
        sync_attempts        INTEGER     DEFAULT 0,
        fecha_retencion_hasta DATE,
        tabla                VARCHAR(64) NOT NULL,
        uuid_origen          UUID NOT NULL,
        uuid_resuelto        UUID NOT NULL,
        UNIQUE (uuid_origen)
    )

**Defense in depth, same carved-out ``[A]`` pattern as
``prod.sync_cursor`` (migration 0051) -- except simpler.** A resolved
alias never changes once recorded (unlike ``sync_cursor``'s advancing
``ultimo_seq``), so this table needs NO update carve-out at all:

  * ``REVOKE UPDATE, DELETE`` on the table from ``rol_app``.
  * ``BEFORE UPDATE OR DELETE`` trigger rejects BOTH unconditionally --
    same shape as ``prod.sync_conflict``'s ``fn_sync_conflict_inmutable``
    (migration 0001), not ``sync_cursor``'s carve-out variant.

**Local-only, never replicated.** Pure sync bookkeeping, exactly like its
siblings ``sync_cursor``/``sync_log``/``sync_conflict``: registered in
``OUT_OF_CATALOG`` (``sync/catalog/out_of_catalog.py``), never a
``SYNC_CATALOG``/``LOCAL_ONLY_CATALOG`` entry, and never ER-modeled
(``EXPECTED_NON_ER_TABLES``, ``openspec/scripts/check_schema_match.py``).
No ``fn_enqueue_sync`` trigger is attached.

**Idempotency.** CREATE TABLE wraps in a DO block that checks ``pg_class``
first (replay-safe, per the 0041/0042/0051 precedent).

Refs: D17, REQ-HOOK-010, ``sync/motor/sync_motor.py::SyncMotor.apply_batch``
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0081_add_sync_identity_alias"
down_revision = "0080_grant_uuid_usuario_fk_propagation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create prod.sync_identity_alias + REVOKE + unconditional immutability trigger."""
    op.execute("CREATE SCHEMA IF NOT EXISTS prod;")

    # ---------------------------------------------------------------------
    # 1) prod.sync_identity_alias ([A] durable identity-alias table)
    # ---------------------------------------------------------------------
    op.execute(
        """
        DO $$
        DECLARE
            _n_table bigint;
        BEGIN
            SELECT count(*) INTO _n_table
                FROM pg_catalog.pg_class
                WHERE relname='sync_identity_alias'
                  AND relnamespace='prod'::regnamespace;
            IF _n_table IS NULL OR _n_table = 0 THEN
                CREATE TABLE prod.sync_identity_alias (
                    -- IdMixin
                    uuid            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    -- AuditMixin
                    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
                    created_by      UUID,
                    -- SyncMixin
                    sync_status     VARCHAR(16) DEFAULT 'pendiente',
                    sync_timestamp  TIMESTAMP,
                    sync_attempts   INTEGER     DEFAULT 0,
                    -- RetentionMixin (operational table; NULL by default,
                    -- no DIAN retention obligation)
                    fecha_retencion_hasta DATE,
                    -- Business columns
                    tabla           VARCHAR(64) NOT NULL,
                    uuid_origen     UUID NOT NULL,
                    uuid_resuelto   UUID NOT NULL,
                    -- One durable alias per arriving uuid (globally unique
                    -- via gen_random_uuid(), no table dimension needed).
                    UNIQUE (uuid_origen)
                );
                RAISE NOTICE '0081: prod.sync_identity_alias created';
            ELSE
                RAISE NOTICE '0081: prod.sync_identity_alias already present '
                             '(count=%), no-op', _n_table;
            END IF;
        END $$;
        """
    )

    # ---------------------------------------------------------------------
    # 2) REVOKE + unconditional immutability trigger (same migration)
    # ---------------------------------------------------------------------
    op.execute("REVOKE UPDATE, DELETE ON prod.sync_identity_alias FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.sync_identity_alias TO rol_app;")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prod.fn_sync_identity_alias_inmutable()
        RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'SYNC_IDENTITY_ALIAS_INMUTABLE: '
                             'prod.sync_identity_alias is append-only; a '
                             'resolved alias never changes once recorded'
                USING ERRCODE = '42501',
                      HINT = 'corrections must be expressed as a new row, '
                             'never an UPDATE/DELETE of an existing one.';
            RETURN NULL;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_sync_identity_alias_inmutable
            BEFORE UPDATE OR DELETE ON prod.sync_identity_alias
            FOR EACH ROW EXECUTE FUNCTION
                prod.fn_sync_identity_alias_inmutable();
        """
    )


def downgrade() -> None:
    """Reverse: drop trigger + function + restore grants + drop table."""
    op.execute(
        "DROP TRIGGER IF EXISTS trg_sync_identity_alias_inmutable "
        "ON prod.sync_identity_alias;"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS prod.fn_sync_identity_alias_inmutable();"
    )
    op.execute("GRANT UPDATE, DELETE ON prod.sync_identity_alias TO rol_app;")
    op.execute("DROP TABLE IF EXISTS prod.sync_identity_alias CASCADE;")


__all__ = ["downgrade", "upgrade"]
