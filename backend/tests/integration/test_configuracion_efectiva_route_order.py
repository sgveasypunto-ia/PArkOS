"""test_configuracion_efectiva_route_order.py — route-registration-order
regression for ``GET /configuracion/{configuracion-seguridad,
configuracion-caja}/efectiva``.

THE DEFECT (found QA-testing the Sucursal detail "Caja" tab, 2026-10-02)
--------------------------------------------------------------------------
``api/v1/configuracion.py`` used to call ``_mount_config(resource=
"configuracion-seguridad" | "configuracion-caja", ...)`` (which adds a
factory ``GET /configuracion-caja/{uuid}`` route) BEFORE registering the
dedicated ``@router.get("/configuracion-caja/efectiva", ...)`` handler.
FastAPI matches routes in registration order, so a request for the literal
path ``/configuracion-caja/efectiva`` matched the factory's ``{uuid}``
pattern FIRST, with ``uuid="efectiva"`` — Pydantic's UUID parser then
rejects that string and the endpoint 422s (``uuid_parsing``, ``input:
"efectiva"``) instead of ever reaching ``efectiva_caja``'s business logic.
This broke the whole "Base y redondeo" section of the Sucursal detail
"Caja" tab in `web_admin` with "No se pudo cargar la configuración de
caja." Same bug shape for ``configuracion-seguridad/efectiva``.

THE FIX
-------
The dedicated routes are now registered on ``router`` before their
resource's ``_mount_config`` call (see the "ROUTE ORDER" comment in
``configuracion.py``) — same ordering rule ``api/v1/empresa.py`` already
documents and applies for its ``tarifas-sucursal`` dedicated router.

THIS TEST
---------
Pins the HTTP-level routing outcome directly: an ``admin-`` JWT with NO
``X-Sucursal-Context`` header runs in "global mode" (``get_tenant_ctx``,
``auth/tenancy.py`` — the header is optional for ``admin-``, no DB-backed
scope check needed), so no extra seeding (sucursal / usuarios_sucursal /
permisos) is required at all. With nothing configured yet, the business
outcome is a clean 404 (``error: "not_found"``) — the regression signature
to guard against is specifically a 422 with ``loc: ["path", "uuid"]``.
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest

_ADMIN_HTTP_PYTESTMARK = pytest.mark.parametrize("app", ["admin"], indirect=True)


@_ADMIN_HTTP_PYTESTMARK
async def test_configuracion_caja_efectiva_route_resolves_not_the_factory_uuid_route(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
):
    token = mint_admin_jwt()
    uuid_sucursal = uuid_lib.uuid4()

    res = await client.get(
        "/api/v1/configuracion/configuracion-caja/efectiva",
        params={"uuid_sucursal": str(uuid_sucursal)},
        headers={"Authorization": f"Bearer {token}"},
    )

    # The regression signature: a 422 whose error location is the factory's
    # path-level {uuid} parameter trying (and failing) to parse the literal
    # string "efectiva" as a UUID.
    assert res.status_code != 422, res.text
    assert res.status_code == 404, res.text
    body = res.json()
    assert body["detail"]["error"] == "not_found"
    assert body["detail"]["resource"] == "configuracion-caja"


@_ADMIN_HTTP_PYTESTMARK
async def test_configuracion_seguridad_efectiva_route_resolves_not_the_factory_uuid_route(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
):
    token = mint_admin_jwt()
    uuid_sucursal = uuid_lib.uuid4()

    res = await client.get(
        "/api/v1/configuracion/configuracion-seguridad/efectiva",
        params={"uuid_sucursal": str(uuid_sucursal)},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status_code != 422, res.text
    assert res.status_code == 404, res.text
    body = res.json()
    assert body["detail"]["error"] == "not_found"
    assert body["detail"]["resource"] == "configuracion-seguridad"
