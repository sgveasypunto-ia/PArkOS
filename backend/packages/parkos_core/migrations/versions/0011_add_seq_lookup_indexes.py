"""add seq-lookup partial index on prod.sync_queue (D4, T-PR7-003)

Revision ID: 0011_add_seq_lookup_indexes
Revises: 0010_drop_le_vigente_inicial_triggers
Create Date: 2026-09-09 00:00:00.000000

design.md §2 Issue #4 / §4: partial index backing
``motor/read_local_seq.py::ReadLocalSeq``'s ``seq_via_datos`` strategy —
``SELECT MAX((datos->>'seq')::bigint) FROM prod.sync_queue WHERE tabla = :name
AND uuid_registro = :row_uuid AND uuid_sucursal IS NOT DISTINCT FROM
:branch_uuid`` (REQ-MOT-009). This migration ONLY adds the index to the
already-applied ``prod.sync_queue`` table (``0001_initial_schema.py``); it
does not alter that table's columns, triggers, or grants in any way.

**Renumbering note (session decision, confirmed against
``ls migrations/versions/`` at PR7 start — the highest existing revision was
``0010_drop_le_vigente_inicial_triggers``; ``0011`` is the next real
sequential number, exactly as ``0008_add_identity_nk_indexes.py``'s own
renumbering note predicted for "PR7/PR8/PR10").** ``tasks.md``'s PR7 section
originally named this file ``0013_add_seq_lookup_indexes.py`` — a draft-era
placeholder from an earlier ``tasks.md`` revision, corrected here (and in
``tasks.md`` itself) to ``0011``. The next free number for PR8 is ``0012``
— re-verify against ``ls migrations/versions/`` at that PR's start regardless,
since this note only reflects the state at PR7's start.

Restricted to ``estado IN ('exitoso', 'pendiente')`` (design.md's exact
wording) — a ``'fallido'`` row is retried with a NEW ``sync_queue`` insert
(``repo/sync_queue.py::mark_failed`` re-queues via
``estado='pendiente'``, never leaves a stale ``'fallido'`` row as the
canonical seq source), so excluding it keeps the index smaller without
losing any seq the lookup needs to see.

Every migration in this project sets ``lock_timeout`` on its first statement
starting with ``0008``/``0009`` (design.md §4); this one follows the same
convention.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0011_add_seq_lookup_indexes"
down_revision = "0010_drop_le_vigente_inicial_triggers"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"


def upgrade() -> None:
    """Create the ``seq_via_datos`` lookup partial index (T-PR7-003)."""
    op.execute(_LOCK_TIMEOUT_SQL)

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_sync_queue_seq_lookup
        ON prod.sync_queue (
            tabla,
            uuid_registro,
            ((datos->>'seq')::bigint)
        )
        WHERE estado IN ('exitoso', 'pendiente')
        """
    )


def downgrade() -> None:
    """Drop the seq-lookup index.

    Lossy only in the sense that ``ReadLocalSeq``'s ``seq_via_datos``
    strategy reverts to an unindexed scan over ``prod.sync_queue`` — no
    persisted data is affected, and the query itself stays correct (just
    slower) with no index present.
    """
    op.execute("DROP INDEX IF EXISTS prod.ix_sync_queue_seq_lookup")
