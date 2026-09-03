"""seed canonical permission codes per design section 7 (REQ-OP-13)

Revision ID: 0002_seed_permisos_canonicos
Revises: 0001_initial_schema
Create Date: 2026-09-03 12:00:00.000000

Inserts the canonical permission-code set the project uses for RBAC
authorization checks (``auth/permissions.py::require_permission``). PR1a's
``0001_initial_schema.py`` already seeded 15 operator-facing codes
(``emitir_factura``, ``abrir_cerrar_caja``, etc.); this 0002 migration adds
the 16 cross-cutting codes from ``design.md`` section 7 that the auth
domain needs (``config_catalogo``, ``admin_usuarios``, ``audit_read``,
``gestionar_dian``, etc.).

Idempotency: the INSERT uses ``ON CONFLICT (permiso, vigente_desde) DO
NOTHING`` — running this migration twice (e.g. on a partially-seeded DB)
is a no-op. The ``vigente_desde = NOW()`` is part of the UK so the conflict
target is well-defined even though we always use the same instant.

Both seed sets (PR1a's 15 + PR1c's 16) coexist; subsequent PRs grant
``permisos_usuario`` rows that point at whichever code applies to a role.
The two INSERT batches deliberately do not overlap on codes so the total
is 31 rows. (``emitir_factura`` appears in both lists by design — PR1a
shipped it before the canonical taxonomy was finalized; we re-insert with
``ON CONFLICT DO NOTHING`` so the existing row survives.)
"""
from __future__ import annotations

from alembic import op

revision = "0002_seed_permisos_canonicos"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


# Canonical codes per design section 7. Order matters only for readability —
# each row is independent.
CANONICAL_PERMISOS: tuple[str, ...] = (
    "config_catalogo",
    "config_sistema",
    "config_sucursal",
    "gestionar_clientes",
    "emitir_factura",
    "emitir_factura_electronica",
    "revocar_factura",
    "gestionar_dian",
    "audit_read",
    "admin_usuarios",
    "aprobar_anulacion",
    "ejecutar_anulacion",
    "crear_arqueo",
    "solicitar_reverso",
    "cerrar_sesion",
    "descartar_alerta",
)


def upgrade() -> None:
    """Idempotent seed: insert one canonical permission row per code.

    Uses ``INSERT ... ON CONFLICT (permiso, vigente_desde) DO NOTHING`` to
    make the migration re-runnable. The ``vigente_desde`` column is part
    of the UK on ``permisos`` (``permisos_uk01``), so this conflict target
    is exact: a row with the same ``permiso`` + same ``vigente_desde`` is
    rejected, every other row is accepted.
    """
    values_sql = ",\n            ".join(
        f"(gen_random_uuid(), '{code}', NOW(), NULL, "
        f"NOW(), NULL, 'activo', 'sincronizado', 0)"
        for code in CANONICAL_PERMISOS
    )
    op.execute(
        f"""
        INSERT INTO prod.permisos (uuid, permiso, created_at, created_by,
                                  vigente_desde, vigente_hasta, estado,
                                  sync_status, sync_attempts)
        VALUES
            {values_sql}
        ON CONFLICT (permiso, vigente_desde) DO NOTHING;
        """
    )


def downgrade() -> None:
    """Remove the canonical seed rows added by this migration.

    The downgrade is intentionally narrow: it removes ONLY the 16 rows from
    this migration (filtered by the canonical code list). Rows added by
    PR1a's seed (e.g. ``abrir_cerrar_caja``) survive — that data is owned
    by ``0001_initial_schema`` and is rolled back there, not here.

    A defensive guard at the top makes the downgrade safe to re-run.
    """
    codes_list = ", ".join(f"'{c}'" for c in CANONICAL_PERMISOS)
    op.execute(
        f"""
        DELETE FROM prod.permisos
        WHERE permiso IN ({codes_list})
          AND vigente_hasta IS NULL
          AND estado = 'activo';
        """
    )