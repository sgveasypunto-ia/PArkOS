"""pull RLS for ``envio_dian`` (now a ``cloud_to_branch`` / ``single_branch`` entry).

Revision ID: 0096_pull_rls_envio_dian
Revises: 0095_deterministic_catalog_seed_uuids

``envio_dian`` is cloud-authored (the cloud is the only egress to the DIAN
provider) and returns ``cufe`` / ``estado`` to the branch that issued the
document through ``POST /sync/pull``. Migration 0085 (ADR-005) put a database
barrier under every pulled table; this one adds ``envio_dian`` to it, with the
same shape as the other ``owned`` tables (``uuid_sucursal = pull branch``):

* ``rol_sync_pull`` gets ``SELECT`` only (the pull reads as that role; without
  the grant the first pull of a branch would fail with ``permission denied``);
* ``ENABLE ROW LEVEL SECURITY`` (never ``FORCE``: the table owner and the
  migration owner keep bypassing it);
* ``pull_rls_app_envio_dian``: permissive ``rol_app`` policy (``USING (true)``)
  so the cloud dispatcher, the routers and the sweep behave exactly as before;
* ``pull_rls_envio_dian``: ``SELECT`` for ``rol_sync_pull`` limited to the
  pulling branch's own rows, failing closed when ``parkos.pull_sucursal`` is
  unset (``uuid_sucursal = NULL`` matches nothing).

**Append-only contract untouched.** ``envio_dian`` is ``[L-W]``, not ``[A]``;
its ``REVOKE UPDATE, DELETE`` + narrow ``UPDATE (payload)`` grant (0021) are
not touched, no trigger changes, no table is created, and ``rol_sync_pull``
holds no write privilege. RLS only adds a read filter. No row is ever modified
or deleted by this migration or its downgrade.

**Idempotent.** Policies are ``DROP ... IF EXISTS`` + ``CREATE``; the grant and
``ENABLE`` are repeatable. The role itself is created by 0085.
"""

from __future__ import annotations

from alembic import op

revision = "0096_pull_rls_envio_dian"
down_revision = "0095_deterministic_catalog_seed_uuids"
branch_labels = None
depends_on = None

ROLE = "rol_sync_pull"
TABLE = "envio_dian"
_BRANCH = "prod.fn_pull_branch()"
_USING = f"uuid_sucursal = {_BRANCH}"


def upgrade() -> None:
    """Grant, enable RLS and create both policies on ``prod.envio_dian`` (idempotent)."""
    op.execute("SET LOCAL lock_timeout = '5s'")
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


def downgrade() -> None:
    """Drop both policies, disable RLS and revoke the grant (no row is touched)."""
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
