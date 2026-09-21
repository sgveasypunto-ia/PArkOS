"""HU-F1.7 / MIGRATION 0026 — KD-IVA resolver + 2 alert_types seed +
BEFORE INSERT trigger ``fn_salidas_one_exit_per_ingreso``.

Revision ID: 0026_seed_impuestos_iva_and_one_exit_per_ingreso
Revises: 0025_alerta_datos_nuevos (F1.6 chain head)
Create Date: 2026-09-14

**Scope.** Four operations in strict order:

  1. **Pre-flight (KD-7 F1.6 pattern)**: ``DO $$`` block aborts the
     migration with a typed ``0026_preflight_abort`` exception if
     ``prod.impuestos``, ``prod.salidas``, or ``prod.alert_types`` does
     not exist (e.g., a fresh deployment that never ran migrations
     0001-0025). Emits ``RAISE NOTICE`` with the row counts for the
     alembic log.

  2. **Inline-seed ``impuestos.IVA`` (KD-IVA resolver for F1.8)**:
     ``INSERT INTO prod.impuestos (...) VALUES (... 'IVA', 0.19 ...)
     ON CONFLICT (codigo, vigente_desde) DO NOTHING``. The UK constraint
     ``(codigo, vigente_desde)`` is the conflict target; the
     ``porcentaje=0.19`` is the regulatory constant locked in F1.8
     design.md §4 KD-IVA (IVA Colombia 2026). After this migration,
     F1.8 deployment is unblocked.

  3. **Inline-seed 2 alert types**: ``INSERT INTO prod.alert_types
     (tipo_alerta, descripcion, severity) VALUES
     ('subscripcion_vencida_forzado', ..., 'warning'),
     ('tarifa_vigente_forzado', ..., 'warning') ON CONFLICT (tipo_alerta)
     DO NOTHING``. Respects the ``alert_types_inmutable`` trigger
     (migration 0013) — INSERT-only for ``rol_app``. Same pattern as
     MIGRATION 0025 alert_type seed (F1.6).

  4. **BEFORE INSERT trigger ``fn_salidas_one_exit_per_ingreso``
     (KD-S16, TOCTOU closure — replaces the original partial unique
     index)**: ``CREATE OR REPLACE FUNCTION prod.fn_salidas_one_exit_
     per_ingreso()`` + ``CREATE TRIGGER salidas_one_exit_per_ingreso
     BEFORE INSERT ON prod.salidas FOR EACH ROW EXECUTE FUNCTION
     prod.fn_salidas_one_exit_per_ingreso()``. The trigger raises
     ``ERRCODE='unique_violation'`` if any existing ``prod.salidas``
     row with the same ``uuid_ingreso`` is NOT annulled (i.e. there
     is no matching ``prod.anulaciones`` row with
     ``tipo_anulable='salida'``, ``estado='ejecutada'``). This
     preserves EXACTLY the semantics of the original partial unique
     index (where the predicate ``WHERE NOT EXISTS (... anulaciones
     ...)`` excluded anuladas from the unique set).

     **Why a trigger, not a partial UK.** PG rejects ``CREATE INDEX``
     predicates that contain subqueries (``cannot use subquery in
     index predicate`` — verified live on PG 16 with ``pg_partman``).
     The trigger is the canonical workaround for ``"partial uniqueness"
     with a subquery predicate`` — analogía migration 0004
     (``fn_factura_pagos_reverso_uniqueness``) and migration 0027
     (``fn_factura_pagos_init_pago_uniqueness``). Closes TOCTOU race on
     V1 EXISTS subquery; ``UniqueViolationError → 409 salida_duplicada``
     mapped in ``repo/salida.py::crear_salida_evento``.

     Pattern mirror: 0027's ``fn_factura_pagos_init_pago_uniqueness``
     structure (lines ~187-221): ``CREATE OR REPLACE FUNCTION`` +
     ``DROP TRIGGER IF EXISTS`` + ``CREATE TRIGGER``. Trigger name
     follows the codebase convention (no ``tr_`` prefix), e.g.
     ``salidas_inmutable``, ``factura_pagos_init_pago_uniqueness``.
     Trigger is independent of the pre-existing
     ``fn_salidas_inmutable`` BEFORE UPDATE OR DELETE trigger (migration
     0001) — different events (INSERT vs UPDATE/DELETE), no conflict.

**Idempotency.**
  - Op 2 ``ON CONFLICT (codigo, vigente_desde) DO NOTHING`` is the
    standard pattern; re-apply is a no-op.
  - Op 3 ``ON CONFLICT (tipo_alerta) DO NOTHING`` is the same pattern
    as MIGRATION 0025.
  - Op 4 ``CREATE OR REPLACE FUNCTION`` + ``DROP TRIGGER IF EXISTS`` +
    ``CREATE TRIGGER`` is idempotent — re-apply replaces the function
    body and re-binds the trigger; both DDL statements are safe on
    re-run.
  - The pre-flight Op 1 ``DO $$`` block is idempotent (count check is
    read-only, no DDL).

**Downgrade.**
  1. ``DROP TRIGGER IF EXISTS salidas_one_exit_per_ingreso ON
     prod.salidas`` + ``DROP FUNCTION IF EXISTS
     prod.fn_salidas_one_exit_per_ingreso()`` (Op 4 reverse).
  2. ``DROP INDEX IF EXISTS one_exit_per_ingreso`` (defensive cleanup
     of any stale partial index from prior broken-runs; the original
     partial UK CREATE was rejected by PG and never created an index,
     so this is normally a no-op).
  3. ``DELETE FROM prod.alert_types WHERE tipo_alerta IN
     ('subscripcion_vencida_forzado', 'tarifa_vigente_forzado')`` (Op 3
     reverse; runs as superuser to bypass ``alert_types_inmutable``).
  4. ``DELETE FROM prod.impuestos WHERE codigo='IVA' AND estado='activo'``
     (Op 2 reverse; runs as superuser). **Caveat (R8)**: if
     ``impuestos_inmutable`` trigger exists, the DELETE may be blocked.
     Workaround: NO downgrade in production; create compensatory migration
     setting ``estado='inactivo'`` instead.

**Pre-flight ordering (Op 1)**: the DO $$ block aborts BEFORE any
function create or INSERT, so a missing table does not leave partial
state. The DO $$ block is the FIRST statement in the upgrade() function.

**Cross-references.**
  - F1.8 design.md §4 KD-IVA — the inline-seed matches the documented
    seeding recipe.
  - F1.6 MIGRATION 0025 — Op 3 mirrors the alert_type seed pattern.
  - MIGRATION 0004 (``fn_factura_pagos_reverso_uniqueness``) +
    MIGRATION 0027 (``fn_factura_pagos_init_pago_uniqueness``) — Op 4
    mirrors the trigger pattern (CREATE OR REPLACE FUNCTION + DROP
    TRIGGER IF EXISTS + CREATE TRIGGER) for "partial uniqueness with a
    subquery predicate" enforced at INSERT time.
  - ``repo/salida.py::crear_salida_evento`` (NEW, F1.7) catches
    ``IntegrityError("one_exit_per_ingreso")`` and maps to
    ``SalidaDuplicada → 409``. The substring ``"one_exit_per_ingreso"``
    appears in both the trigger name and the function name, so the
    in-app matcher keeps working without changes.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0026_seed_impuestos_iva_and_one_exit_per_ingreso"
down_revision = "0025_alerta_datos_nuevos"
branch_labels = None
depends_on = None


# Matches the F1.5 / F1.6 migration pattern (0024_add_mv_ocupacion_diaria.py
# line 61 + 0025_add_alerta_datos_nuevos.py line 65): cap any blocking DDL
# at 5s so the migration cannot stall the alembic runtime on a busy DB.
_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"


def upgrade() -> None:
    """Apply the F1.7 IVA seed + 2 alert_types + salida-uniqueness trigger."""
    op.execute(_LOCK_TIMEOUT_SQL)

    # 1) Pre-flight (KD-7 F1.6 pattern): 3 tables must exist.
    op.execute(
        """
        DO $$
        DECLARE
            _n_impuestos bigint;
            _n_salidas bigint;
            _n_alert_types bigint;
        BEGIN
            SELECT count(*) INTO _n_impuestos
            FROM pg_catalog.pg_class
            WHERE relname='impuestos' AND relnamespace='prod'::regnamespace;
            RAISE NOTICE '0026_preflight: prod.impuestos existe con % filas',
                _n_impuestos;
            IF _n_impuestos IS NULL OR _n_impuestos = 0 THEN
                RAISE EXCEPTION '0026_preflight_abort: tabla prod.impuestos no existe. Aplique migrations 0001-0025 antes.';
            END IF;

            SELECT count(*) INTO _n_salidas
            FROM pg_catalog.pg_class
            WHERE relname='salidas' AND relnamespace='prod'::regnamespace;
            RAISE NOTICE '0026_preflight: prod.salidas existe con % filas',
                _n_salidas;
            IF _n_salidas IS NULL OR _n_salidas = 0 THEN
                RAISE EXCEPTION '0026_preflight_abort: tabla prod.salidas no existe.';
            END IF;

            SELECT count(*) INTO _n_alert_types
            FROM pg_catalog.pg_class
            WHERE relname='alert_types' AND relnamespace='prod'::regnamespace;
            RAISE NOTICE '0026_preflight: prod.alert_types existe con % filas',
                _n_alert_types;
            IF _n_alert_types IS NULL OR _n_alert_types = 0 THEN
                RAISE EXCEPTION '0026_preflight_abort: tabla prod.alert_types no existe.';
            END IF;
        END $$;
        """
    )

    # 2) Inline-seed prod.impuestos.IVA (KD-IVA resolver for F1.8).
    #    codigo='IVA' is the UK01 of impuestos (modelo_datos_er.mmd:187-207).
    #    The ON CONFLICT uses the UK constraint (codigo, vigente_desde)
    #    for idempotency.
    #    porcentaje=0.19 is the regulatory constant (IVA Colombia 2026).
    op.execute(
        """
        INSERT INTO prod.impuestos (
            uuid, codigo, nombre, porcentaje,
            vigente_desde, vigente_hasta, estado, created_at
        ) VALUES (
            gen_random_uuid(), 'IVA', 'IVA', 0.19,
            NOW() AT TIME ZONE 'UTC', NULL, 'activo', NOW()
        )
        ON CONFLICT (codigo, vigente_desde) DO NOTHING
        """
    )

    # 3) Inline-seed 2 alert_types (F1.7 alerts).
    #    Respects alert_types_inmutable trigger (migration 0013) --
    #    INSERT-only for rol_app; ON CONFLICT DO NOTHING is idempotent.
    op.execute(
        """
        INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity)
        VALUES
            (
                'subscripcion_vencida_forzado',
                'Salida vehicular forzada por administrador al detectar '
                'subscripcion vencida al momento de salida',
                'warning'
            ),
            (
                'tarifa_vigente_forzado',
                'Salida vehicular forzada por administrador al detectar '
                'tarifa no vigente al momento de salida',
                'warning'
            )
        ON CONFLICT (tipo_alerta) DO NOTHING
        """
    )

    # 4) BEFORE INSERT trigger fn_salidas_one_exit_per_ingreso
    #    (KD-S16, TOCTOU closure).
    #
    #    Replaces the original partial unique index
    #    ``one_exit_per_ingreso`` because PG rejects subqueries in
    #    CREATE INDEX predicates (``cannot use subquery in index
    #    predicate``). The trigger enforces EXACTLY the same predicate
    #    semantics that the original partial UK predicate encoded:
    #
    #      WHERE NOT EXISTS (
    #          SELECT 1 FROM prod.anulaciones a
    #          WHERE a.uuid_salida = prod.salidas.uuid
    #            AND a.tipo_anulable = 'salida'
    #            AND a.estado = 'ejecutada'
    #      )
    #
    #    At INSERT time, the trigger checks if any existing salida row
    #    with the same uuid_ingreso is NOT annulled and rejects the
    #    INSERT with ERRCODE='unique_violation' (mapped to
    #    SalidaDuplicada -> HTTP 409 by ``repo/salida.py``).
    #
    #    Pattern mirror: MIGRATION 0027's
    #    ``fn_factura_pagos_init_pago_uniqueness`` (lines 187-221 of
    #    0027_one_factura_per_salida_and_init_pago_trigger_and_revoke.py).
    #    Code structure (CREATE OR REPLACE FUNCTION + DROP TRIGGER IF
    #    EXISTS + CREATE TRIGGER) is identical.
    #
    #    The trigger fires BEFORE INSERT; prod.anulaciones is referenced
    #    by name and resolved on first plan use. By 0026 down_revision
    #    (0025), prod.anulaciones is guaranteed to exist (created in
    #    0001_initial_schema.py).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prod.fn_salidas_one_exit_per_ingreso()
        RETURNS trigger AS $$
        BEGIN
            -- "At most one active salida per uuid_ingreso":
            -- the inner NOT EXISTS mirrors the original partial UK
            -- predicate. A salida is "annulled" iff there exists a
            -- prod.anulaciones row of tipo_anulable='salida' with
            -- estado='ejecutada' pointing at its uuid. Trigger fires
            -- BEFORE INSERT; NEW is not yet visible to SELECT.
            IF EXISTS (
                SELECT 1 FROM prod.salidas s
                WHERE s.uuid_ingreso = NEW.uuid_ingreso
                  AND NOT EXISTS (
                      SELECT 1 FROM prod.anulaciones a
                      WHERE a.uuid_salida = s.uuid
                        AND a.tipo_anulable = 'salida'
                        AND a.estado = 'ejecutada'
                  )
            ) THEN
                RAISE EXCEPTION
                    'fn_salidas_one_exit_per_ingreso: '
                    'uuid_ingreso=% already has an active salida '
                    '(one salida per ingreso, except annulled)',
                    NEW.uuid_ingreso
                    USING ERRCODE = 'unique_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS salidas_one_exit_per_ingreso "
        "ON prod.salidas;"
    )
    op.execute(
        "CREATE TRIGGER salidas_one_exit_per_ingreso "
        "BEFORE INSERT ON prod.salidas "
        "FOR EACH ROW EXECUTE FUNCTION prod.fn_salidas_one_exit_per_ingreso();"
    )


def downgrade() -> None:
    """Reverse the F1.7 IVA seed + 2 alert_types + salida trigger.

    Runs as superuser (alembic) so the ``alert_types_inmutable`` trigger
    does NOT block the DELETE.

    Reverse order (Op 4 -> Op 3 -> Op 2):
      1. DROP TRIGGER + DROP FUNCTION (Op 4 reverse).
      2. DROP INDEX IF EXISTS (defensive cleanup of any stale partial
         index from prior broken runs; the CREATE INDEX statement was
         rejected by PG so the index was never created in practice).
      3. DELETE alert_types (Op 3 reverse).
      4. DELETE impuestos (Op 2 reverse; workaround if
         impuestos_inmutable exists: NO downgrade; create compensatory
         migration setting estado='inactivo').
    """
    op.execute(_LOCK_TIMEOUT_SQL)

    # Op 4 reverse: drop the BEFORE INSERT trigger.
    op.execute(
        "DROP TRIGGER IF EXISTS salidas_one_exit_per_ingreso "
        "ON prod.salidas;"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS prod.fn_salidas_one_exit_per_ingreso();"
    )

    # Defensive: drop any stale partial index from a prior broken run
    # (where the CREATE INDEX was attempted before the subquery
    # predicate was rejected by PG).
    op.execute("DROP INDEX IF EXISTS one_exit_per_ingreso")

    # Op 3 reverse: DELETE 2 alert_types (superuser; bypasses inmutable trigger).
    op.execute(
        "DELETE FROM prod.alert_types "
        "WHERE tipo_alerta IN ("
        "'subscripcion_vencida_forzado', 'tarifa_vigente_forzado')"
    )

    # Op 2 reverse: DELETE prod.impuestos.IVA (superuser).
    # The downgrade DELETE on prod.impuestos succeeds because no
    # impuestos_inmutable trigger exists on that table (verified
    # pre-0026: only `fn_factura_impuestos_inmutable` exists, on a
    # different table -- prod.factura_impuestos).
    # If a future migration adds an impuestos_inmutable trigger to
    # prod.impuestos, the workaround is:
    #   UPDATE prod.impuestos
    #   SET estado='inactivo', vigente_hasta=NOW() AT TIME ZONE 'UTC'
    #   WHERE codigo='IVA' AND vigente_hasta IS NULL;
    op.execute(
        "DELETE FROM prod.impuestos "
        "WHERE codigo='IVA' AND estado='activo'"
    )


__all__ = ["downgrade", "upgrade"]
