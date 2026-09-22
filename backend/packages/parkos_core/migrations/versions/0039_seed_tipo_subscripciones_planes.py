"""F11.3 BE follow-up -- seed prod.tipo_subscripciones with 5 real subscription plans so the F11.3 Venta wizard step 3 catalog renders substantive plans instead of empty placeholder rows.

Revision ID: 0039_seed_tipo_subscripciones_planes
Revises: 0038_calcular_cotizacion_2nd_plate_rotation (F1.13 chain head)
Create Date: 2026-09-21

**Scope.**

Before this migration, prod.tipo_subscripciones carried 53 rows
(F1.13-era) all with valor IS NULL or duracion_dias IS NULL -- placeholder
rows from the initial schema migration. The catalog list endpoint
faithfully returned them via vigente_hasta IS NULL. The F11.3 catalog UI
in apps/electron-sucursal rendered those with formatCOP(0) -- "$ 0 COP"
cards. Useless for an operator trying to pick a plan.

Two operations:

1. Op 1 -- close stale rows. UPDATE prod.tipo_subscripciones SET
   vigente_hasta = NOW() WHERE (valor IS NULL OR BTRIM(tipo) = '') AND
   vigente_hasta IS NULL. Closes the 53 placeholder rows so the SELECT
   list (filters vigente_hasta IS NULL) returns ONLY the new plans
   from Op 2.

2. Op 2 -- insert 5 real plans. INSERT INTO prod.tipo_subscripciones
   (uuid, tipo, valor, duracion_dias, cantidad_maxima_vehiculos,
   mismo_tipo_vehiculo, tipo_cliente_permitido, vigente_desde,
   vigente_hasta, estado, created_at, created_by) -- five Colombian
   parking plans covering the auto / moto / corporate tiers.

**Pre-flight (KD-7 pattern).**

DO $$ block verifies prod.tipo_subscripciones exists (created in
migration 0001_initial_schema lines 195-210) before any DML. Aborts
with a typed 0039_preflight_abort exception if missing.

**Bi-temporal versioning (UK on (tipo, vigente_desde)).**

Op 2 sets vigente_desde = NOW() so the new rows become the canonical
vigente versions (the SELECT list filters vigente_hasta IS NULL).
Op 1 already closed the stale rows; the two operations together leave
the SELECT list returning exactly the 5 new plans.

**Idempotency.**

The migration is intentionally NOT idempotent across re-applies:
re-running Op 1 + Op 2 on a stack that ALREADY has the 5 new plans
will leave the stale rows still closed (harmless) and produce a UK
collision when re-inserting Op 2 (the migration aborts). Recovery:
alembic stamp 0039_head if a re-run is ever needed.

**Downgrade.**

Op 2 inverse: DELETE FROM prod.tipo_subscripciones WHERE tipo IN (...)
(closes + delete the 5 new rows). The stale rows from Op 1 stay
closed (reviving them would require bi-temporal history; not
necessary for a downgrade). Effectively the operator re-applies
migration 0001-era placeholder rows if they want a clean state.

**Cross-references.**

- apps/electron-sucursal/src/features/suscripciones/hooks/useTiposSubscripciones.ts
  consumes this catalog via GET /api/v1/catalogos/tipo-subscripciones.
- catalogos.py lines 148-155 mounts the catalog endpoint at
  /api/v1/catalogos/tipo-subscripciones (F1.12 archive).
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0039_seed_tipo_subscripciones_planes"
down_revision = "0038_calcular_cotizacion_2nd_plate_rotation"
branch_labels = None
depends_on = None


# Matches the F1.5 / F1.14 / F9.1 / F11.2 migration pattern
# (0024_add_mv_ocupacion_diaria.py line 61, 0013_add_alert_types.py
# line 61, 0030_venta_suscripcion_optional.py line 65): cap any blocking
# DDL at 5s so the migration cannot stall the alembic runtime on a
# busy DB.
_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"


def upgrade() -> None:
    """Apply the F11.3 plan catalog seed."""
    op.execute(_LOCK_TIMEOUT_SQL)

    # 1) Pre-flight (KD-7 pattern): prod.tipo_subscripciones must exist.
    op.execute(
        """
        DO $$
        DECLARE
            _n_tipo_subscripciones bigint;
        BEGIN
            SELECT count(*) INTO _n_tipo_subscripciones
            FROM pg_catalog.pg_class
            WHERE relname='tipo_subscripciones'
              AND relnamespace='prod'::regnamespace;
            IF _n_tipo_subscripciones IS NULL OR _n_tipo_subscripciones = 0 THEN
                RAISE EXCEPTION
                    '0039_preflight_abort: tabla prod.tipo_subscripciones no existe. '
                    'Corra 0001_initial_schema.py antes de 0039_seed_tipo_subscripciones_planes.py.';
            END IF;
            RAISE NOTICE '0039_preflight OK: prod.tipo_subscripciones existe (% filas).', _n_tipo_subscripciones;
        END $$;
        """
    )

    # 2) Op 1 -- close stale empty placeholder rows so the SELECT list
    # (vigente_hasta IS NULL) does not return them after the new plans
    # are inserted. Closes 53 rows. Idempotent: re-runs close zero rows
    # if Op 1 already ran.
    op.execute(
        """
        UPDATE prod.tipo_subscripciones
        SET vigente_hasta = NOW()
        WHERE (valor IS NULL OR BTRIM(tipo) = '')
          AND vigente_hasta IS NULL
        """
    )

    # 3) Op 2 -- insert 5 real Colombian parking subscription plans.
    # The (tipo, vigente_desde) UK means each tipo appears at most once
    # with vigente_hasta IS NULL -- exactly what the catalog endpoint
    # returns. The 0001_initial_schema.py column list + the audit /
    # set-vigente-inicial triggers apply the standard column defaults
    # (created_at = NOW(), created_by = NULL), so we just need to
    # supply the business columns.
    op.execute(
        """
        INSERT INTO prod.tipo_subscripciones (
            uuid,
            tipo,
            valor,
            duracion_dias,
            cantidad_maxima_vehiculos,
            mismo_tipo_vehiculo,
            tipo_cliente_permitido,
            vigente_desde,
            vigente_hasta,
            estado
        ) VALUES
            (
                '11111111-1111-4111-8111-111111111111',
                'MENSUAL_AUTO',
                120000.0000,
                30,
                1,
                TRUE,
                'natural',
                NOW(),
                NULL,
                'activo'
            ),
            (
                '22222222-2222-4222-8222-222222222222',
                'MENSUAL_MOTO',
                60000.0000,
                30,
                1,
                TRUE,
                'natural',
                NOW(),
                NULL,
                'activo'
            ),
            (
                '33333333-3333-4333-8333-333333333333',
                'BIMESTRAL_AUTO',
                220000.0000,
                60,
                1,
                TRUE,
                'natural',
                NOW(),
                NULL,
                'activo'
            ),
            (
                '44444444-4444-4444-8444-444444444444',
                'TRIMESTRAL_AUTO',
                320000.0000,
                90,
                1,
                TRUE,
                'natural',
                NOW(),
                NULL,
                'activo'
            ),
            (
                '55555555-5555-4555-8555-555555555555',
                'MENSUAL_EMPRESA',
                800000.0000,
                30,
                10,
                FALSE,
                'juridica',
                NOW(),
                NULL,
                'activo'
            )
        """
    )


def downgrade() -> None:
    """Reverse Op 2: delete the 5 new plans. Op 1 is not reversed
    (reviving closed stale rows would require bi-temporal history
    beyond what a downgrade should do)."""
    op.execute(_LOCK_TIMEOUT_SQL)
    op.execute(
        """
        DELETE FROM prod.tipo_subscripciones
        WHERE tipo IN (
            'MENSUAL_AUTO',
            'MENSUAL_MOTO',
            'BIMESTRAL_AUTO',
            'TRIMESTRAL_AUTO',
            'MENSUAL_EMPRESA'
        )
        """
    )
