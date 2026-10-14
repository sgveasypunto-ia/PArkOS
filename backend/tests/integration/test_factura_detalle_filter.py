"""test_factura_detalle_filter.py — HU-X.1b, DB-backed.

TDD RED → GREEN for the custom handler that fixes
``GET /api/v1/facturacion/factura-detalle?uuid_factura=<uuid>``.

Background (X.1b / Bug #1 of the 2026-10-13 E2E report):
The generic ``make_router`` factory (``api/router_factory.py:189-255``)
defines ``list_endpoint(cursor, limit, session, ctx, _claims)`` WITHOUT a
``Query('uuid_factura', ...)`` param, so FastAPI silently discards any
``?uuid_factura=...`` sent by the client. The factory applies no
``WHERE`` on the filter. The 2026-10-13 E2E proved this: opening the
admin ``FacturaDetalle`` page for ABC123 returned 5 items from 5
different facturas (the response was the full global set).

Resolution:
Replace the factory mount for ``factura-detalle`` with a custom handler
in ``api/v1/facturacion.py`` that mirrors the X.1a ``factura-pagos``
handler. Accepts ``uuid_factura: uuid_lib.UUID | None = Query(None)`` as
an optional param, copies the factory query verbatim
(``select(FacturaDetalle).order_by(created_at, uuid)``), applies
``WHERE FacturaDetalle.uuid_factura == :uuid_factura`` when present, and
preserves the cursor pagination verbatim.

Four scenarios (all gated ``PARKOS_DOCKER_TEST=1`` because they need a
real DB to seed ``prod.factura_detalle`` rows):

  1. ``test_factura_detalle_filter_by_uuid_factura_returns_only_matching``
     — seed 2 detalle of F and 1 detalle of F2; ``?uuid_factura=F``
     returns only the 2 matching detalle. REGRESSION: pre-fix returned
     all 3.
  2. ``test_factura_detalle_filter_empty_uuid_returns_zero_items`` —
     non-existent ``uuid_factura`` returns 0 items.
  3. ``test_factura_detalle_no_filter_returns_global_list`` — backward
     compat: sin filter, retorna la lista global paginada.
  4. ``test_factura_detalle_filter_with_cursor_pagination`` — el filter
     se aplica ANTES de la paginación: con 5 detalle de F, ``limit=2``
     pagina dentro del set filtrado, no contra el universo completo.

The handler reuses the ``_facturacion_issuer_dep`` chain
(``operador-, admin-``) so the tests mint an admin- JWT to satisfy the
issuer dep.
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
    reason="PARKOS_DOCKER_TEST=1 not set; skip factura-detalle filter DB tests",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _truncate(pg_dsn: str) -> None:
    """Truncate every table touched by these scenarios.

    Same CASCADE pattern as ``test_factura_pagos_filter.py``.
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


async def _seed_factura_detalle(
    pg_engine,
    *,
    uuid_detalle: uuid_lib.UUID,
    uuid_factura: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    concepto: str = "Estadia test",
    valor_unitario: str = "1000.0000",
    subtotal: str = "1000.0000",
) -> None:
    """Seed a minimal ``prod.factura_detalle`` row.

    The minimal columns: ``uuid`` (PK part), ``fecha_retencion_hasta``
    (PK part + partition key), ``uuid_factura``, ``concepto``,
    ``cantidad``, ``valor_unitario``, ``subtotal``. ``created_at`` /
    ``created_by`` are stamped by the audit trigger.
    """
    from datetime import UTC, date, datetime, timedelta

    from parkos_core.models.A.factura_detalle import FacturaDetalle

    now = datetime.now(UTC).replace(tzinfo=None)
    frh = date.today() + timedelta(days=5 * 365)
    async with pg_engine() as session:
        new_detalle = FacturaDetalle(
            uuid=uuid_detalle,
            fecha_retencion_hasta=frh,
            uuid_sucursal=uuid_sucursal,
            uuid_factura=uuid_factura,
            concepto=concepto,
            cantidad=1,
            valor_unitario=valor_unitario,
            subtotal=subtotal,
            created_at=now,
        )
        session.add(new_detalle)
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


async def test_factura_detalle_filter_by_uuid_factura_returns_only_matching(
    pg_engine, pg_dsn
) -> None:
    """X.1b scenario #1 — REGRESSION TEST for Bug #1.

    Seed 2 detalle of F and 1 detalle of F2. ``?uuid_factura=F`` returns
    only the 2 matching detalle. Pre-fix: returned all 3 (filter ignored,
    the entire global set of every tenant-visible factura_detalle row).
    """
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)

    f = uuid_lib.uuid4()
    f2 = uuid_lib.uuid4()
    await _seed_factura_detalle(
        pg_engine, uuid_detalle=uuid_lib.uuid4(),
        uuid_factura=f, uuid_sucursal=branch,
        concepto="Estadia F1", valor_unitario="1000.0000", subtotal="1000.0000",
    )
    await _seed_factura_detalle(
        pg_engine, uuid_detalle=uuid_lib.uuid4(),
        uuid_factura=f, uuid_sucursal=branch,
        concepto="Estadia F2", valor_unitario="2000.0000", subtotal="2000.0000",
    )
    await _seed_factura_detalle(
        pg_engine, uuid_detalle=uuid_lib.uuid4(),
        uuid_factura=f2, uuid_sucursal=branch,
        concepto="Estadia F2-other", valor_unitario="3000.0000", subtotal="3000.0000",
    )

    fastapi_app = create_app()
    admin_actor = uuid_lib.uuid4()
    token = _admin_jwt(actor_uuid=admin_actor, permitidas=[branch])

    response = await _get(
        fastapi_app,
        f"/api/v1/facturacion/factura-detalle?uuid_factura={f}",
        token,
    )
    assert response.status_code == 200
    body = response.json()
    items = body["items"]
    assert len(items) == 2
    assert all(item["uuid_factura"] == str(f) for item in items)
    assert {item["concepto"] for item in items} == {"Estadia F1", "Estadia F2"}


