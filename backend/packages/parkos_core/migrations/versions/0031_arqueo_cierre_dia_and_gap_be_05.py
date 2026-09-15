"""HU-F1.13 / MIGRATION 0031 -- REAL siembra (cierre_dia + descuadre_critico).

Revision ID: 0031_arqueo_cierre_dia_and_gap_be_05
Revises: 0030_venta_suscripcion_optional (F1.12 head)
Create Date: 2026-09-15

**Scope.** REAL siembra + pre-flight audit trail (DEC-ARQUEO-09 + DEC-ARQUEO-08).

Pre-flight on 2026-09-15 confirmed:

  * ``prod.tipo_arqueo`` carries 3 seeded values (cierre_turno, auditoria,
    cierre_sesion). ``cierre_dia`` is MISSING -> Op 1 seeds it (A-07,
    plan.md line 458).
  * ``prod.alert_types`` carries 9 seeded values (registry migration 0013
    + 0025). ``descuadre_critico`` is MISSING -> Op 2 seeds it
    (DEC-ARQUEO-09b; F1.14's planned batch will be no-op for that code).
  * GAP-BE-05 (DEC-ARQUEO-08, plan.md lines 7349-7374 verbatim): Python-only
    permission correction at ``api/v1/caja.py:53`` (emitir_factura ->
    realizar_arqueo) + ``api/v1/caja_sesion.py:257`` (emitir_factura ->
    abrir_cerrar_caja). NO migration required -> Op 3 NO-DDL comment
    serves as an audit-trail anchor.

**Pre-flight DO $$ block.**

Verifies all 7 required tables exist (tipo_arqueo, alert_types, arqueo,
sesion, alerta, configuracion_tolerancias, factura_pagos). Aborts with
a typed ``0031_preflight_abort`` exception if any table is missing.

**Siembra operations.**

* Op 1: ``prod.tipo_arqueo.codigo='cierre_dia'`` (A-07). Idempotent via
  ``IF siembra_count = 0`` + ``ON CONFLICT (codigo, vigente_desde) DO
  NOTHING``.
* Op 2: ``prod.alert_types.tipo_alerta='descuadre_critico', severity=
  'critical'``. Idempotent via ``INSERT ... ON CONFLICT DO NOTHING``
  (respects ``alert_types_inmutable`` trigger, migration 0013:21-22).

**Downgrade.**

Reverses Op 1 (close ``vigente_hasta`` on the ``cierre_dia`` row) + Op 2
(disable ``alert_types_inmutable`` trigger, DELETE the seeded row,
re-enable trigger). The known 1-hour window limitation (F1.11 pattern)
is documented inline.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0031_arqueo_cierre_dia_and_gap_be_05"
down_revision = "0030_venta_suscripcion_optional"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """MIGRATION 0031 upgrade: pre-flight + Op 1 siembra cierre_dia + Op 2 siembra descuadre_critico + Op 3 NO-DDL anchor."""
    # Op 0 -- pre-flight DO $$ (KD-7 F1.6..F1.12 pattern).
    # Verifies the 7 tables required by F1.13 are present in ``prod``.
    op.execute(
        """
        DO $$
        DECLARE
            _n_tipo_arqueo              bigint;
            _n_alert_types              bigint;
            _n_arqueo                   bigint;
            _n_sesion                   bigint;
            _n_alerta                   bigint;
            _n_config_tolerancias       bigint;
            _n_factura_pagos            bigint;
        BEGIN
            SELECT count(*) INTO _n_tipo_arqueo
                FROM pg_catalog.pg_class
                WHERE relname='tipo_arqueo' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_alert_types
                FROM pg_catalog.pg_class
                WHERE relname='alert_types' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_arqueo
                FROM pg_catalog.pg_class
                WHERE relname='arqueo' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_sesion
                FROM pg_catalog.pg_class
                WHERE relname='sesion' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_alerta
                FROM pg_catalog.pg_class
                WHERE relname='alerta' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_config_tolerancias
                FROM pg_catalog.pg_class
                WHERE relname='configuracion_tolerancias' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_factura_pagos
                FROM pg_catalog.pg_class
                WHERE relname='factura_pagos' AND relnamespace='prod'::regnamespace;

            IF _n_tipo_arqueo IS NULL OR _n_tipo_arqueo = 0 THEN
                RAISE EXCEPTION '0031_preflight_abort: tabla prod.tipo_arqueo no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_alert_types IS NULL OR _n_alert_types = 0 THEN
                RAISE EXCEPTION '0031_preflight_abort: tabla prod.alert_types no existe. '
                                'Aplique MIGRATION 0013 antes.';
            END IF;
            IF _n_arqueo IS NULL OR _n_arqueo = 0 THEN
                RAISE EXCEPTION '0031_preflight_abort: tabla prod.arqueo no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_sesion IS NULL OR _n_sesion = 0 THEN
                RAISE EXCEPTION '0031_preflight_abort: tabla prod.sesion no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_alerta IS NULL OR _n_alerta = 0 THEN
                RAISE EXCEPTION '0031_preflight_abort: tabla prod.alerta no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_config_tolerancias IS NULL OR _n_config_tolerancias = 0 THEN
                RAISE EXCEPTION '0031_preflight_abort: tabla prod.configuracion_tolerancias no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_factura_pagos IS NULL OR _n_factura_pagos = 0 THEN
                RAISE EXCEPTION '0031_preflight_abort: tabla prod.factura_pagos no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;

            RAISE NOTICE '0031_preflight: 7/7 tablas OK '
                         '(tipo_arqueo, alert_types, arqueo, sesion, alerta, '
                         'configuracion_tolerancias, factura_pagos)';
        END;
        $$;
        """
    )

    # Op 1 -- siembra prod.tipo_arqueo.codigo='cierre_dia' (A-07).
    # Idempotent via IF siembra_count = 0 + ON CONFLICT (codigo, vigente_desde) DO NOTHING.
    # The UK tipo_arqueo_uk01(codigo, vigente_desde) enforces uniqueness.
    op.execute(
        """
        DO $$
        DECLARE
            siembra_count INTEGER;
        BEGIN
            SELECT COUNT(*) INTO siembra_count
            FROM prod.tipo_arqueo
            WHERE codigo = 'cierre_dia' AND vigente_hasta IS NULL;

            IF siembra_count = 0 THEN
                INSERT INTO prod.tipo_arqueo (
                    uuid, codigo, nombre, descripcion,
                    vigente_desde, vigente_hasta, estado,
                    created_at, created_by, sync_status, sync_attempts
                ) VALUES (
                    gen_random_uuid(),
                    'cierre_dia',
                    'Cierre de día (mass cierre de sesiones)',
                    'Arqueo de cierre diario que cierra todas las sesiones abiertas del día',
                    NOW(), NULL, 'activo',
                    NOW(), NULL, 'sincronizado', 0
                )
                ON CONFLICT (codigo, vigente_desde) DO NOTHING;
                RAISE NOTICE '0031_op1: siembra inserted (codigo=cierre_dia)';
            ELSE
                RAISE NOTICE '0031_op1: siembra already present (count=%), no-op', siembra_count;
            END IF;
        END $$;
        """
    )

    # Op 2 -- siembra prod.alert_types.tipo_alerta='descuadre_critico', severity='critical'.
    # Idempotent via ON CONFLICT DO NOTHING (respects alert_types_inmutable trigger,
    # migration 0013:21-22). F1.14's planned seed becomes a no-op.
    op.execute(
        """
        INSERT INTO prod.alert_types (tipo_alerta, severity, created_at, created_by)
        VALUES ('descuadre_critico', 'critical', NOW(), 'migrations/0031')
        ON CONFLICT (tipo_alerta) DO NOTHING;
        """
    )

    # Op 3 -- NO-DDL anchor for GAP-BE-05 (DEC-ARQUEO-08).
    # GAP-BE-05 is a Python-only permission correction:
    #   - api/v1/caja.py:53 -- permission_required="emitir_factura" -> "realizar_arqueo"
    #   - api/v1/caja_sesion.py:257 -- permission_required="emitir_factura" -> "abrir_cerrar_caja"
    # No DB schema changes; this comment serves as an audit-trail anchor.
    op.execute(
        """
        DO $$
        BEGIN
            RAISE NOTICE '0031_op3: GAP-BE-05 is a Python-only correction (DEC-ARQUEO-08, plan.md lines 7349-7374). '
                         'No DB schema changes. See api/v1/caja.py:53 + api/v1/caja_sesion.py:257.';
        END $$;
        """
    )


def downgrade() -> None:
    """Reverse Op 1 (close vigente_hasta) + Op 2 (DELETE descuadre_critico)."""
    # Reverse Op 2 -- DELETE prod.alert_types 'descuadre_critico'.
    # alert_types_inmutable trigger blocks DELETE; disable temporarily.
    op.execute("ALTER TABLE prod.alert_types DISABLE TRIGGER alert_types_inmutable;")
    op.execute("DELETE FROM prod.alert_types WHERE tipo_alerta = 'descuadre_critico';")
    op.execute("ALTER TABLE prod.alert_types ENABLE TRIGGER alert_types_inmutable;")

    # Reverse Op 1 -- close vigente_hasta on the cierre_dia row (bi-temporal VersionedBase).
    op.execute(
        """
        UPDATE prod.tipo_arqueo
        SET vigente_hasta = NOW()
        WHERE codigo = 'cierre_dia' AND vigente_hasta IS NULL;
        """
    )

    # Op 3 -- NO-DDL reversal: GAP-BE-05 reversal is a Python revert
    # (out of scope for downgrade()).


__all__ = ["down_revision", "downgrade", "revision", "upgrade"]
