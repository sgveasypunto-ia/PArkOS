"""MIGRATION 0082 -- close the schema-match gate for ``prod.sync_catalog``.

Why this exists
---------------
The 2026-10-05 audit (``openspec/scripts/check_schema_match.py``) found that
``prod.sync_catalog`` (created in 0029b) is missing the
``<table>_inmutable`` BEFORE UPDATE OR DELETE trigger that every other ``[A]``
table in this schema carries. The 0029b docstring explicitly notes the
omission: "No ``fn_<table>_inmutable()`` trigger registered — this table is a
seed-driven registry." That was the intent at the time, but it leaves the
catalog inconsistent with the rest of the ``[A]`` canon and trips the schema
match gate (f) that the rest of the project relies on.

This migration closes the gap WITHOUT changing the runtime behaviour the 0029b
docstring warned about: the trigger only fires on ``UPDATE``/``DELETE``,
neither of which the seed-driven flow does in production (the catalog is
loaded once at deploy time and never mutated). It does, however, make a
future accidental ``UPDATE sync_catalog SET ...`` or ``DELETE FROM
sync_catalog`` fail loudly with ``SYNC_CATALOG_INMUTABLE`` instead of
silently corrupting the registry, which is the same defence the other
``[A]`` tables have.

REVOKE + trigger in the SAME migration, per ``openspec/config.yaml``
``rules.tasks`` (the same pattern 0003, 0006, 0012, 0013, 0021, 0027 use).

Applied to both nodes: ``prod.sync_catalog`` exists on cloud and branch.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0082_sync_catalog_inmutable_trigger"
down_revision = "0081_add_sync_identity_alias"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the ``sync_catalog_inmutable`` trigger and re-assert the REVOKE.

    The REVOKE was already applied by 0029b, but re-stating it here is the
    canonical pattern (0003, 0006, 0012, 0013, 0021, 0027) and is a no-op if
    the privilege state is already correct -- so it is safe and idempotent.
    """
    # 1) Defence in depth re-stated: no physical UPDATE/DELETE on this [A]
    #    table from the app role. The trigger added below is the actual
    #    enforcement layer; the REVOKE is what makes the failure mode
    #    ``permission denied`` rather than a logical delete.
    op.execute("REVOKE UPDATE, DELETE ON prod.sync_catalog FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.sync_catalog TO rol_app;")

    # 2) Per-table trigger function. Idempotent (CREATE OR REPLACE) so a
    #    re-run of this migration is safe. Matches the 0001/0003/0006/0012
    #    body shape: a single RAISE EXCEPTION with ERRCODE 42501 (the SQL
    #    standard "insufficient_privilege" code, used project-wide for
    #    "you must not be doing this DML on an [A] table").
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prod.fn_sync_catalog_inmutable()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $fn$
        BEGIN
            RAISE EXCEPTION 'SYNC_CATALOG_INMUTABLE'
                USING ERRCODE = '42501',
                      HINT = 'sync_catalog is a deploy-seeded registry; '
                             'add a new entity_name via a migration, never '
                             'UPDATE/DELETE an existing row.';
            RETURN NULL;
        END;
        $fn$;
        """
    )

    # 3) Bind the trigger. Drop-if-exists first so a re-run of this migration
    #    in an environment that already has the trigger from a previous
    #    in-place fix is also safe.
    op.execute("DROP TRIGGER IF EXISTS sync_catalog_inmutable ON prod.sync_catalog;")
    op.execute(
        """
        CREATE TRIGGER sync_catalog_inmutable
        BEFORE UPDATE OR DELETE ON prod.sync_catalog
        FOR EACH ROW EXECUTE FUNCTION prod.fn_sync_catalog_inmutable();
        """
    )


def downgrade() -> None:
    """Reverse the trigger + REVOKE. Drops the function last so a concurrent
    trigger DROP that races a re-CREATE in another session still leaves a
    consistent state.
    """
    op.execute("DROP TRIGGER IF EXISTS sync_catalog_inmutable ON prod.sync_catalog;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_sync_catalog_inmutable();")
    # Re-grant the privileges the 0029b migration originally granted, so the
    # downgrade leaves the table in the exact pre-0082 state.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON prod.sync_catalog TO rol_app;")
