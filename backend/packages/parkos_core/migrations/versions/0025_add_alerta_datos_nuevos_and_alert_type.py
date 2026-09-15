"""HU-F1.6 — ``prod.alerta.datos_nuevos JSONB`` column +
``prod.alert_types(tipo_alerta='capacidad_agotada_forzado')`` seed.

Revision ID: 0025_alerta_datos_nuevos
Revises: 0024_mv_ocupacion_diaria (F1.5 chain head)
Create Date: 2026-09-14

**Scope.** Two operations:

  1. ``ALTER TABLE prod.alerta ADD COLUMN IF NOT EXISTS datos_nuevos JSONB``
     — adds a JSONB column to carry the ``motivo`` + ``uuid_ingreso``
     payload for ``capacidad_agotada_forzado`` alerts (REQ-OPS-041.C,
     R-A2 mitigation). NULLABLE — pre-existing rows have no payload; new
     rows set it via :func:`parkos_core.repo.alerta.insertar_alerta_forzado`.

  2. ``INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity)
     VALUES ('capacidad_agotada_forzado', 'Ingreso vehicular forzado
     por administrador al detectar cupo agotado en la sucursal',
     'warning') ON CONFLICT (tipo_alerta) DO NOTHING`` — deploy-seeds
     the canonical alert type identifier (analogous to F1.14's 8 seed
     rows in migration 0013). ``alert_types_inmutable`` trigger
     (migration 0013) blocks UPDATE/DELETE for non-superuser; this
     INSERT-only path respects that contract by using ``ON CONFLICT
     DO NOTHING`` for idempotency.

**Pre-flight (KD-7 F1.5 pattern).** ``DO $$`` block aborts the migration
with a typed error if ``prod.alerta`` does not exist (e.g., a fresh
deployment that never ran migration 0001_initial_schema.py). Emits a
``RAISE NOTICE`` with the row count for the alembic log.

**Idempotency.**
  - ``ADD COLUMN IF NOT EXISTS`` allows the migration to be re-run
    after a partial failure without raising.
  - ``INSERT … ON CONFLICT (tipo_alerta) DO NOTHING`` is the only
    mechanism allowed by ``alert_types_inmutable`` for non-superuser;
    it also provides idempotency on re-apply.

**Downgrade.**
  1. ``DELETE FROM prod.alert_types WHERE tipo_alerta='capacidad_agotada_forzado'``
     — runs as superuser (alembic) so the inmutable trigger is bypassed.
  2. ``ALTER TABLE prod.alerta DROP COLUMN IF EXISTS datos_nuevos``.

**Cross-references.**
  - ``repo/alerta.py::insertar_alerta_forzado`` (NEW, ~60 LOC) writes
    the JSONB payload with motivo + uuid_ingreso.
  - ``migrations/versions/0013_add_alert_types.py`` defines the
    inmutable trigger that this migration respects.
  - ``migrations/versions/0024_add_mv_ocupacion_diaria.py`` is the
    chain head this migration extends.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0025_alerta_datos_nuevos"
down_revision = "0024_mv_ocupacion_diaria"
branch_labels = None
depends_on = None


# Matches the F1.5 / F1.14 migration pattern (0024_add_mv_ocupacion_diaria.py
# line 61 + 0013_add_alert_types.py line 61): cap any blocking DDL at 5s
# so the migration cannot stall the alembic runtime on a busy DB.
_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"


def upgrade() -> None:
    """Apply the F1.6 alert column + alert_type seed."""
    op.execute(_LOCK_TIMEOUT_SQL)

    # 1) Pre-flight (KD-7 F1.5 pattern): prod.alerta must exist.
    op.execute(
        """
        DO $$
        DECLARE
            _n_alerta bigint;
        BEGIN
            SELECT count(*) INTO _n_alerta
            FROM pg_catalog.pg_class
            WHERE relname='alerta'
              AND relnamespace='prod'::regnamespace;
            RAISE NOTICE
                '0025_preflight: prod.alerta existe con % filas',
                _n_alerta;
            IF _n_alerta IS NULL THEN
                RAISE EXCEPTION
                    '0025_preflight_abort: tabla prod.alerta no existe. '
                    'Aplique migrations 0001-0024 antes de continuar.';
            END IF;
        END $$;
        """
    )

    # 2) ADD COLUMN IF NOT EXISTS datos_nuevos JSONB.
    #    Nullable — pre-existing rows have no payload. The column
    #    inherits privileges from the table (rol_app has INSERT on
    #    prod.alerta via standard GRANT; explicit GRANT omitted).
    op.execute(
        "ALTER TABLE prod.alerta "
        "ADD COLUMN IF NOT EXISTS datos_nuevos JSONB"
    )

    # 3) INSERT ON CONFLICT DO NOTHING — respects alert_types_inmutable
    #    trigger (only INSERTs allowed for rol_app; the trigger blocks
    #    UPDATE/DELETE). Idempotent on re-apply.
    op.execute(
        """
        INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity)
        VALUES (
            'capacidad_agotada_forzado',
            'Ingreso vehicular forzado por administrador al detectar '
            'cupo agotado en la sucursal',
            'warning'
        )
        ON CONFLICT (tipo_alerta) DO NOTHING
        """
    )


def downgrade() -> None:
    """Reverse the F1.6 alert column + alert_type seed.

    Runs as superuser in alembic so the ``alert_types_inmutable`` trigger
    does NOT block the DELETE.
    """
    op.execute(_LOCK_TIMEOUT_SQL)

    # 1) Remove the alert_type row (superuser; bypasses inmutable trigger).
    op.execute(
        "DELETE FROM prod.alert_types "
        "WHERE tipo_alerta='capacidad_agotada_forzado'"
    )

    # 2) DROP COLUMN IF EXISTS datos_nuevos.
    op.execute(
        "ALTER TABLE prod.alerta DROP COLUMN IF EXISTS datos_nuevos"
    )


__all__ = ["downgrade", "upgrade"]