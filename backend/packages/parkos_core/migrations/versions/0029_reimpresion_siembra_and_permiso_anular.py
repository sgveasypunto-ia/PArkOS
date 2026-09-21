"""HU-F1.11 / MIGRATION 0029 — siembra reimpresion + permiso anular_reimpresion.

Revision ID: 0029_reimpresion_siembra_and_permiso_anular
Revises: 0028_one_fe_per_factura_and_chain_index_and_sync_flip (F1.10 head)
Create Date: 2026-09-15

**Scope.** Four operations in strict order:

  1. **Pre-flight (KD-7 F1.6 / F1.7 / F1.9 / F1.10 pattern)**:
     ``DO $$`` block aborts with a typed ``0029_preflight_abort`` exception
     if any of the 3 expected tables is missing (``costos_servicios``,
     ``permisos``, ``permisos_usuario``) OR the 2 required PG-level
     roles are missing (``rol_app`` and ``rol_admin_auditor`` created
     by migration 0021 ``least_privilege_and_immutability_contract``).
     The DO block emits ``RAISE NOTICE`` with the presence summary on
     success.

     **Why pg_catalog.pg_roles and not ``to_regclass('prod.roles')``**:
     the original check queried ``pg_catalog.pg_class`` for
     ``relname='roles'``, but there is NO ``prod.roles`` table — the
     application roles live in ``pg_catalog.pg_roles`` and were created
     via ``CREATE ROLE`` in migration 0021 (and earlier). The check is
     fixed to query ``pg_roles`` for ``rolname IN ('rol_app',
     'rol_admin_auditor')``.

  2. **Op 1 — DEC-TKT-05 conditional siembra
     ``prod.costos_servicios.concepto='reimpresion'``**: idempotent via
     ``IF siembra_count = 0`` guard + ``ON CONFLICT (concepto,
     vigente_desde) DO NOTHING``. The migration ships regardless of
     whether siembra is already present.

  3. **Op 2 — seed ``prod.permisos`` for ``'anular_reimpresion'``**
     (mirror of F1.7 ``anular_ingreso_salida`` seed pattern):
     ``IF NOT EXISTS`` guard makes the seed idempotent on re-apply.

  4. **Op 3 — grant ``'anular_reimpresion'`` to ``operador`` and
     ``admin`` roles via ``prod.permisos_usuario``**: idempotent via
     ``NOT EXISTS`` subquery + JOIN on ``prod.roles WHERE nombre IN
     ('operador', 'admin')``. One INSERT per (user, permission) pair.

**Idempotency.**
  - Op 0 ``DO $$`` is read-only.
  - Op 1 ``IF siembra_count = 0`` + ``ON CONFLICT`` is the standard
    pattern; re-apply is a no-op.
  - Op 2 ``IF NOT EXISTS`` is the same pattern as F1.7.
  - Op 3 ``NOT EXISTS`` subquery in the SELECT skips already-granted
    rows; re-apply is a no-op.

**Downgrade.** Reverse order:
  1. DELETE FROM ``prod.permisos_usuario`` WHERE uuid_permiso IN
     (SELECT uuid FROM prod.permisos WHERE permiso='anular_reimpresion').
  2. DELETE FROM ``prod.permisos`` WHERE permiso='anular_reimpresion'.
  3. DELETE FROM ``prod.costos_servicios`` WHERE
     concepto='reimpresion' AND vigente_desde >= NOW() - INTERVAL '1
     hour' AND vigente_hasta IS NULL AND estado='activo' (known R8
     limitation: deletes any siembra inserted within the last hour
     — assumes the migration is recent).

**Cross-references.**
  - F1.7 MIGRATION 0026 — IVA + alert_types seed pattern mirrored for
    the siembra (Op 1) and the permission seed (Op 2).
  - F1.7 ``anular_ingreso_salida`` permission + role grants — Op 2 +
    Op 3 mirror the same pattern verbatim.
  - F1.10 MIGRATION 0028 — pre-flight DO $$ block pattern (KD-7).
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0029_reimpresion_siembra_and_permiso_anular"
down_revision = "0028_one_fe_per_factura_and_chain_index_and_sync_flip"
branch_labels = None
depends_on = None


# Matches the F1.5 / F1.6 / F1.10 migration pattern (0028 lines 90-91):
# cap any blocking DDL at 5s so the migration cannot stall the alembic
# runtime on a busy DB.
_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"


def upgrade() -> None:
    """Apply the F1.11 siembra + permission seed + role grants."""
    op.execute(_LOCK_TIMEOUT_SQL)

    # ----------------------------------------------------------------
    # Op 0: pre-flight `DO $$` (KD-7 F1.6 + F1.7 + F1.9 + F1.10 pattern)
    # ----------------------------------------------------------------
    op.execute(
        """
        DO $$
        DECLARE
            _n_costos_servicios bigint;
            _n_permisos bigint;
            _n_permisos_usuario bigint;
            _n_pg_roles bigint;
        BEGIN
            SELECT count(*) INTO _n_costos_servicios
                FROM pg_catalog.pg_class
                WHERE relname='costos_servicios' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_permisos
                FROM pg_catalog.pg_class
                WHERE relname='permisos' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_permisos_usuario
                FROM pg_catalog.pg_class
                WHERE relname='permisos_usuario' AND relnamespace='prod'::regnamespace;
            -- Roles are PG-level (CREATE ROLE), NOT a prod.roles table.
            -- ``rol_app`` + ``rol_admin_auditor`` were created by
            -- migration 0021 (least_privilege_and_immutability_contract).
            SELECT count(*) INTO _n_pg_roles
                FROM pg_catalog.pg_roles
                WHERE rolname IN ('rol_app', 'rol_admin_auditor');

            IF _n_costos_servicios IS NULL OR _n_costos_servicios = 0 THEN
                RAISE EXCEPTION '0029_preflight_abort: tabla prod.costos_servicios no existe. '
                                'Aplique migrations 0001-0028 antes.';
            END IF;
            IF _n_permisos IS NULL OR _n_permisos = 0 THEN
                RAISE EXCEPTION '0029_preflight_abort: tabla prod.permisos no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_permisos_usuario IS NULL OR _n_permisos_usuario = 0 THEN
                RAISE EXCEPTION '0029_preflight_abort: tabla prod.permisos_usuario no existe. '
                                'Aplique MIGRATION 0021 antes.';
            END IF;
            IF _n_pg_roles IS NULL OR _n_pg_roles < 2 THEN
                RAISE EXCEPTION '0029_preflight_abort: faltan roles PG. '
                                'Aplique MIGRATION 0021 (least_privilege_and_immutability_contract) '
                                'para crear rol_app y rol_admin_auditor.';
            END IF;

            RAISE NOTICE '0029_preflight: 3/3 tablas + 2/2 roles PG OK '
                         '(costos_servicios, permisos, permisos_usuario, '
                         'rol_app, rol_admin_auditor)';
        END;
        $$;
        """
    )

    # ----------------------------------------------------------------
    # Op 1: DEC-TKT-05 conditional siembra prod.costos_servicios
    # ----------------------------------------------------------------
    # The migration ships regardless of whether siembra is already present.
    # The IF siembra_count = 0 guard makes the siembra idempotent on
    # re-apply. The ON CONFLICT (concepto, vigente_desde) DO NOTHING
    # closes the concurrent-TX race (the UK
    # ``costos_servicios_uk01(``concepto, vigente_desde)`` enforces
    # uniqueness).
    op.execute(
        """
        DO $$
        DECLARE
            siembra_count INTEGER;
        BEGIN
            SELECT COUNT(*) INTO siembra_count
            FROM prod.costos_servicios
            WHERE concepto = 'reimpresion'
              AND vigente_hasta IS NULL
              AND estado = 'activo';

            IF siembra_count = 0 THEN
                INSERT INTO prod.costos_servicios (
                    uuid, concepto, costo, tipo_calculo,
                    vigente_desde, vigente_hasta, estado,
                    created_at, created_by, sync_status, sync_attempts
                ) VALUES (
                    gen_random_uuid(), 'reimpresion', 0, 'fijo',
                    NOW(), NULL, 'activo', NOW(), NULL, 'sincronizado', 0
                )
                ON CONFLICT (concepto, vigente_desde) DO NOTHING;
                RAISE NOTICE '0029_op1: siembra inserted (concepto=reimpresion, costo=0)';
            ELSE
                RAISE NOTICE '0029_op1: siembra already present (count=%), no-op', siembra_count;
            END IF;
        END $$;
        """
    )

    # ----------------------------------------------------------------
    # Op 2: seed prod.permisos for 'anular_reimpresion' (mirror F1.7)
    # ----------------------------------------------------------------
    # The IF NOT EXISTS guard makes this idempotent on re-apply.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM prod.permisos WHERE permiso = 'anular_reimpresion'
            ) THEN
                INSERT INTO prod.permisos (
                    uuid, permiso, descripcion,
                    vigente_desde, vigente_hasta, estado, created_at
                ) VALUES (
                    gen_random_uuid(), 'anular_reimpresion',
                    'Anular una reimpresion de tiquete autorizada/ejecutada (HU-F1.11)',
                    NOW(), NULL, 'activo', NOW()
                );
                RAISE NOTICE '0029_op2: permission seeded (permiso=anular_reimpresion)';
            ELSE
                RAISE NOTICE '0029_op2: permission already present, no-op';
            END IF;
        END $$;
        """
    )

    # ----------------------------------------------------------------
    # Op 3: grant 'anular_reimpresion' to operador + admin roles
    # ----------------------------------------------------------------
    # Idempotent via NOT EXISTS subquery + JOIN on roles. The SELECT
    # cross-product (``usuarios`` x ``permisos``) filtered by
    # ``uuid_rol IN ('operador', 'admin')`` materializes one row per
    # (user, permission) pair, each row inserted only if no current
    # grant exists for that pair.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='prod' AND table_name='permisos_usuario'
            ) THEN
                INSERT INTO prod.permisos_usuario (
                    uuid, uuid_usuario, uuid_permiso,
                    vigente_desde, vigente_hasta, estado, created_at
                )
                SELECT
                    gen_random_uuid(), u.uuid, p.uuid,
                    NOW(), NULL, 'activo', NOW()
                FROM prod.usuarios u, prod.permisos p
                WHERE p.permiso = 'anular_reimpresion'
                  AND u.uuid_rol IN (
                      SELECT uuid FROM prod.roles WHERE nombre IN ('operador', 'admin')
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM prod.permisos_usuario pu
                      WHERE pu.uuid_usuario = u.uuid
                        AND pu.uuid_permiso = p.uuid
                        AND pu.vigente_hasta IS NULL
                  );
                RAISE NOTICE '0029_op3: grants inserted (operador+admin)';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Reverse the 4 ops (R8 known limitation: Op 1 1-hour time window)."""
    # Reverse Op 3 (role grants).
    op.execute(
        """
        DELETE FROM prod.permisos_usuario
        WHERE uuid_permiso IN (
            SELECT uuid FROM prod.permisos WHERE permiso = 'anular_reimpresion'
        );
        """
    )

    # Reverse Op 2 (permission seed).
    op.execute(
        """
        DELETE FROM prod.permisos WHERE permiso = 'anular_reimpresion';
        """
    )

    # Reverse Op 1 (siembra). Known limitation: deletes any siembra
    # inserted within the last hour (assumes migration is recent).
    # If a manual siembra happened between migration and downgrade,
    # the row is also deleted. Documented in design Appendix A.6.
    op.execute(
        """
        DELETE FROM prod.costos_servicios
        WHERE concepto = 'reimpresion'
          AND vigente_desde >= NOW() - INTERVAL '1 hour'
          AND vigente_hasta IS NULL
          AND estado = 'activo';
        """
    )


__all__ = ["downgrade", "upgrade"]
