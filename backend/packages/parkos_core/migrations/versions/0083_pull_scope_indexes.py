"""MIGRATION 0083 -- indexes backing the SQL-scoped ``POST /sync/pull``.

Revision ID: 0083_pull_scope_indexes
Revises: 0082_sync_catalog_inmutable_trigger
Create Date: 2026-10-05 00:00:00.000000

**Scope.** The pull now filters in SQL (``sync/motor/pull_scope.py``) and pages
each catalog table with ``WHERE <scope> AND created_at >= :floor ORDER BY
created_at, uuid LIMIT :n``. Every ``single_branch`` / ``subscription`` /
``all_branches_with_override`` table therefore needs ``(uuid_sucursal,
created_at)`` to serve that shape without scanning the table, and the two
derived-scope lookups planned on top of it (clientes reached through a
subscription or an issued invoice) need ``(uuid_sucursal, uuid_cliente)``.

Only indexes verified MISSING at Phase 0 (against the live DB) are created:

  * ``(uuid_sucursal, created_at)`` on ``tarifas_sucursal``, ``documentos``,
    ``cantidad_vehiculos_sucursal``, ``resolucion_facturacion``,
    ``configuracion_tolerancias``, ``configuracion_seguridad``,
    ``usuarios_sucursal``, ``subscripciones_cliente``.
  * ``subscripciones_cliente (uuid_sucursal, uuid_cliente)``.
  * ``factura_electronica (uuid_sucursal, uuid_cliente)``.

``subscripcion_vehiculos`` is already covered by its UK.

**No REVOKE / trigger needed.** This migration only adds indexes. It creates
no table and relaxes no privilege, so the "REVOKE + BEFORE UPDATE OR DELETE in
the same migration" rule for ``[A]`` tables does not apply (no row mutation
path changes). ``factura_electronica`` is an ``[L-E]`` table and is NOT
partitioned (``0001``: no ``PARTITION BY``), so a plain ``CREATE INDEX`` is
the correct form for every target; none of them is a pg_partman parent.

**Idempotent.** ``CREATE INDEX IF NOT EXISTS`` with explicit names in schema
``prod``; the downgrade is ``DROP INDEX IF EXISTS`` for exactly these names.
Plain (non-CONCURRENT) builds: Alembic runs this inside a transaction, and the
tables involved are small catalog/configuration tables, so the brief
write-lock is acceptable.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0083_pull_scope_indexes"
down_revision = "0082_sync_catalog_inmutable_trigger"
branch_labels = None
depends_on = None

# (index name, table, columns)
_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_tarifas_sucursal_sucursal_created_at", "tarifas_sucursal", "uuid_sucursal, created_at"),
    ("ix_documentos_sucursal_created_at", "documentos", "uuid_sucursal, created_at"),
    (
        "ix_cantidad_vehiculos_sucursal_sucursal_created_at",
        "cantidad_vehiculos_sucursal",
        "uuid_sucursal, created_at",
    ),
    (
        "ix_resolucion_facturacion_sucursal_created_at",
        "resolucion_facturacion",
        "uuid_sucursal, created_at",
    ),
    (
        "ix_configuracion_tolerancias_sucursal_created_at",
        "configuracion_tolerancias",
        "uuid_sucursal, created_at",
    ),
    (
        "ix_configuracion_seguridad_sucursal_created_at",
        "configuracion_seguridad",
        "uuid_sucursal, created_at",
    ),
    ("ix_usuarios_sucursal_sucursal_created_at", "usuarios_sucursal", "uuid_sucursal, created_at"),
    (
        "ix_subscripciones_cliente_sucursal_created_at",
        "subscripciones_cliente",
        "uuid_sucursal, created_at",
    ),
    (
        "ix_subscripciones_cliente_sucursal_cliente",
        "subscripciones_cliente",
        "uuid_sucursal, uuid_cliente",
    ),
    (
        "ix_factura_electronica_sucursal_cliente",
        "factura_electronica",
        "uuid_sucursal, uuid_cliente",
    ),
)


def upgrade() -> None:
    """Create the pull-scope indexes (idempotent)."""
    for name, table, columns in _INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON prod.{table} ({columns});")


def downgrade() -> None:
    """Drop exactly the indexes created by :func:`upgrade`."""
    for name, _table, _columns in reversed(_INDEXES):
        op.execute(f"DROP INDEX IF EXISTS prod.{name};")
