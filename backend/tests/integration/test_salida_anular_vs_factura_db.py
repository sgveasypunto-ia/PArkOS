"""Bug #2: anular-no-pagada y facturar son mutuamente excluyentes, contra Postgres real.

Los guards (``repo/salida.py::bloquear_salida`` + checks en ``anular_salida_no_pagada``
y ``repo/factura.py::buscar_salida_facturable``) solo tenian tests con session falsa.
Aqui se prueban por HTTP real (ASGI + testcontainers) en ambos ordenes y en carrera:

* anular y luego facturar la misma salida -> 409 ``salida_anulada``.
* facturar y luego anular -> 409 ``salida_ya_pagada``.
* anular y facturar CONCURRENTES (sesiones separadas, una por request) -> exactamente
  una gana, la otra recibe 409, y jamas coexisten anulacion ``ejecutada`` y factura.
"""
from __future__ import annotations

import asyncio
import uuid as uuid_lib

import psycopg
from _seeds import ensure_usuario
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.integration.test_factura_mensualidad_iva_neto_db import _body, _mundo
from tests.integration.test_workflows_anulaciones_integration import (
    _grant_existing_permission,
)

URL_FACTURA = "/api/v1/facturacion/factura"
RONDAS_CARRERA = 6


def _url_anular(salida: uuid_lib.UUID) -> str:
    return f"/api/v1/operacion/salidas/{salida}/anular-no-pagada"


async def _mundo_con_permiso(pg_engine, pg_dsn, mint_operador_jwt):
    sucursal, salida, actor = await _mundo(pg_engine, pg_dsn)
    await ensure_usuario(pg_engine, actor)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        await _grant_existing_permission(session, actor_uuid=actor, codigo="anular_ingreso")
    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=sucursal)
    return salida, {"Authorization": f"Bearer {token}"}


def _hdrs(base: dict[str, str]) -> dict[str, str]:
    return {**base, "Idempotency-Key": f"k-{uuid_lib.uuid4()}"}


async def _facturar(client, salida, headers):
    return await client.post(
        URL_FACTURA, json=_body(salida, "1500.00", "0.00"), headers=_hdrs(headers)
    )


async def _anular(client, salida, headers):
    return await client.post(
        _url_anular(salida),
        json={"motivo": "cliente se fue sin pagar"},
        headers=_hdrs(headers),
    )


def _conteos(pg_dsn: str, salida: uuid_lib.UUID) -> tuple[int, int]:
    """(anulaciones ejecutadas de la salida, facturas de la salida)."""
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM prod.anulaciones WHERE uuid_salida = %s "
            "AND tipo_anulable = 'salida' AND estado = 'ejecutada'",
            (str(salida),),
        )
        anuladas = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM prod.facturas WHERE uuid_salida = %s", (str(salida),))
        facturas = cur.fetchone()[0]
    return anuladas, facturas


async def test_anular_y_luego_facturar_responde_409_salida_anulada(
    client, pg_engine, pg_dsn, alembic_upgrade, mint_operador_jwt
) -> None:
    salida, headers = await _mundo_con_permiso(pg_engine, pg_dsn, mint_operador_jwt)

    r_anular = await _anular(client, salida, headers)
    assert r_anular.status_code == 201, r_anular.text

    r_factura = await _facturar(client, salida, headers)
    assert r_factura.status_code == 409, r_factura.text
    assert "salida_anulada" in r_factura.text
    assert _conteos(pg_dsn, salida) == (1, 0)


async def test_facturar_y_luego_anular_responde_409_salida_ya_pagada(
    client, pg_engine, pg_dsn, alembic_upgrade, mint_operador_jwt
) -> None:
    salida, headers = await _mundo_con_permiso(pg_engine, pg_dsn, mint_operador_jwt)

    r_factura = await _facturar(client, salida, headers)
    assert r_factura.status_code == 201, r_factura.text

    r_anular = await _anular(client, salida, headers)
    assert r_anular.status_code == 409, r_anular.text
    assert "salida_ya_pagada" in r_anular.text
    assert _conteos(pg_dsn, salida) == (0, 1)


async def test_anular_y_facturar_concurrentes_solo_una_gana(
    client, pg_engine, pg_dsn, alembic_upgrade, mint_operador_jwt
) -> None:
    ganadores = {"anular": 0, "facturar": 0}
    for _ in range(RONDAS_CARRERA):
        salida, headers = await _mundo_con_permiso(pg_engine, pg_dsn, mint_operador_jwt)

        r_anular, r_factura = await asyncio.gather(
            _anular(client, salida, headers), _facturar(client, salida, headers)
        )

        codigos = sorted([r_anular.status_code, r_factura.status_code])
        assert codigos == [201, 409], (r_anular.text, r_factura.text)
        if r_anular.status_code == 201:
            ganadores["anular"] += 1
            assert "salida_anulada" in r_factura.text
        else:
            ganadores["facturar"] += 1
            assert "salida_ya_pagada" in r_anular.text

        anuladas, facturas = _conteos(pg_dsn, salida)
        assert (anuladas, facturas) in {(1, 0), (0, 1)}, (anuladas, facturas)
    assert sum(ganadores.values()) == RONDAS_CARRERA
