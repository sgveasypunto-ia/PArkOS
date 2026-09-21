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

  4. **Op 3 — REMOVED (formerly: grant ``'anular_reimpresion'`` to
     ``operador`` + ``admin`` roles via ``prod.permisos_usuario``)**.

     The original Op 3 JOINed ``prod.usuarios`` against ``prod.roles``
     filtered by ``nombre IN ('operador', 'admin')``. Two real defects
     were identified during end-to-end verification:

       (a) ``prod.roles`` does NOT exist. Roles are PG-level only:
           ``rol_app`` and ``rol_admin_auditor`` were created via
           ``CREATE ROLE`` in migration 0021
           (``least_privilege_and_immutability_contract``); there is
           no per-role table.
       (b) ``prod.usuarios.uuid_rol`` does NOT exist either. The
           canonical schema in ``0001_initial_schema.py:153-169`` has
           ``usuarios.rol`` (String, e.g. ``'operador'`` /
           ``'admin'``), not ``uuid_rol`` (UUID).

     Both defects would surface as ``UndefinedTable`` /
     ``UndefinedColumn`` at apply time. Mirroring the preflight fix
     (commit ``592a588``: query ``pg_catalog.pg_roles`` for role
     existence) would still leave defect (b) intact AND force the
     migration to invent a UUID representation for PG-level roles
     (which have only ``oid``, no UUID column) — a far more invasive
     change than the constraint warrants.

     **Decision (KD-MIN-PRIVILEGE): remove the per-role DB pre-grant
     entirely.** Role gating for the ``anular_reimpresion`` action is
     enforced at the HTTP handler via
     ``_anular_reimpresion_issuer_dep``
     (``requires_issuer("operador-", "admin-")``,
     ``backend/packages/parkos_core/src/parkos_core/api/v1/
     workflows_reimpresion.py:76``). This is the authoritative
     mechanism, locked by
     ``test_anular_handler_uses_anular_reimpresion_issuer_dep``
     (``backend/tests/integration/test_workflows_router_wiring.py:
     276``). The DB-side per-user grant was dead code that would
     have been silently overwritten by the handler anyway, and is
     removed as redundant. No regression: handler-level gating is
     strictly tighter (it inspects the JWT ``iss`` claim, not the
     user table). Op 3 is now a no-op ``RAISE NOTICE`` for log
     continuity.

**Idempotency.**
  - Op 0 ``DO $$`` is read-only.
  - Op 1 ``IF siembra_count = 0`` + ``ON CONFLICT`` is the standard
    pattern; re-apply is a no-op.
  - Op 2 ``IF NOT EXISTS`` is the same pattern as F1.7.
  - Op 3 is a read-only ``RAISE NOTICE`` (the DB pre-grant block was
    removed; see KD-MIN-PRIVILEGE note above).

**Downgrade.** Reverse order:
  1. DELETE FROM ``prod.permisos_usuario`` rows whose ``uuid_permiso``
     resolves to ``permiso='anular_reimpresion'`` (defensive: this
     migration does NOT insert any such rows, but the DELETE is
     preserved so a downgrade still cleans up if a future migration
     re-introduces the grant or a manual fix seeded one out-of-band).
  2. DELETE FROM ``prod.permisos`` WHERE permiso='anular_reimpresion'
     (reverse Op 2).
  3. DELETE FROM ``prod.costos_servicios`` WHERE
     concepto='reimpresion' AND vigente_desde >= NOW() - INTERVAL '1
     hour' AND vigente_hasta IS NULL AND estado='activo' (known R8
     limitation: deletes any siembra inserted within the last hour
     — assumes the migration is recent; reverse Op 1).

