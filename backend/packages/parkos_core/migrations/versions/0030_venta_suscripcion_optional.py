"""HU-F1.12 / MIGRATION 0030 -- NO-OP audit trail.

Revision ID: 0030_venta_suscripcion_optional
Revises: 0029_reimpresion_siembra_and_permiso_anular (F1.11 head)
Create Date: 2026-09-15

**Scope.** Pre-flight ``DO $$`` assertion block only. NO schema changes,
NO sync catalog seeds, NO permission grants.

**Rationale (DEC-VENTA-08 WITHDRAWN).**

Pre-flight on 2026-09-15 confirmed all 5 [V] tables + sync catalog
entries are pre-existing:

  * ``prod.clientes``              [V] -- 0001_initial_schema lines 435-452
  * ``prod.vehiculos``             [V] -- 0001_initial_schema lines 454-465
  * ``prod.tipo_subscripciones``   [V] -- 0001_initial_schema lines 195-210
  * ``prod.subscripciones_cliente`` [V] -- 0001_initial_schema lines 483-496
  * ``prod.subscripcion_vehiculos`` [V] -- 0001_initial_schema lines 498-509

All 5 [V] sync catalog entries verified at
``backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_v.py``
lines 134, 452, 484, 512, 526 (DEC-VENTA-08 originally speculated seeding
but was withdrawn after pre-flight verification).

The ``gestionar_clientes`` permission is already registered at migration
0001 line 3292 (DEC-VENTA-08 final state: nothing to seed).

**Pre-flight DO $$ block.**

Verifies the 5 [V] tables exist + the 5 [V] sync catalog entries
are registered in ``prod.sync_catalog``. Emits ``RAISE NOTICE`` on
success; aborts with a typed ``0030_preflight_abort`` exception if
any table or sync entry is missing.

**Empty upgrade() + downgrade().**

The pre-flight is the audit trail. No schema or catalog changes
take place; downgrade is a no-op (only the migration head pointer
reverts).
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0030_venta_suscripcion_optional"
# 0029b_seed_sync_catalog (2026-09-21) inserted between 0029 and 0030 to
# create + seed the ``prod.sync_catalog`` projection table the pre-flight
# below queries. Was ``0029_reimpresion_siembra_and_permiso_anular``
# before the fix; the chain now reads
# 0029 → 0029b → 0030 → 0031 → ... → 0038 (single head).
down_revision = "0029b_seed_sync_catalog"
branch_labels = None
depends_on = None

# The 5 [V] sync catalog entry identifiers (DEC-VENTA-08 verified pre-existing).
_V_SYNC_ENTRY_NAMES = (
    "tipo_subscripciones",
    "clientes",
    "vehiculos",
    "subscripciones_cliente",
    "subscripcion_vehiculos",
)


def upgrade() -> None:
    """Pre-flight ``DO $$`` only -- NO schema changes (MIGRATION 0030 audit trail)."""
    op.execute(
        """
        DO $$
        DECLARE
            _n_tipo_subscripciones    bigint;
            _n_clientes               bigint;
            _n_vehiculos              bigint;
            _n_subscripciones_cliente bigint;
            _n_subscripcion_vehiculos bigint;
            _n_sync_entries           bigint;
            _entry_name               text;
        BEGIN
            -- 5 [V] tables must exist -----------------------------------
            SELECT count(*) INTO _n_tipo_subscripciones
                FROM pg_catalog.pg_class
                WHERE relname='tipo_subscripciones' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_clientes
                FROM pg_catalog.pg_class
                WHERE relname='clientes' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_vehiculos
                FROM pg_catalog.pg_class
                WHERE relname='vehiculos' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_subscripciones_cliente
                FROM pg_catalog.pg_class
                WHERE relname='subscripciones_cliente' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_subscripcion_vehiculos
                FROM pg_catalog.pg_class
                WHERE relname='subscripcion_vehiculos' AND relnamespace='prod'::regnamespace;

            IF _n_tipo_subscripciones IS NULL OR _n_tipo_subscripciones = 0 THEN
                RAISE EXCEPTION '0030_preflight_abort: tabla prod.tipo_subscripciones no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_clientes IS NULL OR _n_clientes = 0 THEN
                RAISE EXCEPTION '0030_preflight_abort: tabla prod.clientes no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_vehiculos IS NULL OR _n_vehiculos = 0 THEN
                RAISE EXCEPTION '0030_preflight_abort: tabla prod.vehiculos no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_subscripciones_cliente IS NULL OR _n_subscripciones_cliente = 0 THEN
                RAISE EXCEPTION '0030_preflight_abort: tabla prod.subscripciones_cliente no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_subscripcion_vehiculos IS NULL OR _n_subscripcion_vehiculos = 0 THEN
                RAISE EXCEPTION '0030_preflight_abort: tabla prod.subscripcion_vehiculos no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;

            -- 5 [V] sync catalog entries must be registered -------------
            FOREACH _entry_name IN ARRAY ARRAY[
                'tipo_subscripciones',
                'clientes',
                'vehiculos',
                'subscripciones_cliente',
                'subscripcion_vehiculos'
            ] LOOP
                SELECT count(*) INTO _n_sync_entries
                    FROM prod.sync_catalog
                    WHERE entity_name = _entry_name;
                IF _n_sync_entries IS NULL OR _n_sync_entries = 0 THEN
                    RAISE EXCEPTION '0030_preflight_abort: sync catalog entry % '
                                    'not registered in prod.sync_catalog. '
                                    'Apply MIGRATION 0001 + sync catalog seeds before 0030.',
                                    _entry_name;
                END IF;
            END LOOP;

            RAISE NOTICE '0030_preflight: 5/5 [V] tables OK + 5/5 [V] sync catalog entries registered';
        END;
        $$;
        """
    )


def downgrade() -> None:
    """NO-OP -- MIGRATION 0030 has no schema changes to reverse.

    The pre-flight ``DO $$`` block in ``upgrade()`` is the audit trail.
    Downgrade is empty so the migration head pointer simply reverts
    without affecting any table or catalog state.
    """


__all__ = ["down_revision", "downgrade", "revision", "upgrade"]