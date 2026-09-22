"""MIGRATION 0043 -- grant column-scoped UPDATE on prod.ingreso_consecutivo_contador.

REGRESSION (2026-09-22, REQ-OPS-193 follow-up): migration 0042 issued
``REVOKE UPDATE, DELETE ON prod.ingreso_consecutivo_contador FROM rol_app``
to enforce the [A] (append-only + carve-out) discipline at the DB layer.

That REVOKE was correct for the *user-facing* UPDATE path (the operator
must not bypass the counter via a manual UPDATE). But the operational
carve-out trigger ``fn_ingreso_consecutivo_contador_carveout`` permits
the *server-side* helper ``repo/ingreso_consecutivo::assign_ingreso_
consecutivo`` to advance ``ultimo_consecutivo`` via ``SELECT ... FOR
UPDATE`` + UPDATE on the carve-out columns.

PostgreSQL ``SELECT ... FOR UPDATE`` requires UPDATE privilege on the
table (regardless of which columns the subsequent UPDATE actually
touches). With ``rol_app`` holding only SELECT/INSERT, the helper
raised:

    asyncpg.exceptions.InsufficientPrivilegeError:
        permission denied for table ingreso_consecutivo_contador

Fix: GRANT UPDATE on the *carve-out columns only* (column-level GRANT
syntax, requires PostgreSQL 9.0+). The defense-in-depth posture is
preserved -- UPDATE on any column OUTSIDE the carve-out list is still
rejected by both the GRANT and the BEFORE UPDATE trigger. The trigger
carve-out already enforces byte-identical-to-OLD on all other columns;
the GRANT-level restriction is belt-and-suspenders.

Carve-out columns (matches ``fn_ingreso_consecutivo_contador_carveout``
and the columns ``assign_ingreso_consecutivo`` mutates):

  * ``ultimo_consecutivo``  -- the monotonic counter
  * ``last_event_uuid``      -- idempotency anchor
  * ``sync_status``          -- sync queue metadata
  * ``sync_timestamp``       -- sync queue metadata
  * ``sync_attempts``        -- sync queue metadata

All other columns (uuid, uuid_sucursal, uuid_tipo_vehiculo,
vigente_desde, vigente_hasta, estado, created_at, created_by,
fecha_retencion_hasta) are NOT UPDATEable by rol_app.
"""
from __future__ import annotations

from alembic import op


revision = "0043_counter_table_column_grants"
down_revision = "0042_add_ingreso_consecutivo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply column-scoped UPDATE grants to rol_app on the counter table."""
    op.execute(
        "GRANT UPDATE ("
        "ultimo_consecutivo, "
        "last_event_uuid, "
        "sync_status, "
        "sync_timestamp, "
        "sync_attempts"
        ") ON prod.ingreso_consecutivo_contador TO rol_app"
    )


def downgrade() -> None:
    """Revoke the column-scoped UPDATE grant added in 0043."""
    op.execute(
        "REVOKE UPDATE ("
        "ultimo_consecutivo, "
        "last_event_uuid, "
        "sync_status, "
        "sync_timestamp, "
        "sync_attempts"
        ") ON prod.ingreso_consecutivo_contador FROM rol_app"
    )


__all__ = ["upgrade", "downgrade"]
