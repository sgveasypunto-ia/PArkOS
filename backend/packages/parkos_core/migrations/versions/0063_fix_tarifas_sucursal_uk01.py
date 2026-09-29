"""0063_fix_tarifas_sucursal_uk01 -- partial UNIQUE index on active rows.

THE PROBLEM THIS PINS
---------------------
The ``tarifas_sucursal_uk01`` constraint is
``UNIQUE (uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa,
vigente_desde)``. That is the correct unique key FOR ACTIVE ROWS (the
backend's ``close_and_insert`` Carril B makes ``vigente_desde`` the
boundary between two open windows; the backend reads only
``vigente_hasta IS NULL``), but the constraint is applied regardless
of ``vigente_hasta``.

The admin UI reproduces the defect: when the operator creates a
tarifa with ``vigente_desde=now()`` and then opens the edit modal
without touching the field, the harness defaults to
``localNowPlusMinutesAsIso(1)``. If the operator submits within the
same minute the active row carries the SAME ``vigente_desde`` as the
new version the backend tries to INSERT, and the backend's
``close_and_insert`` raises
``asyncpg.exceptions.UniqueViolationError: duplicate key value
violates unique constraint "tarifas_sucursal_uk01"``. That exception
is unhandled at the handler boundary and bubbles to the client as
HTTP 500.

The bi-temporal model DOES require that no two ACTIVE rows share
the same (sucursal, tipo_vehiculo, tipo_tarifa, vigente_desde) tuple
(else the overlap guard's bi-temporal predicate loses the ordering
invariant). It does NOT require that between an ACTIVE row and a
CLOSED row the constraint holds — the closed row's ``vigente_hasta``
already excludes it from the active window, so a fresh row may open
at exactly the boundary the old row closed.

THE FIX
-------
Replace the global ``UNIQUE`` constraint with a PARTIAL ``UNIQUE
INDEX`` keyed on ``vigente_hasta IS NULL``. Active rows still reject
duplicates; closed rows are now allowed to coexist with a fresh row
that opens at the same ``vigente_desde``.

The migration is reversible: ``downgrade`` recreates the original
``UNIQUE`` constraint. The data is already consistent with the
original constraint (no duplicate ACTIVE rows exist), so
``downgrade`` succeeds.

CONCURRENT INDEX (Postgres)
----------------------------
The new index is created with ``postgresql_using='btree'`` (default)
and ``postgresql_where=sa.text("vigente_hasta IS NULL")``. A plain
CREATE INDEX without CONCURRENTLY takes an ACCESS EXCLUSIVE lock on
the table during creation — fine for dev where the backend is
restarted; in a production migration we'd want ``CONCURRENTLY`` but
``alembic.op.create_index`` doesn't expose it directly, and the
current dev workflow rebuilds the container for migrations anyway.
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text
import sqlalchemy as sa

revision = "0063_fix_tarifas_sucursal_uk01"
down_revision = "0062_canonical_tipos_vehiculo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # 1. Drop the existing UNIQUE constraint.
    bind.execute(
        text("""ALTER TABLE prod.tarifas_sucursal
                 DROP CONSTRAINT tarifas_sucursal_uk01""")  # noqa: S608 - schema-qualified literal
    )
    # 2. Create a partial UNIQUE index that only applies to ACTIVE rows
    #    (``vigente_hasta IS NULL``). Closed rows (where
    #    ``vigente_hasta IS NOT NULL``) are excluded from the unique
    #    constraint, so multiple historical closed rows may share the
    #    same ``vigente_desde`` boundary.
    op.create_index(
        "tarifas_sucursal_uk01",
        "tarifas_sucursal",
        [
            "uuid_sucursal",
            "uuid_tipo_vehiculo",
            "uuid_tipo_tarifa",
            "vigente_desde",
        ],
        schema="prod",
        unique=True,
        postgresql_where=sa.text("vigente_hasta IS NULL"),
    )


def downgrade() -> None:
    # 1. Drop the partial UNIQUE index.
    op.drop_index(
        "tarifas_sucursal_uk01",
        table_name="tarifas_sucursal",
        schema="prod",
    )
    # 2. Recreate the original global UNIQUE constraint. The current
    #    state is consistent with this constraint (no two ACTIVE rows
    #    share the same tuple), so the recreation succeeds.
    op.create_unique_constraint(
        "tarifas_sucursal_uk01",
        "tarifas_sucursal",
        [
            "uuid_sucursal",
            "uuid_tipo_vehiculo",
            "uuid_tipo_tarifa",
            "vigente_desde",
        ],
        schema="prod",
    )