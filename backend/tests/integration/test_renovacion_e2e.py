"""PT-3 -- subscription renewal, end to end over real HTTP against Postgres.

Drives ``POST /api/v1/clientes/subscripciones/{uuid}/renovar`` and
``GET /api/v1/clientes/subscripciones/proximas-vencer`` through the ASGI app
(``client`` fixture) with real migrations, plus repo-level checks with an
injected ``hoy`` for the calendar edge cases (month end, leap year).

Dates are built relative to the real Bogota "today" so the HTTP tests do not
depend on a frozen clock.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from parkos_core.models.A.factura_pagos import FacturaPagos
from parkos_core.models.A.log_transaccional import LogTransaccional
from parkos_core.models.L_E.facturas import Facturas
from parkos_core.models.V.clientes import Clientes
from parkos_core.models.V.permisos import Permisos
from parkos_core.models.V.permisos_usuario import PermisosUsuario
from parkos_core.models.V.resolucion_facturacion import ResolucionFacturacion
from parkos_core.models.V.subscripcion_vehiculos import SubscripcionVehiculos
from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.tipo_subscripciones import TipoSubscripciones
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.models.V.vehiculos import Vehiculos
from parkos_core.repo import renovacion as repo_renovacion
from parkos_core.runtime.tiempo import hoy_bogota
from tests.conftest import VFixtureFactory

BASE = "/api/v1/clientes"


def _now() -> datetime:
    return datetime.utcnow()


class Mundo:
    """Rows seeded for one test (one branch, one plan, one customer)."""

    def __init__(self) -> None:
        self.sucursal = uuid_lib.uuid4()
        self.actor = uuid_lib.uuid4()
        self.plan: uuid_lib.UUID
        self.cliente: uuid_lib.UUID


async def _sembrar_base(
    pg_engine, *, con_permiso: bool = True, con_resolucion: bool = False,
    dias_plan: int = 30, valor: str = "100000", max_veh: int = 2,
) -> Mundo:
    m = Mundo()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        s.add(VFixtureFactory.build(Sucursal, uuid=m.sucursal))
        s.add(
            VFixtureFactory.build(
                Usuarios,
                uuid=m.actor,
                email=f"{m.actor}@example.com",
                password_hash="x",
                rol="operador",
            )
        )
        plan = VFixtureFactory.build(
            TipoSubscripciones,
            tipo=f"plan-{uuid_lib.uuid4().hex[:8]}",
            valor=Decimal(valor),
            duracion_dias=dias_plan,
            cantidad_maxima_vehiculos=max_veh,
            mismo_tipo_vehiculo=False,
        )
        cliente = VFixtureFactory.build(
            Clientes,
            tipo_identificador="CC",
            numero_identificacion=f"id-{uuid_lib.uuid4().hex[:10]}",
            nombre="Ada",
            apellido="Prueba",
        )
        s.add_all([plan, cliente])
        m.plan, m.cliente = plan.uuid, cliente.uuid
        if con_permiso:
            permiso = (
                await s.execute(
                    select(Permisos).where(
                        Permisos.permiso == "gestionar_clientes", Permisos.vigente_hasta.is_(None)
                    )
                )
            ).scalars().first()
            await s.flush()
            s.add(PermisosUsuario(uuid_usuario=m.actor, uuid_permiso=permiso.uuid))
        if con_resolucion:
            s.add(
                ResolucionFacturacion(
                    uuid=uuid_lib.uuid4(),
                    uuid_sucursal=m.sucursal,
                    numero_resolucion=f"RES-{uuid_lib.uuid4().hex[:8]}",
                    prefijo="SETP",
                    rango_desde=1,
                    rango_hasta=999999999,
                    fecha_resolucion=date.today(),
                    fecha_inicio_vigencia=date.today(),
                    fecha_fin_vigencia=None,
                    vigente_desde=_now(),
                    vigente_hasta=None,
                    estado="activo",
                    created_at=_now(),
                    created_by=None,
                    sync_status="pendiente",
                    sync_timestamp=None,
                    sync_attempts=0,
                )
            )
        await s.commit()
    return m


async def _sembrar_suscripcion(
    pg_engine, m: Mundo, *, vencimiento: date, placas: tuple[str, ...] = ("AAA111", "BBB222"),
    dias: int = 30, cliente: uuid_lib.UUID | None = None, plan: uuid_lib.UUID | None = None,
    alerta: int | None = None,
) -> uuid_lib.UUID:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        sub = VFixtureFactory.build(
            SubscripcionesCliente,
            uuid_cliente=cliente or m.cliente,
            uuid_sucursal=m.sucursal,
            uuid_tipo_subscripcion=plan or m.plan,
            fecha_inicio_cobertura=vencimiento - timedelta(days=dias - 1),
            fecha_vencimiento=vencimiento,
            dias_alerta_pre_vencimiento=alerta,
        )
        s.add(sub)
        for placa in placas:
            veh = VFixtureFactory.build(Vehiculos, placa=placa)
            s.add(veh)
            await s.flush()
            s.add(
                VFixtureFactory.build(
                    SubscripcionVehiculos,
                    uuid_subscripcion_cliente=sub.uuid,
                    uuid_vehiculo=veh.uuid,
                )
            )
        await s.commit()
        return sub.uuid


def _headers(mint_operador_jwt, m: Mundo, key: str | None = None) -> dict[str, str]:
    h = {"Authorization": f"Bearer {mint_operador_jwt(actor_uuid=m.actor, sucursal_uuid=m.sucursal)}"}
    if key is not None:
        h["Idempotency-Key"] = key
    return h


async def _contar(pg_engine, model, *conds) -> int:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        return (await s.execute(select(func.count()).select_from(model).where(*conds))).scalar_one()


async def _fila(pg_engine, model, uuid):
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        return (await s.execute(select(model).where(model.uuid == uuid))).scalar_one()


def _url(uuid_sub) -> str:
    return f"{BASE}/subscripciones/{uuid_sub}/renovar"


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


async def test_renovacion_anticipada_conserva_placas_cobra_completo_y_emite_fe(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine, con_resolucion=True, dias_plan=30, valor="100000")
    venc = hoy + timedelta(days=5)
    sub = await _sembrar_suscripcion(pg_engine, m, vencimiento=venc)

    r = await client.post(
        _url(sub), json={"medio_pago": "efectivo"},
        headers=_headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}"),
    )
    assert r.status_code == 201, r.text
    body = r.json()

    # dates: starts the day after the previous due date, EXACTLY 30 days
    inicio = venc + timedelta(days=1)
    assert body["fecha_inicio_cobertura"] == inicio.isoformat()
    assert body["fecha_vencimiento"] == (inicio + timedelta(days=29)).isoformat()
    assert body["renovacion_anticipada"] is True
    assert body["uuid_subscripcion_anterior"] == str(sub)
    assert body["uuid_subscripcion"] != str(sub)
    assert sorted(body["placas"]) == ["AAA111", "BBB222"]
    # full price + IVA (0.19 seeded), no proration
    assert Decimal(body["valor_total_plan"]) == Decimal("100000.00")
    assert Decimal(body["total_con_iva"]) == Decimal("119000.00")
    # factura + pago + FE (same mechanism as the venta)
    assert body["uuid_factura"]
    assert body["factura_electronica_error"] is None
    assert body["factura_electronica_pendiente"] is False
    assert body["uuid_factura_electronica"]
    assert body["factura"]["factura_electronica"] is not None

    nueva = uuid_lib.UUID(body["uuid_subscripcion"])
    vieja_row = await _fila(pg_engine, SubscripcionesCliente, sub)
    nueva_row = await _fila(pg_engine, SubscripcionesCliente, nueva)
    # old closed (bi-temporal), new open and active; new row keeps customer/branch
    assert vieja_row.vigente_hasta is not None and vieja_row.estado == "inactivo"
    assert nueva_row.vigente_hasta is None and nueva_row.estado == "activo"
    assert nueva_row.uuid_cliente == m.cliente and nueva_row.uuid_sucursal == m.sucursal

    # plates: old links closed, 2 NEW open links on the new row, none re-entered
    assert await _contar(
        pg_engine, SubscripcionVehiculos,
        SubscripcionVehiculos.uuid_subscripcion_cliente == nueva,
        SubscripcionVehiculos.vigente_hasta.is_(None),
    ) == 2
    assert await _contar(
        pg_engine, SubscripcionVehiculos,
        SubscripcionVehiculos.uuid_subscripcion_cliente == sub,
        SubscripcionVehiculos.vigente_hasta.is_(None),
    ) == 0
    # a plate is never in two OPEN subscriptions of the branch at once
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        dup = (
            await s.execute(
                select(Vehiculos.placa, func.count())
                .join(SubscripcionVehiculos, SubscripcionVehiculos.uuid_vehiculo == Vehiculos.uuid)
                .join(
                    SubscripcionesCliente,
                    SubscripcionesCliente.uuid == SubscripcionVehiculos.uuid_subscripcion_cliente,
                )
                .where(
                    SubscripcionesCliente.uuid_sucursal == m.sucursal,
                    SubscripcionesCliente.vigente_hasta.is_(None),
                    SubscripcionVehiculos.vigente_hasta.is_(None),
                )
                .group_by(Vehiculos.placa)
                .having(func.count() > 1)
            )
        ).all()
        assert dup == []

    # invoice total, payment row and audit row
    factura = await _fila(pg_engine, Facturas, uuid_lib.UUID(body["uuid_factura"]))
    assert Decimal(factura.total) == Decimal("119000.00")
    assert factura.uuid_subscripcion_cliente == nueva
    assert await _contar(
        pg_engine, FacturaPagos, FacturaPagos.uuid_factura == factura.uuid
    ) == 1
    async with Session() as s:
        log = (
            await s.execute(
                select(LogTransaccional).where(
                    LogTransaccional.accion == "renovar",
                    LogTransaccional.uuid_registro_afectado == nueva,
                )
            )
        ).scalar_one()
    assert log.uuid_referencia == sub
    assert log.hash_actual and log.hash_anterior and log.uuid_usuario == m.actor
    assert log.datos_nuevos["fecha_inicio_cobertura"] == inicio.isoformat()
    assert log.datos_nuevos["placas"] == body["placas"]
    assert log.datos_anteriores["fecha_vencimiento"] == venc.isoformat()


async def test_renovacion_vencida_inicia_hoy_bogota(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine, dias_plan=60)
    sub = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy - timedelta(days=12), placas=("CCC333",))

    r = await client.post(
        _url(sub), json={}, headers=_headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}")
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["fecha_inicio_cobertura"] == hoy.isoformat()
    assert body["fecha_vencimiento"] == (hoy + timedelta(days=59)).isoformat()  # exactly 60 days
    assert body["renovacion_anticipada"] is False
    # no resolution configured: payment succeeded, only the FE degrades
    assert body["uuid_factura"] and body["uuid_factura_electronica"] is None
    assert body["factura_electronica_error"] == "resolucion_facturacion_no_encontrada"
    assert body["factura_electronica_pendiente"] is True  # queued for the worker retry
    assert body["factura"]["factura_electronica"] is None
    assert body["factura"]["factura_electronica_pendiente"] is True


async def test_dia_exacto_del_vencimiento_es_anticipada_y_arranca_manana(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine)
    sub = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy, placas=("DDD444",))
    r = await client.post(
        _url(sub), json={}, headers=_headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}")
    )
    assert r.status_code == 201, r.text
    assert r.json()["fecha_inicio_cobertura"] == (hoy + timedelta(days=1)).isoformat()
    assert r.json()["renovacion_anticipada"] is True


async def test_renueva_con_el_precio_vigente_del_plan(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    """The subscription points at a CLOSED plan version; the renewal charges
    the CURRENT version of the same plan (matched by ``tipo``)."""
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine, valor="100000")
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        viejo = (await s.execute(select(TipoSubscripciones).where(TipoSubscripciones.uuid == m.plan))).scalar_one()
        viejo.vigente_hasta, viejo.estado = _now(), "inactivo"
        nuevo = VFixtureFactory.build(
            TipoSubscripciones, tipo=viejo.tipo, valor=Decimal("120000"), duracion_dias=45,
            cantidad_maxima_vehiculos=2, mismo_tipo_vehiculo=False,
        )
        s.add(nuevo)
        await s.commit()
        uuid_nuevo = nuevo.uuid
    sub = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=2), placas=("EEE555",))

    r = await client.post(
        _url(sub), json={}, headers=_headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}")
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert Decimal(body["valor_total_plan"]) == Decimal("120000.00")
    assert body["uuid_tipo_subscripcion"] == str(uuid_nuevo)
    inicio = date.fromisoformat(body["fecha_inicio_cobertura"])
    assert date.fromisoformat(body["fecha_vencimiento"]) == inicio + timedelta(days=44)


# ---------------------------------------------------------------------------
# Idempotency / double renewal
# ---------------------------------------------------------------------------


async def test_misma_idempotency_key_no_duplica_cobro_ni_suscripcion(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine, con_resolucion=True)
    sub = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=4))
    headers = _headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}")

    r1 = await client.post(_url(sub), json={}, headers=headers)
    r2 = await client.post(_url(sub), json={}, headers=headers)
    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201
    assert r2.headers.get("Idempotent-Replay") == "true"
    assert r2.json()["uuid_subscripcion"] == r1.json()["uuid_subscripcion"]
    assert r2.json()["uuid_factura"] == r1.json()["uuid_factura"]
    # the FE uuid is re-read on replay (the stored body predates the FE attempt)
    assert r1.json()["uuid_factura_electronica"]
    assert r2.json()["uuid_factura_electronica"] == r1.json()["uuid_factura_electronica"]
    assert r2.json()["factura"] is not None  # receipt data survives the replay
    # same key with a DIFFERENT body is a conflict, not a second charge
    r3 = await client.post(_url(sub), json={"medio_pago": "tarjeta"}, headers=headers)
    assert r3.status_code == 409
    assert r3.json()["detail"]["error"] == "idempotency_key_conflict"
    assert await _contar(
        pg_engine, SubscripcionesCliente,
        SubscripcionesCliente.uuid_cliente == m.cliente,
        SubscripcionesCliente.vigente_hasta.is_(None),
    ) == 1
    assert await _contar(
        pg_engine, Facturas, Facturas.uuid_sucursal == m.sucursal
    ) == 1


async def test_segunda_renovacion_de_la_misma_fila_con_otra_key_es_409(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine)
    sub = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=4))
    r1 = await client.post(_url(sub), json={}, headers=_headers(mint_operador_jwt, m, key=f"a-{uuid_lib.uuid4()}"))
    r2 = await client.post(_url(sub), json={}, headers=_headers(mint_operador_jwt, m, key=f"b-{uuid_lib.uuid4()}"))
    assert r1.status_code == 201
    assert r2.status_code == 409
    assert r2.json()["detail"]["error"] == "suscripcion_no_renovable"
    assert await _contar(pg_engine, Facturas, Facturas.uuid_sucursal == m.sucursal) == 1


async def test_sin_idempotency_key_es_400(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine)
    sub = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=4))
    r = await client.post(_url(sub), json={}, headers=_headers(mint_operador_jwt, m))
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "idempotency_key_requerido"
    assert await _contar(pg_engine, Facturas, Facturas.uuid_sucursal == m.sucursal) == 0


# ---------------------------------------------------------------------------
# Window, permissions, scoping, plate conflicts
# ---------------------------------------------------------------------------


async def test_ventana_11_dias_rechaza_y_10_dias_permite(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine)
    # vencimiento = hoy + 10 -> 11 days left (today included): rejected
    fuera = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=10), placas=("FFF661",))
    # vencimiento = hoy + 9 -> 10 days left: allowed
    dentro = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=9), placas=("FFF662",))

    r_fuera = await client.post(_url(fuera), json={}, headers=_headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}"))
    assert r_fuera.status_code == 409
    detail = r_fuera.json()["detail"]
    assert detail["error"] == "renovacion_fuera_de_ventana"
    assert detail["dias_restantes"] == 11 and detail["ventana_dias"] == 10
    assert await _contar(pg_engine, Facturas, Facturas.uuid_sucursal == m.sucursal) == 0

    r_dentro = await client.post(_url(dentro), json={}, headers=_headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}"))
    assert r_dentro.status_code == 201, r_dentro.text


async def test_sin_permiso_gestionar_clientes_es_403(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine, con_permiso=False)
    sub = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=3))
    r = await client.post(_url(sub), json={}, headers=_headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}"))
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "permission_denied"
    assert await _contar(pg_engine, Facturas, Facturas.uuid_sucursal == m.sucursal) == 0


async def test_sin_token_es_401(client, alembic_upgrade) -> None:
    r = await client.post(_url(uuid_lib.uuid4()), json={}, headers={"Idempotency-Key": "k"})
    assert r.status_code in (401, 403)


async def test_suscripcion_de_otra_sucursal_es_404(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine)
    otra = await _sembrar_base(pg_engine)
    sub_otra = await _sembrar_suscripcion(pg_engine, otra, vencimiento=hoy + timedelta(days=3), placas=("GGG771",))
    r = await client.post(_url(sub_otra), json={}, headers=_headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}"))
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "subscripcion_no_encontrada"


async def test_placa_en_otra_suscripcion_vigente_es_422(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine)
    sub = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=3), placas=("HHH881",))
    # a DIFFERENT open subscription of the same branch also holds the plate
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        otro_cliente = VFixtureFactory.build(
            Clientes, tipo_identificador="CC", numero_identificacion=f"id-{uuid_lib.uuid4().hex[:10]}"
        )
        s.add(otro_cliente)
        await s.commit()
        otro_cliente_uuid = otro_cliente.uuid
    await _sembrar_suscripcion(
        pg_engine, m, vencimiento=hoy + timedelta(days=20), placas=("HHH881",), cliente=otro_cliente_uuid
    )
    r = await client.post(_url(sub), json={}, headers=_headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}"))
    assert r.status_code == 422
    assert r.json()["detail"] == {"error": "placa_con_suscripcion_vigente", "placa": "HHH881"}
    # nothing was written: the old row is still open
    assert (await _fila(pg_engine, SubscripcionesCliente, sub)).vigente_hasta is None
    assert await _contar(pg_engine, Facturas, Facturas.uuid_sucursal == m.sucursal) == 0


async def test_vehiculo_cerrado_sin_version_abierta_es_422_y_no_escribe(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine)
    sub = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=3), placas=("OOO601",))
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        veh = (await s.execute(select(Vehiculos).where(Vehiculos.placa == "OOO601"))).scalar_one()
        veh.vigente_hasta, veh.estado = _now(), "inactivo"
        await s.commit()
    r = await client.post(_url(sub), json={}, headers=_headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}"))
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "vehiculo_no_resuelto"
    assert (await _fila(pg_engine, SubscripcionesCliente, sub)).vigente_hasta is None
    assert await _contar(pg_engine, Facturas, Facturas.uuid_sucursal == m.sucursal) == 0


async def test_vehiculo_actualizado_se_resuelve_a_la_version_vigente(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    """The link points at a CLOSED vehicle version; the renewal re-points to
    the open version of the same placa."""
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine)
    sub = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=3), placas=("PPP701",))
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        viejo = (await s.execute(select(Vehiculos).where(Vehiculos.placa == "PPP701"))).scalar_one()
        viejo.vigente_hasta, viejo.estado = _now(), "inactivo"
        nuevo = VFixtureFactory.build(Vehiculos, placa="PPP701")
        s.add(nuevo)
        await s.commit()
        uuid_nuevo = nuevo.uuid
    r = await client.post(_url(sub), json={}, headers=_headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}"))
    assert r.status_code == 201, r.text
    assert r.json()["uuid_vehiculos"] == [str(uuid_nuevo)]


async def test_datafono_sin_voucher_es_400_y_no_escribe(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine)
    sub = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=3), placas=("III991",))
    r = await client.post(
        _url(sub), json={"medio_pago": "datafono"},
        headers=_headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}"),
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "voucher_requerido"
    assert (await _fila(pg_engine, SubscripcionesCliente, sub)).vigente_hasta is None


# ---------------------------------------------------------------------------
# Read model + warning feed
# ---------------------------------------------------------------------------


async def test_subscripciones_activas_expone_dias_restantes_y_puede_renovar(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine)
    lejos = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=10), placas=("JJJ101",))
    cerca = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=9), placas=("JJJ102",))
    vencida = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy - timedelta(days=2), placas=("JJJ103",))

    r = await client.get(f"{BASE}/subscripciones-activas", headers=_headers(mint_operador_jwt, m))
    assert r.status_code == 200, r.text
    items = {i["uuid"]: i for i in r.json()["items"]}
    assert (items[str(lejos)]["dias_restantes"], items[str(lejos)]["puede_renovar"]) == (11, False)
    assert (items[str(cerca)]["dias_restantes"], items[str(cerca)]["puede_renovar"]) == (10, True)
    # expired rows are NOT part of this listing (see the renovables endpoint)
    assert str(vencida) not in items


async def test_proximas_vencer_usa_la_alerta_de_cada_suscripcion_y_fecha_bogota(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine)
    # default alert (NULL -> 7): 6 days left -> listed
    a = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=5), placas=("KKK201",))
    # own alert of 3: 6 days left -> NOT listed
    b = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=5), placas=("KKK202",), alerta=3)
    # own alert of 30: 21 days left -> listed (global 7 would have hidden it)
    c = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=20), placas=("KKK203",), alerta=30)
    # expired -> not listed; beyond default alert -> not listed
    d = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy - timedelta(days=1), placas=("KKK204",))
    e = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=15), placas=("KKK205",))

    r = await client.get(f"{BASE}/subscripciones/proximas-vencer", headers=_headers(mint_operador_jwt, m))
    assert r.status_code == 200, r.text
    items = {i["uuid"]: i for i in r.json()}
    assert set(items) == {str(a), str(c)}
    assert items[str(a)]["dias_restantes"] == 6 and items[str(a)]["dias_alerta_pre_vencimiento"] == 7
    assert items[str(a)]["puede_renovar"] is True  # 6 <= 10
    assert items[str(a)]["placas"] == ["KKK201"] and items[str(a)]["cliente_nombre"] == "Ada Prueba"
    assert items[str(c)]["dias_restantes"] == 21 and items[str(c)]["puede_renovar"] is False
    assert str(b) not in items and str(d) not in items and str(e) not in items


async def test_renovables_incluye_vencidas_y_respeta_la_ventana(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine)
    fuera = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=10), placas=("NNN501",))
    borde = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=9), placas=("NNN502",))
    vencida = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy - timedelta(days=30), placas=("NNN503",))

    r = await client.get(f"{BASE}/subscripciones/renovables", headers=_headers(mint_operador_jwt, m))
    assert r.status_code == 200, r.text
    items = {i["uuid"]: i for i in r.json()}
    assert set(items) == {str(borde), str(vencida)}
    assert items[str(borde)]["dias_restantes"] == 10 and items[str(borde)]["puede_renovar"] is True
    assert items[str(vencida)]["dias_restantes"] == -29 and items[str(vencida)]["puede_renovar"] is True
    assert str(fuera) not in items


# ---------------------------------------------------------------------------
# Repo-level calendar edges with an injected "today"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hoy", "vencimiento_anterior", "dias_plan", "inicio_esperado", "vencimiento_esperado"),
    [
        # end of month: previous period ends Jan 31
        (date(2026, 1, 25), date(2026, 1, 31), 30, date(2026, 2, 1), date(2026, 3, 2)),
        # leap year: Feb 29 exists
        (date(2028, 2, 25), date(2028, 2, 28), 30, date(2028, 2, 29), date(2028, 3, 29)),
        # common year
        (date(2027, 2, 25), date(2027, 2, 28), 30, date(2027, 3, 1), date(2027, 3, 30)),
        # 60 and 90 day plans, late renewal starts "today"
        (date(2026, 10, 6), date(2026, 9, 1), 60, date(2026, 10, 6), date(2026, 12, 4)),
        (date(2026, 10, 6), date(2026, 10, 9), 90, date(2026, 10, 10), date(2027, 1, 7)),
    ],
)
async def test_fechas_de_renovacion_en_bd_con_hoy_inyectado(
    pg_engine, alembic_upgrade, hoy, vencimiento_anterior, dias_plan, inicio_esperado, vencimiento_esperado
) -> None:
    m = await _sembrar_base(pg_engine, dias_plan=dias_plan)
    sub = await _sembrar_suscripcion(
        pg_engine, m, vencimiento=vencimiento_anterior, placas=("LLL301",), dias=dias_plan
    )
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        res = await repo_renovacion.renovar_vigencia(
            s, actor_uuid=m.actor, uuid_subscripcion=sub, uuid_sucursal=m.sucursal, hoy=hoy
        )
        await s.commit()
    assert res.inicio == inicio_esperado
    assert res.vencimiento == vencimiento_esperado
    assert (res.vencimiento - res.inicio).days + 1 == dias_plan
    assert res.monto == Decimal("100000.00")


async def test_repo_rechaza_fuera_de_ventana_con_hoy_inyectado(pg_engine, alembic_upgrade) -> None:
    m = await _sembrar_base(pg_engine)
    sub = await _sembrar_suscripcion(pg_engine, m, vencimiento=date(2028, 3, 5), placas=("MMM401",))
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        with pytest.raises(repo_renovacion.RenovacionFueraDeVentanaError) as exc:
            await repo_renovacion.renovar_vigencia(
                s, actor_uuid=m.actor, uuid_subscripcion=sub, uuid_sucursal=m.sucursal,
                hoy=date(2028, 2, 24),  # 11 days left (leap year)
            )
        assert exc.value.dias_restantes == 11
        await s.rollback()
        res = await repo_renovacion.renovar_vigencia(
            s, actor_uuid=m.actor, uuid_subscripcion=sub, uuid_sucursal=m.sucursal,
            hoy=date(2028, 2, 25),  # 10 days left
        )
        await s.commit()
    assert res.inicio == date(2028, 3, 6)
