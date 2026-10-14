"""test_factura_impuestos_filter.py — HU-X.1b, DB-backed.

TDD RED → GREEN for the custom handler that fixes
``GET /api/v1/facturacion/factura-impuestos?uuid_factura=<uuid>``.

Mirror of ``test_factura_detalle_filter.py`` for the
``prod.factura_impuestos`` resource. Same root cause (factory drops
the filter), same fix pattern (custom handler replicating the X.1a
shape), same four scenarios.
"""
from __future__ import annotations

import uuid as uuid_lib

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from parkos_core.api.app_factory import create_app
from parkos_core.auth.tokens import issue_token


_DOCKER_TEST = __import__("os").environ.get("PARKOS_DOCKER_TEST") == "1"
pytestmark = pytest.mark.skipif(
    not _DOCKER_TEST,
    reason="PARKOS_DOCKER_TEST=1 not set; skip factura-impuestos filter DB tests",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _truncate(pg_dsn: str) -> None:
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE prod.factura_pagos, prod.facturas, "
            "prod.factura_detalle, prod.factura_impuestos, "
            "prod.factura_otros_cobros, "
            "prod.ingreso, prod.tarifas_sucursal, prod.impuestos, "
            "prod.salidas, "
            "prod.usuarios_sucursal, prod.usuarios, prod.sucursal, "
            "prod.empresa, prod.tipos_vehiculo, prod.tipo_tarifa CASCADE"
        )
        conn.commit()


async def _seed_sucursal(pg_engine, *, uuid_sucursal: uuid_lib.UUID) -> None:
    from datetime import UTC, datetime

    from parkos_core.models.V.sucursal import Sucursal
    from parkos_core.models.V.empresa import Empresa

    async with pg_engine() as session:
        empresa_uuid = uuid_lib.uuid4()
        new_empresa = Empresa(
            uuid=empresa_uuid,
            nombre="Test Empresa",
            nit="900000000-0",
            regimen="comun",
            vigente_desde=datetime.now(UTC).replace(tzinfo=None),
            estado="activo",
        )
        session.add(new_empresa)
        await session.flush()

        new_sucursal = Sucursal(
            uuid=uuid_sucursal,
            uuid_empresa=empresa_uuid,
            nombre="BOG-CEN-TEST",
            codigo="BOG-TEST",
            direccion="Test",
            ciudad="Bogota",
            vigente_desde=datetime.now(UTC).replace(tzinfo=None),
            estado="activo",
        )
        session.add(new_sucursal)
        await session.commit()


async def _seed_factura_impuesto(
    pg_engine,
    *,
    uuid_impuesto: uuid_lib.UUID,
    uuid_factura: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    uuid_impuesto_catalogo: uuid_lib.UUID | None = None,
    base_calculo: str = "1000.0000",
    porcentaje_aplicado: str = "0.1900",
    valor: str = "190.0000",
) -> None:
    """Seed a minimal ``prod.factura_impuestos`` row.

    Minimal columns: ``uuid`` (PK), ``uuid_factura``, ``uuid_impuesto``
    (catalogo FK), ``base_calculo``, ``porcentaje_aplicado``, ``valor``.
    ``created_at`` / ``created_by`` are stamped by the audit trigger.
    """
    from datetime import UTC, datetime

    from parkos_core.models.A.factura_impuestos import FacturaImpuestos

    now = datetime.now(UTC).replace(tzinfo=None)
    async with pg_engine() as session:
        new_impuesto = FacturaImpuestos(
            uuid=uuid_impuesto,
            uuid_sucursal=uuid_sucursal,
            uuid_factura=uuid_factura,
            uuid_impuesto=uuid_impuesto_catalogo,
            base_calculo=base_calculo,
            porcentaje_aplicado=porcentaje_aplicado,
            valor=valor,
            created_at=now,
        )
        session.add(new_impuesto)
        await session.commit()


def _admin_jwt(*, actor_uuid: uuid_lib.UUID, permitidas: list[uuid_lib.UUID]) -> str:
    return issue_token(
        subject_uuid=actor_uuid,
        issuer="admin-test",
        claims={
            "rol": "admin",
            "sucursales_permitidas": [str(u) for u in permitidas],
            "sucursal": str(permitidas[0]) if permitidas else None,
        },
    )


