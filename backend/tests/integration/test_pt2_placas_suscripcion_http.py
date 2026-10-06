"""PT-2 -- real-HTTP + real-Postgres tests for agregar/quitar placas.

Covers (testcontainers Postgres at alembic head, ASGI transport):

* 403 ``permission_denied`` for an operador on all 3 write paths, 201/200
  for a supervisor holding ``gestionar_placas_suscripcion``.
* Duplicate rule: same-branch ACTIVE subscription -> 409, other branch -> ok,
  expired subscription -> ok.
* Plan <-> vehicle-type mismatch -> 422 and the plan-list filter.
* Audit: ``log_transaccional`` row with the placa + ``alerta`` info row, and
  the alert is visible through ``GET /workflows/alerta``.
* Supervisor login in the branch app + ``GET /auth/me`` contract.
"""

from __future__ import annotations

import random
import string
import uuid as uuid_lib
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.conftest import VFixtureFactory

PASSWORD = "Correcta123!"
PERM = "gestionar_placas_suscripcion"


def _placa() -> str:
    return "".join(random.choices(string.ascii_uppercase, k=3)) + "".join(
        random.choices(string.digits, k=3)
    )


class _World:
    """Seeded fixtures for one test."""


async def _seed(pg_engine, make_auth_user_with_branch) -> _World:
    from parkos_core.models.V.clientes import Clientes
    from parkos_core.models.V.permisos import Permisos
    from parkos_core.models.V.permisos_usuario import PermisosUsuario
    from parkos_core.models.V.sucursal import Sucursal
    from parkos_core.models.V.tipo_subscripciones import TipoSubscripciones
    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
    from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal
    from parkos_core.runtime.tiempo import hoy_bogota
    from sqlalchemy import select

    w = _World()
    sup_uuid, suc_a, sup_email, _ = await make_auth_user_with_branch(
        rol="Supervisor",
        email=f"sup-{uuid_lib.uuid4().hex[:8]}@example.com",
        branch_nombre=f"Suc {uuid_lib.uuid4().hex[:6]}",
        branch_prefijo=uuid_lib.uuid4().hex[:3].upper(),
    )
    op_uuid, suc_op, op_email, _ = await make_auth_user_with_branch(
        rol="operador",
        email=f"op-{uuid_lib.uuid4().hex[:8]}@example.com",
        branch_nombre=f"Suc {uuid_lib.uuid4().hex[:6]}",
        branch_prefijo=uuid_lib.uuid4().hex[:3].upper(),
    )
    w.sup_uuid, w.suc_a, w.sup_email = sup_uuid, suc_a, sup_email
    w.op_uuid, w.suc_op, w.op_email = op_uuid, suc_op, op_email
    w.hoy = hoy_bogota()

    # Otros tests de la suite hacen TRUNCATE de prod.alert_types: se re-siembran
    # (idempotente, igual que la migracion 0086) para el filtro por severidad.
    async with pg_engine.begin() as conn:
        for tipo in ("suscripcion_placa_agregada", "suscripcion_placa_quitada"):
            await conn.execute(
                text(
                    "INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity) "
                    "VALUES (:t, :t, 'info') ON CONFLICT (tipo_alerta) DO NOTHING"
                ),
                {"t": tipo},
            )

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        suc_b = VFixtureFactory.build(Sucursal, nombre="Otra", prefijo_nombre="OTR")
        session.add(suc_b)
        carro = VFixtureFactory.build(TiposVehiculo, tipo=f"carro-{uuid_lib.uuid4().hex[:6]}")
        moto = VFixtureFactory.build(TiposVehiculo, tipo=f"moto-{uuid_lib.uuid4().hex[:6]}")
        session.add_all([carro, moto])
        await session.flush()  # FK tipo_subscripciones.uuid_tipo_vehiculo (not in the ORM)
        cliente = VFixtureFactory.build(
            Clientes, numero_identificacion=uuid_lib.uuid4().hex[:10], nombre="Ada"
        )
        session.add(cliente)
        plan_moto = VFixtureFactory.build(
            TipoSubscripciones,
            tipo=f"mensual-moto-{uuid_lib.uuid4().hex[:6]}",
            valor=1000,
            duracion_dias=30,
            cantidad_maxima_vehiculos=3,
            mismo_tipo_vehiculo=False,
            uuid_tipo_vehiculo=moto.uuid,
        )
        plan_any = VFixtureFactory.build(
            TipoSubscripciones,
            tipo=f"empresarial-{uuid_lib.uuid4().hex[:6]}",
            valor=5000,
            duracion_dias=30,
            cantidad_maxima_vehiculos=5,
            mismo_tipo_vehiculo=False,
            uuid_tipo_vehiculo=None,
        )
        session.add_all([plan_moto, plan_any])
        await session.flush()

        # Supervisor holds the permission (mirrors migration 0086's grant);
        # the operador only holds the generic clientes permission.
        perm = (
            await session.execute(
                select(Permisos).where(Permisos.permiso == PERM, Permisos.vigente_hasta.is_(None))
            )
        ).scalars().first()
        assert perm is not None, "migration 0086 must seed gestionar_placas_suscripcion"
        gc = (
            await session.execute(
                select(Permisos).where(
                    Permisos.permiso == "gestionar_clientes", Permisos.vigente_hasta.is_(None)
                )
            )
        ).scalars().first()
        session.add(VFixtureFactory.build(PermisosUsuario, uuid_usuario=sup_uuid, uuid_permiso=perm.uuid))
        session.add(VFixtureFactory.build(PermisosUsuario, uuid_usuario=op_uuid, uuid_permiso=gc.uuid))
        # The operador ALSO gets assigned to suc_a so tenancy is not the reason for a 403.
        session.add(
            VFixtureFactory.build(UsuariosSucursal, uuid_usuario=op_uuid, uuid_sucursal=suc_a)
        )
        await session.commit()
        w.suc_b, w.carro, w.moto = suc_b.uuid, carro.uuid, moto.uuid
        w.cliente, w.plan_moto, w.plan_any = cliente.uuid, plan_moto.uuid, plan_any.uuid
    return w


