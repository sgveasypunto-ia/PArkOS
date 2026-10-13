"""Caracterizacion QA #6/#16 -- ida y vuelta UTF-8 de texto con tildes.

El "mojibake" reportado (``Ý``/``¾``/``±`` en lugar de ``í``/``ó``/``ñ``) era la
consola CP850 de psql en Windows con ``client_encoding=LATIN1``: los bytes en BD
son UTF-8 correcto. Este test lo fija: lo que entra por la API sale identico y
los bytes almacenados son exactamente la codificacion UTF-8 de la cadena.
"""
from __future__ import annotations

import uuid as uuid_lib

from _seeds import ensure_usuario
from test_ingreso_create_db import _seed_branch, _seed_full_chain, _truncate

OBSERVACIONES = "Ñandú óleo, camión señalización"


async def test_observaciones_con_tildes_hacen_roundtrip_utf8_exacto(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    await ensure_usuario(pg_engine, actor)
    tipo_auto = uuid_lib.uuid4()
    await _seed_branch(pg_engine, uuid_sucursal=branch)
    await _seed_full_chain(
        pg_engine, uuid_sucursal=branch, uuid_tipo_auto=tipo_auto, cupo_auto=5
    )

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    headers = {"Authorization": f"Bearer {token}", "X-Sucursal-Context": str(branch)}
    resp = await client.post(
        "/api/v1/operacion/ingresos",
        json={"placa": "UTF811", "observaciones": OBSERVACIONES},
        headers=headers,
    )
    assert resp.status_code == 201, f"{resp.status_code}: {resp.text}"
    assert resp.json()["observaciones"] == OBSERVACIONES

    listado = await client.get(
        f"/api/v1/operacion/ingresos?uuid_sucursal={branch}&placa=UTF811",
        headers=headers,
    )
    assert listado.status_code == 200, listado.text
    items = listado.json()
    assert len(items) == 1
    assert items[0]["observaciones"] == OBSERVACIONES

    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT observaciones, encode(convert_to(observaciones, 'UTF8'), 'hex') "
            "FROM prod.ingreso WHERE uuid_sucursal = %s",
            (str(branch),),
        )
        texto, hex_utf8 = cur.fetchone()
    assert texto == OBSERVACIONES
    assert hex_utf8 == OBSERVACIONES.encode("utf-8").hex()
    # Los bytes Latin-1 de i/o/n con tilde NO deben aparecer como texto guardado.
    assert not any(c in texto for c in "Ý¾±")


APELLIDO = "Peña Muñoz Ávila"


async def test_apellido_de_cliente_hace_roundtrip_utf8_exacto(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    from _seeds import ensure_usuario
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from test_workflows_anulaciones_integration import _grant_existing_permission

    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    await ensure_usuario(pg_engine, actor)
    await _seed_branch(pg_engine, uuid_sucursal=branch)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        await _grant_existing_permission(
            session, actor_uuid=actor, codigo="gestionar_clientes"
        )

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    headers = {"Authorization": f"Bearer {token}", "X-Sucursal-Context": str(branch)}
    numero = f"utf8-{uuid_lib.uuid4().hex[:10]}"
    creado = await client.post(
        "/api/v1/clientes/clientes",
        json={
            "tipo_identificador": "CC",
            "numero_identificacion": numero,
            "nombre": "Zoë",
            "apellido": APELLIDO,
        },
        headers=headers,
    )
    assert creado.status_code == 201, f"{creado.status_code}: {creado.text}"
    assert creado.json()["apellido"] == APELLIDO

    consultado = await client.get(
        f"/api/v1/clientes/clientes/{creado.json()['uuid']}", headers=headers
    )
    assert consultado.status_code == 200, consultado.text
    assert consultado.json()["apellido"] == APELLIDO

    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT apellido, encode(convert_to(apellido, 'UTF8'), 'hex') "
            "FROM prod.clientes WHERE numero_identificacion = %s",
            (numero,),
        )
        texto, hex_utf8 = cur.fetchone()
    assert texto == APELLIDO
    assert hex_utf8 == APELLIDO.encode("utf-8").hex()
    assert not any(c in texto for c in "Ý¾±")
