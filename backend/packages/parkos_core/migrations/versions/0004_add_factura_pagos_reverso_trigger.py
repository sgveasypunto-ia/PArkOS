"""BEFORE INSERT trigger for factura_pagos reverso uniqueness (PR6-T06, SC-11).

PostgreSQL rejects partial UNIQUE indexes on RANGE-partitioned tables that
don't include the partition key. Since ``prod.factura_pagos`` is
partitioned by ``RANGE (fecha_retencion_hasta)`` and its PK is
``(uuid, fecha_retencion_hasta)``, the original partial-UK design would
silently fail SC-11.

This migration installs a ``BEFORE INSERT`` trigger that raises when a
``tipo_movimiento='reverso'`` row already exists for the given
``uuid_pago_revertido``. Works across partitions (DB-level enforcement).

Re-asserts defensively:
- ``REVOKE UPDATE, DELETE ON prod.factura_pagos FROM rol_app``
- ``GRANT SELECT, INSERT ON prod.factura_pagos TO rol_app``
- The canonical ``fn_factura_pagos_inmutable()`` BEFORE UPDATE/DELETE
  trigger (idempotent re-install).

Idempotent: ``CREATE OR REPLACE FUNCTION`` + ``DROP TRIGGER IF EXISTS`` +
``CREATE TRIGGER``.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_add_factura_pagos_reverso_trigger"
down_revision = "0003_add_idempotency_keys_and_revoked_sync_jwts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. The reverso-uniqueness trigger function (DB-level SC-11 enforcement).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prod.fn_factura_pagos_reverso_uniqueness()
        RETURNS trigger AS $$
        BEGIN
            -- Only enforce on reverso inserts.
            IF NEW.tipo_movimiento = 'reverso' AND NEW.uuid_pago_revertido IS NOT NULL THEN
                IF EXISTS (
                    SELECT 1 FROM prod.factura_pagos
                    WHERE tipo_movimiento = 'reverso'
                      AND uuid_pago_revertido = NEW.uuid_pago_revertido
                ) THEN
                    RAISE EXCEPTION
                        'factura_pagos reverso uniqueness violation: '
                        'uuid_pago_revertido=% already has a reverso row',
                        NEW.uuid_pago_revertido
                        USING ERRCODE = 'unique_violation';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # 2. Wire the trigger on prod.factura_pagos (BEFORE INSERT).
    op.execute("DROP TRIGGER IF EXISTS factura_pagos_reverso_uniqueness ON prod.factura_pagos;")
    op.execute(
        "CREATE TRIGGER factura_pagos_reverso_uniqueness "
        "BEFORE INSERT ON prod.factura_pagos "
        "FOR EACH ROW EXECUTE FUNCTION prod.fn_factura_pagos_reverso_uniqueness();"
    )

    # 3. Defensive REVOKE re-assertion (config.yaml rules.tasks).
    op.execute("REVOKE UPDATE, DELETE ON prod.factura_pagos FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.factura_pagos TO rol_app;")

    # 4. Canonical _inmutable trigger re-assertion (idempotent).
    op.execute("DROP TRIGGER IF EXISTS factura_pagos_inmutable ON prod.factura_pagos;")
    op.execute(
        "CREATE TRIGGER factura_pagos_inmutable "
        "BEFORE UPDATE OR DELETE ON prod.factura_pagos "
        "FOR EACH ROW EXECUTE FUNCTION prod.fn_factura_pagos_inmutable();"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS factura_pagos_reverso_uniqueness ON prod.factura_pagos;")
    op.execute("DROP TRIGGER IF EXISTS factura_pagos_inmutable ON prod.factura_pagos;")
    # NOTE: do NOT re-grant UPDATE/DELETE on downgrade — the REVOKE is correct.