async def _make_sub(pg_engine, w, *, sucursal, plan, vence=None, vehiculos=()):
    """Insert a subscripcion (+ junction rows for ``vehiculos`` = [(placa, tipo)])."""
    from parkos_core.models.V.subscripcion_vehiculos import SubscripcionVehiculos
    from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sub = VFixtureFactory.build(
            SubscripcionesCliente,
            uuid_cliente=w.cliente,
            uuid_sucursal=sucursal,
            uuid_tipo_subscripcion=plan,
            fecha_inicio_cobertura=w.hoy - timedelta(days=5),
            fecha_vencimiento=vence or (w.hoy + timedelta(days=20)),
        )
        session.add(sub)
        await session.flush()
        out = []
        for placa, tipo in vehiculos:
            veh = await _ensure_vehiculo(session, placa, tipo)
            row = VFixtureFactory.build(
                SubscripcionVehiculos,
                uuid_subscripcion_cliente=sub.uuid,
                uuid_vehiculo=veh,
            )
            session.add(row)
            out.append(row)
        await session.commit()
        return sub.uuid, [r.uuid for r in out]


async def _ensure_vehiculo(session, placa, tipo):
    from parkos_core.models.V.vehiculos import Vehiculos
    from sqlalchemy import select

    existing = (
        await session.execute(
            select(Vehiculos).where(Vehiculos.placa == placa, Vehiculos.vigente_hasta.is_(None))
        )
    ).scalars().first()
    if existing is not None:
        return existing.uuid
    veh = VFixtureFactory.build(Vehiculos, placa=placa, uuid_tipo_vehiculo=tipo)
    session.add(veh)
    await session.flush()
    return veh.uuid


async def _login(client, email) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token, sucursal=None):
    h = {"Authorization": f"Bearer {token}"}
    if sucursal is not None:
        h["X-Sucursal-Context"] = str(sucursal)
    return h


@pytest.fixture
async def world(pg_engine, make_auth_user_with_branch, auth_seguridad_global):
    return await _seed(pg_engine, make_auth_user_with_branch)


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


