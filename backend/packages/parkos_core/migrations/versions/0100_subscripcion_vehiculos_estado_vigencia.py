"""MIGRATION 0100 -- ``subscripcion_vehiculos``: estado y vigencia coherentes (bug #18).

Revision ID: 0100_subscripcion_vehiculos_estado_vigencia
Revises: 0099_sync_configuracion_caja

**Why.** "Quitar placa" cerraba la fila vigente y ``versioned.close_and_insert``
insertaba una fila NUEVA con ``estado='inactivo'`` pero ``vigente_hasta IS NULL``:
quedaba una fila abierta fantasma y los lectores que filtran solo por vigencia
trataban la placa quitada como inscrita (salida sin cobro de mensualidad).
El codigo ya cierra con ``versioned.close_only``; esta migracion repara los
datos y deja la invariante en la base.

**What it does** (``subscripcion_vehiculos`` is ``[V]``, not ``[A]``: the
immutability rule "REVOKE + BEFORE UPDATE OR DELETE" does not apply, and the
table has no UPDATE trigger):

1. Data repair: a phantom row (open + ``estado='inactivo'``) is closed with
   ``vigente_hasta = vigente_desde`` (a zero-length interval: it never covered
   anything). No row is deleted and no ``estado`` changes. ``vigente_hasta`` is
   only set where it is NULL, so the repair is idempotent.
2. Partial unique index ``uq_subscripcion_vehiculos_abierta_activa`` on
   ``(uuid_subscripcion_cliente, uuid_vehiculo) WHERE vigente_hasta IS NULL AND
   estado = 'activo'``: at most one open active version per (subscription,
   vehicle).
3. ``CHECK ck_subscripcion_vehiculos_estado_vigencia``:
   ``(estado = 'inactivo') = (vigente_hasta IS NOT NULL)``. Created ``NOT VALID``
   and validated after the repair (so the ACCESS EXCLUSIVE window is short and
   the validation scans with a weaker lock).

**Idempotent.** The UPDATE is a no-op once repaired; the index uses
``IF NOT EXISTS``; the constraint is added only if absent and validated every
time. Plain (non-CONCURRENT) index build under ``lock_timeout = '5s'``: the
table is small. The downgrade drops the CHECK and the index; the repaired data
stays repaired.
"""

from __future__ import annotations

from alembic import op

revision = "0100_subscripcion_vehiculos_estado_vigencia"
down_revision = "0099_sync_configuracion_caja"
branch_labels = None
depends_on = None

TABLE = "prod.subscripcion_vehiculos"
INDEX = "uq_subscripcion_vehiculos_abierta_activa"
CHECK = "ck_subscripcion_vehiculos_estado_vigencia"


REPAIR_SQL = f"""
    UPDATE {TABLE}
       SET vigente_hasta = vigente_desde
     WHERE vigente_hasta IS NULL
       AND estado = 'inactivo'
    """


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    # 1. Repair the phantom open-inactive rows (closed at their own start).
    op.execute(REPAIR_SQL)
    # 2. One open active version per (subscription, vehicle).
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {INDEX}
            ON {TABLE} (uuid_subscripcion_cliente, uuid_vehiculo)
         WHERE vigente_hasta IS NULL AND estado = 'activo'
        """
    )
    # 3. estado <-> vigencia coherence: NOT VALID first, VALIDATE after repair.
    op.execute(
        f"""
        DO $do$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                 WHERE conrelid = '{TABLE}'::regclass AND conname = '{CHECK}'
            ) THEN
                ALTER TABLE {TABLE}
                    ADD CONSTRAINT {CHECK}
                    CHECK ((estado = 'inactivo') = (vigente_hasta IS NOT NULL))
                    NOT VALID;
            END IF;
        END
        $do$
        """
    )
    op.execute(f"ALTER TABLE {TABLE} VALIDATE CONSTRAINT {CHECK}")


def downgrade() -> None:
    """Drop the CHECK and the index (the repaired rows are left as they are)."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {CHECK}")
    op.execute(f"DROP INDEX IF EXISTS prod.{INDEX}")
