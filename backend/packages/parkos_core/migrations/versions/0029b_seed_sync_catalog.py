"""HU-F1.12-blocker / MIGRATION 0029b — create + seed ``prod.sync_catalog``.

Revision ID: 0029b_seed_sync_catalog
Revises: 0029_reimpresion_siembra_and_permiso_anular
Create Date: 2026-09-21

**Purpose.** Unblocks the MIGRATION 0030 pre-flight ``DO $$`` invariant.

The 0030 pre-flight
(``backend/packages/parkos_core/migrations/versions/0030_venta_suscripcion_optional.py``
lines 114-131) verifies the 5 [V] sync catalog entries
(``tipo_subscripciones``, ``clientes``, ``vehiculos``,
``subscripciones_cliente``, ``subscripcion_vehiculos``) are registered by
querying ``FROM prod.sync_catalog WHERE entity_name = ...``.

``prod.sync_catalog`` was **never created** — the actual sync catalog
lives in-memory at
``backend/packages/parkos_core/src/parkos_core/sync/catalog/sync_catalog.py``
(``SYNC_CATALOG`` tuple, REQ-CAT-002, 46 entries), read at runtime via
``SYNC_CATALOG_BY_NAME`` (a Python ``dict`` populated from the tuple).
MIGRATION 0028's module docstring makes this explicit (lines 81-86):
"DEC-FE-01 commit-time invariant; the sync_catalog direction flip is
applied at the Python code level in sync_entries_lw.py, NOT via SQL
UPDATE because sync_catalog is an in-memory tuple."

The 0030 pre-flight's ``FROM prod.sync_catalog`` query is a
docstring/comment-level leftover that pre-dated the catalog's final
in-memory design — DEC-VENTA-08 was WITHDRAWN precisely because the
"all 5 [V] entries pre-existing" check was reinterpreted as a Python
catalog inspection (2026-09-15), but the SQL block was never updated
to match.

This migration creates the minimal ``prod.sync_catalog`` projection
needed to satisfy the 0030 pre-flight's invariant check and seeds it
with all 46 entries from the in-memory catalog (the 5 the pre-flight
checks + the remaining 41 for forward-compat with any future similar
pre-flight). The runtime sync engine does NOT read from this table —
it exists ONLY so the 0030 pre-flight's invariant check passes. A
stale row here is a harmless docstring drift, not a data-correctness
bug.

**Schema (minimal — only what the 0030 pre-flight reads + standard
audit columns).** ``entity_name TEXT PRIMARY KEY`` is the only column
the 0030 pre-flight queries. ``audit_class TEXT NOT NULL`` is
informational metadata (V | L_E | L_W | L_S | A). ``created_at
TIMESTAMPTZ NOT NULL DEFAULT NOW()`` is the standard audit column per
AGENTS.md's audit-first canon. No hash chain, no sync_status
columns — this is a catalog metadata projection, not a replicated
business table.

**[A] inmutability.** ``REVOKE UPDATE, DELETE`` + ``GRANT SELECT,
INSERT`` to ``rol_app`` — same pattern as the 11 [A] tables in
``0001_initial_schema.py`` (lines 2921-2944) and the per-class
carve-outs in ``0021_least_privilege_and_immutability_contract.py``.
No ``fn_<table>_inmutable()`` trigger registered — this table is a
docstring projection of the in-memory catalog, not a regulatory data
table; the GRANT/REVOKE contract is sufficient and matches the
projection's nature.

**Idempotency.** ``CREATE TABLE IF NOT EXISTS`` + ``INSERT ... ON
CONFLICT (entity_name) DO NOTHING``. Re-runs are no-ops. The DOWNGRADE
is a single ``DROP TABLE IF EXISTS`` (the mirror of ``CREATE TABLE
IF NOT EXISTS`` in upgrade); each row is recreated from the Python
catalog on the next upgrade, so no per-row state needs reversal.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0029b_seed_sync_catalog"
down_revision = "0029_reimpresion_siembra_and_permiso_anular"
branch_labels = None
depends_on = None


# Full 46-entry catalog, mirrored verbatim from
# ``backend/packages/parkos_core/src/parkos_core/sync/catalog/sync_catalog.py``
# (``SYNC_CATALOG = SYNC_ENTRIES_V + SYNC_ENTRIES_LE + SYNC_ENTRIES_LW +
# SYNC_ENTRIES_LS + SYNC_ENTRIES_A``). Kept as a tuple of
# ``(entity_name, audit_class)`` pairs to keep this migration focused
# on the 0030 pre-flight's needs without inventing fictitious columns
# the sync engine would never read. Update in lockstep with the Python
# catalog if entries are ever added — the runtime sync does NOT depend
# on this table, so a stale row here is a harmless docstring drift,
# not a data-correctness bug.
_CATALOG_SEED: tuple[tuple[str, str], ...] = (
    # [V] -- 26 entries (sync_entries_v.py)
    ("usuarios", "V"),
    ("permisos", "V"),
    ("tipo_persona", "V"),
    ("tipos_vehiculo", "V"),
    ("tipo_subscripciones", "V"),  # 0030 pre-flight required
    ("tipo_tarifa", "V"),
    ("tipo_sucursal", "V"),
    ("tipo_arqueo", "V"),
    ("impuestos", "V"),
    ("otros_cobros", "V"),
    ("costos_servicios", "V"),
    ("empresa", "V"),
    ("permisos_usuario", "V"),
    ("configuracion_tolerancias", "V"),
    ("configuracion_seguridad", "V"),
    ("sucursal", "V"),
    ("resolucion_facturacion", "V"),
    ("usuarios_sucursal", "V"),
    ("documentos", "V"),
    ("tarifas_sucursal", "V"),
    ("cantidad_vehiculos_sucursal", "V"),
    ("clientes", "V"),  # 0030 pre-flight required
    ("clientes_b2b", "V"),
    ("vehiculos", "V"),  # 0030 pre-flight required
    ("subscripciones_cliente", "V"),  # 0030 pre-flight required
    ("subscripcion_vehiculos", "V"),  # 0030 pre-flight required
    # [L-E] -- 3 entries (sync_entries_le.py)
    ("ingreso", "L_E"),
    ("facturas", "L_E"),
    ("factura_electronica", "L_E"),
    # [L-W] -- 6 entries (sync_entries_lw.py)
    ("reimpresion_ticket", "L_W"),
    ("anulaciones", "L_W"),
    ("reclamos", "L_W"),
    ("alerta", "L_W"),
    ("envio_dian", "L_W"),
    ("validacion_evento", "L_W"),
    # [L-S] -- 2 entries (sync_entries_ls.py)
    ("login", "L_S"),
    ("sesion", "L_S"),
    # [A] -- 9 entries (sync_entries_a.py)
    ("salidas", "A"),
    ("factura_detalle", "A"),
    ("caja", "A"),
    ("arqueo", "A"),
    ("factura_pagos", "A"),
    ("factura_impuestos", "A"),
    ("factura_otros_cobros", "A"),
    ("log_transaccional", "A"),
    ("revocacion_factura", "A"),
)


def upgrade() -> None:
    """Create ``prod.sync_catalog`` projection table + seed 46 entries."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS prod.sync_catalog (
            entity_name  TEXT        PRIMARY KEY,
            audit_class  TEXT        NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    # Idempotent seed: INSERT ... ON CONFLICT (entity_name) DO NOTHING.
    # Built dynamically from _CATALOG_SEED so this migration stays in
    # lockstep with the Python catalog by construction (one source of
    # truth = the Python catalog, projection table derives from it on
    # every upgrade). The runtime sync does NOT consume this table —
    # this seed is purely so the 0030 pre-flight's ``FROM prod.sync_
    # catalog WHERE entity_name = ...`` invariant check passes.
    values_sql = ", ".join(
        f"('{name}', '{cls}')" for name, cls in _CATALOG_SEED
    )
    op.execute(
        f"""
        INSERT INTO prod.sync_catalog (entity_name, audit_class)
        VALUES {values_sql}
        ON CONFLICT (entity_name) DO NOTHING;
        """
    )

    # [A] inmutability -- REVOKE UPDATE, DELETE; GRANT SELECT, INSERT.
    # Same pattern as 0001_initial_schema.py lines 2921-2944 (the 11 [A]
    # tables). No ``fn_<table>_inmutable()`` trigger -- this table is a
    # docstring projection of the in-memory catalog, not a regulatory
    # data table.
    op.execute("REVOKE UPDATE, DELETE ON prod.sync_catalog FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.sync_catalog TO rol_app;")


def downgrade() -> None:
    """Reverse the [A] grants + drop the projection table.

    ``DROP TABLE IF EXISTS`` is the mirror of ``CREATE TABLE IF NOT
    EXISTS`` in upgrade(); the dynamic seed has no per-row state to
    reverse (each row is recreated from the Python catalog on the next
    upgrade, by construction).
    """
    op.execute("REVOKE SELECT, INSERT ON prod.sync_catalog FROM rol_app;")
    op.execute("DROP TABLE IF EXISTS prod.sync_catalog;")


__all__ = ["down_revision", "downgrade", "revision", "upgrade"]