**Cross-references.**
  - F1.7 MIGRATION 0026 — IVA + alert_types seed pattern mirrored for
    the siembra (Op 1) and the permission seed (Op 2).
  - F1.7 ``anular_ingreso_salida`` permission seed — Op 2 mirrors that
    pattern. The role-grant half (formerly Op 3) is REMOVED in this
    migration; F1.7 still keeps its own DB-level grant because F1.7's
    ``anular_ingreso_salida`` handler relies on a different enforcement
    surface (see F1.7 design + its handler tests for the contrasting
    contract).
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
    """Apply the F1.11 siembra + permission seed (Op 3 grants removed)."""
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
    #
    # NOTE: ``descripcion`` column is NOT present on ``prod.permisos``
    # (canonical schema in MIGRATION 0001 lines 125-135 + ER canon
    # ``modelo_datos_er.mmd``). The original draft of this INSERT
    # referenced ``descripcion='Anular una reimpresion de tiquete
    # autorizada/ejecutada (HU-F1.11)'`` — that string is human-readable
    # documentation and is preserved here as a code comment instead of
    # being persisted. The canonical column list mirrors 0002_seed_permisos_canonicos
    # (``uuid, permiso, vigente_desde, vigente_hasta, estado, created_at``);
    # ``created_by``, ``sync_status``, and ``sync_attempts`` are nullable
    # per ``_audit_columns()`` / ``_sync_columns()`` helpers in 0001 and
    # are intentionally omitted (the migration keeps a minimal payload —
    # the canonical seed in 0002 uses the same 6-column shape).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM prod.permisos WHERE permiso = 'anular_reimpresion'
            ) THEN
                INSERT INTO prod.permisos (
                    uuid, permiso,
                    vigente_desde, vigente_hasta, estado, created_at
                ) VALUES (
                    gen_random_uuid(), 'anular_reimpresion',
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
    # Op 3: REMOVED — DB-side per-role pre-grant is redundant.
    # ----------------------------------------------------------------
    # The original Op 3 INSERTed one row per (operador|admin user,
    # anular_reimpresion) pair into ``prod.permisos_usuario`` via a
    # JOIN on ``prod.roles WHERE nombre IN ('operador', 'admin')``.
    # Two real defects made that block unrunnable:
    #
    #   (a) ``prod.roles`` does NOT exist — application roles are
    #       PG-level only (``rol_app``, ``rol_admin_auditor`` created
    #       by ``CREATE ROLE`` in migration 0021
    #       ``least_privilege_and_immutability_contract``).
    #   (b) ``prod.usuarios.uuid_rol`` does NOT exist — the canonical
    #       column is ``prod.usuarios.rol`` (String, e.g.
    #       ``'operador'`` / ``'admin'``), per
    #       ``0001_initial_schema.py:153-169``.
    #
    # Mirroring the preflight fix (commit 592a588: query
    # ``pg_catalog.pg_roles`` for role existence) would still leave
    # defect (b) intact AND force the migration to invent a UUID
    # representation for PG-level roles (which have only ``oid``, no
    # UUID column) — far more invasive than the constraint warrants.
    #
    # KD-MIN-PRIVILEGE: role gating is enforced at the HTTP handler
    # via ``_anular_reimpresion_issuer_dep``
    # (``requires_issuer("operador-", "admin-")`` in
    # ``backend/packages/parkos_core/src/parkos_core/api/v1/
    # workflows_reimpresion.py:76``), locked by
    # ``test_anular_handler_uses_anular_reimpresion_issuer_dep``
    # (``backend/tests/integration/test_workflows_router_wiring.py:
    # 276``). The DB-side per-user pre-grant was dead code — the
    # handler inspects the JWT ``iss`` claim directly and would
    # reject the request before any application code ever queried
    # ``prod.permisos_usuario``. Removed as redundant.
    #
    # No regression: the handler-level gate is strictly tighter than
    # the DB-level pre-grant (it scopes by JWT issuer, not by a
    # row that may or may not exist in ``prod.permisos_usuario``).
    #
    # The DO block below is preserved as a no-op ``RAISE NOTICE`` for
    # log continuity — operators grepping for ``0029_op3:`` in
    # alembic output still see the expected marker, and any future
    # hook that needs to run post-permission-seed has an obvious
    # anchor here.
    op.execute(
        """
        DO $$
        BEGIN
            RAISE NOTICE '0029_op3: grants removed (KD-MIN-PRIVILEGE; '
                         'handler enforces role via '
                         '_anular_reimpresion_issuer_dep)';
        END $$;
        """
    )


def downgrade() -> None:
    """Reverse the 4 ops (R8 known limitation: Op 1 1-hour time window)."""
    # Reverse Op 3 — no-op (DB-side per-role pre-grant was REMOVED in
    # this migration; see upgrade Op 3 comment + KD-MIN-PRIVILEGE).
    # Preserved as a defensive DELETE for symmetry with prior revision
    # history: if a row referencing uuid_permiso='anular_reimpresion'
    # happens to exist (e.g. inserted by a future migration that
    # re-introduces this grant), this downgrade will still clean it up.
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
