"""HU-F1.12 V8/V8b STUB closure (qa-2026-09-17) — add ``uuid_subscripcion_cliente`` column + FK on ``prod.facturas``.

HU-F1.12 / REQ-OPS-083..090 mandates ``cobrar_ahora=true`` en ``POST /clientes/venta-suscripcion``
must INSERT into ``prod.facturas`` (F1.9 cobro sub-chain). The original F1.12 archive
reported this sub-chain as "D2 LOW deferred" — but plan.md lines 1053 (T2) + 2027 + 2029 + REQ-OPS-090
canon require the cobro sub-chain to be implemented, not stubbed. This migration is the Q1-A
resolution chosen by orchestrator on 2026-09-17: a proper FK column on ``prod.facturas`` so
the V8 chain links the issued factura to the originating subscripcion_cliente row.

Schema change:

  1. ``ALTER TABLE prod.facturas ADD COLUMN IF NOT EXISTS uuid_subscripcion_cliente UUID NULL``
     — PG11+ metadata-only; nullable because F1.8/F1.9 always use ``uuid_salida`` or
     ``uuid_ingreso`` (existing FKs) and ``uuid_subscripcion_cliente`` only applies to the F1.12
     venta-atómica path.
  2. ``DO $$ ... ALTER TABLE prod.facturas ADD CONSTRAINT
     fk_facturas_subscripcion_cliente FOREIGN KEY (uuid_subscripcion_cliente)
     REFERENCES prod.subscripciones_cliente (uuid) ON DELETE SET NULL`` — wrapped in
     ``DO`` block because Alembic's ``op.create_foreign_key`` is not idempotent across replays.
     ``ON DELETE SET NULL`` (not CASCADE) because deleting a subscripcion should not cascade-
     delete its historical factura (DIAN retention requires keeping the invoice).

Both pieces are idempotent: the ALTER uses ``IF NOT EXISTS``; the DO block checks
``pg_constraint`` for the FK name before ADDing. Replays are no-ops.

KEPT IN SYNC WITH: ``openspec/changes/2026-09-17-f1-12-v8-v8b-stub-closure/specs/operations/spec.md``
REQ-OPS-090 amendment (additive) — schema-conformance gate scope expansion.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0037_add_uuid_subscripcion_cliente_to_facturas"
down_revision = "0036_add_fecha_retencion_to_idempotency_keys"  # follow 0036 in the chain
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable FK column + FK constraint to ``prod.facturas``.

    Idempotent on both branches (column ADD IF NOT EXISTS; FK added via DO block that
    checks ``pg_constraint`` first). Downgrade reverses both cleanly.
    """
    # 1) Nullable UUID column (metadata-only; no table rewrite).
    op.execute(
        "ALTER TABLE prod.facturas "
        "ADD COLUMN IF NOT EXISTS uuid_subscripcion_cliente UUID NULL"
    )

    # 2) FK constraint (idempotent via DO block; Alembic's create_foreign_key
    #    is not replay-safe). ON DELETE SET NULL preserves historical factura
    #    rows even if the subscripcion is later closed-and-archived.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_facturas_subscripcion_cliente'
                  AND conrelid = 'prod.facturas'::regclass
            ) THEN
                ALTER TABLE prod.facturas
                ADD CONSTRAINT fk_facturas_subscripcion_cliente
                FOREIGN KEY (uuid_subscripcion_cliente)
                REFERENCES prod.subscripciones_cliente (uuid)
                ON DELETE SET NULL;
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    """Reverse both changes cleanly."""
    op.execute(
        "ALTER TABLE prod.facturas "
        "DROP CONSTRAINT IF EXISTS fk_facturas_subscripcion_cliente"
    )
    op.execute(
        "ALTER TABLE prod.facturas "
        "DROP COLUMN IF EXISTS uuid_subscripcion_cliente"
    )


__all__ = ["upgrade", "downgrade"]