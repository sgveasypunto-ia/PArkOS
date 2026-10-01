"""test_catalog_tipos_vehiculo_cap.py — pin the 5-active-tipos guard and
the BR3 "subscripciones vigentes dependientes" PUT guard.

The dedicated POST handler in
``backend/packages/parkos_core/src/parkos_core/api/v1/catalogos.py``
enforces ``tipos_vehiculo_max_reached`` (HTTP 409) when the count of
currently-open tipos_vehiculo rows is already 5 (the canonical set
seeded by migration 0062_canonical_tipos_vehiculo: carro, moto,
bicicleta, patineta, otro).

Without this guard the factory's bare
``make_router.create_endpoint`` would happily INSERT a 6th row — and
since ``tipos_vehiculo`` is a level-0 sync catalog (entries propagate
to every branch via ``sync_entries_v.py:118``), the row would
replicate to all branches. The placa detector
(electron-sucursal/src/lib/validation/placa.ts:67) hardcodes
``["carro", "moto", "bicicleta", "patineta"]``, so a typo (``"motoo"``)
or a 6th canonical entry would silently bypass it.

The dedicated PUT handler (HU-F14.1-T5, BR3, plan.md CU-12 E3) enforces
``tipo_vehiculo_con_subscripciones_vigentes`` (HTTP 409) when the
``tipos_vehiculo`` row being closed still has a vigente ``vehiculos``
row pointing at it (``uuid_tipo_vehiculo``) covered by a vigente
``subscripciones_cliente`` (via the ``subscripcion_vehiculos``
junction) — closing it would regenerate the business ``uuid`` (see
``repo.versioned.close_and_insert``'s "UUID REGENERATION" docstring)
and silently orphan that subscriber's vehicle-type reference, since
``tipos_vehiculo`` has no FK-propagation hook registered there (unlike
``Sucursal``).

These tests run via real ASGI + testcontainers Postgres so the full
factory sub-router, the dedicated handlers, and the
``close_and_insert`` call all execute end-to-end.
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest


async def _grant_permission(pg_engine, *, actor_uuid: uuid_lib.UUID, perm_code: str) -> None:
    """Seed one ``usuarios`` row + one ``permisos_usuario`` row.

    Mirrors the helper in
    ``tests/integration/test_router_factory_payload_body_binding.py``.
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


async def _seed_active_tipos_vehiculo(pg_engine, tipos: list[str]) -> None:
    """Insert N active ``tipos_vehiculo`` rows. Bypasses the API to seed
    fast and avoid the cap we're trying to test."""
    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        for tipo in tipos:
            session.add(
                TiposVehiculo(
                    tipo=tipo,
                    vigente_hasta=None,
                    estado="activo",
                )
            )
        await session.commit()


