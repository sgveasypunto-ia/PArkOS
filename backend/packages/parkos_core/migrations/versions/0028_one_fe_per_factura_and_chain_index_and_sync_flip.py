"""HU-F1.10 / MIGRATION 0028 — sync_flip + partial_UK + covering_index + GRANT.

Revision ID: 0028_one_fe_per_factura_and_chain_index_and_sync_flip
Revises: 0027_one_factura_per_salida_and_init_pago_trigger_and_revoke (F1.9 head)
Create Date: 2026-09-14

**Scope.** Four operations in strict order:

  1. **Pre-flight (KD-7 F1.6/F1.9 pattern)**: ``DO $$`` block aborts the
     migration with a typed ``0028_preflight_abort`` exception if any of
     the 4 expected tables does not exist
     (``factura_electronica``, ``envio_dian``, ``resolucion_facturacion``,
     ``facturas``). The DEC-FE-01 sync direction flip from
     ``cloud_to_branch`` to ``branch_to_cloud`` is enforced at the
     in-memory Python catalog level (``sync_entries_lw.py``); the
     migration's pre-flight verifies the catalog was updated by
     introspecting the running Python process via ``plpy`` is NOT
     available — instead, the migration carries a comment-block marker
     that the F1.10 alpha apply run flips inline (DEC-FE-01 commitment
     is recorded in the migration's module docstring + the entry file
     ``sync_entries_lw.py``).

  2. **Partial unique index ``one_fe_per_factura`` (REQ-OPS-067)**:
     ``CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
     one_fe_per_factura ON prod.factura_electronica (uuid_factura) WHERE
     uuid_factura IS NOT NULL``. ``CONCURRENTLY`` for no lock on
     reads/writes; ``IF NOT EXISTS`` for idempotency.
     ``prod.factura_electronica`` is NOT range-partitioned (verified
     pre-apply via ``models/L_E/factura_electronica.py`` lines 91-94),
     so a partial unique index is feasible. Defense in depth alongside
     the existing UK ``factura_electronica_uk01
     (uuid_resolucion_facturacion, consecutivo)``.

  3. **Covering index ``idx_envio_dian_chain_tip`` (REQ-OPS-068)**:
     ``CREATE INDEX CONCURRENTLY IF NOT EXISTS
     idx_envio_dian_chain_tip ON prod.envio_dian
     (uuid_factura_electronica, timestamp_evento DESC) WHERE
     uuid_factura_electronica IS NOT NULL``. Speeds up the GET JOIN to
     ``prod.v_factura_electronica_acuse``.

  4. **Defensive GRANT re-assertion** for ``factura_electronica``,
     ``envio_dian``, ``resolucion_facturacion``. Defends against
     accidental privilege drift across deployments.

**Idempotency.**
  - Op 1 ``DO $$`` is read-only.
  - Op 2 ``CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`` is the
    standard idempotent pattern; re-apply is a no-op.
  - Op 3 ``CREATE INDEX CONCURRENTLY IF NOT EXISTS`` matches.
  - Op 4 mirror matches F1.9's REVOKE/GRANT defensive re-assertion.

**Downgrade.** Reverse order:
  1. REVOKE (Op 4 reverse).
  2. DROP INDEX CONCURRENTLY IF EXISTS ``idx_envio_dian_chain_tip``
     (Op 3 reverse).
  3. DROP INDEX CONCURRENTLY IF EXISTS ``one_fe_per_factura`` (Op 2
     reverse).
  4. (Op 1 reverse is a no-op; the catalog flip is a separate
     code-level revert in ``sync_entries_lw.py``).

**DEC-FE-01 sync catalog flip.** The ``envio_dian`` entry in
``backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/
sync_entries_lw.py`` was changed from ``direction="cloud_to_branch"``
to ``direction="branch_to_cloud"`` in the same commit as this migration
file. The migration does NOT touch that file directly; the
``sync_entries_lw.py`` change is the source of truth for the runtime
catalog. F1.10 commits both atomically.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0028_one_fe_per_factura_and_chain_index_and_sync_flip"
down_revision = "0027_one_factura_per_salida_and_init_pago_trigger_and_revoke"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------
    # Op 1: pre-flight `DO $$` (KD-7 F1.6/F1.9 pattern) — verify 4
    # tables exist (DEC-FE-01 commit-time invariant; the sync_catalog
    # direction flip is applied at the Python code level in
    # sync_entries_lw.py, NOT via SQL UPDATE because sync_catalog is
    # an in-memory tuple).
    # ---------------------------------------------------------------
    op.execute(
        """
        DO $$
        DECLARE
            _n_factura_electronica bigint;
            _n_envio_dian bigint;
            _n_resolucion_facturacion bigint;
            _n_facturas bigint;
        BEGIN
            SELECT count(*) INTO _n_factura_electronica
                FROM pg_catalog.pg_class
                WHERE relname='factura_electronica' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_envio_dian
                FROM pg_catalog.pg_class
                WHERE relname='envio_dian' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_resolucion_facturacion
                FROM pg_catalog.pg_class
                WHERE relname='resolucion_facturacion' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_facturas
                FROM pg_catalog.pg_class
                WHERE relname='facturas' AND relnamespace='prod'::regnamespace;

            IF _n_factura_electronica IS NULL OR _n_factura_electronica = 0 THEN
                RAISE EXCEPTION '0028_preflight_abort: tabla prod.factura_electronica no existe. '
                                'Aplique migrations 0001-0027 antes.';
            END IF;
            IF _n_envio_dian IS NULL OR _n_envio_dian = 0 THEN
                RAISE EXCEPTION '0028_preflight_abort: tabla prod.envio_dian no existe. '
                                'Aplique migrations 0001-0027 antes.';
            END IF;
            IF _n_resolucion_facturacion IS NULL OR _n_resolucion_facturacion = 0 THEN
                RAISE EXCEPTION '0028_preflight_abort: tabla prod.resolucion_facturacion no existe. '
                                'Aplique migrations 0001-0027 antes.';
            END IF;
            IF _n_facturas IS NULL OR _n_facturas = 0 THEN
                RAISE EXCEPTION '0028_preflight_abort: tabla prod.facturas no existe. '
                                'Aplique migrations 0001-0027 antes.';
            END IF;

            RAISE NOTICE '0028_preflight: 4/4 tablas OK (factura_electronica, envio_dian, '
                         'resolucion_facturacion, facturas). DEC-FE-01 sync_catalog flip '
                         'applied via sync_entries_lw.py at the Python level (in-memory catalog).';
        END;
        $$;
        """
    )

    # ---------------------------------------------------------------
    # Op 2: partial unique index `one_fe_per_factura` (REQ-OPS-067).
    # Defense in depth against the V2 SELECT-before-INSERT TOCTOU
    # race; complements the existing UK01 (resolucion, consecutivo).
    # ---------------------------------------------------------------
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
            one_fe_per_factura
            ON prod.factura_electronica (uuid_factura)
            WHERE uuid_factura IS NOT NULL;
            """
        )

    # ---------------------------------------------------------------
    # Op 3: covering index `idx_envio_dian_chain_tip` (REQ-OPS-068).
    # Speeds up the GET JOIN to prod.v_factura_electronica_acuse.
    # ---------------------------------------------------------------
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS
            idx_envio_dian_chain_tip
            ON prod.envio_dian (uuid_factura_electronica, timestamp_evento DESC)
            WHERE uuid_factura_electronica IS NOT NULL;
            """
        )

    # ---------------------------------------------------------------
    # Op 4: defensive GRANT re-assertion for the 3 tables touched by
    # F1.10's handlers. Re-asserts rol_app's INSERT/SELECT privileges
    # in case drift accumulated between migrations.
    # ---------------------------------------------------------------
    op.execute("GRANT SELECT, INSERT ON prod.factura_electronica TO rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.envio_dian TO rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.resolucion_facturacion TO rol_app;")


def downgrade() -> None:
    # Reverse Op 4 first.
    op.execute("REVOKE SELECT, INSERT ON prod.factura_electronica FROM rol_app;")
    op.execute("REVOKE SELECT, INSERT ON prod.envio_dian FROM rol_app;")
    op.execute("REVOKE SELECT, INSERT ON prod.resolucion_facturacion FROM rol_app;")

    # Reverse Op 3 (CONCURRENTLY index).
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_envio_dian_chain_tip;")

    # Reverse Op 2 (CONCURRENTLY index).
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS one_fe_per_factura;")


__all__ = ["downgrade", "upgrade"]
