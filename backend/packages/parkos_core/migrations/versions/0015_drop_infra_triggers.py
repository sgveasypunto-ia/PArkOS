"""drop fn_enqueue_sync trigger from prod.sync_log / prod.sync_conflict
(T-PR10-002, D21 guard 1, REQ-OPS-014)

Revision ID: 0015_drop_infra_triggers
Revises: 0014_add_catalog_triggers
Create Date: 2026-09-09 01:10:00.000000

design.md §4 / §11 AST/CI Guards (D21 guard 1): ``sync_log`` and
``sync_conflict`` are 2 of the 5 out-of-catalog names
(``catalog/out_of_catalog.py::OUT_OF_CATALOG`` — the other 3 are
``sync_queue``, ``sync_queue_lw_buffer``, ``alert_types``) — pure sync
infrastructure that must never itself generate a replicated ``sync_queue``
row. ``0001_initial_schema.py`` nonetheless wired both of them to
``fn_enqueue_sync()`` (an oversight predating the catalog-driven
architecture: every ``[A]`` table except ``sync_queue`` got the trigger
uniformly). This migration removes exactly those 2 triggers — it does
**not** drop ``fn_enqueue_sync()`` itself (still required by the other 28
tables that keep it until stage 5 of the cutover per design.md §12
Rollback) and does **not** touch any of the 18 new
``fn_enqueue_sync_catalog()`` triggers from ``0014``.

**Why not also drop from the other 28 tables.** design.md §12 (Rollback,
amended): "Legacy ``fn_enqueue_sync`` triggers likewise stay throughout the
14-day dual-protocol window and are dropped only in stage 5." D21 guard 1
is narrowly scoped to the 2 tables that should never have had the trigger
at all (an infra classification bug, not a cutover-timing decision) —
conflating the two would have dropped real ``[V]``/other ``[A]`` table
replication ahead of schedule.

Renumbered ``0012`` -> ``0015`` (session decision, same chain as
``0014``'s own renumbering note). ``tasks.md``'s PR10 section originally
named this file ``0012_drop_infra_triggers.py``; corrected here (and in
``tasks.md`` itself) to ``0015``.

Pre-flight: ``uv run alembic upgrade --sql 0015_drop_infra_triggers``
reviewed before apply (2 ``DROP TRIGGER IF EXISTS`` statements only — no
data-destructive statements, no function drop).
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0015_drop_infra_triggers"
down_revision = "0014_add_catalog_triggers"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

# The 2 out-of-catalog [A] tables that must never enqueue a sync_queue row
# (D21 guard 1) — sync_queue and the other 2 out-of-catalog names
# (sync_queue_lw_buffer, alert_types) never had this trigger in the first
# place, so there is nothing to drop for them.
INFRA_TRIGGER_TABLES: tuple[str, ...] = ("sync_log", "sync_conflict")


def upgrade() -> None:
    """Drop ``<table>_enqueue_sync`` from ``sync_log`` / ``sync_conflict`` (T-PR10-002)."""
    op.execute(_LOCK_TIMEOUT_SQL)

    for table in INFRA_TRIGGER_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_enqueue_sync ON prod.{table};")


def downgrade() -> None:
    """Recreate ``<table>_enqueue_sync`` on ``sync_log`` / ``sync_conflict``.

    Restores the exact ``0001_initial_schema.py`` trigger definition
    (``fn_enqueue_sync()``, unchanged/still present) for both tables.
    """
    op.execute(_LOCK_TIMEOUT_SQL)

    for table in INFRA_TRIGGER_TABLES:
        op.execute(f"""
            CREATE TRIGGER {table}_enqueue_sync
                AFTER INSERT ON prod.{table}
                FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
        """)
