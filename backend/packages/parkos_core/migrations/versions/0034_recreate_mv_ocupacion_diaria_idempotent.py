"""REQ-OPS-133 — idempotent recreate of ``prod.mv_ocupacion_diaria``.

QA-2026-09-17 bug remediation: bug-3 surfaced the case where the MV is
missing from branch containers that successfully applied migration 0024
but lost the view to a partial-commit / restore-from-backup failure. A
plain ``alembic upgrade head`` afterwards silently no-ops because the
revision table already marks 0024 as applied. This migration:

  1. ``CREATE OR REPLACE MATERIALIZED VIEW prod.mv_ocupacion_diaria``
     using the canonical SELECT (identical body to 0024). The
     ``OR REPLACE`` form is idempotent against the missing-MV case AND
     against the present-MV case (the index is preserved across
     replacement in PostgreSQL 16+).
  2. Post-upgrade ``to_regclass`` assertion — fails the migration with
     ``mv_ocupacion_diaria_missing_post_create`` if the MV is somehow
     still missing (defensive layer against a future Postgres version
     dropping OR REPLACE for materialized views).
  3. Recreates the UNIQUE INDEX required by REFRESH CONCURRENTLY if it
     was dropped alongside the MV in a disaster-recovery scenario.
     ``IF NOT EXISTS`` keeps the second-run case idempotent.
  4. Re-issues the GRANT — orphaned views lose their grants after a
     DROP/RECREATE; running it again costs nothing.

Idempotency is the primary design goal (D3 design decision); the
``CREATE OR REPLACE`` form is the only DDL shape that is safe against
both the missing-MV case AND a previously-applied-0024-with-MV case.

KEPT IN SYNC WITH: ``specs/operations/spec.md`` REQ-OPS-133 (Bug 3 of
qa-2026-09-17-bug-remediation).
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0034_recreate_mv_ocupacion_diaria_idempotent"
down_revision = "0024_mv_ocupacion_diaria"  # follow 0024 in the linear chain
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Idempotent recreate of the MV + UNIQUE INDEX + GRANT."""
    # 1) Recreate the MV. ``CREATE OR REPLACE`` is idempotent against both
    #    missing-MV and present-MV states. The SELECT is identical to 0024
    #    body so the contract (uuid_sucursal, uuid_tipo_vehiculo, activos)
    #    is preserved byte-for-byte.
    op.execute(
        """
        CREATE OR REPLACE MATERIALIZED VIEW prod.mv_ocupacion_diaria AS
        SELECT
            i.uuid_sucursal,
            i.uuid_tipo_vehiculo,
            count(*) AS activos
        FROM prod.ingreso i
        WHERE
            i.uuid_tipo_vehiculo IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM prod.salidas s
                WHERE s.uuid_ingreso = i.uuid
                  AND s.uuid_sucursal = i.uuid_sucursal
            )
            AND NOT EXISTS (
                SELECT 1 FROM prod.anulaciones a
                WHERE a.uuid_ingreso = i.uuid
                  AND a.estado = 'ejecutada'
                  AND a.tipo_anulable IN ('ingreso', 'salida')
            )
        GROUP BY i.uuid_sucursal, i.uuid_tipo_vehiculo;
        """
    )

    # 2) Post-upgrade assertion. ``to_regclass`` returns NULL when the
    #    relation does not exist; if ``CREATE OR REPLACE`` was a no-op
    #    (future Postgres dropping the OR REPLACE syntax), this catches
    #    it loudly rather than silently shipping an MV-less release.
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('prod.mv_ocupacion_diaria') IS NULL THEN
                RAISE EXCEPTION 'mv_ocupacion_diaria_missing_post_create: '
                                'CREATE OR REPLACE did not produce the view. '
                                'Inspect the migration log.';
            END IF;
        END $$;
        """
    )

    # 3) UNIQUE INDEX — re-asserted in case a DROP/RECREATE cycle wiped
    #    it. ``IF NOT EXISTS`` is no-op when the index is already
    #    present (the 0024 grant preserved it). CONCURRENTLY not
    #    required here because the MV was just (re)created and has no
    #    rows to lock against — a plain CREATE INDEX is the right tool.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            prod.uq_mv_ocupacion_diaria_sucursal_tipo
        ON prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo);
        """
    )

    # 4) Re-issue the GRANT. Cost: zero on subsequent runs.
    op.execute(
        "GRANT SELECT ON prod.mv_ocupacion_diaria TO parkos_app;"
    )


def downgrade() -> None:
    """Drop the MV (drops its indexes too). Mirrors 0024 downgrade."""
    op.execute(
        "DROP MATERIALIZED VIEW IF EXISTS prod.mv_ocupacion_diaria;"
    )


__all__ = ["downgrade", "upgrade"]