"""SC1 -- branch scope of ``api/v1/admin_usuarios.py``.

An ``admin-`` token is scoped to the branches in the actor's OPEN
``prod.usuarios_sucursal`` rows (read fresh from the DB, same source as
``admin_views`` / ``BranchScope``). A "global" cloud admin is one assigned to
every branch. A user is manageable when it holds an open assignment in the
actor's scope, or has no open assignment at all (a freshly created, not yet
assigned user -- the web_admin wizard assigns branches in a second step).

Real Postgres, real handlers, real ``admin-`` JWTs (no mocks).
"""

from __future__ import annotations

import sys
import uuid as uuid_lib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
for _p in (
    _BACKEND_ROOT / "packages" / "parkos_core" / "src",
    _BACKEND_ROOT / "packages" / "api_admin" / "src",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from parkos_core.api.v1 import admin_usuarios as _mod  # noqa: E402
from parkos_core.auth.tokens import issue_token  # noqa: E402
from parkos_core.db.engine import get_session  # noqa: E402
from parkos_core.models.V.permisos import Permisos  # noqa: E402
from parkos_core.models.V.sucursal import Sucursal  # noqa: E402
from parkos_core.models.V.usuarios import Usuarios  # noqa: E402
from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal  # noqa: E402

_BASE = "/api/v1/admin/usuarios"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _app(pg_engine) -> FastAPI:
    app = FastAPI()
    outer = APIRouter(prefix="/api/v1")
    outer.include_router(_mod.router)
    outer.include_router(_mod.catalog_router)
    app.include_router(outer)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async def _override() -> AsyncIterator:
        async with Session() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    return app


def _auth(actor: uuid_lib.UUID) -> dict[str, str]:
    # The claim is deliberately WIDE: the scope must come from the DB rows,
    # never from the login-time ``sucursales_permitidas`` snapshot.
    token = issue_token(
        subject_uuid=actor,
        issuer="admin-test",
        claims={"rol": "admin", "sucursales_permitidas": [str(uuid_lib.uuid4())]},
        expires_in=3600,
    )
    return {"Authorization": f"Bearer {token}"}


async def _seed_sucursal(Session) -> uuid_lib.UUID:
    async with Session() as s:
        row = Sucursal(
            nombre="Sucursal Scope",
            ciudad="Bogota",
            vigente_desde=_now(),
            vigente_hasta=None,
            estado="activo",
        )
        s.add(row)
        await s.flush()
        await s.commit()
        return row.uuid


async def _seed_user(Session, *, rol: str, branches: list[uuid_lib.UUID]) -> uuid_lib.UUID:
    user_uuid = uuid_lib.uuid4()
    now = _now()
    async with Session() as s:
        s.add(
            Usuarios(
                uuid=user_uuid,
                nombre="Scope",
                apellido=rol,
                email=f"scope-{user_uuid.hex[:10]}@parkos.local",
                password_hash="placeholder-bcrypt",
                rol=rol,
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await s.flush()
        for b in branches:
            s.add(
                UsuariosSucursal(
                    uuid_usuario=user_uuid,
                    uuid_sucursal=b,
                    vigente_desde=now,
                    vigente_hasta=None,
                    estado="activo",
                    created_at=now,
                    created_by=None,
                    sync_status="sincronizado",
                )
            )
        await s.commit()
    return user_uuid


class _World:
    """Two branches, a scoped admin per branch, a global admin, and a user per branch."""

    a: uuid_lib.UUID
    b: uuid_lib.UUID
    admin_a: uuid_lib.UUID
    admin_b: uuid_lib.UUID
    admin_global: uuid_lib.UUID
    user_a: uuid_lib.UUID
    user_b: uuid_lib.UUID
    user_orphan: uuid_lib.UUID


@pytest_asyncio.fixture
async def world(pg_engine, alembic_upgrade) -> AsyncIterator[_World]:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(
            text(
                "TRUNCATE prod.permisos_usuario, prod.usuarios_sucursal, "
                "prod.usuarios, prod.sync_queue, prod.sucursal CASCADE"
            )
        )
        await s.commit()
    w = _World()
    w.a = await _seed_sucursal(Session)
    w.b = await _seed_sucursal(Session)
    w.admin_a = await _seed_user(Session, rol="admin", branches=[w.a])
    w.admin_b = await _seed_user(Session, rol="admin", branches=[w.b])
    w.admin_global = await _seed_user(Session, rol="admin", branches=[w.a, w.b])
    w.user_a = await _seed_user(Session, rol="operador", branches=[w.a])
    w.user_b = await _seed_user(Session, rol="operador", branches=[w.b])
    w.user_orphan = await _seed_user(Session, rol="operador", branches=[])
    yield w


def _client(pg_engine) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(pg_engine)), base_url="http://cloud"
    )


async def _permiso_uuid(pg_engine) -> uuid_lib.UUID:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        return (
            await s.execute(
                select(Permisos).where(
                    Permisos.permiso == "config_catalogo", Permisos.vigente_hasta.is_(None)
                )
            )
        ).scalar_one().uuid


# ---------------------------------------------------------------- list / read


async def test_list_is_filtered_to_scope(pg_engine, world) -> None:
    async with _client(pg_engine) as c:
        r = await c.get(_BASE, headers=_auth(world.admin_a))
    assert r.status_code == 200, r.text
    got = {i["uuid"] for i in r.json()["items"]}
    assert str(world.user_a) in got
    assert str(world.user_b) not in got
    assert str(world.user_orphan) in got  # not yet assigned: manageable


async def test_list_hides_foreign_branches_inside_a_shared_user(pg_engine, world) -> None:
    shared = await _seed_user(
        async_sessionmaker(pg_engine, expire_on_commit=False),
        rol="operador",
        branches=[world.a, world.b],
    )
    async with _client(pg_engine) as c:
        r = await c.get(_BASE, headers=_auth(world.admin_a))
    item = next(i for i in r.json()["items"] if i["uuid"] == str(shared))
    assert {s["uuid_sucursal"] for s in item["sucursales"]} == {str(world.a)}


async def test_global_admin_lists_every_user(pg_engine, world) -> None:
    async with _client(pg_engine) as c:
        r = await c.get(_BASE, headers=_auth(world.admin_global))
    got = {i["uuid"] for i in r.json()["items"]}
    assert {str(world.user_a), str(world.user_b), str(world.user_orphan)} <= got


async def test_admin_without_assignments_sees_nothing(pg_engine, world) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    nobody = await _seed_user(Session, rol="admin", branches=[])
    async with _client(pg_engine) as c:
        lst = await c.get(_BASE, headers=_auth(nobody))
        one = await c.get(f"{_BASE}/{world.user_orphan}", headers=_auth(nobody))
    assert lst.status_code == 200
    assert lst.json()["items"] == []
    assert one.status_code == 404


async def test_get_foreign_user_is_404_own_is_200(pg_engine, world) -> None:
    async with _client(pg_engine) as c:
        own = await c.get(f"{_BASE}/{world.user_a}", headers=_auth(world.admin_a))
        foreign = await c.get(f"{_BASE}/{world.user_b}", headers=_auth(world.admin_a))
        glob = await c.get(f"{_BASE}/{world.user_b}", headers=_auth(world.admin_global))
    assert own.status_code == 200, own.text
    assert foreign.status_code == 404
    assert glob.status_code == 200


# ----------------------------------------------------------------- write paths


async def test_update_foreign_user_is_404_and_does_not_mutate(pg_engine, world) -> None:
    async with _client(pg_engine) as c:
        denied = await c.put(
            f"{_BASE}/{world.user_b}", headers=_auth(world.admin_a), json={"nombre": "Hacked"}
        )
        ok = await c.put(
            f"{_BASE}/{world.user_a}", headers=_auth(world.admin_a), json={"nombre": "Fine"}
        )
    assert denied.status_code == 404
    assert ok.status_code == 200, ok.text
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        names = (
            (
                await s.execute(
                    select(Usuarios.nombre).where(
                        Usuarios.uuid == world.user_b, Usuarios.vigente_hasta.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
    assert names == ["Scope"]


async def test_reset_password_foreign_user_is_404(pg_engine, world) -> None:
    async with _client(pg_engine) as c:
        denied = await c.post(f"{_BASE}/{world.user_b}/reset-password", headers=_auth(world.admin_a))
        ok = await c.post(f"{_BASE}/{world.user_a}/reset-password", headers=_auth(world.admin_a))
    assert denied.status_code == 404
    assert ok.status_code == 200, ok.text


async def test_create_with_foreign_branch_is_403_own_is_201(pg_engine, world) -> None:
    body = {"email": "new-a@parkos.local", "password": "Pass1234word", "rol": "operador"}
    async with _client(pg_engine) as c:
        denied = await c.post(
            _BASE, headers=_auth(world.admin_a), json={**body, "sucursales_asignadas": [str(world.b)]}
        )
        mixed = await c.post(
            _BASE,
            headers=_auth(world.admin_a),
            json={**body, "email": "mix@parkos.local", "sucursales_asignadas": [str(world.a), str(world.b)]},
        )
        ok = await c.post(
            _BASE, headers=_auth(world.admin_a), json={**body, "sucursales_asignadas": [str(world.a)]}
        )
        glob = await c.post(
            _BASE,
            headers=_auth(world.admin_global),
            json={**body, "email": "glob@parkos.local", "sucursales_asignadas": [str(world.b)]},
        )
    assert denied.status_code == 403
    assert mixed.status_code == 403
    assert ok.status_code == 201, ok.text
    assert glob.status_code == 201, glob.text
    # The rejected creates left no user behind.
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        emails = (await s.execute(select(Usuarios.email))).scalars().all()
    assert "mix@parkos.local" not in emails


async def test_assign_branch_requires_user_and_branch_in_scope(pg_engine, world) -> None:
    async with _client(pg_engine) as c:
        foreign_user = await c.post(
            f"{_BASE}/{world.user_b}/sucursales",
            headers=_auth(world.admin_a),
            json={"uuid_sucursal": str(world.a)},
        )
        foreign_branch = await c.post(
            f"{_BASE}/{world.user_a}/sucursales",
            headers=_auth(world.admin_a),
            json={"uuid_sucursal": str(world.b)},
        )
        adopt_orphan = await c.post(
            f"{_BASE}/{world.user_orphan}/sucursales",
            headers=_auth(world.admin_a),
            json={"uuid_sucursal": str(world.a)},
        )
    assert foreign_user.status_code == 404
    assert foreign_branch.status_code == 403
    assert adopt_orphan.status_code == 201, adopt_orphan.text


async def test_assignments_read_and_revoke_are_scoped(pg_engine, world) -> None:
    async with _client(pg_engine) as c:
        foreign_list = await c.get(f"{_BASE}/{world.user_b}/sucursales", headers=_auth(world.admin_a))
        foreign_revoke = await c.post(
            f"{_BASE}/{world.user_b}/sucursales/{world.b}/revocar", headers=_auth(world.admin_a)
        )
        own_list = await c.get(f"{_BASE}/{world.user_a}/sucursales", headers=_auth(world.admin_a))
    assert foreign_list.status_code == 404
    assert foreign_revoke.status_code == 404
    assert own_list.status_code == 200
    assert [r["uuid_sucursal"] for r in own_list.json()] == [str(world.a)]


async def test_revoke_cannot_close_a_branch_outside_scope(pg_engine, world) -> None:
    shared = await _seed_user(
        async_sessionmaker(pg_engine, expire_on_commit=False),
        rol="operador",
        branches=[world.a, world.b],
    )
    async with _client(pg_engine) as c:
        denied = await c.post(
            f"{_BASE}/{shared}/sucursales/{world.b}/revocar", headers=_auth(world.admin_a)
        )
        ok = await c.post(
            f"{_BASE}/{shared}/sucursales/{world.a}/revocar", headers=_auth(world.admin_a)
        )
    assert denied.status_code == 403
    assert ok.status_code == 204


async def test_permission_endpoints_are_scoped(pg_engine, world) -> None:
    permiso = await _permiso_uuid(pg_engine)
    async with _client(pg_engine) as c:
        list_foreign = await c.get(f"{_BASE}/{world.user_b}/permisos", headers=_auth(world.admin_a))
        grant_foreign = await c.post(
            f"{_BASE}/{world.user_b}/permisos/{permiso}", headers=_auth(world.admin_a)
        )
        revoke_foreign = await c.post(
            f"{_BASE}/{world.user_b}/permisos/{permiso}/revocar", headers=_auth(world.admin_a)
        )
        grant_own = await c.post(
            f"{_BASE}/{world.user_a}/permisos/{permiso}", headers=_auth(world.admin_a)
        )
    assert list_foreign.status_code == 404
    assert grant_foreign.status_code == 404
    assert revoke_foreign.status_code == 404
    assert grant_own.status_code == 201, grant_own.text


async def test_sessions_and_login_history_are_scoped(pg_engine, world) -> None:
    async with _client(pg_engine) as c:
        ses = await c.get(f"{_BASE}/{world.user_b}/sesiones", headers=_auth(world.admin_a))
        hist = await c.get(f"{_BASE}/{world.user_b}/login-historico", headers=_auth(world.admin_a))
        close = await c.post(
            f"{_BASE}/{world.user_b}/sesiones/{uuid_lib.uuid4()}/cerrar", headers=_auth(world.admin_a)
        )
        own_ses = await c.get(f"{_BASE}/{world.user_a}/sesiones", headers=_auth(world.admin_a))
        own_hist = await c.get(f"{_BASE}/{world.user_a}/login-historico", headers=_auth(world.admin_a))
    assert ses.status_code == 404
    assert hist.status_code == 404
    assert close.status_code == 404
    assert own_ses.status_code == 200
    assert own_hist.status_code == 200


async def test_scope_is_read_from_db_not_from_jwt_claim(pg_engine, world) -> None:
    """Revoking the actor's own branch assignment takes effect on the next call."""
    async with _client(pg_engine) as c:
        before = await c.get(f"{_BASE}/{world.user_a}", headers=_auth(world.admin_a))
        Session = async_sessionmaker(pg_engine, expire_on_commit=False)
        async with Session() as s:
            await s.execute(
                text(
                    "UPDATE prod.usuarios_sucursal SET vigente_hasta = NOW() "
                    "WHERE uuid_usuario = :u"
                ),
                {"u": world.admin_a},
            )
            await s.commit()
        after = await c.get(f"{_BASE}/{world.user_a}", headers=_auth(world.admin_a))
    assert before.status_code == 200
    assert after.status_code == 404
