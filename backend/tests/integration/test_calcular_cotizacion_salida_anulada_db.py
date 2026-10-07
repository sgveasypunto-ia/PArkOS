"""prod.calcular_cotizacion ignora salidas anuladas (migracion 0090), DB-backed.

Un ingreso con una salida cuya anulacion esta ``ejecutada`` vuelve a estar
abierto (misma regla que ``repo/ingreso_activo.py::salida_vigente_exists_sql``)
y debe poder cotizarse. Una anulacion en otro estado NO lo reabre.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.integration.test_calcular_cotizacion_db import (
    _seed_minimal_happy_path,
    _truncate_tables,
)

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "packages/parkos_core/migrations/versions"
    / "0090_cotizar_ignora_salida_anulada.py"
)


def _insert_salida(pg_dsn: str, sucursal: uuid_lib.UUID, ingreso: uuid_lib.UUID) -> uuid_lib.UUID:
    import psycopg

    salida = uuid_lib.uuid4()
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO prod.salidas (uuid, fecha_retencion_hasta, uuid_sucursal, "
            "uuid_ingreso, fecha_salida, created_at, created_by) "
            "VALUES (%s, CURRENT_DATE + 365, %s, %s, NOW(), NOW(), NULL)",
            (str(salida), str(sucursal), str(ingreso)),
        )
        conn.commit()
    return salida


async def _insert_anulacion(
    pg_engine, sucursal: uuid_lib.UUID, salida: uuid_lib.UUID, estado: str
) -> None:
    from parkos_core.models.L_W.anulaciones import Anulaciones

    now = datetime.now(UTC).replace(tzinfo=None)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        session.add(
            Anulaciones(
                uuid=uuid_lib.uuid4(),
                fecha_retencion_hasta=now.date(),
                uuid_sucursal=sucursal,
                tipo_anulable="salida",
                uuid_ingreso=None,
                uuid_salida=salida,
                uuid_usuario=None,
                motivo="test cotizar salida anulada",
                uuid_anulacion_padre=None,
                timestamp_evento=now,
                vigente_desde=now,
                vigente_hasta=None,
                estado=estado,
            )
        )
        await session.commit()


async def _cotizar(pg_engine, ingreso: uuid_lib.UUID) -> dict:
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        return (
            await session.execute(
                text("SELECT prod.calcular_cotizacion(:u) AS p"), {"u": str(ingreso)}
            )
        ).scalar_one()


async def _seed(pg_engine, pg_dsn):
    await _truncate_tables(pg_dsn)
    sucursal = uuid_lib.uuid4()
    ingreso = await _seed_minimal_happy_path(
        pg_engine,
        uuid_sucursal=sucursal,
        uuid_tipo_vehiculo=uuid_lib.uuid4(),
        uuid_tipo_tarifa=uuid_lib.uuid4(),
        minutos_en_estacionamiento=30,
    )
    return sucursal, ingreso


async def test_ingreso_con_salida_viva_no_se_cotiza(pg_engine, alembic_upgrade, pg_dsn) -> None:
    sucursal, ingreso = await _seed(pg_engine, pg_dsn)
    _insert_salida(pg_dsn, sucursal, ingreso)
    assert await _cotizar(pg_engine, ingreso) == {"error": "ingreso_no_encontrado"}


async def test_ingreso_con_salida_anulada_ejecutada_se_cotiza(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    sucursal, ingreso = await _seed(pg_engine, pg_dsn)
    salida = _insert_salida(pg_dsn, sucursal, ingreso)
    await _insert_anulacion(pg_engine, sucursal, salida, "ejecutada")
    payload = await _cotizar(pg_engine, ingreso)
    assert "error" not in payload
    assert payload["cobrar"] is True


@pytest.mark.parametrize("estado", ["pendiente", "rechazada"])
async def test_anulacion_no_ejecutada_no_reabre_el_ingreso(
    pg_engine, alembic_upgrade, pg_dsn, estado: str
) -> None:
    sucursal, ingreso = await _seed(pg_engine, pg_dsn)
    salida = _insert_salida(pg_dsn, sucursal, ingreso)
    await _insert_anulacion(pg_engine, sucursal, salida, estado)
    assert await _cotizar(pg_engine, ingreso) == {"error": "ingreso_no_encontrado"}


def test_migracion_0090_usa_predicado_de_anulacion_en_upgrade() -> None:
    """Chequeo estatico (sin Docker): upgrade lleva el predicado; downgrade (0050) no."""
    src = _MIGRATION.read_text(encoding="utf-8")
    upgrade, downgrade = src.split("def downgrade()")
    for needle in ("prod.anulaciones a", "a.uuid_salida = s.uuid",
                   "a.tipo_anulable = 'salida'", "a.estado = 'ejecutada'"):
        assert needle in upgrade
        assert needle not in downgrade


def test_migracion_0090_cubre_tiene_salida_y_conteo_de_otras_placas() -> None:
    upgrade, downgrade = _MIGRATION.read_text(encoding="utf-8").split("def downgrade()")
    assert upgrade.count("a.estado = 'ejecutada'") == 2
    assert downgrade.count("a.estado = 'ejecutada'") == 0