async def test_operador_recibe_403_en_los_tres_caminos(client, pg_engine, world) -> None:
    w = world
    sub, (sv,) = await _make_sub(
        pg_engine, w, sucursal=w.suc_a, plan=w.plan_any, vehiculos=[(_placa(), w.carro)]
    )
    # Mint pinned to suc_a so tenancy passes and ONLY the permission can fail.
    from parkos_core.auth.tokens import issue_token

    token = issue_token(
        subject_uuid=w.op_uuid,
        issuer="operador-test",
        claims={"rol": "operador", "sucursal": str(w.suc_a)},
        expires_in=3600,
    )
    placa = _placa()
    async with async_sessionmaker(pg_engine)() as s:
        veh = await _ensure_vehiculo(s, placa, w.carro)
        await s.commit()

    r1 = await client.post(
        "/api/v1/clientes/subscripcion-vehiculos/agregar",
        json={"uuid_subscripcion_cliente": str(sub), "placa": placa},
        headers=_h(token),
    )
    r2 = await client.put(
        f"/api/v1/clientes/subscripcion-vehiculos/{sv}/quitar", headers=_h(token)
    )
    r3 = await client.post(
        "/api/v1/clientes/subscripcion-vehiculos",
        json={"uuid_subscripcion_cliente": str(sub), "uuid_vehiculo": str(veh)},
        headers=_h(token),
    )
    for r in (r1, r2, r3):
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == {"error": "permission_denied", "detail": PERM}

    # Generic CRUD: no write verbs are mounted at all (read-only router).
    r4 = await client.put(
        f"/api/v1/clientes/subscripcion-vehiculos/{sv}", json={}, headers=_h(token)
    )
    r5 = await client.delete(f"/api/v1/clientes/subscripcion-vehiculos/{sv}", headers=_h(token))
    assert r4.status_code in (404, 405)
    assert r5.status_code in (404, 405)


async def test_supervisor_agrega_y_quita_con_auditoria_y_alerta(client, pg_engine, world) -> None:
    w = world
    sub, _ = await _make_sub(pg_engine, w, sucursal=w.suc_a, plan=w.plan_any)
    token = await _login(client, w.sup_email)
    placa = _placa()

    r = await client.post(
        "/api/v1/clientes/subscripcion-vehiculos/agregar",
        json={"uuid_subscripcion_cliente": str(sub), "placa": placa},
        headers=_h(token, w.suc_a),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    inscrito = next(v for v in body["vehiculos"] if v["placa"] == placa)

    async with pg_engine.connect() as conn:
        logs = (
            await conn.execute(
                text(
                    "SELECT datos_nuevos, uuid_usuario, uuid_sucursal FROM prod.log_transaccional "
                    "WHERE accion = 'agregar_placa_subscripcion' "
                    "AND datos_nuevos->>'placa' = :p"
                ),
                {"p": placa},
            )
        ).all()
        alertas = (
            await conn.execute(
                text(
                    "SELECT tipo_alerta, estado, datos_nuevos FROM prod.alerta "
                    "WHERE tipo_alerta = 'suscripcion_placa_agregada' "
                    "AND datos_nuevos->>'placa' = :p"
                ),
                {"p": placa},
            )
        ).all()
        facturas = (
            await conn.execute(
                text("SELECT count(*) FROM prod.factura_pagos")
            )
        ).scalar_one()
    assert len(logs) == 1
    datos, uuid_usuario, uuid_sucursal = logs[0]
    assert datos["accion"] == "agregar"
    assert datos["uuid_subscripcion"] == str(sub)
    assert uuid_usuario == w.sup_uuid and uuid_sucursal == w.suc_a
    assert len(alertas) == 1 and alertas[0][1] == "abierta"
    assert alertas[0][2]["actor"] == str(w.sup_uuid)
    assert facturas == 0  # sin cobro

    # La alerta info es visible para el administrador del listado.
    lst = await client.get(
        "/api/v1/workflows/alerta",
        params={
            "tipo_alerta": "suscripcion_placa_agregada",
            "severidad": "info",
            "uuid_sucursal": str(w.suc_a),
            "limit": 200,
        },
        headers=_h(token, w.suc_a),
    )
    assert lst.status_code == 200, lst.text
    assert any((i["datos_nuevos"] or {}).get("placa") == placa for i in lst.json()["items"]), lst.text[:1500]

    # Quitar
    q = await client.put(
        f"/api/v1/clientes/subscripcion-vehiculos/{inscrito['uuid']}/quitar",
        headers=_h(token, w.suc_a),
    )
    assert q.status_code == 200, q.text
    assert all(v["placa"] != placa for v in q.json()["vehiculos"])
    async with pg_engine.connect() as conn:
        n_log = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM prod.log_transaccional "
                    "WHERE accion = 'quitar_placa_subscripcion' AND datos_nuevos->>'placa' = :p"
                ),
                {"p": placa},
            )
        ).scalar_one()
        n_alerta = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM prod.alerta WHERE tipo_alerta = "
                    "'suscripcion_placa_quitada' AND datos_nuevos->>'placa' = :p"
                ),
                {"p": placa},
            )
        ).scalar_one()
    assert n_log == 1 and n_alerta == 1


