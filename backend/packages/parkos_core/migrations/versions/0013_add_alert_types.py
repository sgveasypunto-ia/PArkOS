"""add prod.alert_types — generic alert-type registry (T-PR8-002, design §2 Issue #6)

Revision ID: 0013_add_alert_types
Revises: 0012_add_sync_queue_lw_buffer
Create Date: 2026-09-09 00:20:00.000000

design.md §2 Issue #6 (amended: generic identifiers): ``prod.alert_types`` is
a deploy-seeded registry table, out-of-catalog (never enters the sync
pipeline — ``alert_types`` members are referenced by identifier in Python
source, so adding one already ships with a deploy). Seeded idempotently on
**both** cloud and branch by this SAME migration script — there is no
role/deploy-target distinction in this file.

Business-key PK (``tipo_alerta``), not a ``uuid`` surrogate — this is the
first table in the schema shaped this way, matching T-PR8-002's literal
column spec exactly (``tipo_alerta TEXT PK, descripcion TEXT, severity TEXT
CHECK IN ('info','warning','critical'), created_at``). ``created_by`` +
``sync_status``/``sync_timestamp``/``sync_attempts`` are added beyond that
literal list per ``AGENTS.md``'s universal "every model has created_at,
created_by, ..., sync_status/sync_timestamp/sync_attempts" rule and to
match the ``sync_queue``/``sync_log``/``sync_conflict`` out-of-catalog [A]
precedent (``0001_initial_schema.py``), which carry the same columns despite
also never being replicated.

**Timestamp type.** T-PR8-002's literal spec says ``created_at TIMESTAMPTZ``.
No table anywhere in this schema (49 tables across ``0001_initial_schema.py``
plus every later migration) uses a timezone-aware timestamp column — every
single one uses ``DateTime(timezone=False)`` / plain ``TIMESTAMP``. Per the
project's own "match existing code patterns and conventions" rule, this
migration uses ``TIMESTAMP`` (naive), consistent with all 49+ existing
tables, rather than introducing the first ``TIMESTAMPTZ`` column in the
schema on the strength of one task line's literal wording.

**Not partitioned, no pg_partman.** Alert-type identifiers are a small,
rarely-changing seed set (8 rows today) — no volume rationale for monthly
or daily partitioning exists, matching ``sync_conflict``'s "conflicts are
rare events; volume does not warrant partitioning" precedent.

Renumbered ``0010`` -> ``0013`` (session decision, same renumbering chain as
``0012``'s own note — the next free number after ``0012`` is ``0013``).
``tasks.md``'s PR8 section originally named this file
``0010_add_alert_types.py``; corrected here (and in ``tasks.md`` itself) to
``0013``. **Next free number for PR9/PR10 is 0014** — re-verify against
``ls migrations/versions/`` at that PR's start regardless.

Pre-flight: ``uv run alembic upgrade --sql 0013_add_alert_types`` reviewed
before apply (clean ``CREATE TABLE`` + idempotent ``INSERT ... ON CONFLICT
DO NOTHING`` only).
"""
from __future__ import annotations

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0013_add_alert_types"
down_revision = "0012_add_sync_queue_lw_buffer"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"
PG_UUID = postgresql.UUID(as_uuid=True)

# (tipo_alerta, descripcion, severity) — design.md §2 Issue #6's exact 8
# rows. Generic identifiers only (addendum #5, REQ-OPS-016): no row names
# the third-party DIAN provider.
_SEED_ROWS: tuple[tuple[str, str, str], ...] = (
    (
        "hash_chain_anomaly",
        "Hash chain integrity break detected by the chain verifier",
        "critical",
    ),
    (
        "dian_rechazada",
        "DIAN provider rejected the submitted electronic-invoicing document",
        "warning",
    ),
    (
        "dian_timeout",
        "DIAN provider request timed out",
        "critical",
    ),
    (
        "dian_error",
        "Generic DIAN provider error on a terminal poll outcome",
        "warning",
    ),
    (
        "branch_offline_reauth_required",
        "Branch JWT requires re-authentication after an extended offline period",
        "warning",
    ),
    (
        "orphan_workflow_chain",
        "Dependency-buffer TTL sweep found an unresolved parent wait",
        "warning",
    ),
    (
        "fe_provider_error",
        "DIAN provider exchange exhausted its retry budget",
        "critical",
    ),
    (
        "fe_numbering_exhausted",
        "Authorized invoice numbering range (resolucion_facturacion) exhausted",
        "critical",
    ),
)


def upgrade() -> None:
    """Create ``prod.alert_types`` and seed the 8 canonical identifiers (T-PR8-002)."""
    op.execute(_LOCK_TIMEOUT_SQL)

    op.execute("""
        CREATE TABLE IF NOT EXISTS prod.alert_types (
            tipo_alerta TEXT PRIMARY KEY,
            descripcion TEXT,
            severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            created_by UUID,
            sync_status VARCHAR(16) DEFAULT 'pendiente',
            sync_timestamp TIMESTAMP,
            sync_attempts INTEGER DEFAULT 0
        );
    """)

    # ---- REVOKE + inmutable trigger ([A] contract, design §4) ----
    op.execute("REVOKE UPDATE, DELETE ON prod.alert_types FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.alert_types TO rol_app;")

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_alert_types_inmutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'ALERT_TYPES_INMUTABLE'
                USING ERRCODE = '42501',
                      HINT = 'alert_types is a deploy-seeded registry; add a new identifier via a migration, never UPDATE/DELETE.';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER alert_types_inmutable
            BEFORE UPDATE OR DELETE ON prod.alert_types
            FOR EACH ROW EXECUTE FUNCTION prod.fn_alert_types_inmutable();
    """)

    # ---- Idempotent seed (applied identically on cloud AND branch) ----
    values_sql = ",\n            ".join(
        f"('{tipo}', '{descripcion}', '{severity}')" for tipo, descripcion, severity in _SEED_ROWS
    )
    op.execute(
        f"""
        INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity)
        VALUES
            {values_sql}
        ON CONFLICT (tipo_alerta) DO NOTHING;
        """
    )


def downgrade() -> None:
    """Drop ``prod.alert_types`` and its supporting objects."""
    op.execute(_LOCK_TIMEOUT_SQL)

    op.execute("DROP TRIGGER IF EXISTS alert_types_inmutable ON prod.alert_types;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_alert_types_inmutable();")
    op.execute("DROP TABLE IF EXISTS prod.alert_types CASCADE;")
