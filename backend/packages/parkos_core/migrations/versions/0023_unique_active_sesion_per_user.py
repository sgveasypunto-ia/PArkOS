"""HU-F1.3 partial unique index on ``prod.sesion(uuid_usuario)``.

Revision ID: 0023_unique_active_sesion_per_user
Revises: 0022_create_calcular_cotizacion
Create Date: 2026-09-14 18:00:00.000000

**Scope.** Creates the partial unique index
``uq_prod_sesion_one_active_per_user`` on
``prod.sesion(uuid_usuario) WHERE timestamp_cierre IS NULL`` (REQ-OPS-026).

**Naming.** The index name is bare (``uq_prod_sesion_one_active_per_user``).
``CREATE INDEX CONCURRENTLY`` with a schema-qualified identifier fails on
PostgreSQL 16 with ``syntax error at or near "."`` — the schema comes from
``search_path`` / ``current_schema``, NOT from the identifier. The
``prod`` token here is part of the table's namespace
(``prod.sesion``), reflected in the index name as a name-prefix per
the repo convention ``uq_<schema-prefix>_<table>_<purpose>`` (see
migration 0024 line 119 [still has the legacy bug — fix in 0025b follow-up]
and the corrected precedent in migration 0034 line 113, verified live
against ``PostgreSQL 16.15`` on 2026-09-17).

The index enforces the invariant ``one OPEN cash session per
operator`` at the DB level, defense in depth on top of the existing
app-level ``open_session`` fast-path check. The ``WHERE
timestamp_cierre IS NULL`` predicate is mandatory: a full unique index
would forbid two CLOSED sesiones for the same actor (a legitimate
state — one actor can have many historical shifts).

**Architecture.** Two ``op.execute`` blocks run in order:

  1. Pre-flight — ``DO $$ … HAVING count(*) > 1 … RAISE EXCEPTION``
     aborts the migration with a typed error if any
     ``uuid_usuario`` already has > 1 active sesiones in the table.
     Operators decide manually before retrying.

  2. ``CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`` — applies the
     partial unique index without taking an ``AccessExclusiveLock``
     against ``prod.sesion`` while cashier operations continue.

**Volatility / idempotency.** ``CONCURRENTLY`` cannot run inside a
transaction; alembic's default ``begin_transaction()`` wraps the
migration, so we explicitly opt out via ``autocommit_block()`` on the
CONCURRENTLY call (matches migration 0033 line 73 precedent).
``IF NOT EXISTS`` makes the migration idempotent against retries: a
second ``alembic upgrade`` no-ops without re-running the pre-flight
block (the pre-flight is also idempotent — it counts orphans; the
absence of orphans is a no-op).

**Precedente.** PRE-F1.8 + F1.4 use ``CONCURRENTLY`` for
production-safe index creation; this migration follows the same
pattern.

**Downgrade.** ``DROP INDEX CONCURRENTLY IF EXISTS`` mirrors the
build mode — same idiom as F1.4's downgrade.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0023_unique_active_sesion_per_user"
down_revision = "0022_create_calcular_cotizacion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Pre-flight: abort the migration if any (uuid_usuario) already
    #    has > 1 active sesion. CREATE UNIQUE INDEX would fail with a
    #    cryptic "duplicate key value violates unique constraint"
    #    message; we emit a typed error listing the offender UUIDs so
    #    an operator can close them manually before retrying.
    op.execute(
        """
        DO $$
        DECLARE
            n_bad INT;
            offenders TEXT;
        BEGIN
            SELECT count(*) INTO n_bad
            FROM (
                SELECT uuid_usuario
                FROM prod.sesion
                WHERE timestamp_cierre IS NULL
                GROUP BY uuid_usuario
                HAVING count(*) > 1
            ) t;
            IF n_bad > 0 THEN
                SELECT string_agg(uuid_usuario::text, ', ') INTO offenders
                FROM (
                    SELECT uuid_usuario
                    FROM prod.sesion
                    WHERE timestamp_cierre IS NULL
                    GROUP BY uuid_usuario
                    HAVING count(*) > 1
                ) ord;
                RAISE EXCEPTION
                    'unique_active_sesion_preflight_failed: % uuid_usuario(s) '
                    'with >1 active sesion. Close them manually first: %',
                    n_bad, offenders
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
        END $$;
        """
    )

    # 2) Create the partial unique index CONCURRENTLY so we do NOT
    #    take an AccessExclusiveLock against prod.sesion while it is
    #    serving cashier operations. CONCURRENTLY cannot run inside a
    #    transaction — alembic's default ``begin_transaction()`` wraps
    #    the migration; we explicitly opt OUT for this op via
    #    ``autocommit_block()`` (KD-LOGIN-06 + F1.15 migration 0033
    #    precedent, lines 73-80). The index name is BARE: the
    #    ``IF NOT EXISTS`` clause does not support a schema-qualified
    #    identifier on PostgreSQL 16 (``syntax error at or near "."``,
    #    verified live 2026-09-17) — the schema comes from the
    #    ``ON prod.sesion`` clause.
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
                uq_prod_sesion_one_active_per_user
            ON prod.sesion (uuid_usuario)
            WHERE timestamp_cierre IS NULL;
            """
        )


def downgrade() -> None:
    # Schema-qualified DROP — ``DROP INDEX CONCURRENTLY IF EXISTS``
    # resolves the index regardless of the connection's ``search_path``
    # (which env.py does not pin). The bare index name on the
    # upgrade side is fine because ``ON prod.sesion (...)`` supplies
    # the schema implicitly. Same autocommit opt-out as the upgrade
    # (mirrors migration 0033 line 89).
    with op.get_context().autocommit_block():
        op.execute(
            """
            DROP INDEX CONCURRENTLY IF EXISTS
                prod.uq_prod_sesion_one_active_per_user;
            """
        )


__all__ = ["downgrade", "upgrade"]
