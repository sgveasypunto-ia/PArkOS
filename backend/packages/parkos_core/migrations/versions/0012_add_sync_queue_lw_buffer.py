"""add prod.sync_queue_lw_buffer — dependency buffer table (T-PR8-001, D18, ADR-002/003)

Revision ID: 0012_add_sync_queue_lw_buffer
Revises: 0011_add_seq_lookup_indexes
Create Date: 2026-09-09 00:10:00.000000

design.md §2 Issue #2 (amended) / §4: the dependency buffer holds a row for
ANY catalog entry with a missing declared ``depends_on`` parent (generalized
past ``[L-W]``-only), keyed generically on ``(tabla_padre, uuid_padre)``. The
physical table name is deliberately NOT renamed from its historical
``sync_queue_lw_buffer`` (design decision, Issue #2: ratified in proposal
§6.3/§9.2 and in ``check_catalog_drift.py``'s exemption-list literal, which
must carry "exactly these five names" — a rename would cost a migration
rename plus edits to those artifacts for zero functional gain).

Columns: ``uuid, uuid_sucursal, tabla, uuid_registro, tabla_padre, uuid_padre,
datos JSONB, estado, buffered_at, expires_at`` per T-PR8-001's literal spec,
PLUS ``ultimo_error`` (needed by T-PR8-009's TTL sweep — marks
``ultimo_error='parent_missing_timeout'`` on expiry; the literal T-PR8-001
column list predates that requirement) and the audit/sync columns every
table in this schema carries (``AGENTS.md`` §"Every row carries created_at,
created_by" / "Every model has ... sync_status/sync_timestamp/sync_attempts")
— matching the exact precedent of the OTHER out-of-catalog ``[A]`` tables
(``sync_queue``, ``sync_log``, ``sync_conflict``, see ``0001_initial_schema.py``),
which also carry these columns despite never being replicated.

Renumbered ``0009`` -> ``0012`` (session decision, pre-confirmed by the
orchestrating prompt and re-verified here: ``ls migrations/versions/`` showed
``0011_add_seq_lookup_indexes.py`` as the highest applied revision at PR8
start, exactly as ``0011``'s own renumbering note predicted — "next free
number for PR8 is 0012"). ``tasks.md``'s PR8 section originally named this
file ``0009_add_sync_queue_lw_buffer.py``; corrected here (and in
``tasks.md`` itself) to ``0012``. **Next free number for PR9/PR10 is 0014**
— re-verify against ``ls migrations/versions/`` at that PR's start
regardless, per every prior renumbering note's own caveat.

**pg_partman note.** ``partman`` schema + the ``pg_partman`` extension are
already installed by ``0001_initial_schema.py`` — this migration does not
re-declare them. Unlike ``0001``'s 8 monthly-partitioned tables, this
migration deliberately does NOT rename ``partman.part_config.parent_table``
to a ``parkos.prod.*`` value: that rename is a documented, out-of-scope
pre-existing defect in ``0001`` (see
``backend/tests/migrations/test_partman_parents.py``'s xfail — "espurio,
rompe el filtro de partman ... requiere fix de migración dedicado"), and
propagating the same defect into new code would be a regression, not a
convention to follow. Leaving ``parent_table = 'prod.sync_queue_lw_buffer'``
(the objectively correct qualified relation name) is the corrected
behavior, not a deviation from anything this PR is asked to preserve.

**Carve-out, not a blanket ``[A]`` REVOKE (bug found and fixed during
T-PR8-007/009's own integration tests).** T-PR8-001's literal "REVOKE
UPDATE, DELETE" wording copies the standard ``[A]`` append-only pattern,
but T-PR8-007/009 (same PR) require ``estado``/``ultimo_error`` state
TRANSITIONS on this exact table after insert (``'pendiente' ->
'aplicado'`` on drain, ``'pendiente' -> 'fallido'`` on TTL timeout) — a
blanket ``BEFORE UPDATE OR DELETE`` trigger makes that impossible and
broke both integration tests on first run (``SYNC_QUEUE_LW_BUFFER_
INMUTABLE`` on the drain's own ``estado`` flip). This is the EXACT same
tension design §12 already resolved for ``prod.sync_queue`` (workers flip
``estado``/``intentos`` after insert) via a carve-out: keep append-only
for DELETE ("never deleted", T-PR8-008's own literal requirement), allow
UPDATE. ``REVOKE DELETE`` (not ``UPDATE, DELETE``) + a ``BEFORE DELETE``
-only trigger (not ``BEFORE UPDATE OR DELETE``) is the fix, mirroring
``sync_queue``'s "full UPDATE grant, Python-side discipline" convention
rather than inventing a column-level GRANT this codebase uses nowhere
else. Only :mod:`parkos_core.sync.motor.dependency_buffer` ever writes to
this table (no other call site), so the mutation surface is already
narrow by construction.

Retention policy is intentionally left at pg_partman defaults (no
``UPDATE partman.part_config SET retention = ...``): buffered rows are
either drained (``estado='aplicado'``) or time out via the TTL sweep
(``estado='fallido'``) well within a day, but nothing in T-PR8's scope asks
for automatic partition/data deletion, and silently adding one here could
discard evidence an operator investigating an escalated
``orphan_workflow_chain`` alert still needs.

Pre-flight: ``uv run alembic upgrade --sql 0012_add_sync_queue_lw_buffer``
reviewed before apply (clean ``CREATE TABLE`` + ``CREATE INDEX`` +
``partman.create_parent`` DDL only, no data-destructive statements).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0012_add_sync_queue_lw_buffer"
down_revision = "0011_add_seq_lookup_indexes"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"
PG_UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    """Create ``prod.sync_queue_lw_buffer`` (T-PR8-001)."""
    op.execute(_LOCK_TIMEOUT_SQL)

    op.create_table(
        "sync_queue_lw_buffer",
        sa.Column(
            "uuid",
            PG_UUID,
            nullable=False,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "buffered_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("uuid_sucursal", PG_UUID, nullable=True),
        sa.Column("tabla", sa.String(), nullable=False),
        sa.Column("uuid_registro", PG_UUID, nullable=False),
        sa.Column("tabla_padre", sa.String(), nullable=False),
        sa.Column("uuid_padre", PG_UUID, nullable=False),
        sa.Column("datos", postgresql.JSONB(), nullable=False),
        sa.Column(
            "estado",
            sa.String(length=16),
            nullable=False,
            server_default="pendiente",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("ultimo_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("created_by", PG_UUID, nullable=True),
        sa.Column("sync_status", sa.String(length=16), nullable=True, server_default="pendiente"),
        sa.Column("sync_timestamp", sa.DateTime(timezone=False), nullable=True),
        sa.Column("sync_attempts", sa.Integer(), nullable=True, server_default="0"),
        # ``AppendOnlyBase``'s ``RetentionMixin`` unconditionally declares this
        # column on every [A] ORM class (matching the ``sync_conflict``
        # precedent, which also carries it despite never using it for
        # partitioning) — nullable, unused here since ``buffered_at`` is
        # THIS table's actual partition key, not ``fecha_retencion_hasta``.
        sa.Column("fecha_retencion_hasta", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("uuid", "buffered_at", name="sync_queue_lw_buffer_pk"),
        schema="prod",
        postgresql_partition_by="RANGE (buffered_at)",
    )

    # ---- Carve-out: REVOKE DELETE only, allow UPDATE (see module docstring's
    # "Carve-out, not a blanket [A] REVOKE" note — mirrors design §12's
    # sync_queue carve-out: the drain/TTL-sweep workers flip estado/
    # ultimo_error after insert, so a blanket BEFORE UPDATE OR DELETE
    # trigger would block the table's own required behavior). ----
    op.execute("REVOKE DELETE ON prod.sync_queue_lw_buffer FROM rol_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE ON prod.sync_queue_lw_buffer TO rol_app;")

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_sync_queue_lw_buffer_inmutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'SYNC_QUEUE_LW_BUFFER_INMUTABLE'
                USING ERRCODE = '42501',
                      HINT = 'sync_queue_lw_buffer rows are never deleted; estado/ultimo_error transitions are UPDATE, not DELETE.';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER sync_queue_lw_buffer_inmutable
            BEFORE DELETE ON prod.sync_queue_lw_buffer
            FOR EACH ROW EXECUTE FUNCTION prod.fn_sync_queue_lw_buffer_inmutable();
    """)

    # ---- Indexes (design.md §4) ----
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_sync_queue_lw_buffer_parent
        ON prod.sync_queue_lw_buffer (tabla_padre, uuid_padre)
        WHERE estado = 'pendiente'
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_sync_queue_lw_buffer_expires_at
        ON prod.sync_queue_lw_buffer (expires_at)
    """)

    # ---- pg_partman: daily partitions, premake=3 (design.md §4) ----
    # ``partman`` schema + extension are already installed by
    # ``0001_initial_schema.py``; not re-declared here.
    op.execute("""
        SELECT partman.create_parent(
            p_parent_table := 'prod.sync_queue_lw_buffer',
            p_control := 'buffered_at',
            p_type := 'range',
            p_interval := '1 day',
            p_premake := 3
        );
    """)
    # pg_partman's create_parent only creates FUTURE children (same
    # behavior 0001_initial_schema.py already worked around for its 8
    # monthly parents) — drop them and create today's partition manually
    # so inserts made "today" (including this migration's own tests) find
    # a partition immediately.
    op.execute("""
        DO $$ DECLARE r record; BEGIN
            FOR r IN SELECT inhrelid::regclass AS child
                          FROM pg_inherits
                         WHERE inhparent = 'prod.sync_queue_lw_buffer'::regclass LOOP
                EXECUTE 'DROP TABLE ' || r.child || ' CASCADE';
            END LOOP;
        END $$;
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS prod.sync_queue_lw_buffer_p_current
        PARTITION OF prod.sync_queue_lw_buffer
        FOR VALUES FROM (date_trunc('day', NOW())) TO (date_trunc('day', NOW()) + INTERVAL '1 day');
    """)


def downgrade() -> None:
    """Drop ``prod.sync_queue_lw_buffer`` and its supporting objects."""
    op.execute(_LOCK_TIMEOUT_SQL)

    op.execute("DELETE FROM partman.part_config WHERE parent_table = 'prod.sync_queue_lw_buffer';")
    op.execute("DROP TRIGGER IF EXISTS sync_queue_lw_buffer_inmutable ON prod.sync_queue_lw_buffer;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_sync_queue_lw_buffer_inmutable();")
    op.execute("DROP TABLE IF EXISTS prod.sync_queue_lw_buffer CASCADE;")
