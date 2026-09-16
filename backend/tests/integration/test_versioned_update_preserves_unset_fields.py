"""test_versioned_update_preserves_unset_fields.py — regression coverage for
a real defect found doing manual QA against the live Docker cloud stack
(qa-e2e audit session, 2026-09-10): a partial ``PUT /{uuid}`` on ANY
``router_factory``-mounted ``[V]`` resource silently NULLs every business
column the caller did not include in the request body.

Confirmed live on ``clientes``: ``PUT /api/v1/clientes/clientes/{uuid}``
with body ``{"nombre": "AuditoriaRenombrada"}`` produced a new open version
with ``numero_identificacion`` and ``tipo_identificador`` both NULL — the
row's own natural key, gone. Root cause: ``repo.versioned.close_and_insert``
built the new row from ``new_attrs`` alone; the endpoint sends
``payload.model_dump(exclude_none=True)`` — a partial diff BY DESIGN (every
``*Update`` schema derives its fields from the matching ``*Create`` schema
made ``Optional``) — so any field the caller omits was never carried
forward from the version being closed.

Beyond plain data loss, a NULLed natural-key column breaks
``identity_reconciler`` (D17) for every subsequent sync of that row: the
next legitimate full-field write can no longer match it by natural key, and
the corruption (a client with no national ID, a permission with no code,
...) replicates to every other node exactly as sync is designed to do.

This was never caught by ``test_e2e_full_catalog_sync.py`` and friends —
they build the update payload as a full replacement in Python (every field
present), never a real partial HTTP diff.
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest


async def _grant_permission(pg_engine, *, actor_uuid: uuid_lib.UUID, perm_code: str) -> None:
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
async def test_partial_update_preserves_natural_key_on_clientes(
    client, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """A PUT naming only ``nombre`` must keep the existing
    ``numero_identificacion``/``tipo_identificador`` on the new version —
    not NULL them out."""
    actor_uuid = uuid_lib.uuid4()
    sucursal_ctx = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="gestionar_clientes")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[sucursal_ctx])
    headers = {"Authorization": f"Bearer {token}", "X-Sucursal-Context": str(sucursal_ctx)}

    numero = f"AUD{uuid_lib.uuid4().hex[:8]}"
    create_resp = await client.post(
        "/api/v1/clientes/clientes",
        json={
            "tipo_identificador": "CC",
            "numero_identificacion": numero,
            "nombre": "Original",
            "apellido": "Uno",
            "telefono": "3000000000",
            "email": "original@example.com",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    original_uuid = create_resp.json()["uuid"]

    update_resp = await client.put(
        f"/api/v1/clientes/clientes/{original_uuid}",
        json={"nombre": "Renombrado"},
        headers=headers,
    )
    assert update_resp.status_code == 200, update_resp.text
    body = update_resp.json()

    assert body["nombre"] == "Renombrado"
    assert body["numero_identificacion"] == numero, (
        "numero_identificacion (the natural key) must survive an update "
        f"that never mentioned it, got {body['numero_identificacion']!r}"
    )
    assert body["tipo_identificador"] == "CC"
    assert body["apellido"] == "Uno"
    assert body["telefono"] == "3000000000"
    assert body["email"] == "original@example.com"
    assert body["uuid"] != original_uuid, "close_and_insert must open a NEW version"


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_partial_update_preserves_fields_on_costos_servicios(
    client, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """Generalization check: a SECOND, unrelated ``[V]`` resource must ALSO
    carry forward fields the update omits — proves the fix is in the shared
    ``close_and_insert`` helper, not ``clientes``-specific.

    ``CostosServiciosUpdate`` (unlike ``ClientesUpdate``) requires
    ``concepto`` on every call — the two schemas are inconsistent about
    which fields are resend-required — but ``costo``/``tipo_calculo`` stay
    Optional there too, so omitting ``tipo_calculo`` alone still exercises
    the exact same carry-forward path.
    """
    actor_uuid = uuid_lib.uuid4()
    sucursal_ctx = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_catalogo")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[sucursal_ctx])
    headers = {"Authorization": f"Bearer {token}", "X-Sucursal-Context": str(sucursal_ctx)}

    concepto = f"servicio-{uuid_lib.uuid4().hex[:8]}"
    create_resp = await client.post(
        "/api/v1/catalogos/costos-servicios",
        json={"concepto": concepto, "costo": "1500.00", "tipo_calculo": "fijo"},
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    original_uuid = create_resp.json()["uuid"]

    update_resp = await client.put(
        f"/api/v1/catalogos/costos-servicios/{original_uuid}",
        json={"concepto": concepto, "costo": "1800.00"},
        headers=headers,
    )
    assert update_resp.status_code == 200, update_resp.text
    body = update_resp.json()

    assert float(body["costo"]) == 1800.0
    assert body["concepto"] == concepto
    assert body["tipo_calculo"] == "fijo", (
        "tipo_calculo must survive an update that never mentioned it, "
        f"got {body['tipo_calculo']!r}"
    )
