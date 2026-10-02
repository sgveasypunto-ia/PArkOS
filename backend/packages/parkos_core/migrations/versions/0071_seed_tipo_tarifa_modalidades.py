"""MIGRATION 0071 -- siembra prod.tipo_tarifa (4 modalidades canonicas).

Revision ID: 0071_seed_tipo_tarifa_modalidades
Revises: 0070_grant_configuracion_caja_privileges
Create Date: 2026-10-02

**Scope.** QA Fase 2 (batch Tarifas/Cupos) pre-flight found
``prod.tipo_tarifa`` completely empty in every environment -- no prior
migration ever seeded it -- while
``apps/web_admin/src/features/tarifas/api/tarifaAgrupada.ts:43-46``
hardcodes 4 fixed UUIDs (hora/fraccion/plena/nocturna) to build the
CREATE/EDIT/HISTORIAL payloads and to group the flattened tarifas list
(``Tarifas.tsx::onSubmit`` imports the same constants). Without a seed
the Tarifas module is broken out of the box on any fresh install, not
just this QA environment -- this is the real bug, not merely a QA data
gap.

**Decision.** Seed the catalog with the SAME fixed UUIDs the frontend
already hardcodes (instead of rewriting the frontend to resolve by
name/code), because: (1) the generic catalog POST
(``router_factory.make_router``) always calls ``gen_random_uuid()`` on
insert, so there is no way to make the UI "create" these 4 rows with a
chosen UUID; (2) the 4 modalidades are a fixed, closed, non-editable-by-
operators set (no catalog screen lets an admin add a 5th modalidad --
``Tarifas.tsx`` only ever emits these 4 literals), so a migration-level
siembra matches the existing project pattern for closed catalogs
(``0040_seed_tipo_arqueo_codigos``, ``0032_seed_alert_types_operativos``)
far better than threading a name/code lookup through every tarifa
CREATE/EDIT/HISTORIAL call site. Explicit fixed ``uuid`` literals (not
``gen_random_uuid()``) keep the frontend lookup stable across
re-applies and fresh installs.

**Siembra operations.** Idempotent: one ``DO $$`` block per modalidad,
inserts only when no row with that exact fixed ``uuid`` exists yet.
``vigente_hasta=NULL`` makes the row "current".
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0071_seed_tipo_tarifa_modalidades"
down_revision = "0070_grant_configuracion_caja_privileges"
branch_labels = None
depends_on = None


# (tipo, uuid fijo) -- el uuid DEBE coincidir exacto con
# apps/web_admin/src/features/tarifas/api/tarifaAgrupada.ts:43-46.
_SEED_ROWS: tuple[tuple[str, str], ...] = (
    ("hora", "12e3886a-7059-47ee-bdb2-aa5fb1272bea"),
    ("fraccion", "c41b6602-f7b2-437d-bcfc-0462cd385eda"),
    ("plena", "d83ebff8-9546-43b3-91b1-bedffa57717f"),
    ("nocturna", "9f8ba4a9-6fd9-4da7-8ddb-97ce323a8600"),
)


def upgrade() -> None:
    """Siembra idempotente: inserta las 4 modalidades con UUID fijo."""
    for tipo, uuid_fijo in _SEED_ROWS:
        op.execute(
            f"""
            DO $$
            DECLARE
                siembra_count INTEGER;
            BEGIN
                SELECT COUNT(*) INTO siembra_count
                FROM prod.tipo_tarifa
                WHERE uuid = '{uuid_fijo}';

                IF siembra_count = 0 THEN
                    INSERT INTO prod.tipo_tarifa (
                        uuid, tipo,
                        vigente_desde, vigente_hasta, estado,
                        created_at, created_by, sync_status, sync_attempts
                    ) VALUES (
                        '{uuid_fijo}',
                        '{tipo}',
                        NOW(), NULL, 'activo',
                        NOW(), NULL, 'sincronizado', 0
                    )
                    ON CONFLICT (tipo, vigente_desde) DO NOTHING;
                    RAISE NOTICE '0071_op: siembra inserted (tipo=%, uuid=%)', '{tipo}', '{uuid_fijo}';
                ELSE
                    RAISE NOTICE '0071_op: siembra already present (tipo=%, uuid=%), no-op',
                                  '{tipo}', '{uuid_fijo}';
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    """Reverse: bi-temporal close (set vigente_hasta=NOW()) on the 4
    canonical rows. Rows stay in the table for audit (4NF insert-only).
    """
    for _tipo, uuid_fijo in _SEED_ROWS:
        op.execute(
            f"""
            UPDATE prod.tipo_tarifa
            SET vigente_hasta = NOW()
            WHERE uuid = '{uuid_fijo}' AND vigente_hasta IS NULL;
            """
        )
