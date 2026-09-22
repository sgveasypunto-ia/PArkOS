"""MIGRATION 0041 -- REAL siembra prod.configuracion_tolerancias.

Revision ID: 0041_seed_configuracion_tolerancias
Revises: 0040_seed_tipo_arqueo_codigos
Create Date: 2026-09-21

**Scope.** F11.3 follow-up to the arqueo e2e test (PRs #22, #23, #24).
The BE handler at api/v1/caja_arqueo.py:162-178 looks up the vigente
``prod.configuracion_tolerancias`` row (branch override OR global
fallback) before computing esperado + diferencia. Pre-flight on
2026-09-21 confirmed:

  * ``prod.configuracion_tolerancias`` carries ZERO rows.
  * The original seed at ``0001_initial_schema.py:3302-3311`` should
    have inserted a global default ``(uuid_sucursal=NULL,
    tolerancia_efectivo=0.00, tolerancia_datafono=0.00)`` but the row
    is missing. Possibly a rolled-back migration or a misapplied
    INSERT.
  * No per-branch override exists either.

Without this seed the POST /api/v1/caja/arqueo returns 404
``tolerancia_no_configurada`` even for the F10.1 partial arqueo (which
only needs the tolerance for the ``es_descuadre_critico`` alerta
branch, KD-ARQUEO-04; the basic diferencia compute doesn't need it
but the handler short-circuits on missing tolerance for consistency).

**Siembra operations.**

Two idempotent INSERTs:

  1. Global default (``uuid_sucursal IS NULL``, tolerancia 10000.00
     COP for both medios_pago). The branch override resolver falls
     back to this row when no per-branch row exists.

  2. Branch override for the local dev branch
     ``2049f2cd-b2a8-4e45-9d19-31fa87eb67c6`` (BOG-CEN from the dev
     seed) with the same 10000.00 COP tolerancia. The override exists
     so the e2e test in PR #21's verification script
     (``apps/electron-sucursal/docs/dashboard-arqueo-right-panel.png``)
     has a non-empty branch-specific path. A future PR can either
     drop this row (rely on the global) or replace it with the
     admin-configured per-branch value via the F1.14
     configuracion_tolerancias PUT endpoint.

The tolerancia value 10000.00 COP is a placeholder: any
``|diferencia| < 10000`` is considered within tolerance, anything
above triggers the ``es_descuadre_critico`` flag. The admin can
override this via the configuracion endpoint; this seed value is
intentionally conservative so the F10.1 e2e test that posts a
70000 COP diferencia triggers the alerta branch.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0041_seed_configuracion_tolerancias"
down_revision = "0040_seed_tipo_arqueo_codigos"
branch_labels = None
depends_on = None


_GLOBAL_DEFAULT_UUID_SUCURSAL = "2049f2cd-b2a8-4e45-9d19-31fa87eb67c6"
_GLOBAL_DEFAULT_TOLERANCIA_EFECTIVO = 10000.00
_GLOBAL_DEFAULT_TOLERANCIA_DATAFONO = 10000.00


def upgrade() -> None:
    """Siembra idempotente: 1 global default + 1 branch override."""
    # Global default -- uuid_sucursal=NULL row.
    op.execute(
        f"""
        DO $$
        DECLARE
            siembra_count INTEGER;
        BEGIN
            SELECT COUNT(*) INTO siembra_count
            FROM prod.configuracion_tolerancias
            WHERE uuid_sucursal IS NULL AND vigente_hasta IS NULL;

            IF siembra_count = 0 THEN
                INSERT INTO prod.configuracion_tolerancias (
                    uuid, uuid_sucursal,
                    tolerancia_efectivo, tolerancia_datafono,
                    vigente_desde, vigente_hasta, estado,
                    created_at, created_by, sync_status, sync_attempts
                ) VALUES (
                    gen_random_uuid(), NULL,
                    {_GLOBAL_DEFAULT_TOLERANCIA_EFECTIVO},
                    {_GLOBAL_DEFAULT_TOLERANCIA_DATAFONO},
                    NOW(), NULL, 'activo',
                    NOW(), NULL, 'sincronizado', 0
                )
                ON CONFLICT (uuid_sucursal, vigente_desde) DO NOTHING;
                RAISE NOTICE '0041_op1: global default inserted (uuid_sucursal=NULL)';
            ELSE
                RAISE NOTICE '0041_op1: global default already present (count=%), no-op',
                              siembra_count;
            END IF;
        END $$;
        """
    )

    # Branch override for the dev branch.
    op.execute(
        f"""
        DO $$
        DECLARE
            siembra_count INTEGER;
        BEGIN
            SELECT COUNT(*) INTO siembra_count
            FROM prod.configuracion_tolerancias
            WHERE uuid_sucursal = '{_GLOBAL_DEFAULT_UUID_SUCURSAL}'
                  AND vigente_hasta IS NULL;

            IF siembra_count = 0 THEN
                INSERT INTO prod.configuracion_tolerancias (
                    uuid, uuid_sucursal,
                    tolerancia_efectivo, tolerancia_datafono,
                    vigente_desde, vigente_hasta, estado,
                    created_at, created_by, sync_status, sync_attempts
                ) VALUES (
                    gen_random_uuid(), '{_GLOBAL_DEFAULT_UUID_SUCURSAL}',
                    {_GLOBAL_DEFAULT_TOLERANCIA_EFECTIVO},
                    {_GLOBAL_DEFAULT_TOLERANCIA_DATAFONO},
                    NOW(), NULL, 'activo',
                    NOW(), NULL, 'sincronizado', 0
                )
                ON CONFLICT (uuid_sucursal, vigente_desde) DO NOTHING;
                RAISE NOTICE '0041_op2: branch override inserted for %',
                              '{_GLOBAL_DEFAULT_UUID_SUCURSAL}';
            ELSE
                RAISE NOTICE '0041_op2: branch override already present (count=%), no-op',
                              siembra_count;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Reverse: close (vigente_hasta=NOW) both rows so the catalogo
    filters them out. Rows stay in the table for audit (4NF
    insert-only).
    """
    op.execute(
        """
        UPDATE prod.configuracion_tolerancias
        SET vigente_hasta = NOW()
        WHERE uuid_sucursal IS NULL AND vigente_hasta IS NULL;
        """
    )
    op.execute(
        f"""
        UPDATE prod.configuracion_tolerancias
        SET vigente_hasta = NOW()
        WHERE uuid_sucursal = '{_GLOBAL_DEFAULT_UUID_SUCURSAL}'
              AND vigente_hasta IS NULL;
        """
    )