async def test_factura_detalle_filter_empty_uuid_returns_zero_items(
    pg_engine, pg_dsn
) -> None:
    """X.1b scenario #2.

    Non-existent ``uuid_factura`` returns 0 items. Pre-fix: returned the
    full global set (filter ignored).
    """
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)

    f = uuid_lib.uuid4()
    await _seed_factura_detalle(
        pg_engine, uuid_detalle=uuid_lib.uuid4(),
        uuid_factura=f, uuid_sucursal=branch,
    )

    fastapi_app = create_app()
    admin_actor = uuid_lib.uuid4()
    token = _admin_jwt(actor_uuid=admin_actor, permitidas=[branch])

    response = await _get(
        fastapi_app,
        "/api/v1/facturacion/factura-detalle?uuid_factura=00000000-0000-0000-0000-000000000000",
        token,
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_factura_detalle_no_filter_returns_global_list(
    pg_engine, pg_dsn
) -> None:
    """X.1b scenario #3 (backward compat).

    Sin filter, el endpoint retorna la lista global paginada (mismo
    comportamiento que antes del fix). Protege contra un over-restrictive
    WHERE accidental.
    """
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)

    f1 = uuid_lib.uuid4()
    f2 = uuid_lib.uuid4()
    for i in range(3):
        await _seed_factura_detalle(
            pg_engine, uuid_detalle=uuid_lib.uuid4(),
            uuid_factura=f1, uuid_sucursal=branch,
            concepto=f"F1 item {i}",
        )
    for i in range(2):
        await _seed_factura_detalle(
            pg_engine, uuid_detalle=uuid_lib.uuid4(),
            uuid_factura=f2, uuid_sucursal=branch,
            concepto=f"F2 item {i}",
        )

    fastapi_app = create_app()
    admin_actor = uuid_lib.uuid4()
    token = _admin_jwt(actor_uuid=admin_actor, permitidas=[branch])

    response = await _get(
        fastapi_app,
        "/api/v1/facturacion/factura-detalle?limit=200",
        token,
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 5
    distinct_facturas = {item["uuid_factura"] for item in items}
    assert distinct_facturas == {str(f1), str(f2)}


async def test_factura_detalle_filter_with_cursor_pagination(
    pg_engine, pg_dsn
) -> None:
    """X.1b scenario #4.

    El filter se aplica ANTES de la paginación. Con 5 detalle de F, page 1
    retorna 2, page 2 retorna 2, page 3 retorna 1; nunca se filtra el
    universo completo.
    """
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)

    f = uuid_lib.uuid4()
    other = uuid_lib.uuid4()
    # 5 detalle of F + 3 of other (que NO deberían aparecer).
    for i in range(5):
        await _seed_factura_detalle(
            pg_engine, uuid_detalle=uuid_lib.uuid4(),
            uuid_factura=f, uuid_sucursal=branch,
            concepto=f"F item {i}",
        )
    for i in range(3):
        await _seed_factura_detalle(
            pg_engine, uuid_detalle=uuid_lib.uuid4(),
            uuid_factura=other, uuid_sucursal=branch,
            concepto=f"other item {i}",
        )

    fastapi_app = create_app()
    admin_actor = uuid_lib.uuid4()
    token = _admin_jwt(actor_uuid=admin_actor, permitidas=[branch])

    # Page 1.
    page1 = await _get(
        fastapi_app,
        f"/api/v1/facturacion/factura-detalle?uuid_factura={f}&limit=2",
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
        f"/api/v1/facturacion/factura-detalle?uuid_factura={f}&limit=2&cursor={body1['next_cursor']}",
        token,
    )
    assert page2.status_code == 200
    body2 = page2.json()
    assert len(body2["items"]) == 2
    assert all(item["uuid_factura"] == str(f) for item in body2["items"])

    # Page 3 — last item, no next_cursor.
    page3 = await _get(
        fastapi_app,
        f"/api/v1/facturacion/factura-detalle?uuid_factura={f}&limit=2&cursor={body2['next_cursor']}",
        token,
    )
    assert page3.status_code == 200
    body3 = page3.json()
    assert len(body3["items"]) == 1
    assert body3["items"][0]["uuid_factura"] == str(f)
    assert body3["next_cursor"] is None