async def test_supervisor_sin_header_de_sucursal_o_fuera_de_alcance(client, pg_engine, world) -> None:
    w = world
    sub, (sv,) = await _make_sub(
        pg_engine, w, sucursal=w.suc_a, plan=w.plan_any, vehiculos=[(_placa(), w.carro)]
    )
    token = await _login(client, w.sup_email)
    body = {"uuid_subscripcion_cliente": str(sub), "placa": _placa()}

    # admin- sin X-Sucursal-Context: modo global NO sirve para escribir placas.
    r = await client.post(
        "/api/v1/clientes/subscripcion-vehiculos/agregar", json=body, headers=_h(token)
    )
    assert r.status_code == 400 and r.json()["detail"]["error"] == "missing_sucursal_context"
    # Sucursal que no es suya.
    r = await client.post(
        "/api/v1/clientes/subscripcion-vehiculos/agregar",
        json=body,
        headers=_h(token, w.suc_b),
    )
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "unauthorized_sucursal_context"
    r = await client.put(
        f"/api/v1/clientes/subscripcion-vehiculos/{sv}/quitar", headers=_h(token, w.suc_b)
    )
    assert r.status_code == 403


async def test_quitar_placa_de_suscripcion_de_otra_sucursal_404(client, pg_engine, world) -> None:
    """El supervisor tiene permiso y contexto valido, pero la placa es de OTRA sucursal."""
    from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal

    w = world
    async with async_sessionmaker(pg_engine)() as s:
        s.add(
            VFixtureFactory.build(
                UsuariosSucursal, uuid_usuario=w.sup_uuid, uuid_sucursal=w.suc_b
            )
        )
        await s.commit()
    _, (sv_b,) = await _make_sub(
        pg_engine, w, sucursal=w.suc_b, plan=w.plan_any, vehiculos=[(_placa(), w.carro)]
    )
    token = await _login(client, w.sup_email)
    r = await client.put(
        f"/api/v1/clientes/subscripcion-vehiculos/{sv_b}/quitar", headers=_h(token, w.suc_a)
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "vehiculo_inscrito_no_encontrado"


# ---------------------------------------------------------------------------
# Duplicates (same branch ACTIVE only)
# ---------------------------------------------------------------------------


async def test_duplicados_por_sucursal_en_los_tres_caminos(client, pg_engine, world) -> None:
    from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal

    w = world
    async with async_sessionmaker(pg_engine)() as s:
        s.add(
            VFixtureFactory.build(
                UsuariosSucursal, uuid_usuario=w.sup_uuid, uuid_sucursal=w.suc_b
            )
        )
        await s.commit()
    token = await _login(client, w.sup_email)

    placa_misma, placa_otra, placa_vencida = _placa(), _placa(), _placa()
    # Activa en OTRA suscripcion de la MISMA sucursal -> 409.
    await _make_sub(
        pg_engine, w, sucursal=w.suc_a, plan=w.plan_any, vehiculos=[(placa_misma, w.carro)]
    )
    # Activa SOLO en otra sucursal -> permitido.
    await _make_sub(
        pg_engine, w, sucursal=w.suc_b, plan=w.plan_any, vehiculos=[(placa_otra, w.carro)]
    )
    # Vencida en la misma sucursal -> no bloquea.
    await _make_sub(
        pg_engine,
        w,
        sucursal=w.suc_a,
        plan=w.plan_any,
        vence=w.hoy - timedelta(days=1),
        vehiculos=[(placa_vencida, w.carro)],
    )
    target, _ = await _make_sub(pg_engine, w, sucursal=w.suc_a, plan=w.plan_any)

    async def agregar(placa):
        return await client.post(
            "/api/v1/clientes/subscripcion-vehiculos/agregar",
            json={"uuid_subscripcion_cliente": str(target), "placa": placa},
            headers=_h(token, w.suc_a),
        )

    r = await agregar(placa_misma)
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"] == "placa_con_suscripcion_activa"
    assert (await agregar(placa_otra)).status_code == 201
    assert (await agregar(placa_vencida)).status_code == 201

    # Camino 3: POST /subscripcion-vehiculos (uuid_vehiculo)
    async with async_sessionmaker(pg_engine)() as s:
        veh_misma = await _ensure_vehiculo(s, placa_misma, w.carro)
        await s.commit()
    r = await client.post(
        "/api/v1/clientes/subscripcion-vehiculos",
        json={"uuid_subscripcion_cliente": str(target), "uuid_vehiculo": str(veh_misma)},
        headers=_h(token, w.suc_a),
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"] == "placa_con_suscripcion_activa"


# ---------------------------------------------------------------------------
# Plan <-> tipo de vehiculo
# ---------------------------------------------------------------------------


async def test_plan_de_moto_rechaza_carro_y_filtro_de_planes(client, pg_engine, world) -> None:
    w = world
    sub, _ = await _make_sub(pg_engine, w, sucursal=w.suc_a, plan=w.plan_moto)
    token = await _login(client, w.sup_email)
    placa_carro, placa_moto = _placa(), _placa()
    async with async_sessionmaker(pg_engine)() as s:
        await _ensure_vehiculo(s, placa_carro, w.carro)
        await _ensure_vehiculo(s, placa_moto, w.moto)
        await s.commit()

    r = await client.post(
        "/api/v1/clientes/subscripcion-vehiculos/agregar",
        json={"uuid_subscripcion_cliente": str(sub), "placa": placa_carro},
        headers=_h(token, w.suc_a),
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"] == "tipo_vehiculo_plan_incompatible"
    ok = await client.post(
        "/api/v1/clientes/subscripcion-vehiculos/agregar",
        json={"uuid_subscripcion_cliente": str(sub), "placa": placa_moto},
        headers=_h(token, w.suc_a),
    )
    assert ok.status_code == 201, ok.text

    # Listado de planes filtrado por tipo de vehiculo (incluye los NULL).
    lst = await client.get(
        "/api/v1/catalogos/tipo-subscripciones",
        params={"uuid_tipo_vehiculo": str(w.carro), "limit": 200},
        headers=_h(token),
    )
    assert lst.status_code == 200, lst.text
    uuids = {i["uuid"] for i in lst.json()["items"]}
    assert str(w.plan_moto) not in uuids and str(w.plan_any) in uuids
    lst = await client.get(
        "/api/v1/catalogos/tipo-subscripciones",
        params={"uuid_tipo_vehiculo": str(w.moto), "limit": 200},
        headers=_h(token),
    )
    uuids = {i["uuid"] for i in lst.json()["items"]}
    assert {str(w.plan_moto), str(w.plan_any)} <= uuids


# ---------------------------------------------------------------------------
# Supervisor en la app de sucursal: login + /auth/me
# ---------------------------------------------------------------------------


async def test_supervisor_login_y_auth_me_devuelve_permisos(client, world) -> None:
    w = world
    token = await _login(client, w.sup_email)
    # Via header
    r = await client.get("/api/v1/auth/me", headers=_h(token, w.suc_a))
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["user"]["rol"] == "Supervisor"
    assert PERM in me["permisos"]
    assert me["sucursal"]["uuid"] == str(w.suc_a)
    assert str(w.suc_a) in {s["uuid"] for s in me["sucursales_permitidas"]}
    # Sin header: usa la sucursal fijada en el login
    r = await client.get("/api/v1/auth/me", headers=_h(token))
    assert r.status_code == 200, r.text
    # Sucursal que no le pertenece -> 404 anti-enumeracion
    r = await client.get("/api/v1/auth/me", headers=_h(token, w.suc_b))
    assert r.status_code == 404


async def test_auth_me_no_se_abre_a_otros_roles_admin_ni_a_tokens_temporales(
    client, pg_engine, world, make_auth_user_with_branch
) -> None:
    from parkos_core.auth.tokens import issue_token

    w = world
    _uuid, suc, email, _ = await make_auth_user_with_branch(
        rol="Administrador",
        email=f"adm-{uuid_lib.uuid4().hex[:8]}@example.com",
        branch_nombre=f"Suc {uuid_lib.uuid4().hex[:6]}",
        branch_prefijo=uuid_lib.uuid4().hex[:3].upper(),
    )
    token = await _login(client, email)
    r = await client.get("/api/v1/auth/me", headers=_h(token, suc))
    assert r.status_code == 404  # solo Supervisor entra por /auth/me con admin-

    temp = issue_token(
        subject_uuid=w.sup_uuid,
        issuer="admin-test",
        claims={"purpose": "must_change", "must_change_password": True},
        expires_in=300,
    )
    r = await client.get("/api/v1/auth/me", headers=_h(temp, w.suc_a))
    assert r.status_code == 404

    # El operador sigue igual: permisos propios, sin nada nuevo.
    op_token = await _login(client, w.op_email)
    r = await client.get("/api/v1/auth/me", headers=_h(op_token))
    assert r.status_code == 200
    assert PERM not in r.json()["permisos"]
