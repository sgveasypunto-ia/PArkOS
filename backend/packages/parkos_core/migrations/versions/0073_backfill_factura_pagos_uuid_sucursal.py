"""0073_backfill_factura_pagos_uuid_sucursal -- populate the NULL column.

Revision ID: 0073_backfill_factura_pagos_uuid_sucursal
Revises: 0072_grant_v_factura_electronica_acuse_select
Create Date: 2026-10-02 00:00:00.000000

THE PROBLEM THIS PINS
----------------------
``repo/factura.py::crear_factura_pago`` has NEVER populated
``prod.factura_pagos.uuid_sucursal`` on INSERT (the column is nullable and
was simply left out of the ``FacturaPagos(...)`` constructor call). Every
payment ever created through the real application -- cajero POS, the
additional-payment endpoint, and ``venta-suscripcion`` -- landed with
``uuid_sucursal IS NULL``.

The global tenant listener (``db/tenancy.py``'s ``do_orm_execute``)
injects ``WHERE uuid_sucursal = :ctx_sucursal`` on ANY ORM
SELECT/UPDATE/DELETE touching an entity that carries a ``uuid_sucursal``
column -- regardless of whether the query already scopes itself another
way. ``reporte_pagos`` (``api/v1/reporteria.py``) deliberately joins
through ``facturas.uuid_sucursal`` instead of trusting
``factura_pagos.uuid_sucursal`` directly (see that function's docstring),
but the listener applies its own filter on top regardless -- and since the
real column is NULL, ``NULL = :ctx`` is never true, so EVERY admin-scoped
read of ``factura_pagos`` silently drops every row. Live defect: ``GET
/api/v1/admin/reporteria/pagos`` returned ``items: []`` with a 200 despite
4 real payment rows existing for the queried branch and date range
(QA-testing Reportería financiera's "Pagos" tab, 2026-10-02). The same
join-through-facturas pattern backs ``reporte_operacional``'s
``per_day_pagos`` subquery (same file, ~line 298) and is presumably
affected the same way.

THE FIX
-------
1. (Code, same change, not this migration) ``crear_factura_pago`` now
   requires an explicit ``uuid_sucursal`` and sets it on every new row;
   ``reverse_payment`` already copied it from the original row, so new
   reversos inherit a real value once the row they reverse has one.
2. (This migration) One-time idempotent backfill of every EXISTING NULL
   row from its owning ``facturas.uuid_sucursal`` -- the same
   source-of-truth ``reporte_pagos`` already trusts. Safe to re-run: the
   ``WHERE ... IS NULL`` guard makes a second run a no-op.

Deliberately NOT in scope: adding a ``NOT NULL`` constraint or a
``CHECK``/trigger to guarantee future rows are populated at the DB layer.
The code fix above is the enforcement point for new rows; tightening the
schema is a separate, larger decision (every other ``[A]`` table's
``uuid_sucursal`` nullability would need the same review) and not needed
to close the live QA defect this migration targets.
"""
from __future__ import annotations

from alembic import op

revision = "0073_backfill_factura_pagos_uuid_sucursal"
down_revision = "0072_grant_v_factura_electronica_acuse_select"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ``prod.factura_pagos`` is ``[A]`` (append-only): the ``factura_pagos_
    # inmutable`` BEFORE UPDATE/DELETE trigger (migration 0004,
    # ``fn_factura_pagos_inmutable()``) rejects ANY UPDATE unconditionally,
    # even from a superuser connection -- triggers, unlike GRANT/REVOKE,
    # are never bypassed by role privilege. A migration-time backfill of a
    # column that was simply never populated (not a correction of a real
    # business value) is the documented exception this repo already uses
    # for other ``[A placeholder]``/immutable tables -- see
    # ``0032_seed_alert_types_operativos.py`` and
    # ``0058_hash_chain_causal_seq.py``'s DISABLE/ENABLE TRIGGER bracket.
    op.execute("ALTER TABLE prod.factura_pagos DISABLE TRIGGER factura_pagos_inmutable;")
    op.execute(
        """
        UPDATE prod.factura_pagos fp
        SET uuid_sucursal = f.uuid_sucursal
        FROM prod.facturas f
        WHERE f.uuid = fp.uuid_factura
          AND fp.uuid_sucursal IS NULL;
        """
    )
    op.execute("ALTER TABLE prod.factura_pagos ENABLE TRIGGER factura_pagos_inmutable;")


def downgrade() -> None:
    # No-op by design. A backfill is not safely reversible: rows inserted
    # by the application BETWEEN this migration's upgrade and a later
    # downgrade (now correctly populated at INSERT time by the
    # accompanying code fix) would be indistinguishable from rows this
    # migration touched, so a blind "set back to NULL" would re-break
    # live traffic rather than restore prior state. Pinning this gap is
    # the point of the migration; there is nothing correct to undo.
    pass
