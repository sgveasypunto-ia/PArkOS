"""BUG-#7 (qa-2026-09-17-2-new-bugs) — add ``fecha_retencion_hasta`` column
to ``prod.idempotency_keys``.

Bug 7 surfaced during QA replay on 2026-09-17: ``parkos_core.models.base.RetentionMixin``
declares ``fecha_retencion_hasta: Mapped[date | None]`` for every ``[A]`` table
that inherits from ``AppendOnlyBase`` (``prod.idempotency_keys`` is ``[A]`` per
AGENTS.md §1). Migration ``0003_add_idempotency_keys_and_revoked_sync_jwts``
created the table without the column, so the ORM-generated
``SELECT prod.idempotency_keys.uuid, ... prod.idempotency_keys.fecha_retencion_hasta``
crashed with ``UndefinedColumn`` on every POST that runs through
``parkosFetch``'s ``idempotency_mw`` middleware.

This migration brings the schema in sync with the ORM:

  1. ``ALTER TABLE prod.idempotency_keys ADD COLUMN IF NOT EXISTS
     fecha_retencion_hasta DATE NULL`` (PG11+ instant; no rewrite).
  2. ``downgrade()`` drops the column cleanly.

The live branch-db was patched manually during QA replay (see memory
#1806); this migration is the backport for fresh containers and the cloud
side via the existing
``prod.idempotency_keys`` sync queue entry.

Idempotency: ``ADD COLUMN IF NOT EXISTS`` lets the migration run cleanly
on a live DB already carrying the column (replays are no-ops). No
backfill needed — ``NULL`` is the correct value (idempotency keys expire
within 24h via the separate ``expires_at`` column; DIAN retention on
this table is intentionally N/A per the model docstring).

KEPT IN SYNC WITH: ``specs/operations/spec.md`` REQ-OPS-133 (Bug 3 of
qa-2026-09-17-bug-remediation) — schema-conformance gate scope
expansion.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0036_add_fecha_retencion_to_idempotency_keys"
down_revision = "0035_add_observaciones_to_sesion"  # follow 0035 in the chain
branch_labels = None
depends_on = None


def upgrade() -> None:
    """ALTER TABLE prod.idempotency_keys ADD COLUMN IF NOT EXISTS fecha_retencion_hasta DATE NULL.

    PG11+ metadata-only operation; no table rewrite. Date type matches
    ``RetentionMixin.fecha_retencion_hasta: Mapped[date | None]`` in
    ``backend/packages/parkos_core/src/parkos_core/models/base.py``.
    """
    # Pre-flight: confirm prod.idempotency_keys exists so we don't silently
    # add a column to the wrong table on a misconfigured environment.
    op.execute(
        """
        DO $$
        DECLARE
            _n_idem bigint;
        BEGIN
            SELECT count(*) INTO _n_idem
                FROM pg_catalog.pg_class
                WHERE relname='idempotency_keys' AND relnamespace='prod'::regnamespace;
            IF _n_idem IS NULL OR _n_idem = 0 THEN
                RAISE EXCEPTION '0036_preflight_abort: tabla prod.idempotency_keys '
                                'no existe. Aplique MIGRATION 0003 antes.';
            END IF;
            RAISE NOTICE '0036_preflight: prod.idempotency_keys exists; '
                         'ADD COLUMN IF NOT EXISTS fecha_retencion_hasta DATE NULL '
                         '(PG11+ instant; idempotent on re-apply).';
        END $$;
        """
    )

    # IF NOT EXISTS makes this migration safe to re-apply on a live DB
    # that already received the column via a manual hot-fix (memory #1806).
    op.execute(
        "ALTER TABLE prod.idempotency_keys "
        "ADD COLUMN IF NOT EXISTS fecha_retencion_hasta DATE NULL;"
    )


def downgrade() -> None:
    """DROP COLUMN IF EXISTS fecha_retencion_hasta: pure DDL, no rewrite.

    The live branch-db can lose the column cleanly; the ORM will raise
    ``UndefinedColumn`` again until a re-``upgrade()``. Tests of
    ``parkosFetch`` idempotency replay will SKIP instead of FAIL.
    """
    op.execute(
        "ALTER TABLE prod.idempotency_keys "
        "DROP COLUMN IF EXISTS fecha_retencion_hasta;"
    )


__all__ = ["downgrade", "upgrade"]
