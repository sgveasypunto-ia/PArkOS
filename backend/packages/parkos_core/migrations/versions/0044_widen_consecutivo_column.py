"""MIGRATION 0044 -- widen prod.ingreso.consecutivo from VARCHAR(20) to VARCHAR(30).

REGRESSION (2026-09-22): the migration 0042 ``consecutivo VARCHAR(20)``
column underestimates the storage required by the REQ-OPS-191 format
``<TIPO>-NNNNNN-<uuid8>``.

Length math:

  * TIPO = uppercase ``tipo`` from ``prod.tipos_vehiculo``
    - ``carro``   -> 5 chars
    - ``moto``    -> 4 chars
    - ``bicicleta`` -> 9 chars  (longest current seeded tipo)
  * ``-`` separator -> 1 char
  * ``NNNNNN`` zero-padded counter -> 6 chars (max 999,999 per REQ-OPS-191)
  * ``-`` separator -> 1 char
  * ``<uuid8>`` -> 8 hex chars (first 8 of source UUID)

Worst case: ``bicicleta-000001-3f8a1b2c`` = 9 + 1 + 6 + 1 + 8 = **25 chars**.
The seeded ``patineta`` is 8 chars (8 + 1 + 6 + 1 + 8 = 24).

VARCHAR(20) was the original migration's estimate based on the assumed
``carro|moto`` types only (4-5 chars). When the catalog was broadened
to ``bicicleta|patineta`` (commit ``281bb66``), the column width
wasn't revisited.

Fix: ALTER COLUMN to VARCHAR(30) — leaves headroom for any future
tipo name up to 14 chars (14 + 1 + 6 + 1 + 8 = 30). The unique index
``uq_ingreso_consecutivo_partial`` is unaffected (key length is well
under the 8191-byte btree index limit).

The ORM (``models/L_E/ingreso.py``) and the Pydantic schema
(``schemas/operacion.py::IngresoRead.consecutivo``) are updated in the
same change so the application-side validators match the column width.
"""
from __future__ import annotations

from alembic import op


revision = "0044_widen_consecutivo_column"
down_revision = "0043_counter_table_column_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Widen ``prod.ingreso.consecutivo`` from VARCHAR(20) to VARCHAR(30)."""
    op.execute(
        "ALTER TABLE prod.ingreso "
        "ALTER COLUMN consecutivo TYPE VARCHAR(30) USING consecutivo::VARCHAR(30)"
    )


def downgrade() -> None:
    """Revert ``prod.ingreso.consecutivo`` to VARCHAR(20).

    WARNING: this is a destructive operation if any row has a consecutivo
    longer than 20 chars (the ALTER will fail). For the seeded data this
    is safe; production deployments should verify before rolling back.
    """
    op.execute(
        "ALTER TABLE prod.ingreso "
        "ALTER COLUMN consecutivo TYPE VARCHAR(20) "
        "USING SUBSTRING(consecutivo FROM 1 FOR 20)"
    )


__all__ = ["upgrade", "downgrade"]
