"""drop fn_set_vigente_inicial triggers wrongly attached to 3 [L-E] tables (T-PR6-000)

Revision ID: 0010_drop_le_vigente_inicial_triggers
Revises: 0009_add_derived_read_views
Create Date: 2026-09-09 00:00:00.000000

**Bug discovered during PR5, fixed here (T-PR6-000).** ``0001_initial_schema.py``
attaches ``fn_set_vigente_inicial()`` (a ``BEFORE INSERT`` trigger that stamps
``NEW.vigente_desde``/``NEW.estado`` when either is ``NULL``) to THREE
``[L-E]`` tables — ``ingreso`` (line ~2560), ``facturas`` (line ~2583),
``factura_electronica`` (line ~2654) — that do NOT carry
``_versioning_columns()`` in their ``create_table()`` call (only
``*_audit_columns()`` + ``*_sync_columns()``, plus ``_retention_column()``
for ``factura_electronica``). Any real INSERT into one of these 3 tables
fires the trigger, which references ``NEW.vigente_desde`` — a column that
does not exist on the row — and Postgres raises ``UndefinedColumnError``
(``record "new" has no field "vigente_desde"``).

The 6 other tables sharing this same "trigger attached but not obviously
[V]" shape — ``reimpresion_ticket``, ``anulaciones``, ``reclamos``,
``alerta``, ``envio_dian``, ``validacion_evento`` (all ``[L-W]``) — DO
declare ``*_versioning_columns()`` (confirmed by reading
``0001_initial_schema.py``'s ``create_table()`` calls for each) — those are
correctly targeted and are NOT touched by this migration.

This bug was discovered during PR5 (``test_bi_temporal_compensation.py``
needed a ``session_replication_role = replica`` workaround to seed a
``prod.facturas`` row — see that test's ``_seed_factura`` docstring) and is
fixed here, in PR6, once a dedicated migration slot was available.

``downgrade()`` re-creates the exact 3 triggers with the same trigger body
reference as ``0001_initial_schema.py`` (``fn_set_vigente_inicial()`` itself
is untouched — it is still legitimately used by the 26 ``[V]`` tables plus
the 6 ``[L-W]`` tables above).
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0010_drop_le_vigente_inicial_triggers"
down_revision = "0009_add_derived_read_views"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

# (trigger_name, table_name) — the 3 [L-E] tables wrongly targeted in 0001.
_WRONGLY_TARGETED = (
    ("ingreso_set_vigente_inicial", "ingreso"),
    ("facturas_set_vigente_inicial", "facturas"),
    ("factura_electronica_set_vigente_inicial", "factura_electronica"),
)


def upgrade() -> None:
    """Drop the 3 [L-E] ``fn_set_vigente_inicial`` triggers (T-PR6-000)."""
    op.execute(_LOCK_TIMEOUT_SQL)

    for trigger_name, table_name in _WRONGLY_TARGETED:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON prod.{table_name};")


def downgrade() -> None:
    """Re-create the 3 dropped triggers (restores the PR5-discovered bug).

    Same trigger body reference as ``0001_initial_schema.py`` —
    ``fn_set_vigente_inicial()`` itself is never dropped/recreated here,
    only its attachment to these 3 tables.
    """
    op.execute(_LOCK_TIMEOUT_SQL)

    for trigger_name, table_name in _WRONGLY_TARGETED:
        op.execute(
            f"""
            CREATE TRIGGER {trigger_name}
                BEFORE INSERT ON prod.{table_name}
                FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
            """
        )
