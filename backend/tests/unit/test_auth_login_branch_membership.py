"""test_auth_login_branch_membership.py — branch login requires membership.

Defense in depth on the BRANCH API (``PARKOS_DEPLOY=branch``): a usuario with
a valid password but NO vigente ``usuarios_sucursal`` row for THIS branch
(``PARKOS_SUCURSAL_UUID``) must not obtain a token. Before this check the
handler issued a token with ``sucursal: None`` (or pinned to ANOTHER branch)
and only ``tenancy`` rejected it later (``missing_sucursal_in_jwt``).

Decisions pinned here:

* Rejection is the SAME generic ``401 invalid_credentials`` as a bad
  password (no enumeration), and is evaluated AFTER bcrypt so the response
  cost class is identical.
* The attempt is recorded as ``estado='fallido'`` against THIS branch and
  COUNTS toward lockout. Otherwise "valid password, no membership" would
  never lock while "bad password" does — a distinguishable oracle.
* The admin API (``PARKOS_DEPLOY=cloud``, multi-tenant) is unchanged.
* No ``admin`` exception: an admin-rol usuario without membership here is
  rejected too.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

import bcrypt
import pytest
from parkos_core.api.v1.auth import DEFAULT_MAX_INTENTOS
from parkos_core.auth.tokens import verify_token
from parkos_core.models.L_S.login import Login
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from tests.conftest import VFixtureFactory

LOGIN_URL = "/api/v1/auth/login"
PASSWORD = "Membresia123!"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seed(
    pg_engine: AsyncEngine,
    *,
    rol: str = "operador",
    member_of_this: bool = False,
    closed_member_of_this: bool = False,
    member_of_other: bool = False,
) -> tuple[str, uuid_lib.UUID, uuid_lib.UUID]:
    """Seed THIS branch, another branch and one usuario. Returns
    ``(email, usuario_uuid, this_branch_uuid)``."""
    email = f"memb-{uuid_lib.uuid4().hex[:10]}@example.com"
    pw_hash = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        this_branch = VFixtureFactory.build(Sucursal)
        other_branch = VFixtureFactory.build(Sucursal)
        user = VFixtureFactory.build(Usuarios, email=email, password_hash=pw_hash, rol=rol)
        s.add_all([this_branch, other_branch, user])
        await s.flush()
        if member_of_this:
            s.add(VFixtureFactory.build(
                UsuariosSucursal, uuid_sucursal=this_branch.uuid, uuid_usuario=user.uuid))
        if closed_member_of_this:
            s.add(VFixtureFactory.build(
                UsuariosSucursal, uuid_sucursal=this_branch.uuid, uuid_usuario=user.uuid,
                vigente_desde=_now() - timedelta(days=2),
                vigente_hasta=_now() - timedelta(days=1), estado="inactivo"))
        if member_of_other:
            s.add(VFixtureFactory.build(
                UsuariosSucursal, uuid_sucursal=other_branch.uuid, uuid_usuario=user.uuid))
        await s.commit()
        return email, user.uuid, this_branch.uuid


@pytest.fixture
def as_branch(monkeypatch: pytest.MonkeyPatch):
    def _pin(branch_uuid: uuid_lib.UUID) -> None:
        monkeypatch.setenv("PARKOS_DEPLOY", "branch")
        monkeypatch.setenv("PARKOS_SUCURSAL_UUID", str(branch_uuid))
    return _pin


async def _logins(pg_engine: AsyncEngine, user_uuid: uuid_lib.UUID) -> list[Login]:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        return list((await s.execute(
            select(Login).where(Login.uuid_usuario == user_uuid))).scalars().all())


async def test_member_of_this_branch_logs_in_with_branch_pin(client, pg_engine, as_branch):
    email, _, branch = await _seed(pg_engine, member_of_this=True, member_of_other=True)
    as_branch(branch)

    resp = await client.post(LOGIN_URL, json={"email": email, "password": PASSWORD})

    assert resp.status_code == 200, resp.text
    claims = verify_token(resp.json()["access_token"])
    assert claims["sucursal"] == str(branch)


async def test_member_pin_is_this_branch_even_with_other_assignments(
    client, pg_engine, as_branch
):
    """The old ``limit(1)`` could pin ANY of the user's branches."""
    email, _, branch = await _seed(pg_engine, member_of_this=True, member_of_other=True)
    as_branch(branch)
    for _ in range(3):
        resp = await client.post(LOGIN_URL, json={"email": email, "password": PASSWORD})
        assert resp.status_code == 200, resp.text
        assert verify_token(resp.json()["access_token"])["sucursal"] == str(branch)


