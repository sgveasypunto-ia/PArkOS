"""test_auth_login_branch_scope.py — login branch scope / claims conformance.

Closes a structural blind spot in the auth suite. ``test_auth_login_password``
documented the handler's ``sucursal_uuid = user.uuid`` fallback in a docstring
and then worked around it by always seeding a ``usuarios_sucursal`` row, so no
test ever logged in a user WITHOUT a branch — the only shape that actually
fails. The bug shipped anyway.

Two defects, one root cause (a user uuid standing in for a branch uuid):

1. ``record_login(sucursal_uuid=... or user.uuid)`` wrote a USER uuid into
   ``login.uuid_sucursal``, a nullable FK to ``prod.sucursal(uuid)``, which
   raised ForeignKeyViolationError and returned HTTP 500 on every cloud-admin
   login.
2. The same fallback put a non-branch id into the ``sucursales_permitidas``
   and ``sucursal`` claims. ``tenancy.require_tenant`` fail-closes an empty or
   missing permitted list and requires the ``X-Sucursal-Context`` header to be
   a member of it, so a cloud admin was both unable to log in and, once (1)
   was fixed naively, unable to make a single authorized call.

The permitted list is the FULL set of active assignments, which is what
``GET /auth/me`` reports and what ``schemas/auth.py::AuthMeResponse`` documents
as the KD-4 contract: singular ``sucursal`` is the JWT pin, plural
``sucursales_permitidas`` is the complete DB list.

Emails are randomized per test (no physical DELETE on ``[V]`` tables).
"""
from __future__ import annotations

import uuid as uuid_lib

import bcrypt
from parkos_core.auth.tokens import verify_token
from parkos_core.models.L_S.login import Login
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from tests.conftest import VFixtureFactory

LOGIN_URL = "/api/v1/auth/login"


async def _seed_user(
    pg_engine: AsyncEngine,
    *,
    email: str,
    plaintext_password: str,
    rol: str,
    branch_count: int,
) -> tuple[uuid_lib.UUID, list[uuid_lib.UUID]]:
    """Create one user with ``branch_count`` active branch assignments.

    ``branch_count=0`` reproduces the cloud-admin shape: a real user with no
    ``usuarios_sucursal`` row at all. Returns ``(user_uuid, branch_uuids)``.
    """
    password_hash = bcrypt.hashpw(plaintext_password.encode("utf-8"), bcrypt.gensalt()).decode(
        "utf-8"
    )
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        user = VFixtureFactory.build(Usuarios, email=email, password_hash=password_hash, rol=rol)
        session.add(user)
        await session.flush()

        branch_uuids: list[uuid_lib.UUID] = []
        for _ in range(branch_count):
            sucursal = VFixtureFactory.build(Sucursal)
            session.add(sucursal)
            await session.flush()
            session.add(
                VFixtureFactory.build(
                    UsuariosSucursal,
                    uuid_sucursal=sucursal.uuid,
                    uuid_usuario=user.uuid,
                )
            )
            branch_uuids.append(sucursal.uuid)

        await session.commit()
        return user.uuid, branch_uuids


async def _newest_login_branch(
    pg_engine: AsyncEngine, user_uuid: uuid_lib.UUID
) -> uuid_lib.UUID | None:
    """``login.uuid_sucursal`` of the newest login row for ``user_uuid``."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        return (
            await session.execute(
                select(Login.uuid_sucursal)
                .where(Login.uuid_usuario == user_uuid)
                .order_by(Login.timestamp_evento.desc())
                .limit(1)
            )
        ).scalar_one()


async def test_cloud_admin_login_without_branch_assignment_does_not_500(
    client, pg_engine: AsyncEngine
) -> None:
    """The regression: this shape used to raise ForeignKeyViolationError."""
    email = f"login-nobranch-{uuid_lib.uuid4().hex[:10]}@example.com"
    await _seed_user(
        pg_engine,
        email=email,
        plaintext_password="SinRama123!",
        rol="admin",
        branch_count=0,
    )

    resp = await client.post(LOGIN_URL, json={"email": email, "password": "SinRama123!"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


async def test_login_persists_null_sucursal_instead_of_the_user_uuid(
    client, pg_engine: AsyncEngine
) -> None:
    """``login.uuid_sucursal`` is a branch FK; a user uuid violates it."""
    email = f"login-nullfk-{uuid_lib.uuid4().hex[:10]}@example.com"
    user_uuid, _ = await _seed_user(
        pg_engine,
        email=email,
        plaintext_password="SinRama123!",
        rol="admin",
        branch_count=0,
    )

    resp = await client.post(LOGIN_URL, json={"email": email, "password": "SinRama123!"})
    assert resp.status_code == 200, resp.text

    persisted = await _newest_login_branch(pg_engine, user_uuid)
    assert persisted is None, f"expected NULL, got the user uuid {persisted}"
    assert persisted != user_uuid


async def test_login_claims_never_carry_a_user_uuid(client, pg_engine: AsyncEngine) -> None:
    """A non-branch id in the tenant claims is a scope that can never match."""
    email = f"login-claims-{uuid_lib.uuid4().hex[:10]}@example.com"
    user_uuid, _ = await _seed_user(
        pg_engine,
        email=email,
        plaintext_password="SinRama123!",
        rol="admin",
        branch_count=0,
    )

    resp = await client.post(LOGIN_URL, json={"email": email, "password": "SinRama123!"})
    assert resp.status_code == 200, resp.text

    claims = verify_token(resp.json()["access_token"])
    assert claims["sucursal"] is None
    assert claims["sucursales_permitidas"] == []
    assert str(user_uuid) not in claims["sucursales_permitidas"]
    assert claims["rol"] == "admin"


async def test_login_claims_list_every_assigned_branch(client, pg_engine: AsyncEngine) -> None:
    """Multi-branch operators: the old claim carried only the pinned branch.

    The plural is what ``tenancy.require_tenant`` checks the
    ``X-Sucursal-Context`` header against, so a one-element list locked the
    actor out of their other legitimate branches.
    """
    email = f"login-multi-{uuid_lib.uuid4().hex[:10]}@example.com"
    _, branch_uuids = await _seed_user(
        pg_engine,
        email=email,
        plaintext_password="DosRamas123!",
        rol="operador",
        branch_count=2,
    )
    assert len(branch_uuids) == 2

    resp = await client.post(LOGIN_URL, json={"email": email, "password": "DosRamas123!"})
    assert resp.status_code == 200, resp.text

    claims = verify_token(resp.json()["access_token"])
    permitidas = claims["sucursales_permitidas"]
    assert set(permitidas) == {str(u) for u in branch_uuids}
    assert claims["sucursal"] in permitidas, "the JWT pin must be a member of the permitted list"


async def test_single_branch_login_claim_is_unchanged(client, pg_engine: AsyncEngine) -> None:
    """Operator parity: one assignment still yields exactly that one branch."""
    email = f"login-single-{uuid_lib.uuid4().hex[:10]}@example.com"
    _, branch_uuids = await _seed_user(
        pg_engine,
        email=email,
        plaintext_password="UnaRama123!",
        rol="operador",
        branch_count=1,
    )

    resp = await client.post(LOGIN_URL, json={"email": email, "password": "UnaRama123!"})
    assert resp.status_code == 200, resp.text

    claims = verify_token(resp.json()["access_token"])
    assert claims["sucursales_permitidas"] == [str(branch_uuids[0])]
    assert claims["sucursal"] == str(branch_uuids[0])
