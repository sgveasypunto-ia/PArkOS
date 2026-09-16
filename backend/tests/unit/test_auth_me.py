"""test_auth_me.py — R-F1.2-5..9 (operator session profile).

``GET /api/v1/auth/me`` returns the five blocks of ``AuthMeResponse``:

1. ``user`` — identity from ``prod.usuarios``
2. ``sucursal`` — single branch pinned by the ``operador-`` JWT
3. ``sucursales_permitidas`` — all active ``usuarios_sucursal`` for the actor
4. ``permisos`` — list of permission codes (``[]`` if none)
5. ``expires_at`` — ISO 8601 UTC derived from the JWT ``exp`` claim

Cases (S-F1.2-4):

- ``test_me_returns_full_profile_with_five_blocks`` — happy path with
  one branch and several permission rows; verifies every block shape.
- ``test_me_with_zero_permissions_returns_empty_array_not_404`` — the
  user exists with valid branch assignment but has zero permissions;
  ``permisos`` MUST be ``[]`` (empty array), NOT ``null``, NOT a 404.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

import bcrypt
from parkos_core.models.V.permisos import Permisos
from parkos_core.models.V.permisos_usuario import PermisosUsuario
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal
from parkos_core.auth.tokens import issue_token
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from tests.conftest import VFixtureFactory

ME_URL = "/api/v1/auth/me"


async def _seed_user_branch_with_perms(
    pg_engine: AsyncEngine,
    *,
    email: str | None = None,
    plaintext: str = "Correcta123!",
    perm_codes: list[str] | None = None,
    branch_nombre: str = "Sucursal Test",
    branch_prefijo: str = "TST",
) -> tuple[uuid_lib.UUID, uuid_lib.UUID, list[str]]:
    """Insert user + branch + N permissions. Returns
    ``(user_uuid, sucursal_uuid, perm_codes_actual)``.

    The branch FK must be real (FK constraint enforced), so we always
    create one. Permissions are inserted as ``Permisos + PermisosUsuario``
    pairs (both real FKs).
    """
    from parkos_core.auth.tokens import issue_token  # noqa: F401

    perm_codes = perm_codes or []
    password_hash = bcrypt.hashpw(
        plaintext.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    email = email or f"me-{uuid_lib.uuid4().hex[:10]}@example.com"

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal = VFixtureFactory.build(
            Sucursal, nombre=branch_nombre, prefijo_nombre=branch_prefijo
        )
        session.add(sucursal)
        await session.flush()

        user = VFixtureFactory.build(
            Usuarios,
            email=email,
            password_hash=password_hash,
            rol="operador",
            nombre="Test",
            apellido="User",
        )
        session.add(user)
        await session.flush()

        session.add(
            VFixtureFactory.build(
                UsuariosSucursal,
                uuid_sucursal=sucursal.uuid,
                uuid_usuario=user.uuid,
            )
        )
        await session.flush()

        # Seed permissions.
        perm_uuids: list[str] = []
        for code in perm_codes:
            perm = VFixtureFactory.build(Permisos, permiso=code)
            session.add(perm)
            await session.flush()
            session.add(
                VFixtureFactory.build(
                    PermisosUsuario,
                    uuid_usuario=user.uuid,
                    uuid_permiso=perm.uuid,
                )
            )
            perm_uuids.append(str(perm.uuid))

        await session.commit()
        return (user.uuid, sucursal.uuid, perm_codes)


def _mint_operador_jwt_for(
    *, user_uuid: uuid_lib.UUID, sucursal_uuid: uuid_lib.UUID
) -> str:
    """Mint an ``operador-`` JWT pinned to the given branch."""
    return issue_token(
        subject_uuid=user_uuid,
        issuer="operador-test",
        claims={
            "rol": "operador",
            "sucursal": str(sucursal_uuid),
        },
        expires_in=3600,
    )


async def test_me_returns_full_profile_with_five_blocks(
    client, pg_engine: AsyncEngine
) -> None:
    """S-F1.2-1: every block is present and well-typed.

    - ``user.uuid`` matches the actor uuid.
    - ``sucursal.uuid`` matches the JWT claim.
    - ``sucursales_permitidas`` contains exactly 1 entry (the same
      branch).
    - ``permisos`` contains the seeded codes (string array).
    - ``expires_at`` parses as ISO 8601 UTC and is in the future.
    """
    user_uuid, sucursal_uuid, perm_codes = await _seed_user_branch_with_perms(
        pg_engine,
        email="me-happy@example.com",
        perm_codes=["factura_crear", "arqueo_cerrar"],
        branch_nombre="Sucursal Feliz",
        branch_prefijo="FEL",
    )

    token = _mint_operador_jwt_for(
        user_uuid=user_uuid, sucursal_uuid=sucursal_uuid
    )

    resp = await client.get(
        ME_URL, headers={"Authorization": f"Bearer {token}"}
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert set(body.keys()) == {
        "user",
        "sucursal",
        "sucursales_permitidas",
        "permisos",
        "expires_at",
    }

    # user block
    assert body["user"]["uuid"] == str(user_uuid)
    assert body["user"]["email"] == "me-happy@example.com"
    assert body["user"]["nombre"] == "Test"
    assert body["user"]["apellido"] == "User"
    assert body["user"]["rol"] == "operador"

    # sucursal (singular, JWT-pinned)
    assert body["sucursal"]["uuid"] == str(sucursal_uuid)
    assert body["sucursal"]["nombre"] == "Sucursal Feliz"
    assert body["sucursal"]["prefijo_nombre"] == "FEL"

    # sucursales_permitidas (plural, DB-driven)
    assert len(body["sucursales_permitidas"]) == 1
    assert body["sucursales_permitidas"][0]["uuid"] == str(sucursal_uuid)

    # subset invariant (KD-4): the JWT-pinned branch is included in the list
    assert body["sucursal"]["uuid"] in {
        s["uuid"] for s in body["sucursales_permitidas"]
    }

    # permisos
    assert sorted(body["permisos"]) == sorted(perm_codes)

    # expires_at — ISO 8601 UTC and in the future
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert expires_at.tzinfo is not None  # tz-aware
    assert expires_at > datetime.now(expires_at.tzinfo)


async def test_me_with_zero_permissions_returns_empty_array_not_404(
    client, pg_engine: AsyncEngine
) -> None:
    """S-F1.2-4: zero permissions → ``permisos=[]`` (NOT ``null``, NOT 404).

    Edge case: the user exists and is bound to a branch, but has no rows
    in ``permisos_usuario``. The endpoint must still return 200 with an
    empty array (NOT null, NOT a 404 "permisos not found").
    """
    user_uuid, sucursal_uuid, _ = await _seed_user_branch_with_perms(
        pg_engine,
        email="me-empty@example.com",
        perm_codes=[],
        branch_nombre="Sucursal Vacia",
        branch_prefijo="VAC",
    )

    token = _mint_operador_jwt_for(
        user_uuid=user_uuid, sucursal_uuid=sucursal_uuid
    )

    resp = await client.get(
        ME_URL, headers={"Authorization": f"Bearer {token}"}
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()

    # The critical assertion: ``permisos`` is an empty array, not null,
    # and the response is 200 (not 404).
    assert body["permisos"] == []
    assert "permisos" in body  # the key MUST be present
    assert resp.status_code != 404
