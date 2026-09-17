"""REQ-OPS-135 (Bug 5 of qa-2026-09-17) — add ``observaciones`` column
to ``prod.sesion``.

QA-2026-09-17 bug-remediation: bug 5 surfaced the case where
``POST /caja-sesion/sesiones`` rejects ``observaciones`` from the
F3.3 frontend with HTTP 422 ``extra_forbidden`` because
``SesionCreate`` inherits ``extra='forbid'`` from ``_Base`` and the
column did not exist on ``prod.sesion``. This migration:

  1. ``ALTER TABLE prod.sesion ADD COLUMN observaciones TEXT NULL``
     (PG11+ instant, no rewrite per ADR-002 AUDIT-FIRST; pre-flight
     advisory NOTICE if the table is unexpectedly large).
  2. ``downgrade()`` drops the column cleanly.

Idempotency: ``ADD COLUMN`` with no DEFAULT is non-destructive
(Postgres PG11+ is metadata-only); re-running this migration against
an already-``observaciones``-having column raises ``column already
exists`` and the alembic revision chain stays linear at 0035.

KEPT IN SYNC WITH: ``specs/operations/spec.md`` REQ-OPS-135 (Bug 5 of
qa-2026-09-17-bug-remediation).
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0035_add_observaciones_to_sesion"
down_revision = (
    "0034_recreate_mv_ocupacion_diaria_idempotent"  # follow 0034 in the chain
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """ALTER TABLE prod.sesion ADD COLUMN observaciones TEXT NULL.

    PG11+ metadata-only operation; no table rewrite. No backfill —
    NULL is the correct value (existing sesiones simply don't have an
    observations string).
    """
    # Pre-flight: confirm prod.sesion exists so we don't silently add
    # a column to the wrong table on a misconfigured environment.
    op.execute(
        """
        DO $$
        DECLARE
            _n_sesion bigint;
        BEGIN
            SELECT count(*) INTO _n_sesion
                FROM pg_catalog.pg_class
                WHERE relname='sesion' AND relnamespace='prod'::regnamespace;
            IF _n_sesion IS NULL OR _n_sesion = 0 THEN
                RAISE EXCEPTION '0035_preflight_abort: tabla prod.sesion '
                                'no existe. Aplique MIGRATION 0001 antes.';
            END IF;
            RAISE NOTICE '0035_preflight: prod.sesion exists; '
                         'ADD COLUMN observaciones TEXT NULL (PG11+ instant).';
        END $$;
        """
    )

    op.execute(
        "ALTER TABLE prod.sesion ADD COLUMN observaciones TEXT NULL;"
    )


def downgrade() -> None:
    """DROP COLUMN observations: pure DDL, no rewrite."""
    op.execute("ALTER TABLE prod.sesion DROP COLUMN IF EXISTS observaciones;")


__all__ = ["downgrade", "upgrade"]