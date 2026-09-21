"""test_caja_sesion_unique_constraint_db.py — HU-F1.3 / REQ-OPS-026.

TDD RED-then-GREEN for the partial unique index
``uq_prod_sesion_one_active_per_user`` (migration 0023). Two
DB-backed scenarios:

  - T1 — INSERT two active ``prod.sesion`` rows for the same
    ``uuid_usuario`` → second INSERT raises ``UniqueViolation``
    (pgcode 23505).

  - T2 — INSERT a sesion, UPDATE ``timestamp_cierre`` (close it),
    then INSERT another sesion for the same ``uuid_usuario`` →
    succeeds because the partial predicate ``WHERE
    timestamp_cierre IS NULL`` excludes the closed row.

Requires ``PARKOS_DOCKER_TEST=1`` and a reachable ``parkos-branch-db``.
Skipped cleanly otherwise — mirrors the F1.8 precedent
``tests/integration/test_calcular_cotizacion_db.py``.
"""

from __future__ import annotations

import os
import uuid as uuid_lib
from datetime import UTC, datetime

import psycopg
import pytest

_DOCKER_TEST = os.environ.get("PARKOS_DOCKER_TEST") == "1"

pytestmark = pytest.mark.skipif(
    not _DOCKER_TEST,
    reason="PARKOS_DOCKER_TEST=1 not set; skip unique constraint DB "
    "tests (requires live branch-db with migration 0023 applied).",
)


def _now_naive() -> datetime:
    """Naive ``datetime`` matching ``DateTime(timezone=False)`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _truncate_sesion(pg_dsn: str) -> None:
    """Truncate ``prod.sesion`` so each scenario starts clean."""
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE prod.sesion CASCADE")
        conn.commit()


async def _seed_one_sesion(
    pg_dsn: str,
    *,
    uuid_usuario: uuid_lib.UUID,
    timestamp_cierre: datetime | None = None,
    sesion_uuid: uuid_lib.UUID | None = None,
) -> uuid_lib.UUID:
    """Insert one ``prod.sesion`` row via raw SQL.

    Returns the inserted ``uuid``.
    """
    target_uuid = sesion_uuid or uuid_lib.uuid4()
    now = _now_naive()

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO prod.sesion
                (valor_inicial_efectivo, valor_inicial_datafono,
                 uuid_sucursal, uuid_usuario, timestamp_apertura,
                 timestamp_cierre, uuid_usuario_cierre,
                 uuid, created_at, created_by, sync_status)
            VALUES (%s, %s, NULL, %s, %s, %s, NULL, %s, %s, %s, 'sincronizado')
            """,
            (
                100000,
                100000,
                str(uuid_usuario),
                now,
                timestamp_cierre,
                str(target_uuid),
                now,
                str(uuid_usuario),
            ),
        )
        conn.commit()
    return target_uuid


async def _close_sesion_via_sql(pg_dsn: str, sesion_uuid: uuid_lib.UUID) -> None:
    """Mark a sesion closed by setting ``timestamp_cierre = now()``."""
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE prod.sesion
            SET timestamp_cierre = %s
            WHERE uuid = %s
            """,
            (_now_naive(), str(sesion_uuid)),
        )
        conn.commit()


async def test_segunda_sesion_activa_mismo_uuid_usuario_falla_unique_violation(
    alembic_upgrade, pg_dsn
) -> None:
    """T1: After migration 0023 has applied the partial unique index,
    a second INSERT into ``prod.sesion`` for the same ``uuid_usuario``
    with ``timestamp_cierre IS NULL`` MUST raise
    ``psycopg.errors.UniqueViolation`` (pgcode 23505).

    RED (pre-migration): both inserts succeed. GREEN
    (post-migration): the second insert aborts with the typed
    psql error code.
    """
    from psycopg import errors as pg_errors

    await _truncate_sesion(pg_dsn)

    actor_uuid = uuid_lib.uuid4()
    sesion_1_uuid = uuid_lib.uuid4()
    sesion_2_uuid = uuid_lib.uuid4()

    # First open sesion — passes the partial unique constraint.
    await _seed_one_sesion(
        pg_dsn,
        uuid_usuario=actor_uuid,
        timestamp_cierre=None,
        sesion_uuid=sesion_1_uuid,
    )

    # Second open sesion for the SAME uuid_usuario — MUST FAIL.
    with pytest.raises(pg_errors.UniqueViolation) as exc_info:
        await _seed_one_sesion(
            pg_dsn,
            uuid_usuario=actor_uuid,
            timestamp_cierre=None,
            sesion_uuid=sesion_2_uuid,
        )

    # ``pgcode`` for UniqueViolation is "23505" (psycopg surfaces
    # it on the diag object).
    diag = exc_info.value.diag
    assert diag.sqlstate == "23505", (
        f"second open sesion for the same uuid_usuario MUST raise "
        f"UniqueViolation (sqlstate 23505); got {diag.sqlstate!r}"
    )


async def test_segunda_sesion_despues_de_cerrar_primera_pasa(alembic_upgrade, pg_dsn) -> None:
    """T2: Closing sesion #1 (timestamp_cierre NOT NULL) and then
    inserting sesion #2 for the same uuid_usuario MUST succeed,
    because the partial predicate ``WHERE timestamp_cierre IS NULL``
    excludes the closed row.

    RED (no migration or partial predicate missing): both inserts
    pass. GREEN: first insert + close + second insert succeed.
    """
    await _truncate_sesion(pg_dsn)

    actor_uuid = uuid_lib.uuid4()
    sesion_1_uuid = uuid_lib.uuid4()
    sesion_2_uuid = uuid_lib.uuid4()

    # First sesion — open, then close.
    await _seed_one_sesion(
        pg_dsn,
        uuid_usuario=actor_uuid,
        timestamp_cierre=None,
        sesion_uuid=sesion_1_uuid,
    )
    await _close_sesion_via_sql(pg_dsn, sesion_1_uuid)

    # Second sesion for the SAME uuid_usuario — MUST succeed because
    # the partial predicate excludes the closed row.
    result_uuid = await _seed_one_sesion(
        pg_dsn,
        uuid_usuario=actor_uuid,
        timestamp_cierre=None,
        sesion_uuid=sesion_2_uuid,
    )
    assert result_uuid == sesion_2_uuid, (
        f"second open sesion after closing the first MUST succeed; got {result_uuid!r}"
    )

    # Sanity: the table now has TWO rows for this uuid_usuario, one
    # closed and one open.
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT timestamp_cierre IS NULL AS is_open
            FROM prod.sesion
            WHERE uuid_usuario = %s
            ORDER BY timestamp_apertura ASC
            """,
            (str(actor_uuid),),
        )
        is_open_flags = sorted([bool(r[0]) for r in cur.fetchall()])
    assert is_open_flags == [False, True], (
        f"after close+reopen, the table MUST have one closed and one "
        f"open sesion for this uuid_usuario; got is_open={is_open_flags!r}"
    )


__all__ = [
    "test_segunda_sesion_activa_mismo_uuid_usuario_falla_unique_violation",
    "test_segunda_sesion_despues_de_cerrar_primera_pasa",
]
