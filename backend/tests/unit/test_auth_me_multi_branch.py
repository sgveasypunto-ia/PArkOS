"""test_auth_me_multi_branch.py — S-F1.2-5 (multi-branch operator).

When an operator has multiple active ``usuarios_sucursal`` rows, the
``GET /api/v1/auth/me`` response MUST list ALL of them in
``sucursales_permitidas`` — not just the one the JWT is pinned to.

Critically:
- The list MUST contain every active branch (no ``.limit(1)``).
- The list MUST be ordered by ``sucursal.nombre ASC``.
- The JWT-pinned branch MUST appear in the list (subset relationship,
  KD-4).
"""
from __future__ import annotations

import uuid as uuid_lib

import bcrypt
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal
from parkos_core.auth.tokens import issue_token
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from tests.conftest import VFixtureFactory

ME_URL = "/api/v1/auth/me"


async def test_me_returns_all_active_branches_ordered_by_nombre(
    client, pg_engine: AsyncEngine
) -> None:
    """User with 3 active ``usuarios_sucursal`` rows + JWT pinned to the
    middle one → ``sucursales_permitidas`` contains exactly 3, ordered by
    ``sucursal.nombre ASC``, and includes the JWT-pinned branch.
    """
    password_hash = bcrypt.hashpw(
        b"Correcta123!", bcrypt.gensalt()
    ).decode("utf-8")

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        user = VFixtureFactory.build(
            Usuarios,
            email=f"multi-{uuid_lib.uuid4().hex[:10]}@example.com",
            password_hash=password_hash,
            rol="operador",
        )
        session.add(user)
        await session.flush()

        # Three branches with deliberately NON-alphabetical names so the
        # ORDER BY s.nombre ASC assertion is meaningful.
        nombres = ["Sucursal Zulú", "Sucursal Alfa", "Sucursal Mike"]
        sucursal_uuids: list[uuid_lib.UUID] = []
        for n in nombres:
            s = VFixtureFactory.build(
                Sucursal, nombre=n, prefijo_nombre=n[:3].upper()
            )
            session.add(s)
            await session.flush()
            sucursal_uuids.append(s.uuid)
            session.add(
                VFixtureFactory.build(
                    UsuariosSucursal,
                    uuid_sucursal=s.uuid,
                    uuid_usuario=user.uuid,
                )
            )
        await session.commit()

    # JWT pinned to the SECOND branch (Alfa, the middle one in our insert
    # order — but the FIRST one alphabetically).
    pinned_uuid = sucursal_uuids[1]
    token = issue_token(
        subject_uuid=user.uuid,
        issuer="operador-test",
        claims={"rol": "operador", "sucursal": str(pinned_uuid)},
        expires_in=3600,
    )

    resp = await client.get(
        ME_URL, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # All three active branches present.
    assert len(body["sucursales_permitidas"]) == 3

    # Ordered by nombre ASC.
    nombres_ordenados = sorted(nombres)
    nombres_obtenidos = [s["nombre"] for s in body["sucursales_permitidas"]]
    assert nombres_obtenidos == nombres_ordenados

    # Subset relationship: the JWT-pinned branch is included.
    pinned_uuid_str = str(pinned_uuid)
    assert pinned_uuid_str in {s["uuid"] for s in body["sucursales_permitidas"]}

    # The singular ``sucursal`` block reflects the JWT pin.
    assert body["sucursal"]["uuid"] == pinned_uuid_str
