"""test_auth_login_password.py — REQ-43: /auth/login verifies the real password.

Locks in the bcrypt fix to ``api/v1/auth.py::login``: previously any
non-empty ``password_hash`` was treated as a sentry match, so the submitted
plaintext password was never actually compared against it.

Emails are randomized per test invocation to keep isolation against the
shared ``pg_engine`` (no DELETE on ``[V]`` tables per the ER canónico).
"""
from __future__ import annotations

import uuid as uuid_lib

import bcrypt
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from tests.conftest import VFixtureFactory

LOGIN_URL = "/api/v1/auth/login"


async def _seed_user(
    pg_engine: AsyncEngine, *, email: str, plaintext_password: str, rol: str = "operador"
) -> None:
    """Insert one ``usuarios`` row with a REAL bcrypt hash (no branch assignment)."""
    password_hash = bcrypt.hashpw(plaintext_password.encode("utf-8"), bcrypt.gensalt()).decode(
        "utf-8"
    )
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            VFixtureFactory.build(Usuarios, email=email, password_hash=password_hash, rol=rol)
        )
        await session.commit()


async def _seed_user_with_branch(
    pg_engine: AsyncEngine, *, email: str, plaintext_password: str, rol: str = "operador"
) -> None:
    """Insert a ``usuarios`` row WITH a ``usuarios_sucursal`` assignment.

    ``login.uuid_sucursal`` carries a real FK to ``prod.sucursal`` — the
    success path (``record_login``) needs a branch that actually exists,
    not the handler's ``sucursal_uuid = user.uuid`` fallback.
    """
    password_hash = bcrypt.hashpw(plaintext_password.encode("utf-8"), bcrypt.gensalt()).decode(
        "utf-8"
    )
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal = VFixtureFactory.build(Sucursal)
        session.add(sucursal)
        await session.flush()

        user = VFixtureFactory.build(Usuarios, email=email, password_hash=password_hash, rol=rol)
        session.add(user)
        await session.flush()

        session.add(
            VFixtureFactory.build(
                UsuariosSucursal, uuid_sucursal=sucursal.uuid, uuid_usuario=user.uuid
            )
        )
        await session.commit()


async def test_login_succeeds_with_correct_password(client, pg_engine: AsyncEngine) -> None:
    email = f"login-ok-{uuid_lib.uuid4().hex[:10]}@example.com"
    await _seed_user_with_branch(
        pg_engine, email=email, plaintext_password="Correcta123!"
    )

    resp = await client.post(
        LOGIN_URL, json={"email": email, "password": "Correcta123!"}
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]


async def test_login_rejects_wrong_password(client, pg_engine: AsyncEngine) -> None:
    email = f"login-wrong-{uuid_lib.uuid4().hex[:10]}@example.com"
    await _seed_user(
        pg_engine, email=email, plaintext_password="Correcta123!"
    )

    resp = await client.post(
        LOGIN_URL, json={"email": email, "password": "Incorrecta456!"}
    )

    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "invalid_credentials"


async def test_login_rejects_unknown_email_with_same_error_shape(client) -> None:
    resp = await client.post(
        LOGIN_URL,
        json={
            "email": f"no-existe-{uuid_lib.uuid4().hex[:10]}@example.com",
            "password": "CualquieraX1!",
        },
    )

    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "invalid_credentials"
