"""HU-F1.14 / MIGRATION 0032 -- REAL siembra: 11 alert_types codes (10 net new).

Revision ID: 0032_seed_alert_types_operativos
Revises: 0031_arqueo_cierre_dia_and_gap_be_05 (F1.13 head)
Create Date: 2026-09-15

**Scope.** REAL siembra + pre-flight audit trail (DEC-SYNC-05 +
DEC-SYNC-06 + DEC-SYNC-07 + DEC-SYNC-10).

Pre-flight on 2026-09-15 confirmed:

  * ``prod.alert_types`` exists (migration 0013, registry,
    ``alert_types_inmutable`` trigger lines 21-22, ``severity`` CHECK
    constraint line 119 accepting ``('info', 'warning', 'critical')``).
  * ``prod.alert_types`` carries 9 seeded rows pre-F1.14: 8 técnicos
    (migration 0013) + 1 ``descuadre_critico`` (F1.13 MIGRATION 0031
    Op 2 lines 169-175).
  * F1.14 adds 10 net new + idempotent re-attempt of
    ``descuadre_critico`` (becomes no-op via ``ON CONFLICT DO
    NOTHING``). Final total: 19 alert_types seeded.
  * ``prod.sync_log`` + ``prod.sync_queue`` exist (F1.14 endpoint
    reads both via the read-only SELECT helpers in
    ``repo/sync_estado.py``).
  * ``DEC-SYNC-05``: 10 net new (NOT 11) -- ``descuadre_critico``
    already seeded by F1.13 MIGRATION 0031 Op 2.

**Pre-flight DO $$ block.**

Verifies the 4 required objects (alert_types table, ``alert_types_inmutable``
trigger, sync_log table, sync_queue table) are present in ``prod``.
Aborts with a typed ``0032_preflight_abort`` exception if any object is
missing.

**Siembra operations.**

* Op 1: siembra 11 alert_types codes (10 net new + idempotent
  re-attempt of ``descuadre_critico``) per plan.md line 1131 severity
  mapping (DEC-SYNC-06: alta -> critical, media -> warning,
  baja -> info). Idempotent via ``ON CONFLICT (tipo_alerta) DO
  NOTHING`` (respects ``alert_types_inmutable`` trigger migration
  0013:21-22).
* Op 2: NO-DDL anchor for ``DEC-SYNC-03.B`` (audit_read reuse -- pre-
  seeded at ``0002_seed_permisos_canonicos.py:48``). No DB schema
  changes.

**Downgrade.**

Reverses Op 1: ``DISABLE TRIGGER alert_types_inmutable`` + ``DELETE
FROM prod.alert_types WHERE tipo_alerta IN (10 net new codes)`` +
``ENABLE TRIGGER alert_types_inmutable``. The 10 net new codes are
removed; ``descuadre_critico`` (F1.13-owned) + the 8 técnicos (0013-
owned) are preserved.

**Note on ``created_at`` / ``created_by``.**

This migration omits ``created_at`` + ``created_by`` from the INSERT
column list to let the DB defaults fire: ``created_at`` defaults to
``NOW()`` via the column ``server_default``; ``created_by`` is
nullable and defaults to NULL. The earlier design draft proposed
passing ``created_by="migrations/0032"`` via ``op.bulk_insert`` -- but
the column is typed ``UUID`` in ``models/A/alert_types.py`` so the
literal string would be rejected at INSERT time. The raw ``op.execute``
pattern with ``ON CONFLICT DO NOTHING`` (matching F1.11 migration 0025
+ F1.12 migration 0026 precedents) is the safer path.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0032_seed_alert_types_operativos"
down_revision = "0031_arqueo_cierre_dia_and_gap_be_05"
branch_labels = None
depends_on = None


# Canonical seed rows for the 11 codes per plan.md line 1131.
# Severity per DEC-SYNC-06: alta=critical, media=warning, baja=info.
# descripcion per DEC-SYNC-10 from plan.md lines 2311-2323.
_SEED_ROWS: tuple[tuple[str, str, str], ...] = (
    # (tipo_alerta, severity, descripcion)
    ("sync_fallida", "critical", "Sincronización con cloud falló tras N reintentos"),
    ("capacidad_agotada", "warning", "Sucursal sin cupos disponibles"),
    (
        "capacidad_agotada_forzado",
        "warning",
        "Ingreso forzado con capacidad agotada",
    ),
    (
        "evento_no_procesado",
        "critical",
        "Evento en sync_queue sin procesar tras SLA",
    ),
    ("impresora_caida", "critical", "Impresora local no responde"),
    ("fe_error_toppoint", "critical", "Error FE provisto por TopPoint"),
    (
        "numeracion_toppoint_agotada",
        "critical",
        "Numeración TopPoint agotada",
    ),
    ("cache_desactualizado", "info", "Cache local desactualizado"),
    ("arqueo_pendiente_24h", "warning", "Arqueo pendiente >24h"),
    ("suscripcion_proxima_vencer", "warning", "Suscripción próxima a vencer"),
    # descuadre_critico already seeded by F1.13 MIGRATION 0031 Op 2
    # lines 169-175; F1.14 re-seeds it idempotent via ON CONFLICT DO NOTHING.
    ("descuadre_critico", "critical", "Descuadre de caja supera tolerancia"),
)


def upgrade() -> None:
    """MIGRATION 0032 upgrade: pre-flight + Op 1 siembra 11 codes (10 net new) + Op 2 NO-DDL anchor."""
    # Op 0 -- pre-flight DO $$ (KD-7 F1.6..F1.13 pattern).
    # Verifies the 4 required objects in ``prod``:
    #   - alert_types table exists
    #   - alert_types_inmutable trigger active
    #   - sync_log table exists
    #   - sync_queue table exists
    op.execute(
        """
        DO $$
        DECLARE
            _n_alert_types    bigint;
            _n_trigger        bigint;
            _n_sync_log       bigint;
            _n_sync_queue     bigint;
        BEGIN
            SELECT count(*) INTO _n_alert_types
                FROM pg_catalog.pg_class
                WHERE relname='alert_types' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_trigger
                FROM pg_catalog.pg_trigger t
                JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
                WHERE t.tgname = 'alert_types_inmutable'
                  AND c.relnamespace = 'prod'::regnamespace;
            SELECT count(*) INTO _n_sync_log
                FROM pg_catalog.pg_class
                WHERE relname='sync_log' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_sync_queue
                FROM pg_catalog.pg_class
                WHERE relname='sync_queue' AND relnamespace='prod'::regnamespace;

            IF _n_alert_types IS NULL OR _n_alert_types = 0 THEN
                RAISE EXCEPTION '0032_preflight_abort: tabla prod.alert_types no existe. '
                                'Aplique MIGRATION 0013 antes.';
            END IF;
            IF _n_trigger IS NULL OR _n_trigger = 0 THEN
                RAISE EXCEPTION '0032_preflight_abort: trigger alert_types_inmutable '
                                'no está activo. Aplique MIGRATION 0013 antes.';
            END IF;
            IF _n_sync_log IS NULL OR _n_sync_log = 0 THEN
                RAISE EXCEPTION '0032_preflight_abort: tabla prod.sync_log no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_sync_queue IS NULL OR _n_sync_queue = 0 THEN
                RAISE EXCEPTION '0032_preflight_abort: tabla prod.sync_queue no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;

            RAISE NOTICE '0032_preflight: 4/4 objetos OK '
                         '(alert_types + alert_types_inmutable trigger + '
                         'sync_log + sync_queue)';
        END;
        $$;
        """
    )

    # Op 1 -- siembra 11 alert_types codes (10 net new + idempotent
    # re-attempt of descuadre_critico). Idempotent via ON CONFLICT DO
    # NOTHING (respects alert_types_inmutable trigger, migration
    # 0013:21-22 -- the trigger blocks UPDATE/DELETE only, not INSERT).
    # DB defaults fire on created_at (server_default NOW()) and
    # created_by (nullable, defaults to NULL).
    values_sql = ",\n            ".join(
        f"('{t}', '{s}', '{d}')" for t, s, d in _SEED_ROWS
    )
    op.execute(
        f"""
        INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity)
        VALUES
            {values_sql}
        ON CONFLICT (tipo_alerta) DO NOTHING;
        """
    )

    # Op 2 -- NO-DDL anchor for DEC-SYNC-03.B (audit_read reuse).
    # The permission gate audit_read is pre-seeded at
    # 0002_seed_permisos_canonicos.py:48. No DB schema changes; this
    # comment serves as the audit-trail anchor.
    op.execute(
        """
        DO $$
        BEGIN
            RAISE NOTICE '0032_op2: DEC-SYNC-03.B adopted. Permission gate = audit_read '
                         '(pre-seeded at 0002_seed_permisos_canonicos.py:48). '
                         'No new permission seeded.';
        END $$;
        """
    )


def downgrade() -> None:
    """Reverse Op 1: DELETE the 10 NET NEW alert_types rows (preserve ``descuadre_critico``)."""
    # Reverse Op 1 -- DELETE the 10 F1.14 net new codes. descuadre_critico
    # is NOT touched (owned by F1.13 MIGRATION 0031 Op 2 lines 169-175).
    # alert_types_inmutable trigger blocks DELETE; disable temporarily.
    op.execute("ALTER TABLE prod.alert_types DISABLE TRIGGER alert_types_inmutable;")

    net_new_codes = [code for code, _, _ in _SEED_ROWS if code != "descuadre_critico"]
    codes_list = ", ".join(f"'{c}'" for c in net_new_codes)
    op.execute(
        f"""
        DELETE FROM prod.alert_types
        WHERE tipo_alerta IN ({codes_list});
        """
    )

    op.execute("ALTER TABLE prod.alert_types ENABLE TRIGGER alert_types_inmutable;")

    # Op 2 -- NO-DDL reversal: DEC-SYNC-03.B is a Python-only decision
    # (no migration changes).


__all__ = ["_SEED_ROWS", "down_revision", "downgrade", "revision", "upgrade"]
