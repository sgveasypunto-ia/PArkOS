"""HU-F1.9 / MIGRATION 0027 -- one_factura_per_salida + init_pago trigger +
REVOKE re-assertion.

Revision ID: 0027_one_factura_per_salida_and_init_pago_trigger_and_revoke
Revises: 0026_seed_impuestos_iva_and_one_exit_per_ingreso (F1.7 chain head)
Create Date: 2026-09-14

**Scope.** Four operations in strict order:

  1. **Pre-flight (KD-7 F1.6 pattern)**: ``DO $$`` block aborts the
     migration with a typed ``0027_preflight_abort`` exception if any
     of the 9 expected tables does not exist (a fresh deployment that
     never ran migrations 0001-0026 would leave them missing).
     Emits ``RAISE NOTICE`` with the row counts for the alembic log.

  2. **Partial unique index ``one_factura_per_salida`` (R1 closure)**:
     ``CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
     one_factura_per_salida ON prod.facturas (uuid_salida) WHERE
     uuid_salida IS NOT NULL``. ``CONCURRENTLY`` for no lock on
     reads/writes; ``IF NOT EXISTS`` for idempotency.
     ``prod.facturas`` is NOT range-partitioned (verified pre-apply via
     ``models/L_E/facturas.py`` lines 62-72 — no
     ``postgresql_partition_by``), so a partial unique index is
     feasible. Closes the concurrent-cajero race condition: even if two
     T1-aligned POSTs see the same ``uuid_salida`` as "facturable", the
     second INSERT raises ``UniqueViolation`` (Postgres errcode 23505),
     which the repo maps to ``FacturaDuplicadaError → HTTP 409``.

  3. **BEFORE INSERT trigger ``fn_factura_pagos_init_pago_uniqueness``
     (R3 closure)**: analogía migration 0004
     (``fn_factura_pagos_reverso_uniqueness``). Rejects a second
     ``tipo_movimiento IN ('pago', 'ajuste')`` row for the same
     ``uuid_factura`` (the initial pago defense-in-depth). Works
     across partitions because ``prod.factura_pagos`` IS range
     partitioned by ``fecha_retencion_hasta`` (partial UK infeasible;
     trigger is the only DB-layer defense). Reversos are NOT blocked
     here — they go through ``reverse_payment`` (F1.13 reuse).

  4. **REVOKE re-assertion + ``fn_*_inmutable`` trigger re-install for
     the 4 [A] tables**: ``factura_detalle``, ``factura_impuestos``,
     ``factura_pagos``, ``factura_electronica``. Defends against
     accidental privilege drift across deployments. Idempotent via
     ``CREATE OR REPLACE`` + ``DROP TRIGGER IF EXISTS`` + ``CREATE
     TRIGGER``.

**Idempotency.**
  - Op 1 ``DO $$`` is read-only.
  - Op 2 ``CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`` is the
    standard idempotent pattern; re-apply is a no-op (postgres notes
    index already present, returns).
  - Op 3 ``CREATE OR REPLACE FUNCTION`` + ``DROP TRIGGER IF EXISTS`` +
    ``CREATE TRIGGER`` is idempotent.
  - Op 4 mirrors Op 3.

**Downgrade.**
  1. ``DROP TRIGGER IF EXISTS factura_pagos_init_pago_uniqueness ON
     prod.factura_pagos`` (Op 3 reverse).
  2. ``DROP INDEX IF EXISTS prod.one_factura_per_salida`` (Op 2
     reverse).
  3. Trigger re-install reverse (Op 4 reverse) — drop the
     ``fn_*_inmutable`` triggers (those are re-installed by subsequent
     migrations but the DDL is benign).
  4. ``CREATE OR REPLACE FUNCTION fn_*_inmutable() ... body ... ``
     not strictly necessary on downgrade (functions persist across
     migration downgrades).
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0027_one_factura_per_salida_and_init_pago_trigger_and_revoke"
down_revision = "0026_seed_impuestos_iva_and_one_exit_per_ingreso"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------
    # Op 1: pre-flight `DO $$` (KD-7 F1.6 pattern, F1.7 applied to 3 tables)
    # ---------------------------------------------------------------
    op.execute(
        """
        DO $$
        DECLARE
            _n_facturas bigint;
            _n_factura_detalle bigint;
            _n_factura_impuestos bigint;
            _n_factura_pagos bigint;
            _n_factura_electronica bigint;
            _n_clientes bigint;
            _n_impuestos bigint;
            _n_tarifas_sucursal bigint;
            _n_salidas bigint;
        BEGIN
            SELECT count(*) INTO _n_facturas
                FROM pg_catalog.pg_class
                WHERE relname = 'facturas' AND relnamespace = 'prod'::regnamespace;
            SELECT count(*) INTO _n_factura_detalle
                FROM pg_catalog.pg_class
                WHERE relname = 'factura_detalle' AND relnamespace = 'prod'::regnamespace;
            SELECT count(*) INTO _n_factura_impuestos
                FROM pg_catalog.pg_class
                WHERE relname = 'factura_impuestos' AND relnamespace = 'prod'::regnamespace;
            SELECT count(*) INTO _n_factura_pagos
                FROM pg_catalog.pg_class
                WHERE relname = 'factura_pagos' AND relnamespace = 'prod'::regnamespace;
            SELECT count(*) INTO _n_factura_electronica
                FROM pg_catalog.pg_class
                WHERE relname = 'factura_electronica' AND relnamespace = 'prod'::regnamespace;
            SELECT count(*) INTO _n_clientes
                FROM pg_catalog.pg_class
                WHERE relname = 'clientes' AND relnamespace = 'prod'::regnamespace;
            SELECT count(*) INTO _n_impuestos
                FROM pg_catalog.pg_class
                WHERE relname = 'impuestos' AND relnamespace = 'prod'::regnamespace;
            SELECT count(*) INTO _n_tarifas_sucursal
                FROM pg_catalog.pg_class
                WHERE relname = 'tarifas_sucursal' AND relnamespace = 'prod'::regnamespace;
            SELECT count(*) INTO _n_salidas
                FROM pg_catalog.pg_class
                WHERE relname = 'salidas' AND relnamespace = 'prod'::regnamespace;

            IF _n_facturas IS NULL OR _n_facturas = 0 THEN
                RAISE EXCEPTION '0027_preflight_abort: tabla prod.facturas no existe. '
                                'Aplique migrations 0001-0026 antes.';
            END IF;
            IF _n_factura_detalle IS NULL OR _n_factura_detalle = 0 THEN
                RAISE EXCEPTION '0027_preflight_abort: tabla prod.factura_detalle no existe.';
            END IF;
            IF _n_factura_impuestos IS NULL OR _n_factura_impuestos = 0 THEN
                RAISE EXCEPTION '0027_preflight_abort: tabla prod.factura_impuestos no existe.';
            END IF;
            IF _n_factura_pagos IS NULL OR _n_factura_pagos = 0 THEN
                RAISE EXCEPTION '0027_preflight_abort: tabla prod.factura_pagos no existe.';
            END IF;
            IF _n_factura_electronica IS NULL OR _n_factura_electronica = 0 THEN
                RAISE EXCEPTION '0027_preflight_abort: tabla prod.factura_electronica no existe.';
            END IF;
            IF _n_clientes IS NULL OR _n_clientes = 0 THEN
                RAISE EXCEPTION '0027_preflight_abort: tabla prod.clientes no existe.';
            END IF;
            IF _n_impuestos IS NULL OR _n_impuestos = 0 THEN
                RAISE EXCEPTION '0027_preflight_abort: tabla prod.impuestos no existe. '
                                'Aplique MIGRATION 0026 (IVA seed).';
            END IF;
            IF _n_tarifas_sucursal IS NULL OR _n_tarifas_sucursal = 0 THEN
                RAISE EXCEPTION '0027_preflight_abort: tabla prod.tarifas_sucursal no existe.';
            END IF;
            IF _n_salidas IS NULL OR _n_salidas = 0 THEN
                RAISE EXCEPTION '0027_preflight_abort: tabla prod.salidas no existe. '
                                'Aplique MIGRATION 0026 + F1.7 ORM.';
            END IF;

            RAISE NOTICE '0027_preflight: 9/9 tablas OK '
                         '(facturas, factura_detalle, factura_impuestos, factura_pagos, '
                         'factura_electronica, clientes, impuestos, tarifas_sucursal, salidas)';
        END;
        $$;
        """
    )

    # ---------------------------------------------------------------
    # Op 2: partial unique index `one_factura_per_salida`
    # ---------------------------------------------------------------
    # `prod.facturas` is NOT partitioned (verified pre-apply) so a
    # partial unique index IS feasible. Closes TOCTOU race on
    # ``SELECT EXISTS(...) → INSERT`` between V1 and Step 9.
    op.execute(
        """
        CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
        one_factura_per_salida
        ON prod.facturas (uuid_salida)
        WHERE uuid_salida IS NOT NULL;
        """
    )

    # ---------------------------------------------------------------
    # Op 3: BEFORE INSERT trigger `fn_factura_pagos_init_pago_uniqueness`
    # ---------------------------------------------------------------
    # Analogía migration 0004 (`fn_factura_pagos_reverso_uniqueness`).
    # `prod.factura_pagos` IS range-partitioned on
    # `fecha_retencion_hasta`, so partial unique index for init-pago
    # uniqueness is INFEASIBLE — trigger is the only DB-layer defense.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prod.fn_factura_pagos_init_pago_uniqueness()
        RETURNS trigger AS $$
        BEGIN
            -- Only enforce on initial `pago` and `ajuste` movements.
            -- `reverso` rows are NOT subject to this check (they go
            -- through `reverse_payment` and `fn_factura_pagos_reverso_uniqueness`,
            -- which already exists from migration 0004).
            IF NEW.tipo_movimiento IN ('pago', 'ajuste') AND NEW.uuid_factura IS NOT NULL THEN
                IF EXISTS (
                    SELECT 1 FROM prod.factura_pagos
                    WHERE uuid_factura = NEW.uuid_factura
                      AND tipo_movimiento IN ('pago', 'ajuste')
                ) THEN
                    RAISE EXCEPTION
                        'factura_pagos_init_pago_uniqueness: '
                        'uuid_factura=% already has an initial pago row',
                        NEW.uuid_factura
                        USING ERRCODE = 'unique_violation';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        "DROP TRIGGER IF EXISTS factura_pagos_init_pago_uniqueness "
        "ON prod.factura_pagos;"
    )
    op.execute(
        "CREATE TRIGGER factura_pagos_init_pago_uniqueness "
        "BEFORE INSERT ON prod.factura_pagos "
        "FOR EACH ROW EXECUTE FUNCTION prod.fn_factura_pagos_init_pago_uniqueness();"
    )

    # ---------------------------------------------------------------
    # Op 4: REVOKE re-assertion + `fn_*_inmutable` re-install for 4 [A] tables
    # ---------------------------------------------------------------
    # `prod.factura_detalle` (REVOKE + idempotent fn_factura_detalle_inmutable
    # re-install). DROP + CREATE happen inside the conditional DO block so the
    # trigger only exists when its function exists (avoid dangling-trigger
    # references after a partial deployment).
    op.execute("REVOKE UPDATE, DELETE ON prod.factura_detalle FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.factura_detalle TO rol_app;")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE p.proname = 'fn_factura_detalle_inmutable'
                  AND n.nspname = 'prod'
            ) THEN
                DROP TRIGGER IF EXISTS factura_detalle_inmutable ON prod.factura_detalle;
                CREATE TRIGGER factura_detalle_inmutable
                    BEFORE UPDATE OR DELETE ON prod.factura_detalle
                    FOR EACH ROW EXECUTE FUNCTION prod.fn_factura_detalle_inmutable();
            END IF;
        END;
        $$;
        """
    )

    # `prod.factura_impuestos`
    op.execute("REVOKE UPDATE, DELETE ON prod.factura_impuestos FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.factura_impuestos TO rol_app;")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE p.proname = 'fn_factura_impuestos_inmutable'
                  AND n.nspname = 'prod'
            ) THEN
                DROP TRIGGER IF EXISTS factura_impuestos_inmutable ON prod.factura_impuestos;
                CREATE TRIGGER factura_impuestos_inmutable
                    BEFORE UPDATE OR DELETE ON prod.factura_impuestos
                    FOR EACH ROW EXECUTE FUNCTION prod.fn_factura_impuestos_inmutable();
            END IF;
        END;
        $$;
        """
    )

    # `prod.factura_pagos` (REVOKE re-assertion + idempotent re-install of
    # `fn_factura_pagos_inmutable` from migration 0004 + migration 0001).
    op.execute("REVOKE UPDATE, DELETE ON prod.factura_pagos FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.factura_pagos TO rol_app;")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE p.proname = 'fn_factura_pagos_inmutable'
                  AND n.nspname = 'prod'
            ) THEN
                DROP TRIGGER IF EXISTS factura_pagos_inmutable ON prod.factura_pagos;
                CREATE TRIGGER factura_pagos_inmutable
                    BEFORE UPDATE OR DELETE ON prod.factura_pagos
                    FOR EACH ROW EXECUTE FUNCTION prod.fn_factura_pagos_inmutable();
            END IF;
        END;
        $$;
        """
    )

    # `prod.factura_electronica` (L-E bi-temporal — no UPDATE/DELETE
    # privilege expected for rol_app, but defensive REVOKE re-assertion
    # matches F1.7's pattern).
    op.execute("REVOKE UPDATE, DELETE ON prod.factura_electronica FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.factura_electronica TO rol_app;")


def downgrade() -> None:
    # Reverse Op 4 first.
    op.execute("GRANT UPDATE, DELETE ON prod.factura_detalle TO rol_app;")
    op.execute("GRANT UPDATE, DELETE ON prod.factura_impuestos TO rol_app;")
    op.execute("GRANT UPDATE, DELETE ON prod.factura_pagos TO rol_app;")
    op.execute("GRANT UPDATE, DELETE ON prod.factura_electronica TO rol_app;")

    # Reverse Op 3.
    op.execute(
        "DROP TRIGGER IF EXISTS factura_pagos_init_pago_uniqueness "
        "ON prod.factura_pagos;"
    )
    op.execute("DROP FUNCTION IF EXISTS prod.fn_factura_pagos_init_pago_uniqueness();")

    # Reverse Op 2 (CONCURRENTLY index).
    op.execute("DROP INDEX IF EXISTS prod.one_factura_per_salida;")
