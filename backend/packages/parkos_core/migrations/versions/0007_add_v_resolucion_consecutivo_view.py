"""add prod.v_resolucion_consecutivo view (PR11c, T-PR11c-5)

Revision ID: 0007_add_v_resolucion_consecutivo_view
Revises: 0006_add_pairing_tokens_and_normalized_revoked_sync_jwts
Create Date: 2026-09-03 22:30:00.000000

PR11c closes Bug 5: ``prod.v_resolucion_consecutivo`` was referenced by
``atomic_next_consecutivo.py`` (T-PR11-05) as a TODO:

    TODO(T-PR11c): migrate to ``prod.v_resolucion_consecutivo`` VIEW; the
    raw MAX() is a stand-in matching the cloud_router.py bootstrap behavior.

This migration materialises the view: one row per currently-active
resolucion (``vigente_hasta IS NULL``), carrying the next available
``consecutivo`` (the prior cloud-side ``SELECT ... FOR UPDATE`` walk
is now a single view read) and a count of how many have been used so
far. The cloud_router can replace the raw ``MAX(consecutivo)`` query
with a single SELECT against the view in the follow-up PR.

Column map vs the spec snippet (``creates a view with the spec's
``uuid_resolucion_facturacion`` column name):

- ``rf.uuid`` is aliased to ``uuid_resolucion_facturacion`` so the
  view column matches the FK name ``factura_electronica.
  uuid_resolucion_facturacion`` callers already use.
- ``fe.uuid_resolucion_facturacion`` is the FK to ``rf.uuid`` (the
  resolucion PK) — there is no ``resolucion_facturacion.
  uuid_resolucion_facturacion`` column; the ``uuid`` PK is the
  identity.

Views are not subject to the ``REVOKE UPDATE, DELETE`` rule that
applies to the 11 ``[A]`` tables — PostgreSQL views inherit their
permissions from the underlying relations, and the migration does not
introduce a new writeable relation, so no ``REVOKE`` / inmutable
trigger work is required here. The view is read-only by design.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0007_add_v_resolucion_consecutivo_view"
down_revision = "0006_add_pairing_tokens_and_normalized_revoked_sync_jwts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ``prod.v_resolucion_consecutivo`` (Bug 5 — PR11c, T-PR11c-5).

    Idempotent: uses ``CREATE OR REPLACE VIEW`` so a re-run against an
    already-migrated DB is a no-op. The view is partitioned-safe (no
    user-defined functions in the SELECT body); PG17 evaluates the
    ``LEFT JOIN`` against the current ``prod.resolucion_facturacion``
    rows that satisfy ``vigente_hasta IS NULL``.
    """
    op.execute(
        """
        CREATE OR REPLACE VIEW prod.v_resolucion_consecutivo AS
        SELECT
            rf.uuid AS uuid_resolucion_facturacion,
            rf.prefijo,
            rf.rango_desde,
            rf.rango_hasta,
            (COALESCE(MAX(fe.consecutivo), rf.rango_desde - 1) + 1)
                AS consecutivo_siguiente,
            COUNT(fe.uuid) AS consecutivos_usados
        FROM prod.resolucion_facturacion rf
        LEFT JOIN prod.factura_electronica fe
            ON fe.uuid_resolucion_facturacion = rf.uuid
        WHERE rf.vigente_hasta IS NULL
        GROUP BY rf.uuid, rf.prefijo, rf.rango_desde, rf.rango_hasta
        """
    )


def downgrade() -> None:
    """Drop the view. DOWNGRADE IS LOSSY (the cloud router loses the
    fast-path resolver) but does not destroy any persisted data — the
    ``prod.resolucion_facturacion`` + ``prod.factura_electronica``
    rows are untouched.

    The TODO at ``atomic_next_consecutivo.py::44`` will surface again
    after the downgrade; the cloud_router falls back to the raw
    ``SELECT COALESCE(MAX(consecutivo), :start) FROM prod.factura_electronica``
    path.
    """
    op.execute("DROP VIEW IF EXISTS prod.v_resolucion_consecutivo")
