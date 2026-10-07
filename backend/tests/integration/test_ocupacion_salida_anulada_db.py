"""D1 / migracion 0091: la ocupacion cuenta como DENTRO la placa cuya salida se anulo.

DB-backed (testcontainers, migraciones hasta head). La vista materializada
``prod.mv_ocupacion_diaria`` usaba ``NOT EXISTS (salidas)`` y excluia el ingreso
ante cualquier anulacion ``tipo_anulable='salida'`` (que el repo guarda con
``uuid_ingreso``): tras compensar la salida el cupo seguia en 0 aunque la placa
estaba dentro. Misma regla que ``repo/ingreso_activo.py::salida_vigente_exists_sql``.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.integration.test_mv_ocupacion_diaria_db import (
    _seed_empresa_sucursal,
    _seed_ingreso,
    _seed_tipo_vehiculo,
    _truncate_sources,
)

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "packages/parkos_core/migrations/versions"
    / "0091_mv_ocupacion_salida_anulada.py"
)


def _insert_salida(pg_dsn: str, sucursal, ingreso) -> uuid_lib.UUID:
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


async def _anular(pg_engine, sucursal, *, tipo, ingreso=None, salida=None, estado="ejecutada"):
    from parkos_core.models.L_W.anulaciones import Anulaciones

    now = datetime.now(UTC).replace(tzinfo=None)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        session.add(
            Anulaciones(
                uuid=uuid_lib.uuid4(),
                fecha_retencion_hasta=now.date(),
                uuid_sucursal=sucursal,
                tipo_anulable=tipo,
                uuid_ingreso=ingreso,
                uuid_salida=salida,
                uuid_usuario=None,
                motivo="test ocupacion salida anulada",
                uuid_anulacion_padre=None,
                timestamp_evento=now,
                vigente_desde=now,
                vigente_hasta=None,
                estado=estado,
            )
        )
        await session.commit()


async def _activos(pg_engine, sucursal) -> int:
    from parkos_core.repo.ocupacion import get_ocupacion_puros_activos

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await session.execute(text("SELECT prod.refresh_mv_ocupacion_diaria()"))
        await session.commit()
    async with Session() as session:
        rows = await get_ocupacion_puros_activos(session, uuid_sucursal=sucursal)
    return sum(r.activos for r in rows)


async def _seed(pg_engine, pg_dsn):
    await _truncate_sources(pg_dsn)
    sucursal, tipo = uuid_lib.uuid4(), uuid_lib.uuid4()
    await _seed_empresa_sucursal(pg_engine, uuid_sucursal=sucursal)
    await _seed_tipo_vehiculo(pg_engine, uuid_tipo=tipo, tipo="carro")
    ingreso = await _seed_ingreso(pg_engine, uuid_sucursal=sucursal, uuid_tipo_vehiculo=tipo)
    return sucursal, ingreso


async def test_ingreso_sin_salida_cuenta_dentro(pg_engine, alembic_upgrade, pg_dsn) -> None:
    sucursal, _ = await _seed(pg_engine, pg_dsn)
    assert await _activos(pg_engine, sucursal) == 1


async def test_salida_vigente_descuenta(pg_engine, alembic_upgrade, pg_dsn) -> None:
    sucursal, ingreso = await _seed(pg_engine, pg_dsn)
    _insert_salida(pg_dsn, sucursal, ingreso)
    assert await _activos(pg_engine, sucursal) == 0


async def test_salida_anulada_vuelve_a_contar_como_dentro(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    sucursal, ingreso = await _seed(pg_engine, pg_dsn)
    salida = _insert_salida(pg_dsn, sucursal, ingreso)
    await _anular(pg_engine, sucursal, tipo="salida", ingreso=ingreso, salida=salida)
    assert await _activos(pg_engine, sucursal) == 1


@pytest.mark.parametrize("estado", ["pendiente", "rechazada"])
async def test_anulacion_no_ejecutada_no_reabre(
    pg_engine, alembic_upgrade, pg_dsn, estado: str
) -> None:
    sucursal, ingreso = await _seed(pg_engine, pg_dsn)
    salida = _insert_salida(pg_dsn, sucursal, ingreso)
    await _anular(
        pg_engine, sucursal, tipo="salida", ingreso=ingreso, salida=salida, estado=estado
    )
    assert await _activos(pg_engine, sucursal) == 0


async def test_ingreso_anulado_no_cuenta(pg_engine, alembic_upgrade, pg_dsn) -> None:
    sucursal, ingreso = await _seed(pg_engine, pg_dsn)
    await _anular(pg_engine, sucursal, tipo="ingreso", ingreso=ingreso)
    assert await _activos(pg_engine, sucursal) == 0


def test_migracion_0091_metadata_y_rollback() -> None:
    src = _MIGRATION.read_text(encoding="utf-8")
    assert 'down_revision = "0090_cotizar_ignora_salida_anulada"' in src
    upgrade, downgrade = src.split("def downgrade()")
    assert "a.uuid_salida = s.uuid" in upgrade
    assert "a.uuid_salida = s.uuid" not in downgrade
    for fragment in ("uq_mv_ocupacion_diaria_sucursal_tipo", "GRANT SELECT"):
        assert fragment in src  # constantes de modulo
    for call in ("op.execute(_INDEX)", "op.execute(_GRANT)"):
        assert call in upgrade and call in downgrade
