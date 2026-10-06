"""FE always-on emission against a REAL Postgres (``repo/fe_emision.py``).

Covers what the unit doubles cannot: the real numbering lock + UK, the
SAVEPOINT, the pending marker + admin alert rows, the automatic retry, and
consecutivo idempotency. Each test uses its own random ``uuid_sucursal`` and
never truncates anything (safe on a shared DB).

Skipped under default pytest like its siblings; run with
``PARKOS_DOCKER_TEST=1`` + ``DATABASE_URL`` (asyncpg) pointing at a DISPOSABLE
DB already migrated to head, or without the flag plus
``TEST_PG_IMAGE=parkos-postgres:16-pgpartman`` (testcontainers).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from parkos_core.constants import CLIENTE_ESTANDAR_UUID
from parkos_core.models.L_E.factura_electronica import FacturaElectronica
from parkos_core.models.L_W.alerta import Alerta
from parkos_core.models.L_W.envio_dian import EnvioDian
from parkos_core.models.V.clientes import Clientes
from parkos_core.models.V.resolucion_facturacion import ResolucionFacturacion
from parkos_core.repo import factura as repo_factura
from parkos_core.repo.fe_emision import (
    ALERTA_FALLIDA,
    ALERTA_PENDIENTE,
    MAX_REINTENTOS,
    FeRetryScheduler,
    emitir_fe_para_pago,
    reintentar_pendientes,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

# No FK-valid operator exists in a bare DB; created_by / alerta.uuid_usuario are nullable.
ACTOR = None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _sucursal(Session) -> uuid_lib.UUID:  # noqa: N803
    """Insert a fresh empresa + sucursal (real FKs); returns the sucursal uuid."""
    from parkos_core.models.V.empresa import Empresa
    from parkos_core.models.V.sucursal import Sucursal

    suc = uuid_lib.uuid4()
    async with Session() as s:
        # empresa is a singleton (empresa_singleton_uk): reuse the seeded one.
        empresa = (
            await s.execute(select(Empresa.uuid).where(Empresa.vigente_hasta.is_(None)))
        ).scalars().first()
        s.add(
            Sucursal(
                uuid=suc, uuid_empresa=empresa, uuid_tipo_sucursal=None,
                nombre=f"Suc FE {suc.hex[:6]}", prefijo_nombre=f"FE{suc.hex[:4]}",
                ciudad="Ciudad", direccion="Calle 1", telefono="+57111", horario="24/7",
                vigente_desde=_now(), vigente_hasta=None, estado="activo",
                created_at=_now(), created_by=None, sync_status="sincronizado",
                sync_timestamp=None, sync_attempts=0,
            )
        )
        await s.commit()
    return suc


async def _resolucion(session, sucursal, *, desde=1, hasta=1000, prefijo="SETP"):
    row = ResolucionFacturacion(
        uuid=uuid_lib.uuid4(),
        uuid_sucursal=sucursal,
        numero_resolucion=f"R-{uuid_lib.uuid4().hex[:10]}",
        prefijo=prefijo,
        rango_desde=desde,
        rango_hasta=hasta,
        vigente_desde=_now(),
        vigente_hasta=None,
        estado="activo",
        created_at=_now(),
        created_by=None,
        sync_status="sincronizado",
        sync_attempts=0,
    )
    session.add(row)
    await session.commit()
    return row


async def _factura(session, sucursal):
    f = await repo_factura.crear_factura_evento(
        session,
        actor_uuid=ACTOR,
        new_attrs={
            "uuid_sucursal": sucursal,
            "subtotal": Decimal("1000"),
            "descuento": Decimal("0"),
            "total": Decimal("1190"),
        },
    )
    await session.commit()
    return f.uuid


@pytest.fixture
def Session(pg_engine):  # noqa: N802
    return async_sessionmaker(pg_engine, expire_on_commit=False)


async def _fes(session, sucursal):
    return (
        (
            await session.execute(
                select(FacturaElectronica)
                .where(FacturaElectronica.uuid_sucursal == sucursal)
                .order_by(FacturaElectronica.consecutivo)
            )
        )
        .scalars()
        .all()
    )


async def _alertas(session, sucursal, tipo):
    return (
        (
            await session.execute(
                select(Alerta).where(
                    Alerta.uuid_sucursal == sucursal, Alerta.tipo_alerta == tipo
                )
            )
        )
        .scalars()
        .all()
    )


async def test_cliente_estandar_existe_tras_migrar(Session) -> None:
    async with Session() as s:
        row = (
            await s.execute(select(Clientes).where(Clientes.uuid == CLIENTE_ESTANDAR_UUID))
        ).scalar_one()
    assert row.numero_identificacion == "222222222222"
    assert row.vigente_hasta is None and row.estado == "activo"


async def test_sin_cliente_emite_con_estandar_y_envio_pendiente(Session) -> None:
    suc = await _sucursal(Session)
    async with Session() as s:
        res_row = await _resolucion(s, suc, desde=500)
        fac = await _factura(s, suc)
        res = await emitir_fe_para_pago(s, actor_uuid=ACTOR, uuid_factura=fac)
        assert res.emitida and res.error is None
        fes = await _fes(s, suc)
        assert len(fes) == 1
        assert fes[0].uuid_cliente == CLIENTE_ESTANDAR_UUID
        assert fes[0].consecutivo == 500
        assert fes[0].uuid_resolucion_facturacion == res_row.uuid
        envios = (
            (await s.execute(select(EnvioDian).where(EnvioDian.uuid_sucursal == suc)))
            .scalars()
            .all()
        )
        assert [e.estado for e in envios] == ["pendiente"]


async def test_con_datos_de_cliente_usa_ese_cliente(Session) -> None:
    suc = await _sucursal(Session)
    cliente = uuid_lib.uuid4()
    async with Session() as s:
        s.add(
            Clientes(
                uuid=cliente, tipo_identificador="NIT", numero_identificacion=f"8{cliente.int % 10**8}",
                nombre="Cliente FE", vigente_desde=_now(), vigente_hasta=None, estado="activo",
                created_at=_now(), created_by=None, sync_status="sincronizado", sync_attempts=0,
            )
        )
        await s.commit()
        await _resolucion(s, suc)
        fac = await _factura(s, suc)
        await emitir_fe_para_pago(s, actor_uuid=ACTOR, uuid_factura=fac, uuid_cliente=cliente)
        assert (await _fes(s, suc))[0].uuid_cliente == cliente


async def test_reemision_idempotente_no_consume_consecutivo(Session) -> None:
    suc = await _sucursal(Session)
    async with Session() as s:
        await _resolucion(s, suc, desde=10)
        f1 = await _factura(s, suc)
        f2 = await _factura(s, suc)
        a = await emitir_fe_para_pago(s, actor_uuid=ACTOR, uuid_factura=f1)
        a2 = await emitir_fe_para_pago(s, actor_uuid=ACTOR, uuid_factura=f1)
        b = await emitir_fe_para_pago(s, actor_uuid=ACTOR, uuid_factura=f2)
        assert a.uuid_factura_electronica == a2.uuid_factura_electronica
        assert [fe.consecutivo for fe in await _fes(s, suc)] == [10, 11]
        assert b.emitida


async def test_fallo_deja_pendiente_y_el_reintento_emite_sin_duplicar(Session) -> None:
    suc = await _sucursal(Session)
    async with Session() as s:
        fac = await _factura(s, suc)  # payment done, NO resolution yet
        res = await emitir_fe_para_pago(s, actor_uuid=ACTOR, uuid_factura=fac)
        assert res.error == "resolucion_facturacion_no_encontrada" and res.pendiente
        assert await _fes(s, suc) == []
        marcadores = await _alertas(s, suc, ALERTA_PENDIENTE)
        assert len(marcadores) == 1
        assert marcadores[0].datos_nuevos["uuid_factura"] == str(fac)

        # a second failed attempt must not stack markers
        await emitir_fe_para_pago(s, actor_uuid=ACTOR, uuid_factura=fac)
        assert len(await _alertas(s, suc, ALERTA_PENDIENTE)) == 1

        await _resolucion(s, suc, desde=7)  # operator configures the resolution
        sched = FeRetryScheduler()
        cont = await reintentar_pendientes(s, uuid_sucursal=suc, scheduler=sched)
        assert cont["emitidas"] == 1 and cont["alertas"] == 0
        fes = await _fes(s, suc)
        assert [fe.consecutivo for fe in fes] == [7]
        assert fes[0].uuid_factura == fac

        # nothing left pending: a later scan emits nothing and alerts nothing
        sched2 = FeRetryScheduler()
        cont2 = await reintentar_pendientes(s, uuid_sucursal=suc, scheduler=sched2)
        assert cont2 == {"emitidas": 0, "fallidas": 0, "alertas": 0}
        assert len(await _fes(s, suc)) == 1
        assert await _alertas(s, suc, ALERTA_FALLIDA) == []


async def test_numeracion_agotada_reintenta_acotado_y_alerta_una_vez(Session) -> None:
    suc = await _sucursal(Session)
    async with Session() as s:
        await _resolucion(s, suc, desde=1, hasta=1)
        f1 = await _factura(s, suc)
        f2 = await _factura(s, suc)
        assert (await emitir_fe_para_pago(s, actor_uuid=ACTOR, uuid_factura=f1)).emitida
        res = await emitir_fe_para_pago(s, actor_uuid=ACTOR, uuid_factura=f2)
        assert res.error == "numeracion_agotada" and res.pendiente

        t = [1000.0]
        sched = FeRetryScheduler(clock=lambda: t[0])
        total = {"fallidas": 0, "alertas": 0}
        for _ in range(MAX_REINTENTOS + 2):
            t[0] += 100_000
            c = await reintentar_pendientes(s, uuid_sucursal=suc, scheduler=sched)
            total["fallidas"] += c["fallidas"]
            total["alertas"] += c["alertas"]

        assert total == {"fallidas": MAX_REINTENTOS, "alertas": 1}
        alertas = await _alertas(s, suc, ALERTA_FALLIDA)
        assert len(alertas) == 1
        assert alertas[0].estado == "abierta"
        assert alertas[0].datos_nuevos["uuid_factura"] == str(f2)
        # the payment/invoice rows survive and only ONE FE number was consumed
        assert [fe.consecutivo for fe in await _fes(s, suc)] == [1]
        n = (
            await s.execute(
                select(func.count()).select_from(FacturaElectronica).where(
                    FacturaElectronica.uuid_factura == f2
                )
            )
        ).scalar_one()
        assert n == 0


async def test_pendiente_expirado_alerta_sin_reintentar(Session) -> None:
    suc = await _sucursal(Session)
    async with Session() as s:
        fac = await _factura(s, suc)
        await emitir_fe_para_pago(s, actor_uuid=ACTOR, uuid_factura=fac)
        await _resolucion(s, suc)  # would succeed, but the marker is too old
        future = _now() + timedelta(hours=25)
        cont = await reintentar_pendientes(
            s, uuid_sucursal=suc, scheduler=FeRetryScheduler(), now=future
        )
        assert cont["alertas"] == 1 and cont["emitidas"] == 0
        assert len(await _alertas(s, suc, ALERTA_FALLIDA)) == 1
