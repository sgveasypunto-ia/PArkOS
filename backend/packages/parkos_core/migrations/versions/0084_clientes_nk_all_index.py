"""MIGRATION 0084 -- full natural-key index on ``prod.clientes``.

Revision ID: 0084_clientes_nk_all_index
Revises: 0083_pull_scope_indexes
Create Date: 2026-10-05 00:00:00.000000

**Scope.** The derived pull scope of ``clientes_b2b`` (``sync/motor/pull_scope.py``)
resolves a b2b row's cliente by NATURAL KEY across ALL versions: ``uuid_cliente``
keeps pointing at the closed version after a [V] version bump, so the key of any
version (open or closed) is compared. ``ix_clientes_nk_open`` (0008) is partial
(``WHERE vigente_hasta IS NULL``) and cannot serve closed versions; without an
index the planner hashes every cliente version on each pull (measured 16 ms vs
0.4 ms on 20k clientes, linear in the table).

This adds the same expression WITHOUT the partial predicate::

    (tipo_identificador, regexp_replace(numero_identificacion, '[^0-9A-Za-z]', '', 'g'))

The expression must stay identical to ``ix_clientes_nk_open`` and to
``pull_scope._nk_numero`` or the planner cannot use it.

**No REVOKE / trigger needed.** Index only: no table created, no privilege
relaxed, no row mutation path changed. ``clientes`` is a ``[V]`` table and not a
pg_partman parent, so a plain ``CREATE INDEX`` is the correct form.

**Idempotent.** ``CREATE INDEX IF NOT EXISTS`` with an explicit name in schema
``prod``; the downgrade is ``DROP INDEX IF EXISTS``. Plain (non-CONCURRENT)
build: Alembic runs this inside a transaction; ``clientes`` is a master table of
modest size, so the brief write-lock is acceptable.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0084_clientes_nk_all_index"
down_revision = "0083_pull_scope_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the full natural-key index on clientes (idempotent)."""
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_clientes_nk
        ON prod.clientes (
            tipo_identificador,
            regexp_replace(numero_identificacion, '[^0-9A-Za-z]', '', 'g')
        )
        """
    )


def downgrade() -> None:
    """Drop exactly the index created by :func:`upgrade`."""
    op.execute("DROP INDEX IF EXISTS prod.ix_clientes_nk")
