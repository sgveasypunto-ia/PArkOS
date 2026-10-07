"""Numbering (prefijo + rango) on ``/empresa/resolucion-facturacion`` POST/PUT.

Electronic-invoice emission needs ``prefijo`` and ``rango_desde``/``rango_hasta``
on the branch's vigente resolution (``repo/fe_emision.py`` fails with
``resolucion_sin_prefijo`` otherwise). These tests pin the write contract:

- POST accepts and stores the numbering; the list shows it.
- Invalid ranges -> 422 (schema), overlap with another vigente resolution of
  the same prefix -> 409 ``resolucion_rango_solapado``.
- PUT is bi-temporal: it closes the old version and inserts a new one; a
  resolution created WITHOUT numbering can be completed through PUT.
- A PUT that omits numbering carries it forward from the closed version.

Seed/auth helpers are reused from the HU-F15.3 sibling module.
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest
from test_hu_f15_3_resoluciones_dian_api import _actor_headers

_ADMIN = pytest.mark.parametrize("app", ["admin"], indirect=True)
_URL = "/api/v1/empresa/resolucion-facturacion"


async def _seed_sucursal(pg_engine, uuid_sucursal: uuid_lib.UUID) -> None:
    """Sucursal on the seeded empresa (``empresa_singleton_uk``: only one exists)."""
    from datetime import UTC, datetime

    from parkos_core.models.V.empresa import Empresa
    from parkos_core.models.V.sucursal import Sucursal
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    now = datetime.now(UTC).replace(tzinfo=None)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa = (
            (await session.execute(select(Empresa.uuid).where(Empresa.vigente_hasta.is_(None))))
            .scalars()
            .first()
        )
        session.add(
            Sucursal(
                uuid=uuid_sucursal,
                uuid_empresa=empresa,
                uuid_tipo_sucursal=None,
                nombre=f"Suc numeracion {uuid_sucursal.hex[:6]}",
                prefijo_nombre=f"N{uuid_sucursal.hex[:6]}",
                ciudad="Ciudad",
                direccion="Calle 1",
                telefono="+57111",
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


def _prefijo() -> str:
    # Unique per test so the cross-sucursal overlap guard never trips on rows
    # seeded by sibling tests sharing the same database.
    return uuid_lib.uuid4().hex[:4].upper()


def _body(branch_uuid: uuid_lib.UUID, **extra: object) -> dict:
    return {
        "uuid_sucursal": str(branch_uuid),
        "numero_resolucion": f"R-{uuid_lib.uuid4().hex[:10]}",
        "fecha_resolucion": "2026-01-01",
        "fecha_inicio_vigencia": "2026-01-01",
        "fecha_fin_vigencia": "2027-01-01",
        **extra,
    }


@_ADMIN
async def test_post_guarda_prefijo_y_rango_y_la_lista_los_devuelve(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
) -> None:
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch)
    headers = await _actor_headers(pg_engine, mint_admin_jwt, branch_uuid=branch)
    prefijo = _prefijo()

    resp = await client.post(
        _URL,
        json=_body(branch, prefijo=prefijo.lower(), rango_desde=1, rango_hasta=5000),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    creada = resp.json()
    assert (creada["prefijo"], creada["rango_desde"], creada["rango_hasta"]) == (prefijo, 1, 5000)

    lista = await client.get(_URL, params={"limit": 200}, headers=headers)
    assert lista.status_code == 200, lista.text
    fila = next(i for i in lista.json()["items"] if i["uuid"] == creada["uuid"])
    assert (fila["prefijo"], fila["rango_desde"], fila["rango_hasta"]) == (prefijo, 1, 5000)


@_ADMIN
@pytest.mark.parametrize(
    "numeracion",
    [
        {"prefijo": "QA", "rango_desde": 10, "rango_hasta": 9},
        {"prefijo": "QA", "rango_desde": 0, "rango_hasta": 9},
        {"prefijo": "QA", "rango_desde": -5, "rango_hasta": 9},
        {"prefijo": "TOOLONG", "rango_desde": 1, "rango_hasta": 9},
        {"prefijo": "QA", "rango_desde": 1},
    ],
)
async def test_post_rechaza_numeracion_invalida_con_422(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, numeracion: dict
) -> None:
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch)
    headers = await _actor_headers(pg_engine, mint_admin_jwt, branch_uuid=branch)

    resp = await client.post(_URL, json=_body(branch, **numeracion), headers=headers)
    assert resp.status_code == 422, resp.text


@_ADMIN
async def test_post_rechaza_rango_solapado_con_mismo_prefijo_en_otra_sucursal(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
) -> None:
    branch_a, branch_b = uuid_lib.uuid4(), uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_a)
    await _seed_sucursal(pg_engine, branch_b)
    headers_a = await _actor_headers(pg_engine, mint_admin_jwt, branch_uuid=branch_a)
    headers_b = await _actor_headers(pg_engine, mint_admin_jwt, branch_uuid=branch_b)
    prefijo = _prefijo()

    ok = await client.post(
        _URL,
        json=_body(branch_a, prefijo=prefijo, rango_desde=1, rango_hasta=1000),
        headers=headers_a,
    )
    assert ok.status_code == 201, ok.text

    solapa = await client.post(
        _URL,
        json=_body(branch_b, prefijo=prefijo, rango_desde=1000, rango_hasta=2000),
        headers=headers_b,
    )
    assert solapa.status_code == 409, solapa.text
    assert solapa.json()["detail"]["error"] == "resolucion_rango_solapado"

    disjunto = await client.post(
        _URL,
        json=_body(branch_b, prefijo=prefijo, rango_desde=1001, rango_hasta=2000),
        headers=headers_b,
    )
    assert disjunto.status_code == 201, disjunto.text


@_ADMIN
async def test_put_completa_una_resolucion_sin_numeracion_creando_nueva_version(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
) -> None:
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch)
    headers = await _actor_headers(pg_engine, mint_admin_jwt, branch_uuid=branch)
    prefijo = _prefijo()

    base = _body(branch)
    sin_numeracion = await client.post(_URL, json=base, headers=headers)
    assert sin_numeracion.status_code == 201, sin_numeracion.text
    assert sin_numeracion.json()["prefijo"] is None
    viejo = sin_numeracion.json()["uuid"]

    resp = await client.put(
        f"{_URL}/{viejo}",
        json={**base, "prefijo": prefijo, "rango_desde": 1, "rango_hasta": 5000},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    nueva = resp.json()
    assert nueva["uuid"] != viejo  # bi-temporal: new row, old one closed
    assert (nueva["prefijo"], nueva["rango_desde"], nueva["rango_hasta"]) == (prefijo, 1, 5000)
    assert nueva["vigente_hasta"] is None

    lista = await client.get(_URL, params={"limit": 200}, headers=headers)
    uuids = {i["uuid"] for i in lista.json()["items"]}
    assert nueva["uuid"] in uuids
    assert viejo not in uuids


@_ADMIN
async def test_put_sin_numeracion_conserva_la_existente_y_no_se_solapa_consigo_misma(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
) -> None:
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch)
    headers = await _actor_headers(pg_engine, mint_admin_jwt, branch_uuid=branch)
    prefijo = _prefijo()

    base = _body(branch, prefijo=prefijo, rango_desde=1, rango_hasta=5000)
    creada = (await client.post(_URL, json=base, headers=headers)).json()

    # Corrección de fechas sin reenviar numeración.
    sin_num = {k: v for k, v in base.items() if k not in {"prefijo", "rango_desde", "rango_hasta"}}
    sin_num["fecha_fin_vigencia"] = "2028-01-01"
    resp = await client.put(f"{_URL}/{creada['uuid']}", json=sin_num, headers=headers)
    assert resp.status_code == 200, resp.text
    assert (resp.json()["prefijo"], resp.json()["rango_hasta"]) == (prefijo, 5000)

    # Reenviar el MISMO rango sobre la versión vigente no es un solape.
    resp2 = await client.put(f"{_URL}/{resp.json()['uuid']}", json=base, headers=headers)
    assert resp2.status_code == 200, resp2.text


@_ADMIN
async def test_put_inexistente_devuelve_404(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
) -> None:
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch)
    headers = await _actor_headers(pg_engine, mint_admin_jwt, branch_uuid=branch)

    resp = await client.put(f"{_URL}/{uuid_lib.uuid4()}", json=_body(branch), headers=headers)
    assert resp.status_code == 404, resp.text
