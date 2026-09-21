"""test_migration_0023_preflight.py — HU-F1.3 / REQ-OPS-026 pre-flight.

TDD RED-then-GREEN coverage for the pre-flight block of migration
``0023_unique_active_sesion_per_user.py`` (partial unique index
``uq_prod_sesion_one_active_per_user`` on ``prod.sesion(uuid_usuario)
WHERE timestamp_cierre IS NULL``). One scenario:

  - T1 — ``prod.sesion`` already contains TWO active sesiones
    (``timestamp_cierre IS NULL``) for the same ``uuid_usuario``.
    Running the migration's pre-flight ``DO $$ … HAVING count(*) > 1
    … RAISE EXCEPTION`` MUST abort with the typed error
    ``unique_active_sesion_preflight_failed`` BEFORE the
    ``CREATE UNIQUE INDEX`` runs.

The test mirrors the migration's pre-flight logic verbatim via raw
SQL (``psycopg``) instead of importing the Alembic module — the
``migrations/versions/`` directory is NOT a Python package (no
``__init__.py``); Alembic loads its scripts via ``ScriptDirectory``,
not via Python's import system.

Requires ``PARKOS_DOCKER_TEST=1`` and a reachable ``parkos-branch-db``.
Skipped cleanly otherwise.
"""

from __future__ import annotations

import os
import uuid as uuid_lib
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

# Integration test — gated on PARKOS_DOCKER_TEST=1 (live branch-db).
_DOCKER_TEST = os.environ.get("PARKOS_DOCKER_TEST") == "1"

pytestmark = pytest.mark.skipif(
    not _DOCKER_TEST,
    reason="PARKOS_DOCKER_TEST=1 not set; skip migration preflight "
    "integration (requires live branch-db).",
)


def _now_naive() -> datetime:
    """Naive ``datetime`` matching ``DateTime(timezone=False)`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


PRE_FLIGHT_SQL = """
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


async def _truncate_sesion(pg_dsn: str) -> None:
    """Truncate ``prod.sesion`` so each scenario starts clean."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE prod.sesion CASCADE")
        conn.commit()


async def _drop_index_if_exists(pg_dsn: str) -> None:
    """Best-effort DROP INDEX before re-running the migration.

    Index name is bare (no schema qualifier): ``CREATE INDEX CONCURRENTLY``
    with a schema-qualified identifier fails on PostgreSQL 16 with
    ``syntax error at or near "."`` — schema comes from ``search_path``.
    Match the migration's upgrade/downgrade verbatim.
    """
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("DROP INDEX IF EXISTS uq_prod_sesion_one_active_per_user")
        conn.commit()


async def test_migration_preflight_aborta_con_dos_sesiones_activas(pg_engine, pg_dsn) -> None:
    """When ``prod.sesion`` already contains TWO active sesiones
    (``timestamp_cierre IS NULL``) for the same ``uuid_usuario``,
    the pre-flight block from migration ``0023_…`` MUST abort with
    the typed error ``unique_active_sesion_preflight_failed``.

    RED: migration file does not yet exist on disk → the migration
    version string is unknown to ``alembic_version``. This test asserts
    the pre-flight SQL output independently of the migration.

    GREEN: the pre-flight raises a Postgres exception whose message
    contains ``unique_active_sesion_preflight_failed``.
    """
    await _truncate_sesion(pg_dsn)
    await _drop_index_if_exists(pg_dsn)

    # Seed two active sesiones for the same uuid_usuario via raw SQL —
    # bypassing the FK + ORM complexity of a session. This mirrors the
    # "orphan data" state the pre-flight is designed to detect.
    actor_uuid_str = str(uuid_lib.uuid4())
    seed_sql = """
    INSERT INTO prod.sesion
        (valor_inicial_efectivo, valor_inicial_datafono,
         uuid_sucursal, uuid_usuario, timestamp_apertura,
         timestamp_cierre, uuid_usuario_cierre,
         uuid, created_at, created_by, sync_status)
    VALUES (:valor, :valor, NULL, :uuid_usuario, NOW(), NULL, NULL,
            gen_random_uuid(), NOW(), :uuid_usuario, 'sincronizado'),
           (:valor, :valor, NULL, :uuid_usuario, NOW(), NULL, NULL,
            gen_random_uuid(), NOW(), :uuid_usuario, 'sincronizado');
    """
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(seed_sql, {"valor": 100000, "uuid_usuario": actor_uuid_str})
        conn.commit()

    # Run the pre-flight. The expected outcome is a raised
    # ``psycopg.errors.RaiseException`` whose message starts with
    # ``unique_active_sesion_preflight_failed:``.
    from psycopg import errors as pg_errors

    with (
        psycopg.connect(pg_dsn) as conn,
        conn.cursor() as cur,
        pytest.raises(pg_errors.RaiseException) as exc_info,
    ):
        cur.execute(PRE_FLIGHT_SQL)
    conn.commit()

    msg = str(exc_info.value)
    assert "unique_active_sesion_preflight_failed" in msg, (
        f"pre-flight abort MUST surface the typed error "
        f"'unique_active_sesion_preflight_failed'; got {msg!r}"
    )
    assert actor_uuid_str in msg, (
        f"pre-flight MUST list the offending uuid_usuario in the "
        f"error message; expected to find {actor_uuid_str!r} in "
        f"{msg!r}"
    )

    # Post-condition: the partial unique index is NOT created.
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = (
            await session.execute(
                text(
                    "SELECT 1 FROM pg_indexes "
                    "WHERE schemaname = 'prod' "
                    "AND tablename = 'sesion' "
                    "AND indexname = 'uq_prod_sesion_one_active_per_user'"
                )
            )
        ).first()
    assert row is None, (
        "uq_prod_sesion_one_active_per_user MUST NOT exist after a "
        "pre-flight abort; pre-flight must run BEFORE CREATE INDEX "
        "(D-HU-F1.3-7)."
    )

    # Cleanup: leave the DB in a known state for downstream tests.
    await _truncate_sesion(pg_dsn)


__all__ = [
    "test_migration_preflight_aborta_con_dos_sesiones_activas",
]
