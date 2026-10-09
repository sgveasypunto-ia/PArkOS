"""MIGRATION 0099 -- ``configuracion_caja`` joins the sync catalog (cloud_to_branch).

Revision ID: 0099_sync_configuracion_caja
Revises: 0098_seed_alert_type_fe_consecutivo_duplicado

**Why.** The base de caja is parametrized in the cloud (``web_admin``) and read
by the branch when a shift opens. ``configuracion_caja`` was the only one of the
three ``configuracion_*`` tables missing from the sync catalog, so what an admin
configured never reached the branch database. It now travels as
``cloud_to_branch`` / ``all_branches_with_override`` (global default row with
``uuid_sucursal IS NULL`` plus one override per branch), exactly like
``configuracion_tolerancias`` and ``configuracion_seguridad``.

**What this migration adds** (the catalog entry itself lives in Python):

* ``ix_configuracion_caja_sucursal_created_at`` on ``(uuid_sucursal,
  created_at)`` -- the shape the SQL-scoped ``POST /sync/pull`` pages with
  (same as 0083 for the sibling tables);
* the database-level pull barrier of ADR-005 (same shape as 0085 for the
  siblings): ``SELECT`` for ``rol_sync_pull``, ``ENABLE ROW LEVEL SECURITY``
  (never ``FORCE``), a permissive ``rol_app`` policy and a ``rol_sync_pull``
  ``SELECT`` policy limited to the global default plus the pulling branch's own
  override, failing closed when ``parkos.pull_sucursal`` is unset;
* the informational ``prod.sync_catalog`` projection row (0029b), so the
  projection keeps mirroring the in-memory catalog.

**No data is touched.** No table is created, no privilege on a business table is
relaxed, no trigger changes, and ``rol_sync_pull`` holds no write privilege, so
the "REVOKE + BEFORE UPDATE OR DELETE in the same migration" rule for ``[A]``
tables does not apply (``configuracion_caja`` is ``[V]``). The downgrade only
removes what the upgrade added.

**Idempotent.** ``CREATE INDEX IF NOT EXISTS``, ``DROP POLICY IF EXISTS`` +
``CREATE POLICY``, repeatable ``GRANT``/``ENABLE`` and ``ON CONFLICT DO
NOTHING``. Plain (non-CONCURRENT) index build under ``lock_timeout = '5s'``;
the table is tiny (one row per branch at most).
"""

from __future__ import annotations

from alembic import op

revision = "0099_sync_configuracion_caja"
down_revision = "0098_seed_alert_type_fe_consecutivo_duplicado"
branch_labels = None
depends_on = None

ROLE = "rol_sync_pull"
TABLE = "configuracion_caja"
INDEX = "ix_configuracion_caja_sucursal_created_at"
_BRANCH = "prod.fn_pull_branch()"
# global default + per-branch override (fail closed when the branch is unset)
_USING = f"{_BRANCH} IS NOT NULL AND (uuid_sucursal IS NULL OR uuid_sucursal = {_BRANCH})"


def upgrade() -> None:
    """Index, pull RLS and catalog projection row for ``prod.configuracion_caja``."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(f"CREATE INDEX IF NOT EXISTS {INDEX} ON prod.{TABLE} (uuid_sucursal, created_at)")
    op.execute(f"GRANT SELECT ON prod.{TABLE} TO {ROLE}")
    op.execute(f"ALTER TABLE prod.{TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS pull_rls_app_{TABLE} ON prod.{TABLE}")
    op.execute(
        f"CREATE POLICY pull_rls_app_{TABLE} ON prod.{TABLE} "
        "FOR ALL TO rol_app USING (true) WITH CHECK (true)"
    )
    op.execute(f"DROP POLICY IF EXISTS pull_rls_{TABLE} ON prod.{TABLE}")
    op.execute(
        f"CREATE POLICY pull_rls_{TABLE} ON prod.{TABLE} FOR SELECT TO {ROLE} USING ({_USING})"
    )
    op.execute(
        f"""
        DO $do$
        BEGIN
            IF to_regclass('prod.sync_catalog') IS NOT NULL THEN
                INSERT INTO prod.sync_catalog (entity_name, audit_class)
                VALUES ('{TABLE}', 'V')
                ON CONFLICT (entity_name) DO NOTHING;
            END IF;
        END
        $do$
        """
    )


def downgrade() -> None:
    """Drop the policies, disable RLS, revoke the grant and drop the index (no row is touched)."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(f"DROP POLICY IF EXISTS pull_rls_{TABLE} ON prod.{TABLE}")
    op.execute(f"DROP POLICY IF EXISTS pull_rls_app_{TABLE} ON prod.{TABLE}")
    op.execute(f"ALTER TABLE prod.{TABLE} DISABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        DO $do$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                REVOKE SELECT ON prod.{TABLE} FROM {ROLE};
            END IF;
        END
        $do$
        """
    )
    op.execute(f"DROP INDEX IF EXISTS prod.{INDEX}")
