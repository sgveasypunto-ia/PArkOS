"""test_router_factory_payload_body_binding.py — regression coverage for a
real defect confirmed while doing manual QA against the live Docker cloud
stack (2026-09-09): ``POST /api/v1/empresa/sucursal`` (and every OTHER
``create``/``update`` endpoint ``router_factory.make_router`` builds) fails
with a real HTTP client, returning 422 ``{"loc": ["query", "payload"], "msg":
"Field required"}`` — FastAPI never bound ``payload`` to the JSON request
body at all.

Root cause: ``router_factory.py`` has ``from __future__ import annotations``
(PEP 563) — every annotation in the module becomes a lazily-evaluated
string. ``create_endpoint``/``update_endpoint`` declare their ``payload``
parameter with NO annotation at all (``payload,``), because
``payload: create_schema`` would have been just as broken: ``create_schema``
is a local closure variable of the enclosing ``make_router`` call, not a
module global, so FastAPI's ``typing.get_type_hints()`` (which resolves
string annotations against the function's ``__globals__``) could never
resolve it. Left unannotated, FastAPI's dependant-building falls back to
treating ``payload`` as a required ``str`` QUERY parameter — it was never
wired to the request body.

This was never caught by any existing test: ``test_e2e_full_catalog_sync.py``
and friends create rows by calling ``repo.versioned.close_and_insert``
directly in Python, never through a real HTTP request — the ``client``
httpx fixture (``conftest.py``) and ``mint_admin_jwt`` fixture both existed
already but were, before this test, never actually exercised together
against a ``make_router``-built endpoint.

Blast radius: EVERY resource mounted via ``router_factory.make_router`` —
the 9 ``catalogos`` (T-PR3), ``empresa``/``sucursal``/``documentos``/
``tarifas-sucursal``/``cantidad-vehiculos-sucursal`` (T-PR4), and the
``clientes`` family (T-PR5) — roughly 15-20 resources. This test proves the
fix on TWO of them (``sucursal`` — the one this QA session needed — and
``tipos-vehiculo``, a plain catalog) to confirm it is the shared factory
that was broken, not a ``sucursal``-specific bug.
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest


async def _grant_permission(pg_engine, *, actor_uuid: uuid_lib.UUID, perm_code: str) -> None:
    """Insert a real ``usuarios`` row (``permisos_usuario.uuid_usuario`` has a
    real FK to it) plus one ``permisos_usuario`` row for an already-seeded
    ``permisos`` code (migration 0002 seeds ``config_sucursal``/
    ``config_catalogo``)."""
    from parkos_core.models.V.permisos import Permisos
    from parkos_core.models.V.permisos_usuario import PermisosUsuario
    from parkos_core.models.V.usuarios import Usuarios
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Usuarios(
                uuid=actor_uuid,
                nombre="Test",
                apellido="Actor",
                email=f"{actor_uuid}@example.com",
                password_hash="test-hash",
                rol="admin",
            )
        )
        permiso = (
            await session.execute(
                select(Permisos).where(
                    Permisos.permiso == perm_code, Permisos.vigente_hasta.is_(None)
                )
            )
        ).scalar_one()
        session.add(PermisosUsuario(uuid_usuario=actor_uuid, uuid_permiso=permiso.uuid))
        await session.commit()


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_create_sucursal_via_real_http_accepts_json_body(
    client, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """``POST /api/v1/empresa/sucursal`` over a real ASGI HTTP request must
    bind the JSON body to ``SucursalCreate`` and return 201 with the created
    row — not a 422 asking for ``payload`` as a query parameter."""
    from parkos_core.models.V.sucursal import Sucursal
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor_uuid = uuid_lib.uuid4()
    sucursal_ctx = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_sucursal")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[sucursal_ctx])

    resp = await client.post(
        "/api/v1/empresa/sucursal",
        json={"nombre": "Sucursal Router Factory Test", "ciudad": "Bogota"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(sucursal_ctx),
        },
    )
    assert resp.status_code == 201, (
        f"expected 201 with the JSON body bound to SucursalCreate, got "
        f"{resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body["nombre"] == "Sucursal Router Factory Test"

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        found = (
            await session.execute(
                select(Sucursal).where(Sucursal.uuid == uuid_lib.UUID(body["uuid"]))
            )
        ).scalar_one_or_none()
        assert found is not None, "the row must really exist in the DB, not just in the response"
        assert found.nombre == "Sucursal Router Factory Test"


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_create_tipos_vehiculo_via_real_http_accepts_json_body(
    client, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """Generalization check: a SECOND, unrelated ``make_router`` resource
    (a plain ``catalogos`` entry, not ``empresa``) must ALSO accept a real
    JSON body — proves the fix is in the shared factory, not sucursal-specific."""
    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor_uuid = uuid_lib.uuid4()
    sucursal_ctx = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_catalogo")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[sucursal_ctx])

    tipo_value = f"tipo-{uuid_lib.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/catalogos/tipos-vehiculo",
        json={"tipo": tipo_value},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(sucursal_ctx),
        },
    )
    assert resp.status_code == 201, (
        f"expected 201 with the JSON body bound to TiposVehiculoCreate, got "
        f"{resp.status_code}: {resp.text}"
    )
    body = resp.json()

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        found = (
            await session.execute(
                select(TiposVehiculo).where(TiposVehiculo.uuid == uuid_lib.UUID(body["uuid"]))
            )
        ).scalar_one_or_none()
        assert found is not None
        assert found.tipo == tipo_value
