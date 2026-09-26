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

Idempotency: the INSERT is guarded by ``WHERE NOT EXISTS`` against an
already-OPEN row for the same code.

BUG THIS GUARD REPLACES (read before "simplifying" it back)
-----------------------------------------------------------
This migration previously used ``ON CONFLICT (permiso, vigente_desde) DO
NOTHING`` and its docstring claimed that made re-runs a no-op. It does
not. ``permisos_uk01`` is ``(permiso, vigente_desde)`` and
``vigente_desde`` was ``NOW()`` -- re-evaluated per INSERT -- so every
run produced a conflict target that could never match an existing row,
and every run appended a fresh version of all 16 codes.

Measured on the live cloud DB: 15 codes ended up with two OPEN rows
(47 open rows for 32 distinct codes), the first batch stamped
2026-09-23 19:11:32 and the second 19:16:38 — two executions ~5 minutes
apart. The downstream damage was an unhandled HTTP 500 in
``auth/permissions.py::require_permission`` for 16 permission codes.

An ``ON CONFLICT`` whose conflict target contains ``vigente_desde`` does
not do what it looks like it does. The same rule that governs
``0053_seed_resolver_reclamo_permiso.py`` and the ``permisos_usuario``
grant path.

Both seed sets (PR1a's 15 + PR1c's 16) coexist; subsequent PRs grant
``permisos_usuario`` rows that point at whichever code applies to a role.
The two INSERT batches deliberately do not overlap on codes so the total
is 31 rows. (``emitir_factura`` appears in both lists by design — PR1a
shipped it before the canonical taxonomy was finalized; the
``NOT EXISTS`` guard sees PR1a's open row and skips the re-insert, so
that row survives.)
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

    The ``VALUES`` list is projected through a ``SELECT`` so the
    ``NOT EXISTS`` guard can reference ``v.permiso`` per candidate row --
    a single multi-row ``INSERT ... VALUES ... WHERE`` cannot test each
    row against its own code.

    The guard tests for an OPEN (``vigente_hasta IS NULL``) row, not for
    any historical row. The catalogue is versioned, so a closed row must
    NOT block the re-seed: a code that was legitimately closed and then
    re-opened still needs a fresh open version. Testing only for
    "some row with this code exists" would make the seed permanently
    inert after the first logical deletion.

    The explicit ``::uuid`` / ``::timestamptz`` / ``::int`` casts in the
    VALUES list are REQUIRED, not decoration. Routing the tuples through
    ``FROM (VALUES ...) AS v(...)`` detaches them from the INSERT target
    list, so Postgres types each column from the literal expressions
    alone. A bare ``NULL`` there resolves to ``text``, and the INSERT then
    fails with ``DatatypeMismatchError: column "created_by" is of type
    uuid but expression is of type text``. The plain
    ``INSERT ... VALUES`` form this replaced coerced for free; this form
    has to ask.
    """
    values_sql = ",\n            ".join(
        f"(gen_random_uuid()::uuid, '{code}'::text, NOW(), NULL::uuid, "
        f"NOW(), NULL::timestamptz, 'activo'::text, 'sincronizado'::text, 0::int)"
        for code in CANONICAL_PERMISOS
    )
    op.execute(
        f"""
        INSERT INTO prod.permisos (uuid, permiso, created_at, created_by,
                                  vigente_desde, vigente_hasta, estado,
                                  sync_status, sync_attempts)
        SELECT v.uuid, v.permiso, v.created_at, v.created_by,
               v.vigente_desde, v.vigente_hasta, v.estado,
               v.sync_status, v.sync_attempts
        FROM (VALUES
            {values_sql}
        ) AS v (uuid, permiso, created_at, created_by, vigente_desde,
                vigente_hasta, estado, sync_status, sync_attempts)
        WHERE NOT EXISTS (
            SELECT 1 FROM prod.permisos q
            WHERE q.permiso = v.permiso
              AND q.vigente_hasta IS NULL
        );
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