async def _truncate_tipos_vehiculo(pg_engine) -> None:
    """Wipe the catalog for isolation between tests."""
    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        for row in (await session.execute(TiposVehiculo.__table__.select())).scalars():
            await session.delete(row)
        await session.commit()


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_sextu_tipo_returns_409_max_reached(
    client, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """Seed 5 active tipos, then attempt the 6th POST → 409 with detail
    ``{"error": "tipos_vehiculo_max_reached", "limit": 5, "current": 5}``.
    """
    await _truncate_tipos_vehiculo(pg_engine)
    await _seed_active_tipos_vehiculo(
        pg_engine, ["carro", "moto", "bicicleta", "patineta", "otro"]
    )

    actor_uuid = uuid_lib.uuid4()
    sucursal_ctx = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_catalogo")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[sucursal_ctx])

    resp = await client.post(
        "/api/v1/catalogos/tipos-vehiculo",
        json={"tipo": "sexto_tipo"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(sucursal_ctx),
        },
    )
    assert resp.status_code == 409, f"got {resp.status_code}: {resp.text}"
    detail = resp.json()["detail"]
    assert detail["error"] == "tipos_vehiculo_max_reached"
    assert detail["limit"] == 5
    assert detail["current"] == 5


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_post_succeeds_when_one_slot_frees_up_via_bi_temporal_close(
    client, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """Close one active tipo (Carril B), then the 6th POST succeeds.

    Defense-in-depth for the cap: the guard counts ``vigente_hasta IS
    NULL`` only, so closing any of the 5 unblocks a new POST.
    """
    from datetime import UTC, datetime

    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
    from sqlalchemy.ext.asyncio import async_sessionmaker

    await _truncate_tipos_vehiculo(pg_engine)
    await _seed_active_tipos_vehiculo(
        pg_engine, ["carro", "moto", "bicicleta", "patineta", "otro"]
    )

    # Close ``moto`` bi-temporally (no DELETE — canon).
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        moto = (
            await session.execute(
                TiposVehiculo.__table__.select().where(TiposVehiculo.tipo == "moto")
            )
        ).scalar_one()
        moto.vigente_hasta = datetime.now(UTC).replace(tzinfo=None)
        moto.estado = "inactivo"
        await session.commit()

    actor_uuid = uuid_lib.uuid4()
    sucursal_ctx = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_catalogo")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[sucursal_ctx])

    resp = await client.post(
        "/api/v1/catalogos/tipos-vehiculo",
        json={"tipo": "reopened"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(sucursal_ctx),
        },
    )
    assert resp.status_code == 201, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["tipo"] == "reopened"
    assert body["estado"] == "activo"
    assert body["vigente_hasta"] is None


async def _seed_tipo_vehiculo(pg_engine, tipo: str) -> uuid_lib.UUID:
    """Insert one active ``tipos_vehiculo`` row and return its uuid."""
    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = TiposVehiculo(tipo=tipo, vigente_hasta=None, estado="activo")
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.uuid


async def _seed_vehiculo_con_subscripcion_vigente(
    pg_engine, *, uuid_tipo_vehiculo: uuid_lib.UUID
) -> None:
    """Seed one vigente ``vehiculos`` row of ``uuid_tipo_vehiculo``, covered
    by one vigente ``subscripciones_cliente`` via the vigente
    ``subscripcion_vehiculos`` junction row -- the exact BR3 dependency
    chain (``vehiculos.uuid_tipo_vehiculo`` -> ``subscripcion_vehiculos``
    -> ``subscripciones_cliente``, all ``vigente_hasta IS NULL``)."""
    from parkos_core.models.V.subscripcion_vehiculos import SubscripcionVehiculos
    from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente
    from parkos_core.models.V.vehiculos import Vehiculos
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        vehiculo = Vehiculos(
            placa="ABC123",
            uuid_tipo_vehiculo=uuid_tipo_vehiculo,
            vigente_hasta=None,
            estado="activo",
        )
        session.add(vehiculo)
        await session.flush()

        subscripcion = SubscripcionesCliente(vigente_hasta=None, estado="activo")
        session.add(subscripcion)
        await session.flush()

        session.add(
            SubscripcionVehiculos(
                uuid_subscripcion_cliente=subscripcion.uuid,
                uuid_vehiculo=vehiculo.uuid,
                vigente_hasta=None,
                estado="activo",
            )
        )
        await session.commit()


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_put_tipo_vehiculo_returns_409_with_subscripcion_vigente(
    client, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """BR3 (HU-F14.1-T5): PUT on a ``tipos_vehiculo`` covered by a vigente
    subscription (via ``vehiculos`` -> ``subscripcion_vehiculos`` ->
    ``subscripciones_cliente``) is rejected with 409
    ``tipo_vehiculo_con_subscripciones_vigentes`` -- the PUT would close
    the current version (regenerating its ``uuid``) and orphan the
    dependent vehicle's ``uuid_tipo_vehiculo`` FK.
    """
    await _truncate_tipos_vehiculo(pg_engine)
    tipo_uuid = await _seed_tipo_vehiculo(pg_engine, "carro")
    await _seed_vehiculo_con_subscripcion_vigente(pg_engine, uuid_tipo_vehiculo=tipo_uuid)

    actor_uuid = uuid_lib.uuid4()
    sucursal_ctx = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_catalogo")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[sucursal_ctx])

    resp = await client.put(
        f"/api/v1/catalogos/tipos-vehiculo/{tipo_uuid}",
        json={"tipo": "carro"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(sucursal_ctx),
        },
    )
    assert resp.status_code == 409, f"got {resp.status_code}: {resp.text}"
    detail = resp.json()["detail"]
    assert detail["error"] == "tipo_vehiculo_con_subscripciones_vigentes"
    assert detail["uuid"] == str(tipo_uuid)
    assert detail["subscripciones_vigentes"] == 1


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_put_tipo_vehiculo_succeeds_without_subscripcion_vigente(
    client, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """BR3 does not block edits on a tipo with no dependent vigente
    subscription -- the ordinary close+insert PUT keeps working."""
    await _truncate_tipos_vehiculo(pg_engine)
    tipo_uuid = await _seed_tipo_vehiculo(pg_engine, "moto")

    actor_uuid = uuid_lib.uuid4()
    sucursal_ctx = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_catalogo")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[sucursal_ctx])

    resp = await client.put(
        f"/api/v1/catalogos/tipos-vehiculo/{tipo_uuid}",
        json={"tipo": "moto_renombrada"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(sucursal_ctx),
        },
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["tipo"] == "moto_renombrada"
    assert body["estado"] == "activo"
    assert body["vigente_hasta"] is None