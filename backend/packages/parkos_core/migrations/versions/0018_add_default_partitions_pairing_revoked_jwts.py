"""add DEFAULT partitions to ``pairing_tokens`` / ``revoked_sync_jwts`` —
confirmed real ``no partition of relation ... found for row`` failure.

Revision ID: 0018_add_default_partitions_pairing_revoked_jwts
Revises: 0017_fix_hash_chain_prior_row_ordering
Create Date: 2026-09-10 01:00:00.000000

**The bug (confirmed live, Docker + testcontainers).** ``0006_add_pairing_
tokens_and_normalized_revoked_sync_jwts`` declares ``prod.pairing_tokens``
and ``prod.revoked_sync_jwts`` with the composite ``(uuid,
fecha_retencion_hasta)`` PK pg_partman range-partitioning requires
(``PARTITION BY RANGE (fecha_retencion_hasta)`` on the table), but — unlike
``0001_initial_schema.py``'s 8 originally-partitioned tables, each of which
gets an explicit ``CREATE TABLE ..._p_current PARTITION OF ...`` right in
that same migration — neither table's migration ever attaches ANY child
partition. Every INSERT into either table fails outright:
``asyncpg.exceptions.CheckViolationError: no partition of relation
"pairing_tokens" found for row``. First hit during this session's manual
QA (issuing a real admin pairing-token for a freshly-paired branch); a
project-owned negative test for ``LOCAL_ONLY_CATALOG`` tables surfaced the
identical gap for ``revoked_sync_jwts`` in the test suite (the trigger-
introspection test itself doesn't INSERT, so it didn't need this fix, but
the table's real callers — ``repo/revoked_sync_jwt.py::revoke_jwt``,
``api/v1/pairing.py``'s revoke endpoint — do).

Pre-existing, already-tracked as the SAME class of gap
(``test_pairing_flow.py``'s ``_XFAIL_PARTITION`` marker: "Gap preexistente
de mantenimiento de partición partman... requiere fix dedicado") — this
migration is that dedicated fix for these two tables specifically.

**The fix — a DEFAULT partition, not a dated range.** ``0001``'s 8 tables
use a ``_p_current`` partition bounded to "the month migrations happened to
run in", which pg_partman's OWN automatic maintenance is then deliberately
defeated for (see that migration's ``UPDATE partman.part_config SET
parent_table = 'parkos.prod.<table>'`` trick) — meaning even THOSE tables
silently stop accepting rows once the next unhandled month rolls around.
Not something this migration re-litigates for those 8 (out of scope,
undiagnosed whether it has bitten yet in practice), but deliberately NOT
copied here either: a single ``DEFAULT`` partition catches every
``fecha_retencion_hasta`` value forever, with no monthly-rollover failure
mode, and is the simpler, permanently-correct choice for two tables that
have no partition at all today. ``pairing_tokens``/``revoked_sync_jwts``
never registered with ``partman.create_parent`` in the first place, so
there is no existing partman config to fight or disable here.

**Data note.** Both tables are freshly-declared ``[A]`` append-only tables
with (per every real deployment observed) no rows ever successfully
written yet — the INSERT always failed first. Nothing to backfill.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0018_add_default_partitions_pairing_revoked_jwts"
down_revision = "0017_fix_hash_chain_prior_row_ordering"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

_TABLES = ("pairing_tokens", "revoked_sync_jwts")


def upgrade() -> None:
    """Attach one ``DEFAULT`` partition per table — catches every row
    regardless of ``fecha_retencion_hasta``, no rollover maintenance needed.
    """
    op.execute(_LOCK_TIMEOUT_SQL)
    for table in _TABLES:
        op.execute(
            f"""
            CREATE TABLE IF NOT EXISTS prod.{table}_p_default
            PARTITION OF prod.{table}
            DEFAULT;
            """
        )


def downgrade() -> None:
    op.execute(_LOCK_TIMEOUT_SQL)
    for table in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS prod.{table}_p_default;")
