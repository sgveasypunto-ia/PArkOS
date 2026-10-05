"""0076_seed_configuracion_caja_sync_catalog -- add the configuracion_caja row
to the ``prod.sync_catalog`` projection.

Revision ID: 0076_seed_configuracion_caja_sync_catalog
Revises: 0075_fix_ensure_partitions_overlap_and_grants
Create Date: 2026-10-04 00:00:00.000000

THE PROBLEM THIS PINS
---------------------
``prod.configuracion_caja`` (migration ``0066_add_configuracion_caja.py``)
shipped with its ``AFTER INSERT ... prod.fn_enqueue_sync()`` trigger but
without a ``SYNC_CATALOG`` entry. Because ``jobs/sync_cloud.py`` resolves
every queue row through ``SYNC_CATALOG_BY_NAME.get(row.tabla)`` and calls
``mark_failed(..., "unknown_table")`` on a miss, every caja configuration an
administrator saved was enqueued and then permanently parked as failed --
no branch POS ever received one. The Python-side fix adds the entry to
``sync/catalog/entries/sync_entries_v.py``; this migration keeps the DB-side
projection in step with it.

WHAT ``prod.sync_catalog`` IS (AND IS NOT)
------------------------------------------
``0029b_seed_sync_catalog.py`` created this table purely so MIGRATION 0030's
pre-flight ``DO $$`` invariant (``FROM prod.sync_catalog WHERE entity_name =
...``) had something to query. It is a **documentation projection** of the
in-memory Python catalog, mirrored by construction. The runtime sync engine
does NOT read it -- it imports ``SYNC_CATALOG_BY_NAME`` from Python. So this
migration does not change replication behavior; it exists so the projection
does not silently drift from the 47-entry Python catalog, which is exactly
the class of drift that let ``configuracion_caja`` go unclassified for ten
migrations.

``0029b``'s own seed comment states the contract this migration honors:
"Update in lockstep with the Python catalog if entries are ever added."

Only ``configuracion_caja`` is inserted here. The other two tables this
reconciliation classified are deliberately absent, and must stay absent:
``ingreso_consecutivo_contador`` went to ``LOCAL_ONLY_CATALOG`` and
``sync_cursor`` to ``OUT_OF_CATALOG``, and ``prod.sync_catalog`` projects
``SYNC_CATALOG`` only (``0029b``'s seed is the 46 ``SYNC_CATALOG`` entries,
nothing else).

IDEMPOTENCY
-----------
``INSERT ... ON CONFLICT (entity_name) DO NOTHING`` -- the same guard
``0029b`` uses, so a replay is a no-op. ``entity_name`` is the PRIMARY KEY.

The upgrade is also safe on a database provisioned AFTER this migration
landed: ``0029b`` seeds its own 46 rows first and this one adds the 47th,
regardless of whether the two run back to back or years apart.

DOWNGRADE
---------
Deletes exactly the one row it inserted. ``prod.sync_catalog`` carries
``REVOKE UPDATE, DELETE ... FROM rol_app`` but no ``fn_<table>_inmutable()``
trigger (``0029b`` explains why: it is a projection, not a regulatory data
table), and migrations run as the table owner, so the DELETE is permitted.
Alembic's transactional DDL makes the whole step atomic.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0076_seed_configuracion_caja_sync_catalog"
down_revision = "0075_fix_ensure_partitions_overlap_and_grants"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

# Mirrored from ``sync/catalog/entries/sync_entries_v.py::_CONFIGURACION_CAJA``.
_ENTITY_NAME = "configuracion_caja"
_AUDIT_CLASS = "V"


def upgrade() -> None:
    """Insert the ``configuracion_caja`` projection row (idempotent)."""
    op.execute(_LOCK_TIMEOUT_SQL)
    op.execute(
        f"""
        INSERT INTO prod.sync_catalog (entity_name, audit_class)
        VALUES ('{_ENTITY_NAME}', '{_AUDIT_CLASS}')
        ON CONFLICT (entity_name) DO NOTHING;
        """
    )


def downgrade() -> None:
    """Remove the single row this migration added."""
    op.execute(_LOCK_TIMEOUT_SQL)
    op.execute(
        f"DELETE FROM prod.sync_catalog WHERE entity_name = '{_ENTITY_NAME}';"
    )


__all__ = ["down_revision", "downgrade", "revision", "upgrade"]
