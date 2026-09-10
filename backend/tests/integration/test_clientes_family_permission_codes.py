"""test_clientes_family_permission_codes.py — regression coverage for a real
defect confirmed while doing manual QA against the live Docker stack
(2026-09-10, section 4.6.a real-HTTP identity-divergence exercise):
``POST /api/v1/clientes`` (and every sibling in the same family) returned
403 ``permission_denied`` for EVERY caller, including a real admin with
every other permission granted — the router required a permission code
that was never seeded anywhere.

Root cause: ``api/v1/clientes.py``'s ``_ROUTER_CONFIG`` names
``admin_clientes`` / ``admin_clientes_b2b`` / ``admin_subscripciones`` /
``admin_vehiculos`` / ``admin_subscripcion_vehiculos`` as the required
permission for each of its 5 resources — none of those 5 codes exist in
``migrations/versions/0002_seed_permisos_canonicos.py``'s
``CANONICAL_PERMISOS`` (the single source of truth "per design section 7").
The real canonical code for this whole bounded context is
``gestionar_clientes``. Since ``require_permission`` looks up the code
LIVE against ``prod.permisos`` (by design — "revoking a permission takes
effect immediately, no token-cache window"), a permission code matching no
row can never be granted to ANYONE — this was a 100%-unreachable write
surface for the entire clientes family (clientes, clientes-b2b,
subscripciones-cliente, vehiculos, subscripcion-vehiculos) since PR5,
never caught because every existing test creates these rows by calling
``repo.versioned.close_and_insert`` directly, never through the real HTTP
+ permission-dependency chain.
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest


async def _grant(pg_engine, *, actor_uuid: uuid_lib.UUID, perm_code: str) -> None:
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
async def test_create_cliente_via_real_http_with_canonical_permission(
    client, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """The REAL canonical permission (``gestionar_clientes``, the only code
    ``0002_seed_permisos_canonicos`` actually seeds for this bounded
    context) must be sufficient to create a cliente over real HTTP."""
    actor_uuid = uuid_lib.uuid4()
    sucursal_ctx = uuid_lib.uuid4()
    await _grant(pg_engine, actor_uuid=actor_uuid, perm_code="gestionar_clientes")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[sucursal_ctx])

    resp = await client.post(
        "/api/v1/clientes/clientes",
        json={
            "tipo_identificador": "CC",
            "numero_identificacion": f"id-{uuid_lib.uuid4().hex[:10]}",
            "nombre": "Ada",
            "apellido": "Lovelace",
            "telefono": "3000000000",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(sucursal_ctx),
        },
    )
    assert resp.status_code == 201, (
        "gestionar_clientes is the ONLY canonically-seeded permission for "
        f"this bounded context — it must be sufficient. Got {resp.status_code}: {resp.text}"
    )
