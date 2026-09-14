"""HU-F1.3 partial unique index on ``prod.sesion(uuid_usuario)``.

Revision ID: 0023_unique_active_sesion_per_user
Revises: 0022_create_calcular_cotizacion
Create Date: 2026-09-14 18:00:00.000000

**Scope.** Creates the partial unique index
``prod.uq_prod_sesion_one_active_per_user`` on
``prod.sesion(uuid_usuario) WHERE timestamp_cierre IS NULL`` (REQ-OPS-026).

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
transaction; Alembic's ``op.execute`` runs each statement in
autocommit by default. ``IF NOT EXISTS`` makes the migration
idempotent against retries: a second ``alembic upgrade`` no-ops
without re-running the pre-flight block (the pre-flight is also
idempotent — it counts orphans; the absence of orphans is a no-op).

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
    #    transaction; Alembic's op.execute uses autocommit per call.
    op.execute(
        """
        CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
            prod.uq_prod_sesion_one_active_per_user
        ON prod.sesion (uuid_usuario)
        WHERE timestamp_cierre IS NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX CONCURRENTLY IF EXISTS
            prod.uq_prod_sesion_one_active_per_user;
        """
    )


__all__ = ["downgrade", "upgrade"]
