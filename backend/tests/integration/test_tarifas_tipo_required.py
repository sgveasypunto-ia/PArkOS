"""test_tarifas_tipo_required.py — pin non-null uuid_tipo_vehiculo/tarifa in POST/PUT.

The 2026-09-29 UX sweep removed the "Cualquiera" cells (null
``uuid_tipo_vehiculo`` and/or null ``uuid_tipo_tarifa``) from the
admin tarifa CRUD UI: the CREATE selects no longer offer a null
option, and EDIT locks both tipo fields as readonly inputs. The
canonical cell-key is now the full tuple
``(uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa)`` with both
tipo columns required (non-null).

This commit mirrors that rule at the API edge so direct API
callers (curl, Postman, sync-agent) cannot bypass it: a POST or
PUT to ``/api/v1/empresa/tarifas-sucursal`` with either
``uuid_tipo_vehiculo`` or ``uuid_tipo_tarifa`` set to null is
rejected by Pydantic with the standard 422 ``"field required"``
detail. The handler code never sees the request, so no special
branch logic is needed — the schema is the contract.

Historical rows with null tipos continue to exist in the DB and
remain visible through ``GET /api/v1/empresa/tarifas-sucursal``
(because ``TarifasSucursalRead`` keeps both fields nullable). Only
writes are strict; that is the regression surface these tests pin.

Tests run via real ASGI + testcontainers Postgres so the full
Pydantic validation + factory sub-router + ``close_and_insert``
path all execute end-to-end.
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest
from _seeds import grant_admin_scope

# Pydantic v2 reports an OMITTED required field as ``missing`` and an explicit
# ``null`` for a non-nullable UUID as ``uuid_type``. Both mean "the tipo is
# required" -- the contract these tests pin.
_REQUIRED_ERROR_TYPES = ("missing", "uuid_type")


async def _grant_permission(pg_engine, *, actor_uuid: uuid_lib.UUID, perm_code: str) -> None:
    """Seed one ``usuarios`` row + one ``permisos_usuario`` row.

    Mirror of the helper in
    ``tests/integration/test_router_factory_payload_body_binding.py``
    and ``test_catalog_tipos_vehiculo_cap.py``.
    """
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


async def _seed_sucursal(pg_engine, uuid_sucursal: uuid_lib.UUID) -> None:
    """Insert a real Empresa + Sucursal so the tarifa FK resolves."""
    from datetime import UTC, datetime

    from parkos_core.models.V.empresa import Empresa
    from parkos_core.models.V.sucursal import Sucursal
    from sqlalchemy.ext.asyncio import async_sessionmaker

    now = datetime.now(UTC).replace(tzinfo=None)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Empresa Tipo Required Test",
                nit=f"904{empresa_uuid.hex[:6]}",
                mensaje_bienvenida="Hola",
                mensaje_salida="Adios",
                regimen="comun",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        session.add(
            Sucursal(
                uuid=uuid_sucursal,
                uuid_empresa=empresa_uuid,
                nombre="Sucursal Tipo Required Test",
                ciudad="Bogota",
                direccion="Calle 1",
                telefono="000",
                prefijo_nombre=f"T{uuid_sucursal.hex[:6]}",
                horario="24/7",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.commit()


async def _seed_tipo_vehiculo(pg_engine, *, uuid_tipo: uuid_lib.UUID, nombre: str) -> None:
    """Insert an active ``tipos_vehiculo`` row."""
    from datetime import UTC, datetime

    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
    from sqlalchemy.ext.asyncio import async_sessionmaker

    now = datetime.now(UTC).replace(tzinfo=None)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            TiposVehiculo(
                uuid=uuid_tipo,
                tipo=nombre,
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.commit()


async def _seed_tipo_tarifa(pg_engine, *, uuid_tipo: uuid_lib.UUID, nombre: str) -> None:
    """Insert an active ``tipo_tarifa`` row."""
    from datetime import UTC, datetime

    from parkos_core.models.V.tipo_tarifa import TipoTarifa
    from sqlalchemy.ext.asyncio import async_sessionmaker

    now = datetime.now(UTC).replace(tzinfo=None)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            TipoTarifa(
                uuid=uuid_tipo,
                tipo=nombre,
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.commit()


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_post_tarifa_uuid_tipo_vehiculo_null_returns_422(
    client, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """POST with ``uuid_tipo_vehiculo=null`` (and uuid_tipo_tarifa set)
    must return 422. FastAPI's Pydantic layer surfaces the missing
    field in the ``detail``.
    """
    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    tipo_tarifa_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_tipo_vehiculo(
        pg_engine, uuid_tipo=tipo_vehiculo_uuid, nombre="carro"
    )
    await _seed_tipo_tarifa(
        pg_engine, uuid_tipo=tipo_tarifa_uuid, nombre="hora"
    )

    actor_uuid = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    await grant_admin_scope(pg_engine, actor_uuid, [branch_uuid])
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])

    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": None,
            "uuid_tipo_tarifa": str(tipo_tarifa_uuid),
            "valor": "1500",
            "valor_plena": "2000",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert resp.status_code == 422, f"got {resp.status_code}: {resp.text}"
    # FastAPI surfaces the missing field in ``detail[].loc``.
    detail = resp.json()["detail"]
    assert any(
        err["loc"] == ["body", "uuid_tipo_vehiculo"]
        and err["type"] in _REQUIRED_ERROR_TYPES
        for err in detail
    ), detail


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_post_tarifa_uuid_tipo_tarifa_null_returns_422(
    client, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """Symmetric: null ``uuid_tipo_tarifa`` is also a hard 422."""
    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    tipo_tarifa_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_tipo_vehiculo(
        pg_engine, uuid_tipo=tipo_vehiculo_uuid, nombre="carro"
    )
    await _seed_tipo_tarifa(
        pg_engine, uuid_tipo=tipo_tarifa_uuid, nombre="hora"
    )

    actor_uuid = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    await grant_admin_scope(pg_engine, actor_uuid, [branch_uuid])
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])

    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": str(tipo_vehiculo_uuid),
            "uuid_tipo_tarifa": None,
            "valor": "1500",
            "valor_plena": "2000",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert resp.status_code == 422, f"got {resp.status_code}: {resp.text}"
    detail = resp.json()["detail"]
    assert any(
        err["loc"] == ["body", "uuid_tipo_tarifa"]
        and err["type"] in _REQUIRED_ERROR_TYPES
        for err in detail
    ), detail


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_post_tarifa_both_tipos_null_returns_422(
    client, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """The exact scenario the operator reported: POST with
    ``uuid_tipo_vehiculo=null`` AND ``uuid_tipo_tarifa=null`` (the
    "Cualquiera x Cualquiera" cell) must be rejected. Both fields
    appear as missing in the detail.
    """
    branch_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)

    actor_uuid = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    await grant_admin_scope(pg_engine, actor_uuid, [branch_uuid])
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])

    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": None,
            "uuid_tipo_tarifa": None,
            "valor": "1000",
            "valor_plena": "5000",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert resp.status_code == 422, f"got {resp.status_code}: {resp.text}"
    detail = resp.json()["detail"]
    missing_locs = {
        tuple(err["loc"]) for err in detail if err["type"] in _REQUIRED_ERROR_TYPES
    }
    assert ("body", "uuid_tipo_vehiculo") in missing_locs
    assert ("body", "uuid_tipo_tarifa") in missing_locs


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_post_tarifa_both_tipos_set_succeeds(
    client, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """Regression — happy path with both tipos set returns 201.
    Pins that the strict-required schema still accepts valid payloads.
    """
    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    tipo_tarifa_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_tipo_vehiculo(
        pg_engine, uuid_tipo=tipo_vehiculo_uuid, nombre="carro"
    )
    await _seed_tipo_tarifa(
        pg_engine, uuid_tipo=tipo_tarifa_uuid, nombre="hora"
    )

    actor_uuid = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    await grant_admin_scope(pg_engine, actor_uuid, [branch_uuid])
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])

    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": str(tipo_vehiculo_uuid),
            "uuid_tipo_tarifa": str(tipo_tarifa_uuid),
            "valor": "1500.50",
            "valor_plena": "2000.00",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert resp.status_code == 201, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["uuid_tipo_vehiculo"] == str(tipo_vehiculo_uuid)
    assert body["uuid_tipo_tarifa"] == str(tipo_tarifa_uuid)


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_put_tarifa_cannot_clear_tipo_via_update(
    client, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """PUT that tries to clear a tipo via null must be rejected.
    The cell-key is fixed at creation; the operator should CREATE a
    new tarifa in a different cell rather than mutate the tipo
    columns via PUT.
    """
    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    tipo_tarifa_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_tipo_vehiculo(
        pg_engine, uuid_tipo=tipo_vehiculo_uuid, nombre="carro"
    )
    await _seed_tipo_tarifa(
        pg_engine, uuid_tipo=tipo_tarifa_uuid, nombre="hora"
    )

    actor_uuid = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    await grant_admin_scope(pg_engine, actor_uuid, [branch_uuid])
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])

    # Seed a tarifa (happy path).
    post = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": str(tipo_vehiculo_uuid),
            "uuid_tipo_tarifa": str(tipo_tarifa_uuid),
            "valor": "1500",
            "valor_plena": "2000",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert post.status_code == 201, post.text
    tarifa_uuid = post.json()["uuid"]

    # PUT trying to null the tipo_vehiculo field.
    put = await client.put(
        f"/api/v1/empresa/tarifas-sucursal/{tarifa_uuid}",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": None,
            "uuid_tipo_tarifa": str(tipo_tarifa_uuid),
            "valor": "1800",
            "valor_plena": "2400",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert put.status_code == 422, f"got {put.status_code}: {put.text}"
    detail = put.json()["detail"]
    assert any(
        err["loc"] == ["body", "uuid_tipo_vehiculo"]
        and err["type"] in _REQUIRED_ERROR_TYPES
        for err in detail
    ), detail