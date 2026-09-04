"""add pairing_tokens + normalize revoked_sync_jwts (PR8a, T-PR8-06+07)

Revision ID: 0006_add_pairing_tokens_and_normalized_revoked_sync_jwts
Revises: 0004_add_factura_pagos_reverso_trigger
Create Date: 2026-09-03 12:00:00.000000

PR8a ships two changes to the ``prod`` [A] layer (per design §21.3 +
REQ-X5 + ``config.yaml rules.tasks``):

1. ``prod.pairing_tokens`` — NEW [A] table for short-lived (24h)
   admin-issued pairing tokens. Plaintext is NEVER persisted; only
   sha256(plaintext) lives in ``pairing_token_hash`` (String(64)).
   Composite PK (``uuid``, ``fecha_retencion_hasta``) for pg_partman.

2. ``prod.revoked_sync_jwts`` — NORMALIZED. PR2's 0003_* shipped this
   table with the wrong columns (``key_uuid`` / ``reason``) and a
   single-PK ``uuid``. PR8a drops + recreates it with the canonical
   shape (``jwt_kid`` + ``jwt_uuid`` + composite PK + bi-temporal UK
   on ``(jwt_kid, jwt_uuid, vigente_desde)``). The down_revision from
   the PR4/PR5 chain is 0004; before this script ran the chain was
   0001 → 0002 → 0003 → 0004 (there was no 0005 in the chain — the
   prompt's reference to ``0005_fix_idempotency_index_predicate`` was
   a stale docstring, see AGENTS.md risk register row #4 chain
   rationale).

Per ``openspec/config.yaml`` ``rules.tasks`` every migration that
creates an [A] table MUST include the ``REVOKE UPDATE, DELETE`` AND
the ``BEFORE UPDATE OR DELETE`` trigger creation in the SAME
migration script. This is the project's hard rule for defense in
depth at the DB layer, enforced by ``tests/migrations/
test_revokes_active.py`` + ``tests/migrations/test_a_inmutable.py``.

Partial indexes (one per table) target the hot lookup:

- ``ix_pairing_tokens_pending`` — rows that can still be consumed
  (``used=false AND revoked_at IS NULL``). Both constants + column
  references only; ``NOW()`` is intentionally NOT used here so the
  partial-index predicate is IMMUTABLE (required by PostgreSQL when
  the parent table is partitioned — see PR17 fix ``9dc48c9``).
- ``ix_revoked_sync_jwts_active`` — active revocations still in
  effect (``expires_at IS NOT NULL``). Same IMMUTABLE-safe predicate.

Downgrade is intentionally lossy: the dropped ``revoked_sync_jwts``
shape (single-PK ``uuid`` with ``key_uuid`` / ``reason``) cannot be
perfectly recovered from the new composite-PK normalized shape. The
chain cannot roll back past this point without a backup. Operators
who need the original shape back must restore from a pre-``0006``
snapshot.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_add_pairing_tokens_and_normalized_revoked_sync_jwts"
down_revision = "0004_add_factura_pagos_reverso_trigger"
branch_labels = None
depends_on = None

PG_UUID = postgresql.UUID(as_uuid=True)


def _audit_columns() -> list[sa.Column]:
    """``created_at`` + ``created_by`` — mandatory on every table (AGENTS.md §1)."""
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("created_by", PG_UUID, nullable=True),
    ]


def _sync_columns() -> list[sa.Column]:
    """Per-row sync bookkeeping on every replicated table."""
    return [
        sa.Column("sync_status", sa.String(length=16), nullable=True),
        sa.Column("sync_timestamp", sa.DateTime(timezone=False), nullable=True),
        sa.Column("sync_attempts", sa.Integer(), nullable=True),
    ]


def upgrade() -> None:
    """Create both tables with REVOKE + inmutable trigger in one TX.

    The normalize step runs FIRST so the new ``revoked_sync_jwts``
    shape is the only one in place when the trigger / index / REVOKE
    are applied. Idempotent: a re-run against an already-migrated DB
    would fail on the explicit ``CREATE TABLE`` (we use ``IF NOT
    EXISTS`` for indexes + functions but not for tables — the table
    itself is the unique fingerprint of the migration).
    """
    # 1. NORMALIZE: drop the old (PR2-shipped) shape of revoked_sync_jwts
    # including the trigger, function, partial index, and the table itself.
    # DROP TRIGGER / FUNCTION / INDEX use IF EXISTS so re-runs on a DB
    # where 0003_* was applied are safe; DROP TABLE is unconditional
    # because every "successful" migration leaves it gone.
    op.execute("DROP TRIGGER IF EXISTS revoked_sync_jwts_inmutable ON prod.revoked_sync_jwts;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_revoked_sync_jwts_inmutable();")
    op.drop_index(
        "ix_revoked_sync_jwts_active",
        table_name="revoked_sync_jwts",
        schema="prod",
    )
    op.execute("REVOKE UPDATE, DELETE ON prod.revoked_sync_jwts FROM rol_app;")
    op.execute("DROP TABLE IF EXISTS prod.revoked_sync_jwts;")

    # =========================================================================
    # 2. prod.pairing_tokens — NEW (T-PR8-05 + §21.3, REQ-X5)
    # =========================================================================
    op.create_table(
        "pairing_tokens",
        sa.Column(
            "uuid",
            PG_UUID,
            nullable=False,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "fecha_retencion_hasta",
            sa.Date(),
            nullable=False,
            server_default=sa.func.current_date(),
        ),
        sa.Column("uuid_sucursal", PG_UUID, nullable=True),
        # sha256(plaintext), hex-encoded CHAR(64). Plaintext never
        # persists — it's returned ONCE at issuance.
        sa.Column("pairing_token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("used_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("used_by_branch_info", postgresql.JSONB(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("revoked_by", PG_UUID, nullable=True),
        *_audit_columns(),
        *_sync_columns(),
        sa.PrimaryKeyConstraint(
            "uuid",
            "fecha_retencion_hasta",
            name="pairing_tokens_pk",
        ),
        sa.ForeignKeyConstraint(
            ["uuid_sucursal"],
            ["prod.sucursal.uuid"],
            name="fk_pairing_tokens_uuid_sucursal",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by"],
            ["prod.usuarios.uuid"],
            name="fk_pairing_tokens_revoked_by",
        ),
        schema="prod",
        postgresql_partition_by="RANGE (fecha_retencion_hasta)",
    )
    # Active-token partial index — predicates are constants + column
    # references only (no NOW()), so IMMUTABLE; required by PR17's
    # chain-unblock fix so the parent partitioned table can carry the
    # index.
    op.create_index(
        "ix_pairing_tokens_pending",
        "pairing_tokens",
        ["uuid"],
        unique=False,
        postgresql_where=sa.text("used = false AND revoked_at IS NULL"),
        schema="prod",
    )

    # REVOKE + trigger — per config.yaml rules.tasks, in the SAME migration.
    op.execute("REVOKE UPDATE, DELETE ON prod.pairing_tokens FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.pairing_tokens TO rol_app;")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prod.fn_pairing_tokens_inmutable()
        RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'PAIRING_TOKENS_INMUTABLE: UPDATE/DELETE not allowed on prod.pairing_tokens'
                USING ERRCODE = '42501',
                      HINT = 'pairing_tokens is append-only; corrections must be expressed as new rows.';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER pairing_tokens_no_update_delete
            BEFORE UPDATE OR DELETE ON prod.pairing_tokens
            FOR EACH ROW EXECUTE FUNCTION prod.fn_pairing_tokens_inmutable();
        """
    )

    # =========================================================================
    # 3. prod.revoked_sync_jwts — NORMALIZED (T-PR8-05 + §21.3)
    # =========================================================================
    op.create_table(
        "revoked_sync_jwts",
        sa.Column(
            "uuid",
            PG_UUID,
            nullable=False,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "fecha_retencion_hasta",
            sa.Date(),
            nullable=False,
            server_default=sa.func.current_date(),
        ),
        sa.Column(
            "vigente_desde",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("jwt_kid", sa.String(length=64), nullable=False),
        sa.Column("jwt_uuid", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("revoked_by", PG_UUID, nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        *_audit_columns(),
        *_sync_columns(),
        sa.UniqueConstraint(
            "jwt_kid",
            "jwt_uuid",
            "vigente_desde",
            "fecha_retencion_hasta",
            name="revoked_sync_jwts_uk01",
        ),
        sa.PrimaryKeyConstraint(
            "uuid",
            "fecha_retencion_hasta",
            name="revoked_sync_jwts_pk",
        ),
        schema="prod",
        postgresql_partition_by="RANGE (fecha_retencion_hasta)",
    )
    # Active-revocation partial index (constant + nullable predicate).
    op.create_index(
        "ix_revoked_sync_jwts_active",
        "revoked_sync_jwts",
        ["jwt_kid", "jwt_uuid"],
        unique=False,
        postgresql_where=sa.text("expires_at IS NOT NULL"),
        schema="prod",
    )

    # REVOKE + trigger — per config.yaml rules.tasks, in the SAME migration.
    op.execute("REVOKE UPDATE, DELETE ON prod.revoked_sync_jwts FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.revoked_sync_jwts TO rol_app;")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prod.fn_revoked_sync_jwts_inmutable()
        RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'REVOKED_SYNC_JWTS_INMUTABLE: UPDATE/DELETE not allowed on prod.revoked_sync_jwts'
                USING ERRCODE = '42501',
                      HINT = 'revoked_sync_jwts is append-only; revoking a token twice is a no-op (UK rejects).';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER revoked_sync_jwts_no_update_delete
            BEFORE UPDATE OR DELETE ON prod.revoked_sync_jwts
            FOR EACH ROW EXECUTE FUNCTION prod.fn_revoked_sync_jwts_inmutable();
        """
    )


def downgrade() -> None:
    """Drop both tables. DOWNGRADE IS LOSSY for ``revoked_sync_jwts``.

    The shape that PR2's 0003_* shipped (single-PK ``uuid``,
    ``key_uuid``, ``reason``) cannot be perfectly recovered from the
    new composite-PK normalized shape. Re-running ``0003_*`` after
    downgrade would fail because the FKs in 0004's ``01`` assume a
    shape that no longer matches. The chain cannot roll back past
    this point without a backup; operators wanting the old shape must
    restore the pre-``0006`` snapshot.
    """
    # pairing_tokens
    op.execute("DROP TRIGGER IF EXISTS pairing_tokens_no_update_delete ON prod.pairing_tokens;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_pairing_tokens_inmutable();")
    op.execute("GRANT UPDATE, DELETE ON prod.pairing_tokens TO rol_app;")
    op.drop_index(
        "ix_pairing_tokens_pending",
        table_name="pairing_tokens",
        schema="prod",
    )
    op.drop_table("pairing_tokens", schema="prod")

    # revoked_sync_jwts (normalized)
    op.execute("DROP TRIGGER IF EXISTS revoked_sync_jwts_no_update_delete ON prod.revoked_sync_jwts;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_revoked_sync_jwts_inmutable();")
    op.execute("GRANT UPDATE, DELETE ON prod.revoked_sync_jwts TO rol_app;")
    op.drop_index(
        "ix_revoked_sync_jwts_active",
        table_name="revoked_sync_jwts",
        schema="prod",
    )
    op.drop_table("revoked_sync_jwts", schema="prod")