async def test_valid_password_without_membership_is_generic_401(client, pg_engine, as_branch):
    email, user_uuid, branch = await _seed(pg_engine)
    as_branch(branch)

    resp = await client.post(LOGIN_URL, json={"email": email, "password": PASSWORD})
    bad = await client.post(LOGIN_URL, json={"email": email, "password": "otra-clave-X1"})

    assert resp.status_code == 401
    assert resp.json() == bad.json() == {"detail": {"error": "invalid_credentials"}}
    assert "access_token" not in resp.text
    assert "parkos_session" not in resp.headers.get("set-cookie", "")
    rows = await _logins(pg_engine, user_uuid)
    assert rows
    assert all(r.estado == "fallido" for r in rows)
    assert all(r.uuid_sucursal in (None, branch) for r in rows)


async def test_closed_membership_is_rejected(client, pg_engine, as_branch):
    email, _, branch = await _seed(pg_engine, closed_member_of_this=True)
    as_branch(branch)

    resp = await client.post(LOGIN_URL, json={"email": email, "password": PASSWORD})

    assert resp.status_code == 401
    assert resp.json() == {"detail": {"error": "invalid_credentials"}}


async def test_membership_only_at_another_branch_never_issues_a_token(
    client, pg_engine, as_branch
):
    email, user_uuid, branch = await _seed(pg_engine, member_of_other=True)
    as_branch(branch)

    resp = await client.post(LOGIN_URL, json={"email": email, "password": PASSWORD})

    assert resp.status_code == 401
    assert resp.json() == {"detail": {"error": "invalid_credentials"}}
    assert "set-cookie" not in resp.headers
    assert all(r.estado == "fallido" for r in await _logins(pg_engine, user_uuid))


async def test_admin_rol_without_membership_has_no_exception(client, pg_engine, as_branch):
    email, _, branch = await _seed(pg_engine, rol="admin")
    as_branch(branch)

    resp = await client.post(LOGIN_URL, json={"email": email, "password": PASSWORD})

    assert resp.status_code == 401


async def test_no_membership_attempts_count_toward_lockout(client, pg_engine, as_branch):
    """Same lockout class as a bad password: no distinguishing oracle."""
    email, user_uuid, branch = await _seed(pg_engine)
    as_branch(branch)

    for _ in range(DEFAULT_MAX_INTENTOS):
        resp = await client.post(LOGIN_URL, json={"email": email, "password": PASSWORD})
        assert resp.status_code == 401
    locked = await client.post(LOGIN_URL, json={"email": email, "password": PASSWORD})

    assert locked.status_code == 429
    assert locked.json()["detail"]["error"] == "account_locked"
    assert len(await _logins(pg_engine, user_uuid)) == DEFAULT_MAX_INTENTOS


async def test_unrelated_member_is_not_locked_by_another_users_failures(
    client, pg_engine, as_branch
):
    stranger, _, branch = await _seed(pg_engine)
    as_branch(branch)
    for _ in range(DEFAULT_MAX_INTENTOS):
        await client.post(LOGIN_URL, json={"email": stranger, "password": PASSWORD})

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    member_email = f"memb-{uuid_lib.uuid4().hex[:10]}@example.com"
    async with Session() as s:
        u = VFixtureFactory.build(
            Usuarios, email=member_email, rol="operador",
            password_hash=bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode())
        s.add(u)
        await s.flush()
        s.add(VFixtureFactory.build(UsuariosSucursal, uuid_sucursal=branch, uuid_usuario=u.uuid))
        await s.commit()

    resp = await client.post(LOGIN_URL, json={"email": member_email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text


async def test_admin_api_login_is_unchanged_without_membership(
    client, pg_engine, monkeypatch: pytest.MonkeyPatch
):
    """Cloud deploy is multi-tenant: no membership check at all."""
    email, _, other = await _seed(pg_engine, rol="admin")
    monkeypatch.setenv("PARKOS_DEPLOY", "cloud")
    monkeypatch.setenv("PARKOS_SUCURSAL_UUID", str(other))

    resp = await client.post(LOGIN_URL, json={"email": email, "password": PASSWORD})

    assert resp.status_code == 200, resp.text
    assert verify_token(resp.json()["access_token"])["sucursal"] is None
