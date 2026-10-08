"""test_router_factory_read_non_versioned.py — the generic read routes built by
``router_factory.make_router`` must never answer 500.

THE DEFECT (live verification, 2026-10): ``GET /api/v1/facturacion/facturas/{uuid}``
returned 500 ``AttributeError: type object 'Facturas' has no attribute
'vigente_hasta'``. ``get_endpoint`` always called ``repo.versioned.current_version``,
which filters on ``vigente_hasta`` — a column only the ``[V]`` classes have. The
``[L-E]``/``[L-W]``/``[A]`` models the factory also exposes (facturas, ingresos,
salidas, ...) have no ``vigente_*`` columns.

This walks EVERY ``make_router`` route of both apps (branch + cloud admin) and
calls ``GET <list>`` and ``GET <list>/{random uuid}`` with a real issuer token:
200 for the list, 404 for the unknown uuid, never a 5xx.
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest
from _seeds import ensure_usuario, grant_admin_scope


def _factory_routes(app) -> tuple[list[str], list[str]]:
    """(list paths, detail paths) of every ``make_router`` GET route of ``app``.

    FastAPI materialises included routers lazily, so the routes are read from
    the OpenAPI schema; the factory's endpoints are named ``list_endpoint`` /
    ``get_endpoint`` (their ``operationId`` prefix).
    """
    lists: list[str] = []
    details: list[str] = []
    for path, item in app.openapi()["paths"].items():
        op_id = (item.get("get") or {}).get("operationId", "")
        if op_id.startswith("list_endpoint_"):
            lists.append(path)
        elif op_id.startswith("get_endpoint_"):
            details.append(path)
    return sorted(lists), sorted(details)


@pytest.mark.parametrize("app", ["sucursal", "admin"], indirect=True)
async def test_generic_list_and_detail_routes_never_500(
    app, client, pg_engine, alembic_upgrade, mint_admin_jwt, mint_operador_jwt
) -> None:
    fastapi_app = client._transport.app  # type: ignore[attr-defined]
    lists, details = _factory_routes(fastapi_app)
    assert lists and details, "no make_router routes discovered"

    sucursal = uuid_lib.uuid4()
    admin = uuid_lib.uuid4()
    operador = uuid_lib.uuid4()
    await ensure_usuario(pg_engine, admin, rol="admin")
    await ensure_usuario(pg_engine, operador, rol="operador")
    await grant_admin_scope(pg_engine, admin, [sucursal])
    attempts = [
        {
            "Authorization": f"Bearer {mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[sucursal])}",
            "X-Sucursal-Context": str(sucursal),
        },
        {
            "Authorization": f"Bearer {mint_operador_jwt(actor_uuid=operador, sucursal_uuid=sucursal)}",
        },
    ]

    problems: list[str] = []
    reached: list[str] = []
    gated: list[str] = []

    async def probe(url: str, ok_status: int) -> None:
        statuses = []
        for headers in attempts:
            try:
                resp = await client.get(url, headers=headers)
            except Exception as exc:  # the ASGI transport re-raises unhandled 500s
                statuses.append(500)
                problems.append(f"{url}: raised {type(exc).__name__}: {exc}")
                continue
            statuses.append(resp.status_code)
        if any(s >= 500 for s in statuses):
            problems.append(f"{url}: {statuses} (a 5xx)")
        elif ok_status in statuses:
            reached.append(url)
        else:  # auth-gated for both tokens (custom permission): not a read bug
            gated.append(url)

    for path in lists:
        if "{" in path:
            continue
        await probe(path, 200)
    for path in details:
        if path.count("{") != 1:
            continue
        await probe(path.replace("{uuid}", str(uuid_lib.uuid4())), 404)

    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_detail_of_a_non_versioned_row_is_200_and_respects_tenant_scope(
    client, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    from datetime import date, timedelta
    from decimal import Decimal

    from parkos_core.models.L_E.facturas import Facturas
    from sqlalchemy.ext.asyncio import async_sessionmaker

    mine = uuid_lib.uuid4()
    other = uuid_lib.uuid4()
    admin = uuid_lib.uuid4()
    await ensure_usuario(pg_engine, admin, rol="admin")
    await grant_admin_scope(pg_engine, admin, [mine, other])

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = Facturas(
            uuid=uuid_lib.uuid4(),
            fecha_retencion_hasta=date.today() + timedelta(days=5 * 365),
            uuid_sucursal=mine,
            subtotal=Decimal("100"),
            descuento=Decimal("0"),
            total=Decimal("119"),
        )
        session.add(row)
        await session.commit()
        factura_uuid = row.uuid

    token = mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[mine, other])
    url = f"/api/v1/facturacion/facturas/{factura_uuid}"

    ok = await client.get(
        url, headers={"Authorization": f"Bearer {token}", "X-Sucursal-Context": str(mine)}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["uuid"] == str(factura_uuid)

    foreign = await client.get(
        url, headers={"Authorization": f"Bearer {token}", "X-Sucursal-Context": str(other)}
    )
    assert foreign.status_code == 404, foreign.text
