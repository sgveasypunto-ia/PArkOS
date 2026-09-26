"""MIGRATION 0057 -- restore the UPDATE privilege 0051 over-revoked.

Why this exists
---------------
``0051_add_sync_cursor`` created ``prod.sync_cursor`` and ran::

    REVOKE UPDATE, DELETE ON prod.sync_cursor FROM rol_app;
    GRANT SELECT, INSERT ON prod.sync_cursor TO rol_app;

The intent was defence in depth: no ``UPDATE``/``DELETE`` on an ``[A]``
table, with a ``BEFORE UPDATE OR DELETE`` trigger carving out just the
operational columns. But a trigger can only ever *narrow* what a role may
do -- it cannot hand back a privilege the role does not hold. Revoking
``UPDATE`` therefore did not "restrict to the carve-out columns"; it
removed the privilege outright and made the carve-out unreachable.

``repo.sync_cursor.set_seq`` needs it in two places:

1. ``select(SyncCursor).where(...).with_for_update()`` -- in PostgreSQL a
   ``SELECT ... FOR UPDATE`` requires the ``UPDATE`` privilege even though
   the statement is syntactically a read.
2. ``row.ultimo_seq = ultimo_seq`` -- the watermark advance itself.

Without the privilege the branch worker raised
``InsufficientPrivilegeError: permission denied for table sync_cursor`` on
every cycle, so ``prod.sync_cursor`` was never written and every pull
restarted from the last watermark. The ``sync_queue``/``permisos`` reads
that ran before it in the same transaction then failed with
``InFailedSQLTransactionError``, masking the real error.

The fix keeps the layering that was actually wanted: the table-level
``UPDATE`` privilege is restored so the trigger's column carve-out is
reachable, and ``DELETE`` stays revoked -- there is still no physical
DELETE path on this table. The trigger remains the thing that constrains
*which* columns may change, which is the control that matters.

Applied to both nodes: the cloud worker reads the same table.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0057_sync_cursor_update_grant"
down_revision = "0056_deterministic_permisos_uuids_full"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Restore UPDATE on the carve-out columns' table; keep DELETE revoked.

    Per ``openspec/config.yaml`` ``rules.tasks``, the privilege change ships
    in the same migration that touches the ``[A]`` table. The
    ``trg_sync_cursor_inmutable`` BEFORE UPDATE OR DELETE trigger from 0051
    is intentionally left in place and is what actually constrains the
    UPDATE to ``(ultimo_seq, sync_status, sync_timestamp, sync_attempts)``.
    """
    # 1) Reachability: the privilege the 0051 trigger carve-out needs.
    op.execute("GRANT UPDATE ON prod.sync_cursor TO rol_app;")
    # 2) Defence in depth re-stated: no physical DELETE on this [A] table.
    op.execute("REVOKE DELETE ON prod.sync_cursor FROM rol_app;")


def downgrade() -> None:
    """Re-apply the 0051 (broken) privilege set.

    Restoring the pre-0057 state deliberately reintroduces the
    ``InsufficientPrivilegeError`` described above, so the branch worker's
    cursor cannot be written. Kept for symmetry with 0051's own downgrade.
    """
    op.execute("REVOKE UPDATE ON prod.sync_cursor FROM rol_app;")
