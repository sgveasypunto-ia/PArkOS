"""0074_backfill_arqueo_uuid_sucursal -- populate the NULL column.

Revision ID: 0074_backfill_arqueo_uuid_sucursal
Revises: 0073_backfill_factura_pagos_uuid_sucursal
Create Date: 2026-10-02 00:00:00.000000

THE PROBLEM THIS PINS
----------------------
``repo/arqueo.py::insertar_arqueo`` has NEVER populated
``prod.arqueo.uuid_sucursal`` on INSERT (the column is nullable and was
simply left out of the ``attrs`` dict passed to ``append_only.append_event``).
EVERY arqueo ever created through ``POST /api/v1/caja/arqueo`` -- regardless
of issuer (``admin-`` or ``operador-``, this is NOT issuer-specific like the
earlier ``factura_pagos`` gap) -- landed with ``uuid_sucursal IS NULL``.

Same bug class as migration 0073 (``factura_pagos``): the global tenant
listener (``db/tenancy.py``'s ``do_orm_execute``) only auto-filters
SELECT/UPDATE/DELETE, never INSERT, so a write path that forgets the column
leaves it permanently NULL. Any branch-scoped read of ``prod.arqueo`` then
silently drops the row -- confirmed live defect: the QA batch-8 seed arqueo
(``POST /caja/arqueo`` via admin JWT for BRANCH_NORTE) landed in the cloud DB
with ``uuid_sucursal`` NULL, so ``GET /api/v1/caja/arqueo?uuid_sucursal=...``
(the admin ``/arqueos`` Listado tab filtered by branch) silently excluded it
even though the row existed (QA-testing Arqueos, 2026-10-02).

THE FIX
-------
1. (Code, same change, not this migration) ``post_arqueo`` now threads the
   handler's already-computed ``target_sucursal`` (Step 2a, Layer 2 tenant
   scope) into ``insertar_arqueo``, which sets it on every new row.
2. (This migration) One-time idempotent backfill of every EXISTING NULL row
   that has a ``uuid_sesion`` (``cierre_turno`` / ``auditoria`` types) from
   its owning ``prod.sesion.uuid_sucursal``. Safe to re-run: the
   ``WHERE ... IS NULL`` guard makes a second run a no-op.

Deliberately NOT in scope: rows with ``uuid_sesion IS NULL`` (``cierre_dia``
type) have no FK to join through for a safe backfill -- none exist in any
environment yet (``cierre_dia`` is not exercised by current QA batches), so
there is nothing to backfill for that path. Also out of scope: a ``NOT
NULL`` constraint, mirroring 0073's reasoning -- the code fix is the
enforcement point for new rows.
"""
from __future__ import annotations

from alembic import op

revision = "0074_backfill_arqueo_uuid_sucursal"
down_revision = "0073_backfill_factura_pagos_uuid_sucursal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ``prod.arqueo`` is ``[A]`` (append-only): the ``arqueo_inmutable``
    # BEFORE UPDATE/DELETE trigger (migration 0001,
    # ``fn_arqueo_inmutable()``) rejects ANY UPDATE unconditionally, even
    # from a superuser connection. A migration-time backfill of a column
    # that was simply never populated (not a correction of a real business
    # value) follows the same documented exception as 0073.
    op.execute("ALTER TABLE prod.arqueo DISABLE TRIGGER arqueo_inmutable;")
    op.execute(
        """
        UPDATE prod.arqueo a
        SET uuid_sucursal = s.uuid_sucursal
        FROM prod.sesion s
        WHERE s.uuid = a.uuid_sesion
          AND a.uuid_sucursal IS NULL;
        """
    )
    op.execute("ALTER TABLE prod.arqueo ENABLE TRIGGER arqueo_inmutable;")


def downgrade() -> None:
    # No-op by design -- same rationale as 0073's downgrade: a backfill is
    # not safely reversible once new rows (correctly populated at INSERT
    # time by the accompanying code fix) coexist with backfilled ones.
    pass
