"""test_auth_login_cookie.py — R-F1.2-4 (cookie parkos_session).

A successful ``POST /api/v1/auth/login`` MUST set the
``parkos_session`` cookie alongside the JSON body. The cookie carries
the same HS256 access token with attributes
``httponly=True, secure=True, samesite="lax", max_age=3600, path="/"``.

The body MUST remain unchanged (``access_token``, ``refresh_token``,
``expires_in``) so non-browser clients (CLI, mobile) can keep using
the body-based flow.
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


async def _seed_user_with_branch(
    pg_engine: AsyncEngine, *, email: str, plaintext: str = "Correcta123!"
) -> None:
    password_hash = bcrypt.hashpw(
        plaintext.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal = VFixtureFactory.build(Sucursal, nombre="Cookie Norte")
        session.add(sucursal)
        await session.flush()

        user = VFixtureFactory.build(
            Usuarios, email=email, password_hash=password_hash, rol="operador"
        )
        session.add(user)
        await session.flush()

        session.add(
            VFixtureFactory.build(
                UsuariosSucursal, uuid_sucursal=sucursal.uuid, uuid_usuario=user.uuid
            )
        )
        await session.commit()


async def test_login_success_sets_parkos_session_cookie_with_attrs(
    client, pg_engine: AsyncEngine
) -> None:
    """S-F1.2-1: cookie Set-Cookie carries the literal attrs.

    Layout asserted (httpx ASGI delivers the cookie both via the response
    jar and the raw ``set-cookie`` header):

    - Name ``parkos_session``
    - Value equals the body's ``access_token`` (same secret travels both
      channels — whichever the client uses authenticates).
    - ``HttpOnly`` flag set (XSS-trivial exfiltration neutralized).
    - ``Secure`` flag set (HTTPS-only in prod; browsers ignore on HTTP).
    - ``SameSite=Lax`` (CSRF mitigation for mutating POSTs).
    - ``Max-Age=3600`` (matches ``ACCESS_TOKEN_TTL``).
    - ``Path=/`` (browser sends it on every backend request).

    The JSON body remains unchanged (back-compat for non-browser
    clients).
    """
    email = f"cookie-{uuid_lib.uuid4().hex[:10]}@example.com"
    await _seed_user_with_branch(pg_engine, email=email)

    resp = await client.post(
        LOGIN_URL, json={"email": email, "password": "Correcta123!"}
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] == 3600

    # The cookie must be present in the ASGI response jar.
    assert "parkos_session" in resp.cookies, (
        f"missing parkos_session cookie; got cookies={list(resp.cookies.keys())}; "
        f"headers={dict(resp.headers)}"
    )

    cookie_value = resp.cookies["parkos_session"]
    assert cookie_value == body["access_token"], (
        "cookie value MUST equal body access_token (same JWT travels both channels)"
    )

    # Inspect the raw Set-Cookie header for the attribute set.
    raw_set_cookie = resp.headers.get("set-cookie", "")
    assert "parkos_session=" in raw_set_cookie
    assert "HttpOnly" in raw_set_cookie
    assert "Secure" in raw_set_cookie
    assert "SameSite=Lax" in raw_set_cookie or "samesite=lax" in raw_set_cookie.lower()
    assert "Max-Age=3600" in raw_set_cookie
    assert "Path=/" in raw_set_cookie
