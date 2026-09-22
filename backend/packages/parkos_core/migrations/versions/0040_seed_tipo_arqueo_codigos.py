"""MIGRATION 0040 -- REAL siembra tipo_arqueo (4 codigos: auditoria +
cierre_turno + cierre_sesion + cierre_dia).

Revision ID: 0040_seed_tipo_arqueo_codigos
Revises: 0039_seed_tipo_subscripciones_planes
Create Date: 2026-09-21

**Scope.** F11.3 follow-up: the BE handler at api/v1/caja_arqueo.py:77
resolves ``payload.uuid_tipo_arqueo`` (UUID, not codigo) against
``prod.tipo_arqueo`` and branches on ``tipo_arqueo.codigo`` for the
cierre_dia / auditoria discrimination logic. The FE must therefore
send the UUID, not the codigo, and the DB must have rows with all
4 canonical codigos. Pre-flight on 2026-09-21 confirmed:

  * ``prod.tipo_arqueo`` carries 5 placeholder rows (from earlier
    migrations) with ``codigo=NULL``. ``auditoria``, ``cierre_turno``,
    ``cierre_sesion``, ``cierre_dia`` are MISSING -> this migration
    seeds all 4 (A-07, plan.md line 458).
  * The earlier ``0031_arqueo_cierre_dia_and_gap_be_05`` migration's
    Op 1 seed of ``cierre_dia`` was apparently never applied on this
    branch DB (or was rolled back). This migration is idempotent
    (``ON CONFLICT (codigo, vigente_desde) DO NOTHING``) so a re-run
    is a no-op.
  * The 5 placeholder rows are LEFT IN PLACE (they do not conflict
    with the canonical codigos because their codigo is NULL and the
    UK is ``(codigo, vigente_desde)``). A follow-up housekeeping
    migration may close them via bi-temporal close+insert once the
    FE no longer needs them as visual smoke-tests in the catalogo
    GET.

**Siembra operations.**

Inserts one row per codigo, idempotent. ``vigente_hasta=NULL`` makes
the row "current" (visible to the catalogo GET that filters
``vigente_hasta IS NULL``). ``vigente_desde=NOW()`` so the UK
``(codigo, vigente_desde)`` is unique per insert.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0040_seed_tipo_arqueo_codigos"
down_revision = "0039_seed_tipo_subscripciones_planes"
branch_labels = None
depends_on = None


_CODIGOS = [
    (
        "auditoria",
        "Auditoría parcial (sin cierre)",
        "Arqueo parcial de auditoría durante un turno abierto. No cierra la sesión.",
    ),
    (
        "cierre_turno",
        "Cierre de turno",
        "Arqueo al cierre de un turno individual del operador. Cierra la sesión activa.",
    ),
    (
        "cierre_sesion",
        "Cierre de sesión (admin)",
        "Arqueo forzado de una sesión por un supervisor (admin-only).",
    ),
    (
        "cierre_dia",
        "Cierre de día (mass cierre)",
        "Arqueo de cierre diario que cierra todas las sesiones abiertas del día.",
    ),
]


def upgrade() -> None:
    """Siembra idempotente: inserta los 4 codigos canonicos en prod.tipo_arqueo."""
    for codigo, nombre, descripcion in _CODIGOS:
        op.execute(
            f"""
            DO $$
            DECLARE
                siembra_count INTEGER;
            BEGIN
                SELECT COUNT(*) INTO siembra_count
                FROM prod.tipo_arqueo
                WHERE codigo = '{codigo}' AND vigente_hasta IS NULL;

                IF siembra_count = 0 THEN
                    INSERT INTO prod.tipo_arqueo (
                        uuid, codigo, nombre, descripcion,
                        vigente_desde, vigente_hasta, estado,
                        created_at, created_by, sync_status, sync_attempts
                    ) VALUES (
                        gen_random_uuid(),
                        '{codigo}',
                        '{nombre}',
                        '{descripcion}',
                        NOW(), NULL, 'activo',
                        NOW(), NULL, 'sincronizado', 0
                    )
                    ON CONFLICT (codigo, vigente_desde) DO NOTHING;
                    RAISE NOTICE '0040_op: siembra inserted (codigo=%)', '{codigo}';
                ELSE
                    RAISE NOTICE '0040_op: siembra already present (codigo=%, count=%), no-op',
                                  '{codigo}', siembra_count;
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    """Reverse: bi-temporal close (set vigente_hasta=NOW()) on the 4
    canonical rows so the catalogo GET no longer returns them as
    current. The rows stay in the table for audit (4NF insert-only).
    """
    for codigo, _nombre, _descripcion in _CODIGOS:
        op.execute(
            f"""
            UPDATE prod.tipo_arqueo
            SET vigente_hasta = NOW()
            WHERE codigo = '{codigo}' AND vigente_hasta IS NULL;
            """
        )
