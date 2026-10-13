"""test_factura_pagos_filter.py — HU-X.1a / REQ-OPS-203, DB-backed.

TDD RED → GREEN for the custom handler that fixes
``GET /api/v1/facturacion/factura-pagos?uuid_factura=<uuid>``.

Background (REQ-OPS-203):
The generic ``make_router`` factory (``api/router_factory.py:189-255``)
defines ``list_endpoint(cursor, limit, session, ctx, _claims)`` WITHOUT a
``Query('uuid_factura', ...)`` param, so FastAPI silently discards any
``?uuid_factura=...`` sent by the client. The factory applies no
``WHERE`` on the filter. Verified with 4 curl scenarios in
``openspec/changes/hu-x-facturacion-admin/exploration.md`` §2.4: 7 items
returned with/without the filter.

Resolution:
Replace the factory mount for ``factura-pagos`` with a custom handler in
``api/v1/facturacion.py`` that:
1. Accepts ``uuid_factura: uuid_lib.UUID | None = Query(None)`` as an
   optional param.
2. Copies the factory query verbatim
   (``select(FacturaPagos).order_by(created_at, uuid)``).
3. Applies ``WHERE FacturaPagos.uuid_factura == :uuid_factura`` when the
   param is present.
4. Preserves the cursor pagination verbatim (same shape).

Four scenarios (all gated ``PARKOS_DOCKER_TEST=1`` because they need a
real DB to seed ``prod.factura_pagos`` rows):

  1. ``test_factura_pagos_filter_by_uuid_factura_returns_only_matching`` —
     seed 2 pagos of F and 1 pago of F2; ``?uuid_factura=F`` returns
     only the 2 matching pagos (REGRESSION: pre-fix returned all 3).
  2. ``test_factura_pagos_filter_empty_uuid_returns_zero_items`` —
     ``?uuid_factura=00000000-...`` returns 0 items.
  3. ``test_factura_pagos_no_filter_returns_global_list`` — backward
     compat: sin filter, retorna la lista global paginada (comportamiento
     pre-fix preservado).
  4. ``test_factura_pagos_filter_with_cursor_pagination`` — el filter se
     aplica ANTES de la paginación: con 5 pagos de F, ``limit=2&cursor=...``
     pagina dentro del set filtrado, no contra el universo completo.

All tests use httpx + ASGITransport against a FastAPI app built on the
testcontainers DB. The handler reuses the ``_facturacion_issuer_dep``
chain (``operador-, admin-``) so the tests mint an admin- JWT to satisfy
the issuer dep.
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
    reason="PARKOS_DOCKER_TEST=1 not set; skip factura-pagos filter DB tests",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _truncate(pg_dsn: str) -> None:
    """Truncate every table touched by these scenarios.

    Same CASCADE pattern as the other integration tests in the suite.
    """
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

    from sqlalchemy import text

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


async def _seed_factura_pago(
    pg_engine,
    *,
    uuid_factura_pago: uuid_lib.UUID,
    uuid_factura: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    valor: str = "1000.0000",
) -> None:
    """Seed a minimal ``prod.factura_pagos`` row.

    The minimal columns are the ones enforced NOT NULL by the schema:
    ``uuid`` (PK), ``fecha_retencion_hasta``, ``valor``, ``tipo_movimiento``,
    ``timestamp_evento`` (defaults), ``uuid_factura``, ``medio_pago``.
    ``created_at`` / ``created_by`` are stamped by the audit trigger.
    """
    from datetime import UTC, date, datetime, timedelta

    from parkos_core.models.A.factura_pagos import FacturaPagos

    now = datetime.now(UTC).replace(tzinfo=None)
    frh = date.today() + timedelta(days=5 * 365)
    async with pg_engine() as session:
        new_pago = FacturaPagos(
            uuid=uuid_factura_pago,
            fecha_retencion_hasta=frh,
            uuid_sucursal=uuid_sucursal,
            uuid_factura=uuid_factura,
            medio_pago="efectivo",
            valor=valor,
            tipo_movimiento="pago",
            timestamp_evento=now,
        )
        session.add(new_pago)
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


async def test_factura_pagos_filter_by_uuid_factura_returns_only_matching(
    pg_engine, pg_dsn
) -> None:
    """REQ-OPS-203 scenario #1.

    Seed 2 pagos of F and 1 pago of F2. ``?uuid_factura=F`` returns only
    the 2 matching pagos. Pre-fix: returned all 3 (filter ignored).
    """
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)

    f = uuid_lib.uuid4()
    f2 = uuid_lib.uuid4()
    await _seed_factura_pago(
        pg_engine, uuid_factura_pago=uuid_lib.uuid4(),
        uuid_factura=f, uuid_sucursal=branch, valor="1000.0000",
    )
    await _seed_factura_pago(
        pg_engine, uuid_factura_pago=uuid_lib.uuid4(),
        uuid_factura=f, uuid_sucursal=branch, valor="2000.0000",
    )
    await _seed_factura_pago(
        pg_engine, uuid_factura_pago=uuid_lib.uuid4(),
        uuid_factura=f2, uuid_sucursal=branch, valor="3000.0000",
    )

    fastapi_app = create_app()
    admin_actor = uuid_lib.uuid4()
    token = _admin_jwt(actor_uuid=admin_actor, permitidas=[branch])

    response = await _get(
        fastapi_app,
        f"/api/v1/facturacion/factura-pagos?uuid_factura={f}",
        token,
    )
    assert response.status_code == 200
    body = response.json()
    items = body["items"]
    assert len(items) == 2
    assert all(item["uuid_factura"] == str(f) for item in items)
    assert {item["valor"] for item in items} == {"1000.0000", "2000.0000"}


async def test_factura_pagos_filter_empty_uuid_returns_zero_items(
    pg_engine, pg_dsn
) -> None:
    """REQ-OPS-203 scenario #2.

    Non-existent ``uuid_factura`` returns 0 items. Pre-fix: returned the
    full global set (filter ignored).
    """
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)

    f = uuid_lib.uuid4()
    await _seed_factura_pago(
        pg_engine, uuid_factura_pago=uuid_lib.uuid4(),
        uuid_factura=f, uuid_sucursal=branch,
    )

    fastapi_app = create_app()
    admin_actor = uuid_lib.uuid4()
    token = _admin_jwt(actor_uuid=admin_actor, permitidas=[branch])

    response = await _get(
        fastapi_app,
        f"/api/v1/facturacion/factura-pagos?uuid_factura=00000000-0000-0000-0000-000000000000",
        token,
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_factura_pagos_no_filter_returns_global_list(
    pg_engine, pg_dsn
) -> None:
    """REQ-OPS-203 scenario #3 (backward compat).

    Sin filter, el endpoint retorna la lista global paginada (mismo
    comportamiento que antes del fix). Este test protege contra un
    over-restrictive WHERE accidental.
    """
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)

    f1 = uuid_lib.uuid4()
    f2 = uuid_lib.uuid4()
    for _ in range(3):
        await _seed_factura_pago(
            pg_engine, uuid_factura_pago=uuid_lib.uuid4(),
            uuid_factura=f1, uuid_sucursal=branch,
        )
    for _ in range(2):
        await _seed_factura_pago(
            pg_engine, uuid_factura_pago=uuid_lib.uuid4(),
            uuid_factura=f2, uuid_sucursal=branch,
        )

    fastapi_app = create_app()
    admin_actor = uuid_lib.uuid4()
    token = _admin_jwt(actor_uuid=admin_actor, permitidas=[branch])

    response = await _get(
        fastapi_app,
        "/api/v1/facturacion/factura-pagos?limit=200",
        token,
    )
    assert response.status_code == 200
    items = response.json()["items"]
    # 5 total pagos across 2 facturas.
    assert len(items) == 5
    distinct_facturas = {item["uuid_factura"] for item in items}
    assert distinct_facturas == {str(f1), str(f2)}


async def test_factura_pagos_filter_with_cursor_pagination(
    pg_engine, pg_dsn
) -> None:
    """REQ-OPS-203 scenario #4.

    El filter se aplica ANTES de la paginación. Con 5 pagos de F, page 1
    retorna 2, page 2 retorna 2, page 3 retorna 1; nunca se filtra el
    universo completo.
    """
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)

    f = uuid_lib.uuid4()
    other = uuid_lib.uuid4()
    # 5 pagos de F + 3 de other (que NO deberían aparecer).
    for _ in range(5):
        await _seed_factura_pago(
            pg_engine, uuid_factura_pago=uuid_lib.uuid4(),
            uuid_factura=f, uuid_sucursal=branch,
        )
    for _ in range(3):
        await _seed_factura_pago(
            pg_engine, uuid_factura_pago=uuid_lib.uuid4(),
            uuid_factura=other, uuid_sucursal=branch,
        )

    fastapi_app = create_app()
    admin_actor = uuid_lib.uuid4()
    token = _admin_jwt(actor_uuid=admin_actor, permitidas=[branch])

    # Page 1.
    page1 = await _get(
        fastapi_app,
        f"/api/v1/facturacion/factura-pagos?uuid_factura={f}&limit=2",
        token,
    )
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["items"]) == 2
    assert all(item["uuid_factura"] == str(f) for item in body1["items"])
    assert body1["next_cursor"] is not None

    # Page 2.
    page2 = await _get(
        fastapi_app,
        f"/api/v1/facturacion/factura-pagos?uuid_factura={f}&limit=2&cursor={body1['next_cursor']}",
        token,
    )
    assert page2.status_code == 200
    body2 = page2.json()
    assert len(body2["items"]) == 2
    assert all(item["uuid_factura"] == str(f) for item in body2["items"])

    # Page 3 — last item, no next_cursor.
    page3 = await _get(
        fastapi_app,
        f"/api/v1/facturacion/factura-pagos?uuid_factura={f}&limit=2&cursor={body2['next_cursor']}",
        token,
    )
    assert page3.status_code == 200
    body3 = page3.json()
    assert len(body3["items"]) == 1
    assert body3["items"][0]["uuid_factura"] == str(f)
    assert body3["next_cursor"] is None
