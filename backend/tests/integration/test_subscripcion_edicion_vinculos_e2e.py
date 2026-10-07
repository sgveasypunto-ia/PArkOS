"""Editing a subscription (generic PUT, close+insert) keeps its plate links.

``subscripciones_cliente.uuid`` identifies a version; the generic
``PUT /subscripciones-cliente/{uuid}`` mints a new uuid. The open
``subscripcion_vehiculos`` links must follow it in the same transaction, or the
active version loses its plates (renewal 422, duplicate-plate check blind).

Real HTTP against Postgres (``client`` fixture). Seeding helpers are reused
from the renewal e2e module.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from parkos_core.models.V.permisos import Permisos
from parkos_core.models.V.permisos_usuario import PermisosUsuario
from parkos_core.models.V.subscripcion_vehiculos import SubscripcionVehiculos
from parkos_core.models.V.vehiculos import Vehiculos
from tests.conftest import VFixtureFactory
from parkos_core.runtime.tiempo import hoy_bogota
from tests.integration.test_renovacion_e2e import (
    BASE,
    _headers,
    _sembrar_base,
    _sembrar_suscripcion,
)


async def _dar_permiso_placas(pg_engine, m) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        perm = (
            await s.execute(
                select(Permisos).where(
                    Permisos.permiso == "gestionar_placas_suscripcion",
                    Permisos.vigente_hasta.is_(None),
                )
            )
        ).scalars().first()
        s.add(PermisosUsuario(uuid_usuario=m.actor, uuid_permiso=perm.uuid))
        await s.commit()


async def _links(pg_engine, sub_uuid, *, abiertos: bool):
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        q = select(SubscripcionVehiculos).where(
            SubscripcionVehiculos.uuid_subscripcion_cliente == sub_uuid
        )
        if abiertos:
            q = q.where(SubscripcionVehiculos.vigente_hasta.is_(None))
        return list((await s.execute(q)).scalars().all())


async def test_editar_vencimiento_traslada_placas_a_la_version_activa(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine, con_resolucion=True)
    sub = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy + timedelta(days=5))
    veh_antes = {link.uuid_vehiculo for link in await _links(pg_engine, sub, abiertos=True)}
    assert len(veh_antes) == 2

    nuevo_venc = hoy + timedelta(days=8)
    r = await client.put(
        f"{BASE}/subscripciones-cliente/{sub}",
        json={"fecha_vencimiento": nuevo_venc.isoformat()},
        headers=_headers(mint_operador_jwt, m),
    )
    assert r.status_code == 200, r.text
    nueva = uuid_lib.UUID(r.json()["uuid"])
    assert nueva != sub

    # Active version keeps the same two vehicles; the closed version keeps none open.
    abiertos_nueva = await _links(pg_engine, nueva, abiertos=True)
    assert {link.uuid_vehiculo for link in abiertos_nueva} == veh_antes
    assert all(link.estado == "activo" for link in abiertos_nueva)
    assert await _links(pg_engine, sub, abiertos=True) == []
    # History is kept (no physical DELETE): the old links still exist, closed.
    assert len(await _links(pg_engine, sub, abiertos=False)) == 2

    # Renewal works on the edited version (used to be 422 suscripcion_sin_vehiculos).
    r2 = await client.post(
        f"{BASE}/subscripciones/{nueva}/renovar",
        json={"medio_pago": "efectivo"},
        headers=_headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}"),
    )
    assert r2.status_code == 201, r2.text


async def test_placa_sigue_bloqueando_duplicados_tras_editar(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine)
    await _dar_permiso_placas(pg_engine, m)
    sub = await _sembrar_suscripcion(
        pg_engine, m, vencimiento=hoy + timedelta(days=20), placas=("AAA111",)
    )
    # A second, empty subscription in the same branch.
    otra = await _sembrar_suscripcion(
        pg_engine, m, vencimiento=hoy + timedelta(days=20), placas=()
    )

    r = await client.put(
        f"{BASE}/subscripciones-cliente/{sub}",
        json={"fecha_vencimiento": (hoy + timedelta(days=25)).isoformat()},
        headers=_headers(mint_operador_jwt, m),
    )
    assert r.status_code == 200, r.text

    dup = await client.post(
        f"{BASE}/subscripcion-vehiculos/agregar",
        json={"uuid_subscripcion_cliente": str(otra), "placa": "AAA111"},
        headers=_headers(mint_operador_jwt, m),
    )
    assert dup.status_code == 409, dup.text
    assert "placa_con_suscripcion_activa" in dup.text


async def test_editar_sin_vinculos_no_falla(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine)
    sub = await _sembrar_suscripcion(
        pg_engine, m, vencimiento=hoy + timedelta(days=20), placas=()
    )
    r = await client.put(
        f"{BASE}/subscripciones-cliente/{sub}",
        json={"fecha_vencimiento": (hoy + timedelta(days=30)).isoformat()},
        headers=_headers(mint_operador_jwt, m),
    )
    assert r.status_code == 200, r.text
    assert await _links(pg_engine, uuid_lib.UUID(r.json()["uuid"]), abiertos=False) == []


# ---------------------------------------------------------------------------
# POST /subscripcion-vehiculos/validar-alta (dry-run before creating)
# ---------------------------------------------------------------------------


async def _crear_vehiculos(pg_engine, placas: tuple[str, ...]) -> list[uuid_lib.UUID]:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        rows = [VFixtureFactory.build(Vehiculos, placa=p) for p in placas]
        s.add_all(rows)
        await s.commit()
        return [r.uuid for r in rows]


async def test_validar_alta_rechaza_placa_activa_y_no_escribe(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    hoy = hoy_bogota()
    m = await _sembrar_base(pg_engine)
    await _dar_permiso_placas(pg_engine, m)
    placa = f"V{uuid_lib.uuid4().hex[:5].upper()}"
    await _sembrar_suscripcion(
        pg_engine, m, vencimiento=hoy + timedelta(days=20), placas=(placa,)
    )
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        veh = (
            await s.execute(
                select(Vehiculos.uuid).where(
                    Vehiculos.placa == placa, Vehiculos.vigente_hasta.is_(None)
                )
            )
        ).scalar_one()
    h = _headers(mint_operador_jwt, m)
    url = f"{BASE}/subscripcion-vehiculos/validar-alta"

    r = await client.post(
        url,
        json={"uuid_tipo_subscripcion": str(m.plan), "uuid_vehiculos": [str(veh)]},
        headers=h,
    )
    assert r.status_code == 409, r.text
    assert "placa_con_suscripcion_activa" in r.text
    assert str(veh) in r.text

    # A plate nobody covers passes the dry-run.
    sufijo = uuid_lib.uuid4().hex[:4].upper()
    (libre,) = await _crear_vehiculos(pg_engine, (f"L{sufijo}1",))
    ok = await client.post(
        url,
        json={"uuid_tipo_subscripcion": str(m.plan), "uuid_vehiculos": [str(libre)]},
        headers=h,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json() == {"ok": True}

    # Over the plan's maximum (2 in the seeded plan) -> 422.
    tres = await _crear_vehiculos(pg_engine, (f"M{sufijo}1", f"M{sufijo}2", f"M{sufijo}3"))
    r3 = await client.post(
        url,
        json={"uuid_tipo_subscripcion": str(m.plan), "uuid_vehiculos": [str(u) for u in tres]},
        headers=h,
    )
    assert r3.status_code == 422, r3.text
    assert "cantidad_vehiculos_excede_plan" in r3.text
