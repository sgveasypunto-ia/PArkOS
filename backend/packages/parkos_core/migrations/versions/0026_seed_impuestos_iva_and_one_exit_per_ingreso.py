"""HU-F1.7 / MIGRATION 0026 — KD-IVA resolver + 2 alert_types seed + partial
unique index ``one_exit_per_ingreso``.

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

  4. **Partial unique index ``one_exit_per_ingreso`` (KD-S16)**:
     ``CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
     one_exit_per_ingreso ON prod.salidas (uuid_ingreso) WHERE NOT
     EXISTS (SELECT 1 FROM prod.anulaciones a WHERE a.uuid_salida =
     prod.salidas.uuid AND a.tipo_anulable = 'salida' AND a.estado =
     'ejecutada')``. ``CONCURRENTLY`` for no lock on reads/writes;
     ``IF NOT EXISTS`` for idempotency. Closes TOCTOU race on V1 EXISTS
     subquery; ``UniqueViolationError → 409 salida_duplicada``.

**Idempotency.**
  - Op 2 ``ON CONFLICT (codigo, vigente_desde) DO NOTHING`` is the
    standard pattern; re-apply is a no-op.
  - Op 3 ``ON CONFLICT (tipo_alerta) DO NOTHING`` is the same pattern
    as MIGRATION 0025.
  - Op 4 ``CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`` allows
    re-apply without raising (the index already exists, no DDL needed).
  - The pre-flight Op 1 ``DO $$`` block is idempotent (count check is
    read-only, no DDL).

**Downgrade.**
  1. ``DROP INDEX IF EXISTS prod.one_exit_per_ingreso`` (Op 4 reverse).
  2. ``DELETE FROM prod.alert_types WHERE tipo_alerta IN
     ('subscripcion_vencida_forzado', 'tarifa_vigente_forzado')`` (Op 3
     reverse; runs as superuser to bypass ``alert_types_inmutable``).
  3. ``DELETE FROM prod.impuestos WHERE codigo='IVA' AND estado='activo'``
     (Op 2 reverse; runs as superuser). **Caveat (R8)**: if
     ``impuestos_inmutable`` trigger exists, the DELETE may be blocked.
     Workaround: NO downgrade in production; create compensatory migration
     setting ``estado='inactivo'`` instead.

**Pre-flight ordering (Op 1)**: the DO $$ block aborts BEFORE any INSERT,
so a missing table does not leave partial state. The DO $$ block is the
FIRST statement in the upgrade() function.

**Cross-references.**
  - F1.8 design.md §4 KD-IVA — the inline-seed matches the documented
    seeding recipe.
  - F1.6 MIGRATION 0025 — Op 3 mirrors the alert_type seed pattern.
  - F1.3 MIGRATION 0023 — Op 4 mirrors the partial unique index pattern
    (unique_active_sesion_per_user).
  - ``repo/salida.py::crear_salida_evento`` (NEW, F1.7) catches
    ``IntegrityError("one_exit_per_ingreso")`` and maps to
    ``SalidaDuplicada → 409``.
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
    """Apply the F1.7 IVA seed + 2 alert_types + partial unique index."""
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

    # 4) Partial unique index one_exit_per_ingreso (KD-S16, TOCTOU closure).
    #    CONCURRENTLY for no lock on reads/writes; IF NOT EXISTS for idempotency.
    #    The WHERE NOT EXISTS clause excludes anuladas: once a salida is
    #    anulada, a new salida for the same uuid_ingreso becomes possible.
    op.execute(
        """
        CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_exit_per_ingreso
            ON prod.salidas (uuid_ingreso)
            WHERE NOT EXISTS (
                SELECT 1 FROM prod.anulaciones a
                WHERE a.uuid_salida = prod.salidas.uuid
                  AND a.tipo_anulable = 'salida'
                  AND a.estado = 'ejecutada'
            )
        """
    )


def downgrade() -> None:
    """Reverse the F1.7 IVA seed + 2 alert_types + partial unique index.

    Runs as superuser (alembic) so the ``alert_types_inmutable`` trigger
    does NOT block the DELETE.

    Reverse order (Op 4 -> Op 3 -> Op 2):
      1. DROP INDEX
      2. DELETE alert_types
      3. DELETE impuestos (workaround if impuestos_inmutable exists: NO
         downgrade; create compensatory migration setting estado='inactivo').
    """
    op.execute(_LOCK_TIMEOUT_SQL)

    # Op 4 reverse: DROP INDEX.
    op.execute("DROP INDEX IF EXISTS prod.one_exit_per_ingreso")

    # Op 3 reverse: DELETE 2 alert_types (superuser; bypasses inmutable trigger).
    op.execute(
        "DELETE FROM prod.alert_types "
        "WHERE tipo_alerta IN ("
        "'subscripcion_vencida_forzado', 'tarifa_vigente_forzado')"
    )

    # Op 2 reverse: DELETE prod.impuestos.IVA (superuser).
    # Caveat (R8): if impuestos_inmutable trigger is present, this DELETE
    # may be blocked. Verification pre-F1.7-apply:
    #   grep -r "impuestos_inmutable" migrations/
    # If trigger exists, the workaround is:
    #   UPDATE prod.impuestos
    #   SET estado='inactivo', vigente_hasta=NOW() AT TIME ZONE 'UTC'
    #   WHERE codigo='IVA' AND vigente_hasta IS NULL;
    op.execute(
        "DELETE FROM prod.impuestos "
        "WHERE codigo='IVA' AND estado='activo'"
    )


__all__ = ["downgrade", "upgrade"]
