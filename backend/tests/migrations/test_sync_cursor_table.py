"""test_sync_cursor_table.py — CU-07 pull cursor DB contract (migration 0051).

Verifies the ``[A]``-class defense in depth on ``prod.sync_cursor``:

  1. ``rol_app`` has NO UPDATE/DELETE privilege (REVOKE'd in 0051).
  2. ``BEFORE UPDATE OR DELETE`` trigger carve-out: UPDATE of the
     operational column ``ultimo_seq`` (the pull watermark) SUCCEEDS
     (the worker's set_seq path); UPDATE of any other column
     (``uuid_sucursal``) is REJECTED with ``SYNC_CURSOR_IMMUTABLE``;
     DELETE is unconditionally REJECTED.
  3. ``UNIQUE (uuid_sucursal)``: a second row for the same sucursal is
     rejected.

Same idiom as ``test_repo_ingreso_consecutivo.py``: real Postgres
(testcontainers or ``PARKOS_DOCKER_TEST=1`` live branch DB), seeded
empresa + sucursal rows, TRUNCATE between scenarios.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

import pytest
from parkos_core.models.V.empresa import Empresa
from parkos_core.models.V.sucursal import Sucursal
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seed_empresa(pg_engine: AsyncEngine) -> uuid_lib.UUID:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre=f"Empresa cursor {empresa_uuid.hex[:6]}",
                nit=f"900{empresa_uuid.hex[:6]}",
                mensaje_bienvenida="hi",
                mensaje_salida="bye",
                regimen="comun",
                vigente_desde=_now(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now(),
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.commit()
        return empresa_uuid


async def _seed_sucursal(
    pg_engine: AsyncEngine, *, uuid_empresa: uuid_lib.UUID
) -> uuid_lib.UUID:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal_uuid = uuid_lib.uuid4()
        session.add(
            Sucursal(
                uuid=sucursal_uuid,
                uuid_empresa=uuid_empresa,
                uuid_tipo_sucursal=None,
                nombre=f"Suc cursor {sucursal_uuid.hex[:6]}",
                prefijo_nombre=f"S{sucursal_uuid.hex[:4]}",
                ciudad="Bogota",
                direccion="Calle cursor 1",
                telefono="+57111",
                horario="24/7",
                vigente_desde=_now(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now(),
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
        return sucursal_uuid


@pytest.fixture
async def seeded_sucursal(pg_engine: AsyncEngine, pg_dsn: str) -> uuid_lib.UUID:
    """Clean + seed one sucursal row for the cursor tests."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE prod.sync_cursor, prod.sucursal, prod.empresa CASCADE")
        conn.commit()
    empresa_uuid = await _seed_empresa(pg_engine)
    return await _seed_sucursal(pg_engine, uuid_empresa=empresa_uuid)


def _insert_cursor(pg_dsn: str, sucursal_uuid: uuid_lib.UUID, seq: int = 0) -> uuid_lib.UUID:
    """Insert one cursor row for ``sucursal_uuid``; return its uuid."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO prod.sync_cursor (uuid_sucursal, ultimo_seq) "
            "VALUES (%s, %s) RETURNING uuid",
            (sucursal_uuid, seq),
        )
        row_uuid = cur.fetchone()[0]
        conn.commit()
        return row_uuid


# ---------------------------------------------------------------------------
# 1. REVOKE UPDATE/DELETE from rol_app
# ---------------------------------------------------------------------------


async def test_rol_app_cannot_update_or_delete_sync_cursor(pg_dsn: str) -> None:
    """REVOKE (0051): rol_app has no UPDATE/DELETE on prod.sync_cursor."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT has_table_privilege('rol_app', 'prod.sync_cursor', 'UPDATE')"
        )
        can_update = (await cur.fetchone())[0]
        await cur.execute(
            "SELECT has_table_privilege('rol_app', 'prod.sync_cursor', 'DELETE')"
        )
        can_delete = (await cur.fetchone())[0]
    assert can_update is False, "sync_cursor: REVOKE failed — rol_app still has UPDATE"
    assert can_delete is False, "sync_cursor: REVOKE failed — rol_app still has DELETE"


# ---------------------------------------------------------------------------
# 2. Trigger carve-out: ultimo_seq advances, other columns + DELETE blocked
# ---------------------------------------------------------------------------


def test_trigger_allows_update_of_ultimo_seq_only(
    pg_dsn: str, seeded_sucursal: uuid_lib.UUID
) -> None:
    """The carve-out permits exactly the (ultimo_seq) advance (CU-07)."""
    import psycopg

    _insert_cursor(pg_dsn, seeded_sucursal, seq=100)
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE prod.sync_cursor SET ultimo_seq = 200 "
            "WHERE uuid_sucursal = %s",
            (seeded_sucursal,),
        )
        conn.commit()
        cur.execute(
            "SELECT ultimo_seq FROM prod.sync_cursor WHERE uuid_sucursal = %s",
            (seeded_sucursal,),
        )
        assert cur.fetchone()[0] == 200


def test_trigger_rejects_update_of_non_carveout_column(
    pg_dsn: str, seeded_sucursal: uuid_lib.UUID
) -> None:
    """UPDATE of a non-carve-out column raises SYNC_CURSOR_IMMUTABLE."""
    import psycopg

    _insert_cursor(pg_dsn, seeded_sucursal, seq=100)
    try:
        with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE prod.sync_cursor SET uuid_sucursal = gen_random_uuid() "
                "WHERE uuid_sucursal = %s",
                (seeded_sucursal,),
            )
            conn.commit()
    except psycopg.errors.InsufficientPrivilege as exc:
        assert "SYNC_CURSOR_IMMUTABLE" in str(exc), f"unexpected error: {exc}"
    else:
        pytest.fail("UPDATE of uuid_sucursal succeeded but carve-out should have blocked it")


def test_trigger_rejects_delete(pg_dsn: str, seeded_sucursal: uuid_lib.UUID) -> None:
    """DELETE from prod.sync_cursor raises SYNC_CURSOR_IMMUTABLE."""
    import psycopg

    _insert_cursor(pg_dsn, seeded_sucursal, seq=0)
    try:
        with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM prod.sync_cursor WHERE uuid_sucursal = %s",
                (seeded_sucursal,),
            )
            conn.commit()
    except psycopg.errors.InsufficientPrivilege as exc:
        assert "SYNC_CURSOR_IMMUTABLE" in str(exc), f"unexpected error: {exc}"
    else:
        pytest.fail("DELETE succeeded but trigger should have blocked it")


# ---------------------------------------------------------------------------
# 3. UNIQUE (uuid_sucursal) — one cursor row per branch
# ---------------------------------------------------------------------------


def test_unique_uuid_sucursal(pg_dsn: str, seeded_sucursal: uuid_lib.UUID) -> None:
    """UK (0051): a second cursor row for the same sucursal is rejected."""
    import psycopg

    _insert_cursor(pg_dsn, seeded_sucursal, seq=100)
    try:
        _insert_cursor(pg_dsn, seeded_sucursal, seq=101)
    except psycopg.errors.UniqueViolation as exc:
        assert "sync_cursor_uuid_sucursal_key" in str(exc), f"unexpected error: {exc}"
    else:
        pytest.fail("second row for the same uuid_sucursal succeeded against UK")