"""test_mv_ocupacion_diaria_db.py -- HU-F1.5 / REQ-OPS-030 DB integration.

TDD RED-then-GREEN coverage for the materialized view
``prod.mv_ocupacion_diaria`` semantics. Two scenarios:

  T1 -- insert_ingreso_then_refresh: insert an ingreso with
       ``uuid_sucursal=X, uuid_tipo_vehiculo=T``; refresh the MV;
       ``repo.ocupacion.get_ocupacion_puros_activos`` returns the row
       with ``activos == 1`` and ``cupo_maximo == 0`` (no cvs row
       seeded), so ``disponible == -1`` (KD-6 valid negative).

  T2 -- insert_salida_decrements: insert an ingreso, then insert a
       matching ``salidas`` row; refresh; the MV no longer reports
       the ingreso as active -- the breakdown for ``(X, T)`` is
       empty.

Pattern mirrors ``tests/integration/test_calcular_cotizacion_db.py``
(F1.8 precedent) and ``tests/integration/test_caja_sesion_unique
_constraint_db.py`` (F1.3 precedent). Requires
``PARKOS_DOCKER_TEST=1`` and a reachable ``parkos-branch-db``;
skipped cleanly otherwise.
"""
from __future__ import annotations

import os
import uuid as uuid_lib
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

_DOCKER_TEST = os.environ.get("PARKOS_DOCKER_TEST") == "1"

pytestmark = pytest.mark.skipif(
    not _DOCKER_TEST,
    reason="PARKOS_DOCKER_TEST=1 not set; skip mv_ocupacion_diaria "
    "DB tests (requires live branch-db with migration 0024 applied).",
)


def _now_naive() -> datetime:
    """Naive ``datetime`` matching ``DateTime(timezone=False)`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _setup_view(pg_dsn: str) -> None:
    """Best-effort CREATE of the view + UNIQUE INDEX, idempotent.

    The test runs against a live ``parkos-branch-db`` whose migration
    state may or may not include 0024. We build the artifacts
    ourselves so the test is decoupled from the alembic chain."""
    import psycopg

    mv_sql = """
    CREATE MATERIALIZED VIEW IF NOT EXISTS prod.mv_ocupacion_diaria AS
    SELECT
        i.uuid_sucursal,
        i.uuid_tipo_vehiculo,
        count(*) AS activos
    FROM prod.ingreso i
    WHERE
        i.uuid_tipo_vehiculo IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM prod.salidas s
            WHERE s.uuid_ingreso = i.uuid
              AND s.uuid_sucursal = i.uuid_sucursal
        )
        AND NOT EXISTS (
            SELECT 1 FROM prod.anulaciones a
            WHERE a.uuid_ingreso = i.uuid
              AND a.estado = 'ejecutada'
              AND a.tipo_anulable IN ('ingreso', 'salida')
        )
    GROUP BY i.uuid_sucursal, i.uuid_tipo_vehiculo;
    """
    idx_sql = """
    CREATE UNIQUE INDEX IF NOT EXISTS
        uq_mv_ocupacion_diaria_sucursal_tipo
    ON prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo);
    """

    with psycopg.connect(pg_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(mv_sql)
        cur.execute(idx_sql)


async def _drop_mv(pg_dsn: str) -> None:
    """Best-effort DROP for clean state."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS prod.mv_ocupacion_diaria CASCADE")
        conn.commit()


