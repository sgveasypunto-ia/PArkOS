"""add idempotency_keys + revoked_sync_jwts tables (REQ-OP-04, design §8 + §21)

Revision ID: 0003_add_idempotency_keys_and_revoked_sync_jwts
Revises: 0002_seed_permisos_canonicos
Create Date: 2026-09-03 12:00:00.000000

PR2 ships two new ``[A]``-class tables. Per ``openspec/config.yaml``
``rules.tasks`` every migration that creates an ``[A]`` table MUST
include the ``REVOKE UPDATE, DELETE`` AND the ``BEFORE UPDATE OR DELETE``
trigger creation in the SAME migration. This is the project's hard rule
for defense-in-depth at the DB layer.

Tables created:

  - ``prod.idempotency_keys`` — caches HTTP responses keyed by
    ``sha256(issuer + ":" + idem_key)``. The middleware reads on
    request, writes on response. Single PK on ``uuid``. UK on
    ``(issuer, key_hash)``.

  - ``prod.revoked_sync_jwts`` — JWT revocation registry. Single PK on
    ``uuid``. UK on ``key_uuid`` makes the revocation idempotent.

Both follow the same ``[A]`` recipe:
  1. CREATE TABLE with uuid PK + audit columns
  2. CREATE UNIQUE INDEX (per-table UK)
  3. ``REVOKE UPDATE, DELETE ON prod.<table> FROM rol_app``
  4. ``CREATE FUNCTION prod.fn_<table>_inmutable()`` — raises
     ``<TABLE>_INMUTABLE`` on UPDATE OR DELETE
  5. ``CREATE TRIGGER <table>_inmutable BEFORE UPDATE OR DELETE`` —
     invokes the function

The carve-out DELETEs are owner-only (the ``postgres`` role runs the
nightly TTL sweep on ``idempotency_keys``); ``rol_app`` keeps only
``SELECT, INSERT`` grants on these tables.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_add_idempotency_keys_and_revoked_sync_jwts"
down_revision = "0002_seed_permisos_canonicos"
branch_labels = None
depends_on = None

PG_UUID = postgresql.UUID(as_uuid=True)


def _audit_columns() -> list[sa.Column]:
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
    return [
        sa.Column("sync_status", sa.String(length=16), nullable=True),
        sa.Column("sync_timestamp", sa.DateTime(timezone=False), nullable=True),
        sa.Column("sync_attempts", sa.Integer(), nullable=True),
    ]


def upgrade() -> None:
    """Create both tables with REVOKE + inmutable trigger in one TX."""
    # Ensure the schema exists (0001 already creates it, but be idempotent).
    op.execute("CREATE SCHEMA IF NOT EXISTS prod;")

    # =========================================================================
    # prod.idempotency_keys
    # =========================================================================
    op.create_table(
        "idempotency_keys",
        sa.Column(
            "uuid",
            PG_UUID,
            primary_key=True,
            nullable=False,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column("issuer", sa.String(length=32), nullable=True),
        sa.Column("key_hash", sa.CHAR(64), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=True),
        sa.Column("path", sa.String(length=512), nullable=True),
        sa.Column("request_body_hash", sa.CHAR(64), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(), nullable=True),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=False),
            nullable=True,
            server_default=sa.text("NOW() + INTERVAL '24 hours'"),
        ),
        *_audit_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("issuer", "key_hash", name="idempotency_keys_uk01"),
        schema="prod",
    )
    # Active-key partial index — speeds up the middleware's hot-path lookup
    # (``WHERE issuer=:i AND key_hash=:h AND expires_at > NOW()``) and keeps
    # the index small (expired rows are physically dropped by the nightly
    # TTL sweep, so the index only carries live keys).
    op.create_index(
        "ix_idempotency_keys_active",
        "idempotency_keys",
        ["issuer", "key_hash"],
        unique=False,
        postgresql_where=sa.text("expires_at > NOW()"),
        schema="prod",
    )

    # REVOKE + trigger — per config.yaml rules.tasks, in the SAME migration.
    op.execute("REVOKE UPDATE, DELETE ON prod.idempotency_keys FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.idempotency_keys TO rol_app;")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prod.fn_idempotency_keys_inmutable()
        RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'IDEMPOTENCY_KEYS_INMUTABLE: UPDATE/DELETE not allowed on prod.idempotency_keys'
                USING ERRCODE = '42501',
                      HINT = 'idempotency_keys is append-only; corrections must be expressed as new rows.';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER idempotency_keys_inmutable
            BEFORE UPDATE OR DELETE ON prod.idempotency_keys
            FOR EACH ROW EXECUTE FUNCTION prod.fn_idempotency_keys_inmutable();
        """
    )

    # =========================================================================
    # prod.revoked_sync_jwts
    # =========================================================================
    op.create_table(
        "revoked_sync_jwts",
        sa.Column(
            "uuid",
            PG_UUID,
            primary_key=True,
            nullable=False,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column("key_uuid", sa.String(length=64), nullable=True),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=False),
            nullable=True,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("revoked_by", PG_UUID, nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=False),
            nullable=True,
            server_default=sa.text("NOW() + INTERVAL '30 days'"),
        ),
        *_audit_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("key_uuid", name="revoked_sync_jwts_uk01"),
        schema="prod",
    )
    op.create_index(
        "ix_revoked_sync_jwts_active",
        "revoked_sync_jwts",
        ["key_uuid"],
        unique=False,
        postgresql_where=sa.text("expires_at > NOW()"),
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
        CREATE TRIGGER revoked_sync_jwts_inmutable
            BEFORE UPDATE OR DELETE ON prod.revoked_sync_jwts
            FOR EACH ROW EXECUTE FUNCTION prod.fn_revoked_sync_jwts_inmutable();
        """
    )


def downgrade() -> None:
    """Drop both tables, dropping triggers and functions first.

    The ``BEFORE UPDATE OR DELETE`` triggers must be dropped BEFORE
    the table (PostgreSQL doesn't auto-drop triggers when the table
    is dropped — they're owned by the table and dropped together in
    PG 14+, but explicit ordering keeps the migration readable on
    older versions). The function is dropped after to keep the
    sequence reversible.

    ``GRANT UPDATE, DELETE`` is restored before DROP so a downgrade
    on a populated DB succeeds (the trigger would otherwise block the
    DROP indirectly via FKs, though DROP TABLE bypasses triggers).
    """
    # idempotency_keys
    op.execute("DROP TRIGGER IF EXISTS idempotency_keys_inmutable ON prod.idempotency_keys;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_idempotency_keys_inmutable();")
    op.execute("GRANT UPDATE, DELETE ON prod.idempotency_keys TO rol_app;")
    op.drop_index("ix_idempotency_keys_active", table_name="idempotency_keys", schema="prod")
    op.drop_table("idempotency_keys", schema="prod")

    # revoked_sync_jwts
    op.execute("DROP TRIGGER IF EXISTS revoked_sync_jwts_inmutable ON prod.revoked_sync_jwts;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_revoked_sync_jwts_inmutable();")
    op.execute("GRANT UPDATE, DELETE ON prod.revoked_sync_jwts TO rol_app;")
    op.drop_index("ix_revoked_sync_jwts_active", table_name="revoked_sync_jwts", schema="prod")
    op.drop_table("revoked_sync_jwts", schema="prod")