async def _get(fastapi_app: FastAPI, url: str, token: str) -> httpx.Response:
    transport = ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        return await c.get(url, headers={"Authorization": f"Bearer {token}"})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_factura_impuestos_filter_by_uuid_factura_returns_only_matching(
    pg_engine, pg_dsn
) -> None:
    """X.1b scenario #1 — REGRESSION TEST for Bug #1.

    Seed 2 impuestos of F and 1 impuesto of F2. ``?uuid_factura=F``
    returns only the 2 matching impuestos. Pre-fix: returned all 3.
    """
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)

    f = uuid_lib.uuid4()
    f2 = uuid_lib.uuid4()
    await _seed_factura_impuesto(
        pg_engine, uuid_impuesto=uuid_lib.uuid4(),
        uuid_factura=f, uuid_sucursal=branch,
        base_calculo="1000.0000", porcentaje_aplicado="0.1900", valor="190.0000",
    )
    await _seed_factura_impuesto(
        pg_engine, uuid_impuesto=uuid_lib.uuid4(),
        uuid_factura=f, uuid_sucursal=branch,
        base_calculo="2000.0000", porcentaje_aplicado="0.1900", valor="380.0000",
    )
    await _seed_factura_impuesto(
        pg_engine, uuid_impuesto=uuid_lib.uuid4(),
        uuid_factura=f2, uuid_sucursal=branch,
        base_calculo="3000.0000", porcentaje_aplicado="0.1900", valor="570.0000",
    )

    fastapi_app = create_app()
    admin_actor = uuid_lib.uuid4()
    token = _admin_jwt(actor_uuid=admin_actor, permitidas=[branch])

    response = await _get(
        fastapi_app,
        f"/api/v1/facturacion/factura-impuestos?uuid_factura={f}",
        token,
    )
    assert response.status_code == 200
    body = response.json()
    items = body["items"]
    assert len(items) == 2
    assert all(item["uuid_factura"] == str(f) for item in items)
    assert {item["valor"] for item in items} == {"190.0000", "380.0000"}


async def test_factura_impuestos_filter_empty_uuid_returns_zero_items(
    pg_engine, pg_dsn
) -> None:
    """X.1b scenario #2.

    Non-existent ``uuid_factura`` returns 0 items. Pre-fix: returned the
    full global set.
    """
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)

    f = uuid_lib.uuid4()
    await _seed_factura_impuesto(
        pg_engine, uuid_impuesto=uuid_lib.uuid4(),
        uuid_factura=f, uuid_sucursal=branch,
    )

    fastapi_app = create_app()
    admin_actor = uuid_lib.uuid4()
    token = _admin_jwt(actor_uuid=admin_actor, permitidas=[branch])

    response = await _get(
        fastapi_app,
        "/api/v1/facturacion/factura-impuestos?uuid_factura=00000000-0000-0000-0000-000000000000",
        token,
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_factura_impuestos_no_filter_returns_global_list(
    pg_engine, pg_dsn
) -> None:
    """X.1b scenario #3 (backward compat)."""
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)

    f1 = uuid_lib.uuid4()
    f2 = uuid_lib.uuid4()
    for i in range(3):
        await _seed_factura_impuesto(
            pg_engine, uuid_impuesto=uuid_lib.uuid4(),
            uuid_factura=f1, uuid_sucursal=branch,
        )
    for i in range(2):
        await _seed_factura_impuesto(
            pg_engine, uuid_impuesto=uuid_lib.uuid4(),
            uuid_factura=f2, uuid_sucursal=branch,
        )

    fastapi_app = create_app()
    admin_actor = uuid_lib.uuid4()
    token = _admin_jwt(actor_uuid=admin_actor, permitidas=[branch])

    response = await _get(
        fastapi_app,
        "/api/v1/facturacion/factura-impuestos?limit=200",
        token,
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 5
    distinct_facturas = {item["uuid_factura"] for item in items}
    assert distinct_facturas == {str(f1), str(f2)}


async def test_factura_impuestos_filter_with_cursor_pagination(
    pg_engine, pg_dsn
) -> None:
    """X.1b scenario #4.

    El filter se aplica ANTES de la paginación. Con 5 impuestos de F,
    page 1 retorna 2, page 2 retorna 2, page 3 retorna 1.
    """
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)

    f = uuid_lib.uuid4()
    other = uuid_lib.uuid4()
    for i in range(5):
        await _seed_factura_impuesto(
            pg_engine, uuid_impuesto=uuid_lib.uuid4(),
            uuid_factura=f, uuid_sucursal=branch,
        )
    for i in range(3):
        await _seed_factura_impuesto(
            pg_engine, uuid_impuesto=uuid_lib.uuid4(),
            uuid_factura=other, uuid_sucursal=branch,
        )

    fastapi_app = create_app()
    admin_actor = uuid_lib.uuid4()
    token = _admin_jwt(actor_uuid=admin_actor, permitidas=[branch])

    page1 = await _get(
        fastapi_app,
        f"/api/v1/facturacion/factura-impuestos?uuid_factura={f}&limit=2",
        token,
    )
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["items"]) == 2
    assert all(item["uuid_factura"] == str(f) for item in body1["items"])
    assert body1["next_cursor"] is not None

    page2 = await _get(
        fastapi_app,
        f"/api/v1/facturacion/factura-impuestos?uuid_factura={f}&limit=2&cursor={body1['next_cursor']}",
        token,
    )
    assert page2.status_code == 200
    body2 = page2.json()
    assert len(body2["items"]) == 2
    assert all(item["uuid_factura"] == str(f) for item in body2["items"])

    page3 = await _get(
        fastapi_app,
        f"/api/v1/facturacion/factura-impuestos?uuid_factura={f}&limit=2&cursor={body2['next_cursor']}",
        token,
    )
    assert page3.status_code == 200
    body3 = page3.json()
    assert len(body3["items"]) == 1
    assert body3["items"][0]["uuid_factura"] == str(f)
    assert body3["next_cursor"] is None
