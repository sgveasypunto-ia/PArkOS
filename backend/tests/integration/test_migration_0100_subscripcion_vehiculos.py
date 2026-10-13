"""Migration 0100 (bug #18) -- repair + estado/vigencia invariant on subscripcion_vehiculos."""

from __future__ import annotations

import importlib.util
import uuid as uuid_lib
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

MIG = (
    Path(__file__).resolve().parents[2]
    / "packages/parkos_core/migrations/versions/0100_subscripcion_vehiculos_estado_vigencia.py"
)
CHECK = "ck_subscripcion_vehiculos_estado_vigencia"


def _repair_sql() -> str:
    spec = importlib.util.spec_from_file_location("mig0100", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.REPAIR_SQL






@pytest.fixture
async def par(pg_engine):
    from datetime import timedelta

    from parkos_core.models.V.clientes import Clientes
    from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente
    from parkos_core.models.V.sucursal import Sucursal
    from parkos_core.models.V.tipo_subscripciones import TipoSubscripciones
    from parkos_core.models.V.vehiculos import Vehiculos
    from parkos_core.runtime.tiempo import hoy_bogota
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from tests.conftest import VFixtureFactory

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        suc = VFixtureFactory.build(Sucursal, nombre="M100", prefijo_nombre="M10")
        cli = VFixtureFactory.build(
            Clientes, numero_identificacion=uuid_lib.uuid4().hex[:10], nombre="Ada"
        )
        plan = VFixtureFactory.build(
            TipoSubscripciones,
            tipo=f"m100-{uuid_lib.uuid4().hex[:6]}",
            valor=1000,
            duracion_dias=30,
            cantidad_maxima_vehiculos=3,
            mismo_tipo_vehiculo=False,
            uuid_tipo_vehiculo=None,
        )
        veh = VFixtureFactory.build(Vehiculos, placa=f"M{uuid_lib.uuid4().hex[:5].upper()}")
        s.add_all([suc, cli, plan, veh])
        await s.flush()
        sub = VFixtureFactory.build(
            SubscripcionesCliente,
            uuid_cliente=cli.uuid,
            uuid_sucursal=suc.uuid,
            uuid_tipo_subscripcion=plan.uuid,
            fecha_inicio_cobertura=hoy_bogota() - timedelta(days=1),
            fecha_vencimiento=hoy_bogota() + timedelta(days=20),
        )
        s.add(sub)
        await s.commit()
        return sub.uuid, veh.uuid


async def _insert(conn, sub, veh, *, estado, hasta):
    await conn.execute(
        text(
            "INSERT INTO prod.subscripcion_vehiculos "
            "(uuid, uuid_subscripcion_cliente, uuid_vehiculo, vigente_desde, vigente_hasta, "
            " estado, created_at, created_by) "
            "VALUES (:u, :s, :v, now() - (:off || ' seconds')::interval, "
            " CASE WHEN :h THEN now() END, :e, now(), :u)"
        ),
        {"u": uuid_lib.uuid4(), "s": sub, "v": veh, "e": estado, "h": hasta,
         "off": str(uuid_lib.uuid4().int % 100000 + 10)},
    )


async def test_check_rechaza_fila_abierta_inactiva_y_cerrada_activa(pg_engine, par) -> None:
    sub, veh = par
    for estado, hasta in (("inactivo", False), ("activo", True)):
        async with pg_engine.connect() as conn:
            trans = await conn.begin()
            try:
                with pytest.raises(IntegrityError):
                    await _insert(conn, sub, veh, estado=estado, hasta=hasta)
            finally:
                await trans.rollback()


async def test_indice_unico_rechaza_dos_abiertas_activas(pg_engine, par) -> None:
    sub, veh = par
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _insert(conn, sub, veh, estado="activo", hasta=False)
            with pytest.raises(IntegrityError):
                await _insert(conn, sub, veh, estado="activo", hasta=False)
        finally:
            await trans.rollback()


async def test_reparacion_cierra_fantasmas_sin_borrar_ni_tocar_estado(pg_engine, par) -> None:
    sub, veh = par
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        try:
            # Estado pre-0100: sin el CHECK (DDL transaccional) hay un fantasma.
            await conn.execute(
                text(f"ALTER TABLE prod.subscripcion_vehiculos DROP CONSTRAINT {CHECK}")
            )
            await _insert(conn, sub, veh, estado="inactivo", hasta=False)
            antes = (
                await conn.execute(
                    text("SELECT count(*) FROM prod.subscripcion_vehiculos "
                         "WHERE uuid_subscripcion_cliente=:s"), {"s": sub})
            ).scalar_one()
            await conn.execute(text(_repair_sql()))
            await conn.execute(text(_repair_sql()))  # idempotente
            filas = (
                await conn.execute(
                    text("SELECT estado, vigente_hasta, vigente_desde "
                         "FROM prod.subscripcion_vehiculos WHERE uuid_subscripcion_cliente=:s"),
                    {"s": sub},
                )
            ).all()
            assert len(filas) == antes == 1
            estado, hasta, desde = filas[0]
            assert estado == "inactivo"
            assert hasta == desde
            # y la invariante vuelve a poder validarse
            await conn.execute(
                text(f"ALTER TABLE prod.subscripcion_vehiculos ADD CONSTRAINT {CHECK} "
                     "CHECK ((estado = 'inactivo') = (vigente_hasta IS NOT NULL))")
            )
        finally:
            await trans.rollback()