async def _truncate_sources(pg_dsn: str) -> None:
    """Truncate the source tables so each scenario starts clean."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE prod.ingreso, prod.salidas, prod.anulaciones, "
            "prod.cantidad_vehiculos_sucursal, prod.tipos_vehiculo, "
            "prod.sucursal, prod.empresa CASCADE"
        )
        conn.commit()


async def _seed_empresa_sucursal(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
) -> None:
    """Insert ``empresa`` + ``sucursal`` to satisfy the FK chain on
    ``prod.ingreso.uuid_sucursal``.
    """
    from parkos_core.models.V.empresa import Empresa
    from parkos_core.models.V.sucursal import Sucursal

    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Empresa Ocup Test",
                nit=f"900{empresa_uuid.hex[:6]}",
                mensaje_bienvenida="Hola",
                mensaje_salida="Adios",
                regimen="comun",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.flush()
        session.add(
            Sucursal(
                uuid=uuid_sucursal,
                uuid_empresa=empresa_uuid,
                uuid_tipo_sucursal=None,
                nombre=f"Sucursal MV {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"M{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle MV 1",
                telefono="+571234567",
                horario="24/7",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()


async def _seed_tipo_vehiculo(pg_engine, *, uuid_tipo: uuid_lib.UUID, tipo: str) -> None:
    """Insert one vigente ``tipos_vehiculo`` row."""
    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo

    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            TiposVehiculo(
                uuid=uuid_tipo,
                tipo=tipo,
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()


async def _seed_ingreso(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
) -> uuid_lib.UUID:
    """Insert one ``prod.ingreso`` row. Return its UUID."""
    from parkos_core.models.L_E.ingreso import Ingreso

    now = _now_naive()
    ingreso_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Ingreso(
                uuid=ingreso_uuid,
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_vehiculo,
                placa=f"MV{ingreso_uuid.hex[:6]}",
                uuid_subscripcion_cliente=None,
                fecha_ingreso=now,
                observaciones=None,
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return ingreso_uuid


async def _seed_salida(
    pg_dsn: str,
    *,
    uuid_ingreso: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
) -> None:
    """Insert one ``prod.salidas`` row matching ``uuid_ingreso``."""
    import psycopg

    sql = """
    INSERT INTO prod.salidas
        (uuid, fecha_retencion_hasta, uuid_sucursal, uuid_ingreso,
         fecha_salida, created_at, created_by)
    VALUES (gen_random_uuid(), '2026-09-30', %(sucursal)s, %(ingreso)s, NOW(),
            NOW(), NULL);
    """
    # NOTE: ``fecha_retencion_hasta`` must fall within the current
    # monthly partition (e.g. ``salidas_p_current`` covers Sept 2026
    # in our test DB). Use a date inside the partition so the INSERT
    # lands. The MV filter only checks that the matching ``salidas``
    # row EXISTS, so the exact date is irrelevant to the test.
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            sql, {"sucursal": str(uuid_sucursal), "ingreso": str(uuid_ingreso)}
        )
        conn.commit()


# ---------------------------------------------------------------------------
# T1 -- insert_ingreso_then_refresh
# ---------------------------------------------------------------------------


async def test_insert_ingreso_then_refresh_view_includes_row(
    pg_engine, pg_dsn: str
) -> None:
    """After inserting one ingreso and refreshing the MV, the repo
    helper reports the row with ``activos == 1``, ``cupo_maximo == 0``
    (no cvs row seeded) and ``disponible == -1`` (KD-6 valid)."""
    await _drop_mv(pg_dsn)
    await _truncate_sources(pg_dsn)
    await _setup_view(pg_dsn)

    uuid_sucursal = uuid_lib.uuid4()
    uuid_tipo = uuid_lib.uuid4()

    await _seed_empresa_sucursal(pg_engine, uuid_sucursal=uuid_sucursal)
    await _seed_tipo_vehiculo(pg_engine, uuid_tipo=uuid_tipo, tipo="Auto")
    await _seed_ingreso(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        uuid_tipo_vehiculo=uuid_tipo,
    )

    # Refresh the view.
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await session.execute(
            text("REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria")
        )
        await session.commit()

    # Call the repo helper and assert.
    from parkos_core.repo.ocupacion import get_ocupacion_puros_activos

    async with Session() as session:
        rows = await get_ocupacion_puros_activos(
            session, uuid_sucursal=uuid_sucursal
        )

    assert len(rows) == 1, (
        f"breakdown MUST contain exactly one row for the seeded ingreso; "
        f"got {rows!r}"
    )
    row = rows[0]
    assert row.uuid_tipo_vehiculo == uuid_tipo
    assert row.tipo == "Auto"
    assert row.cupo_maximo == 0, (
        f"cupo_maximo MUST be 0 (no cvs row seeded, KD-6 COALESCE); "
        f"got {row.cupo_maximo}"
    )
    assert row.activos == 1
    assert row.disponible == -1, (
        f"disponible MUST be -1 (cupo_maximo 0 - activos 1); got {row.disponible}"
    )

    await _drop_mv(pg_dsn)
    await _truncate_sources(pg_dsn)


# ---------------------------------------------------------------------------
# T2 -- insert_salida_decrements
# ---------------------------------------------------------------------------


async def test_insert_salida_then_refresh_view_decrements_activos(
    pg_engine, pg_dsn: str
) -> None:
    """After inserting an ingreso + a matching ``salidas`` row and
    refreshing, the MV no longer reports the ingreso as active -- the
    breakdown for ``(X, T)`` contains the seeded ``tipos_vehiculo``
    row with ``activos == 0`` (the inner row is excluded by the MV's
    ``NOT EXISTS`` clause on ``salidas``)."""
    await _drop_mv(pg_dsn)
    await _truncate_sources(pg_dsn)
    await _setup_view(pg_dsn)

    uuid_sucursal = uuid_lib.uuid4()
    uuid_tipo = uuid_lib.uuid4()

    await _seed_empresa_sucursal(pg_engine, uuid_sucursal=uuid_sucursal)
    await _seed_tipo_vehiculo(pg_engine, uuid_tipo=uuid_tipo, tipo="Moto")
    ingreso_uuid = await _seed_ingreso(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        uuid_tipo_vehiculo=uuid_tipo,
    )
    await _seed_salida(
        pg_dsn,
        uuid_ingreso=ingreso_uuid,
        uuid_sucursal=uuid_sucursal,
    )

    # Refresh the view (plain -- not CONCURRENTLY; we just changed data).
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await session.execute(
            text("REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria")
        )
        await session.commit()

    from parkos_core.repo.ocupacion import get_ocupacion_puros_activos

    async with Session() as session:
        rows = await get_ocupacion_puros_activos(
            session, uuid_sucursal=uuid_sucursal
        )

    assert len(rows) == 1, (
        f"breakdown MUST contain exactly one row for the seeded tipo; "
        f"got {rows!r}"
    )
    row = rows[0]
    assert row.uuid_tipo_vehiculo == uuid_tipo
    assert row.tipo == "Moto"
    assert row.activos == 0, (
        f"ingreso with matching salida MUST be excluded from the MV; "
        f"expected activos=0, got {row.activos}"
    )

    await _drop_mv(pg_dsn)
    await _truncate_sources(pg_dsn)


__all__ = [
    "test_insert_ingreso_then_refresh_view_includes_row",
    "test_insert_salida_then_refresh_view_decrements_activos",
]
