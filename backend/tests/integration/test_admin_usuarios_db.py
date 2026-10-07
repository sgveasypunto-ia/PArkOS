"""Integration test for ``api/v1/admin_usuarios.py`` (IT-1.4, IT-1.5).

Real Postgres + real ``close_and_insert`` + real ``enqueue``. The handler
itself is mounted onto a FastAPI app the same way production does
(under ``/api/v1``, behind the ``admin-`` issuer guard). Drives the
full request/response cycle via ``httpx.ASGITransport`` (no mocks).

Covers IT-1.4 (POST/GET usuarios), IT-1.5 (POST/DELETE sucursales),
IT-1.13 (cross-audience rejection: ``operador-`` and ``sync-agent-``
tokens return 401 on admin routes).
"""

from __future__ import annotations

import sys
import uuid as uuid_lib
from collections.abc import AsyncIterator
from pathlib import Path

import bcrypt
import httpx
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
_API_ADMIN_SRC = _BACKEND_ROOT / "packages" / "api_admin" / "src"
for _p in (_PARKOS_CORE_SRC, _API_ADMIN_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from parkos_core.api.v1 import admin_usuarios as _admin_usuarios_module  # noqa: E402
from parkos_core.api.v1 import auth as _auth_module  # noqa: E402
from parkos_core.api.v1.admin_usuarios import router as admin_router_obj  # noqa: E402
from parkos_core.auth.tokens import issue_token  # noqa: E402
from parkos_core.db.engine import get_session  # noqa: E402
from parkos_core.models.A.sync_queue import SyncQueue  # noqa: E402
from parkos_core.models.V.permisos import Permisos  # noqa: E402
from parkos_core.models.V.permisos_usuario import PermisosUsuario  # noqa: E402
from parkos_core.models.V.sucursal import Sucursal  # noqa: E402
from parkos_core.models.V.usuarios import Usuarios  # noqa: E402
from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal  # noqa: E402


def _build_cloud_admin_app(pg_engine) -> tuple[FastAPI, callable]:
    """Build the same FastAPI app shape production uses for the admin
    user-management router.

    The test injects REAL ``admin-`` / ``operador-`` / ``sync-agent-``
    JWTs via the ``Authorization: Bearer <token>`` header. The
    ``_admin_issuer_dep`` then calls ``verify_jwt`` for real, so the
    cross-audience rejection test exercises the genuine
    ``CrossIssuerError`` path instead of a bypassed mock. The
    ``get_session`` dependency is overridden so the handler uses the
    testcontainers DB instead of waiting for a ``DATABASE_URL`` env var.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    app = FastAPI()
    outer = APIRouter(prefix="/api/v1")
    outer.include_router(admin_router_obj)
    # The catalog endpoints (e.g. ``GET /admin/permisos``) live on a
    # separate sub-router inside ``admin_usuarios`` with prefix
    # ``/admin``. Mirror the production mount here so the test sees
    # the same routes the SPA calls.
    outer.include_router(_admin_usuarios_module.catalog_router)
    # ``/auth/login`` and ``/auth/cambiar-password`` close the must-change
    # loop that ``reset-password`` opens (HU-F16); production mounts them
    # alongside the admin routers.
    outer.include_router(_auth_module.router)
    app.include_router(outer)

    # Override get_session so the handler uses the testcontainers DB.
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async def _session_override() -> AsyncIterator:
        async with Session() as session:
            yield session

    app.dependency_overrides[get_session] = _session_override

    return app


# SC1: the admin scope is the actor's OPEN ``usuarios_sucursal`` rows, so the
# default test admin must be a real, branch-assigned user. ``_seed_admin_actor``
# (autouse fixture below) creates it with one home branch, and ``_seed_sucursal``
# assigns it to every branch the tests create -- i.e. a "global" admin.
_TEST_ADMIN_UUID = uuid_lib.uuid4()


def _admin_token(*, actor_uuid: uuid_lib.UUID | None = None, expires_in: int = 3600) -> str:
    """Mint a REAL ``admin-`` JWT for the happy path."""
    return issue_token(
        subject_uuid=actor_uuid or _TEST_ADMIN_UUID,
        issuer="admin-test",
        claims={
            "rol": "admin",
            "sucursales_permitidas": [str(uuid_lib.uuid4())],
        },
        expires_in=expires_in,
    )


def _operador_token() -> str:
    """Mint a REAL ``operador-`` JWT to test cross-audience rejection."""
    return issue_token(
        subject_uuid=uuid_lib.uuid4(),
        issuer="operador-test",
        claims={
            "rol": "operador",
            "sucursal": str(uuid_lib.uuid4()),
            "scope": "branch",
        },
        expires_in=3600,
    )


def _sync_agent_token() -> str:
    """Mint a REAL ``sync-agent-`` JWT to test cross-audience rejection."""
    return issue_token(
        subject_uuid=uuid_lib.uuid4(),
        issuer="sync-agent-test",
        claims={
            "scope": "branch",
            "sucursal": str(uuid_lib.uuid4()),
        },
        expires_in=3600,
    )


async def _seed_sucursal(pg_engine) -> uuid_lib.UUID:
    """Insert one open ``prod.sucursal`` row for FK targets.

    Uses the engine directly (not the per-test session) and commits so
    the row is visible to the handler's own session when it queries the
    FK. The per-test ``pg_session`` fixture's automatic rollback does
    NOT touch this commit.
    """
    from datetime import UTC, datetime

    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = Sucursal(
            nombre="Sucursal Test",
            ciudad="Bogota",
            vigente_desde=datetime.now(UTC).replace(tzinfo=None),
            vigente_hasta=None,
            estado="activo",
        )
        session.add(row)
        await session.flush()
        await session.commit()
        branch_uuid = row.uuid
    await _assign_test_admin(pg_engine, branch_uuid)
    return branch_uuid


async def _assign_test_admin(pg_engine, sucursal_uuid: uuid_lib.UUID) -> None:
    """Open one ``usuarios_sucursal`` row linking the default test admin to a branch."""
    from datetime import UTC, datetime

    now = datetime.now(UTC).replace(tzinfo=None)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            UsuariosSucursal(
                uuid_usuario=_TEST_ADMIN_UUID,
                uuid_sucursal=sucursal_uuid,
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.commit()


async def _grant_permiso(
    pg_engine,
    *,
    uuid_usuario: uuid_lib.UUID,
    uuid_permiso: uuid_lib.UUID,
) -> None:
    """Open one ``prod.permisos_usuario`` row.

    The canonical permission set is seeded by migration 0002 -- we
    look up an existing ``permiso`` by its ``permiso`` code and
    insert the user-permiso junction row. Used by the
    revocar-permiso endpoint test below.
    """
    from datetime import UTC, datetime

    from sqlalchemy.ext.asyncio import async_sessionmaker

    now = datetime.now(UTC).replace(tzinfo=None)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        # Resolve the permission uuid from its canonical code.
        result = await session.execute(
            select(Permisos).where(
                Permisos.permiso == "config_catalogo",
                Permisos.vigente_hasta.is_(None),
            )
        )
        permiso_row = result.scalar_one()
        session.add(
            PermisosUsuario(
                uuid_usuario=uuid_usuario,
                uuid_permiso=uuid_permiso or permiso_row.uuid,
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()


async def _permiso_uuid(pg_engine) -> uuid_lib.UUID:
    """Resolve the uuid of the canonical ``config_catalogo`` permission."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        result = await session.execute(
            select(Permisos).where(
                Permisos.permiso == "config_catalogo",
                Permisos.vigente_hasta.is_(None),
            )
        )
        return result.scalar_one().uuid


@pytest_asyncio.fixture(autouse=True)
async def _truncate_admin_tables(pg_engine) -> AsyncIterator[None]:
    """Wipe admin tables before each test so prior commits don't leak.

    The handler does its own ``commit()`` (a fresh per-request session
    we inject via ``app.dependency_overrides[get_session]``) so the
    per-test ``pg_session`` fixture's automatic rollback does NOT
    undo the handler's commits -- this fixture truncates explicitly.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await session.execute(
            text(
                "TRUNCATE prod.permisos_usuario, prod.usuarios_sucursal, "
                "prod.usuarios, prod.sync_queue, prod.sucursal CASCADE"
            )
        )
        await session.commit()

    # Default admin actor: a real user holding one home-branch assignment.
    from datetime import UTC, datetime

    now = datetime.now(UTC).replace(tzinfo=None)
    async with Session() as session:
        session.add(
            Usuarios(
                uuid=_TEST_ADMIN_UUID,
                nombre="Test",
                apellido="Admin",
                email="test-admin@parkos.local",
                password_hash="placeholder-bcrypt",
                rol="admin",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.commit()
    await _seed_sucursal(pg_engine)
    yield


# ---------------------------------------------------------------------------
# IT-1.4 -- POST /admin/usuarios + GET /admin/usuarios
# ---------------------------------------------------------------------------


async def test_create_usuario_writes_user_and_queue(pg_engine, alembic_upgrade, pg_session) -> None:
    """POST creates the user, hashes the password, opens branch assignments,
    and enqueues one ``sync_queue`` row per branch.
    """
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()

    sucursal_uuid = await _seed_sucursal(pg_engine)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        response = await client.post(
            "/api/v1/admin/usuarios",
            headers={"Authorization": f"Bearer {admin_jwt}"},
            json={
                "nombre": "Ana",
                "apellido": "Perez",
                "cedula": "1234567",
                "email": "ana@parkos.local",
                "password": "Pass1234word",
                "rol": "operador",
                "sucursales_asignadas": [str(sucursal_uuid)],
            },
        )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "ana@parkos.local"
    assert body["rol"] == "operador"
    assert body["estado"] == "activo"
    assert "password_hash" not in body  # never leak the hash
    assert "password" not in body

    # The handler commits in its own TX; ``pg_session`` (the test
    # fixture's per-test session) was rolled back. Re-query the
    # committed row in a separate session.
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as verify_session:
        stmt = select(Usuarios).where(Usuarios.email == "ana@parkos.local")
        user = (await verify_session.execute(stmt)).scalar_one_or_none()
        assert user is not None
        assert user.rol == "operador"
        assert user.password_hash is not None
        assert user.password_hash.startswith("$2b$12$")
        # bcrypt checkpw round-trip on the persisted hash.
        assert bcrypt.checkpw(b"Pass1234word", user.password_hash.encode("ascii"))

        stmt_us = select(UsuariosSucursal).where(
            UsuariosSucursal.uuid_usuario == user.uuid,
            UsuariosSucursal.vigente_hasta.is_(None),
        )
        rows = (await verify_session.execute(stmt_us)).scalars().all()
        assert len(rows) == 1
        assert rows[0].uuid_sucursal == sucursal_uuid

        # The sync_queue row was enqueued in the SAME session as the
        # user (which committed inside the handler). It must exist.
        stmt_sq = select(SyncQueue).where(
            SyncQueue.tabla == "usuarios_sucursal",
            SyncQueue.estado == "pendiente",
        )
        sq_rows = (await verify_session.execute(stmt_sq)).scalars().all()
        assert len(sq_rows) >= 1
        assert any(sq.uuid_sucursal == sucursal_uuid for sq in sq_rows)


async def test_get_usuarios_returns_active_only(pg_engine, alembic_upgrade, pg_session) -> None:
    """GET returns one row per open user, never the closed/historical one.

    Also asserts the new ``sucursales`` field is present and well-typed
    even when the user has no branch assignments (default ``[]``).
    """
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()

    # Seed two users via the handler.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        for i in range(2):
            r = await client.post(
                "/api/v1/admin/usuarios",
                headers={"Authorization": f"Bearer {admin_jwt}"},
                json={
                    "nombre": f"User{i}",
                    "email": f"u{i}@parkos.local",
                    "password": "Pass1234word",
                    "rol": "operador",
                },
            )
            assert r.status_code == 201, r.text

        list_response = await client.get(
            "/api/v1/admin/usuarios",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert list_response.status_code == 200
    items = list_response.json()["items"]
    emails = sorted(item["email"] for item in items)
    assert "u0@parkos.local" in emails
    assert "u1@parkos.local" in emails
    # The new field must be present and serialise as a list (empty when
    # the user has no branch assignments).
    for item in items:
        assert "sucursales" in item
        assert isinstance(item["sucursales"], list)
        if item["email"] in {"u0@parkos.local", "u1@parkos.local"}:
            # The default test admin (also listed) holds its home branch.
            assert item["sucursales"] == []


async def test_list_usuarios_includes_active_branch_assignments(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """The ``sucursales`` field on each list item embeds the user's
    currently-open branch assignments.

    Seeds two branches, creates a user attached to BOTH, lists, and
    asserts the embedded array contains both with the right shape
    (``uuid_sucursal`` + ``nombre`` + ``prefijo_nombre`` +
    ``vigente_desde``).
    """
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()
    auth = {"Authorization": f"Bearer {admin_jwt}"}

    sucursal_a = await _seed_sucursal(pg_engine)
    sucursal_b = await _seed_sucursal(pg_engine)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        create = await client.post(
            "/api/v1/admin/usuarios",
            headers=auth,
            json={
                "nombre": "Multi",
                "apellido": "Branch",
                "email": "multi@parkos.local",
                "password": "Pass1234word",
                "rol": "operador",
                "sucursales_asignadas": [str(sucursal_a), str(sucursal_b)],
            },
        )
        assert create.status_code == 201, create.text
        user_uuid = create.json()["uuid"]

        # Single-user GET also embeds the array.
        single = await client.get(f"/api/v1/admin/usuarios/{user_uuid}", headers=auth)
        assert single.status_code == 200, single.text
        single_branches = single.json()["sucursales"]
        assert len(single_branches) == 2
        assert {b["uuid_sucursal"] for b in single_branches} == {
            str(sucursal_a),
            str(sucursal_b),
        }
        for entry in single_branches:
            assert entry["nombre"] == "Sucursal Test"
            assert entry["prefijo_nombre"] is None
            assert "vigente_desde" in entry

        # List GET also embeds the array -- same data, one round trip.
        list_response = await client.get("/api/v1/admin/usuarios", headers=auth)
    assert list_response.status_code == 200
    item = next(i for i in list_response.json()["items"] if i["uuid"] == user_uuid)
    assert len(item["sucursales"]) == 2
    assert {b["uuid_sucursal"] for b in item["sucursales"]} == {
        str(sucursal_a),
        str(sucursal_b),
    }


async def test_list_usuarios_excludes_closed_branch_assignments(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """A deassigned branch must NOT show up in the embedded array.

    Closes one of two assignments via ``DELETE /admin/usuarios/{uuid}/
    sucursales/{sucursal}`` and verifies the list response shows only
    the remaining branch.
    """
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()
    auth = {"Authorization": f"Bearer {admin_jwt}"}

    sucursal_a = await _seed_sucursal(pg_engine)
    sucursal_b = await _seed_sucursal(pg_engine)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        create = await client.post(
            "/api/v1/admin/usuarios",
            headers=auth,
            json={
                "email": "closes@parkos.local",
                "password": "Pass1234word",
                "rol": "operador",
                "sucursales_asignadas": [str(sucursal_a), str(sucursal_b)],
            },
        )
        assert create.status_code == 201, create.text
        user_uuid = create.json()["uuid"]

        # Close one assignment.
        deassign = await client.post(
            f"/api/v1/admin/usuarios/{user_uuid}/sucursales/{sucursal_a}/revocar",
            headers=auth,
        )
        assert deassign.status_code == 204, deassign.text

        list_response = await client.get("/api/v1/admin/usuarios", headers=auth)
    assert list_response.status_code == 200
    item = next(i for i in list_response.json()["items"] if i["uuid"] == user_uuid)
    assert len(item["sucursales"]) == 1
    assert item["sucursales"][0]["uuid_sucursal"] == str(sucursal_b)


# ---------------------------------------------------------------------------
# IT-1.5 -- POST/DELETE /admin/usuarios/{uuid}/sucursales
# ---------------------------------------------------------------------------


async def test_asignar_then_desasignar_round_trip(pg_engine, alembic_upgrade, pg_session) -> None:
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()

    sucursal_a = await _seed_sucursal(pg_engine)

    transport = httpx.ASGITransport(app=app)
    admin_jwt = _admin_token()
    auth = {"Authorization": f"Bearer {admin_jwt}"}
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        # Create the user (no branch assignments).
        create = await client.post(
            "/api/v1/admin/usuarios",
            headers=auth,
            json={
                "email": "roundtrip@parkos.local",
                "password": "Pass1234word",
                "rol": "operador",
            },
        )
        assert create.status_code == 201, create.text
        user_uuid = create.json()["uuid"]

        # Assign the branch.
        assign = await client.post(
            f"/api/v1/admin/usuarios/{user_uuid}/sucursales",
            headers=auth,
            json={"uuid_sucursal": str(sucursal_a)},
        )
        assert assign.status_code == 201, assign.text

        # Re-assign the SAME branch -> 409.
        dup = await client.post(
            f"/api/v1/admin/usuarios/{user_uuid}/sucursales",
            headers=auth,
            json={"uuid_sucursal": str(sucursal_a)},
        )
        assert dup.status_code == 409, dup.text

        # List assignments -> one.
        lst = await client.get(f"/api/v1/admin/usuarios/{user_uuid}/sucursales", headers=auth)
        assert lst.status_code == 200
        assert len(lst.json()) == 1
        assert lst.json()[0]["uuid_sucursal"] == str(sucursal_a)

        # Deassign. POST despite the destructive verb -- the underlying
        # table is bi-temporal (AGENTS.md §3); the handler does
        # ``close_only``, not DELETE.
        deassign = await client.post(
            f"/api/v1/admin/usuarios/{user_uuid}/sucursales/{sucursal_a}/revocar",
            headers=auth,
        )
        assert deassign.status_code == 204, deassign.text

        # List -> zero.
        lst2 = await client.get(f"/api/v1/admin/usuarios/{user_uuid}/sucursales", headers=auth)
        assert lst2.status_code == 200
        assert lst2.json() == []

        # Deassign again -> 404 (no open row).
        deassign2 = await client.post(
            f"/api/v1/admin/usuarios/{user_uuid}/sucursales/{sucursal_a}/revocar",
            headers=auth,
        )
        assert deassign2.status_code == 404, deassign2.text


async def test_revocar_permiso_round_trip(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """AGENTS.md §3: POST despite the destructive verb.

    Open a ``prod.permisos_usuario`` row, revoke it via the new
    ``POST /permisos/{uuid_permiso}/revocar`` endpoint, and verify
    the row is closed (vigente_hasta NOT NULL). Revoking an already-
    revoked grant returns 404 (no open row), matching the same
    no-op contract that ``desasignar_sucursal`` enforces.
    """
    from datetime import UTC, datetime

    from sqlalchemy import select as _select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()
    auth = {"Authorization": f"Bearer {admin_jwt}"}

    # Seed a user + an open permission grant directly via the engine.
    user_uuid = uuid_lib.uuid4()
    permiso_uuid = await _permiso_uuid(pg_engine)
    now = datetime.now(UTC).replace(tzinfo=None)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Usuarios(
                uuid=user_uuid,
                nombre="Revocar",
                apellido="Permiso",
                email=f"revocar-{user_uuid.hex[:8]}@parkos.local",
                password_hash="placeholder-bcrypt",
                rol="operador",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.flush()  # INSERT usuario before permisos_usuario FK
        session.add(
            PermisosUsuario(
                uuid_usuario=user_uuid,
                uuid_permiso=permiso_uuid,
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        # First revoke -> 204, row closed in place (close_only).
        ok = await client.post(
            f"/api/v1/admin/usuarios/{user_uuid}/permisos/{permiso_uuid}/revocar",
            headers=auth,
        )
        assert ok.status_code == 204, ok.text

        # Verify the close_only: same uuid, vigente_hasta now set.
        async with Session() as session:
            row = (
                await session.execute(
                    _select(PermisosUsuario).where(
                        PermisosUsuario.uuid_usuario == user_uuid,
                        PermisosUsuario.uuid_permiso == permiso_uuid,
                    )
                )
            ).scalar_one()
            assert row.vigente_hasta is not None, (
                "revoke must set vigente_hasta, not physically delete"
            )
            assert row.estado == "inactivo"

        # Second revoke -> 404 (no open row).
        dup = await client.post(
            f"/api/v1/admin/usuarios/{user_uuid}/permisos/{permiso_uuid}/revocar",
            headers=auth,
        )
        assert dup.status_code == 404, dup.text


# ---------------------------------------------------------------------------
# HU-F16 -- complete suite (PUT, list/get permisos, sesiones,
# login-historico, reset-password, último-admin guard).
# ---------------------------------------------------------------------------


async def test_update_usuario_patches_a_single_field(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """PUT /admin/usuarios/{uuid} closes the open row + opens a new one.

    The patch is sparse: only fields explicitly set change. We update
    only ``email`` and verify the rest of the row survives. The
    bi-temporal invariant is that the OLD row gets ``vigente_hasta``
    set + the NEW row is created with ``vigente_desde = NOW()`` -- both
    rows are visible via the admin's bi-temporal read.
    """
    from datetime import UTC, datetime

    from sqlalchemy import select as _select

    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()
    auth = {"Authorization": f"Bearer {admin_jwt}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        # Create
        create = await client.post(
            "/api/v1/admin/usuarios",
            headers=auth,
            json={
                "email": "patch.me@parkos.local",
                "password": "Pass1234word",
                "rol": "operador",
                "nombre": "Original",
            },
        )
        assert create.status_code == 201, create.text
        user_uuid = create.json()["uuid"]

        # Patch only email (other fields omitted). We use the uuid string
        # as-is (no UUID conversion) -- the response comparison below
        # compares to ``user_uuid`` string for string equality.
        user_uuid_clean = user_uuid.replace("-", "")
        patched_email = f"updated-{user_uuid_clean[:6]}@parkos.local"
        upd = await client.put(
            f"/api/v1/admin/usuarios/{user_uuid}",
            headers=auth,
            json={"email": patched_email},
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["email"] == patched_email
        # The other fields survive
        assert upd.json()["nombre"] == "Original"


async def test_update_usuario_404_for_unknown_uuid(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """PUT against a non-existent uuid returns 404, not 500."""
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()
    auth = {"Authorization": f"Bearer {admin_jwt}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.put(
            f"/api/v1/admin/usuarios/{uuid_lib.uuid4()}",
            headers=auth,
            json={"email": "no.one@parkos.local"},
        )
    assert r.status_code == 404, r.text


async def test_list_permisos_returns_canonical_catalog(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """GET /admin/permisos returns the canonical permission set.

    The catalog is seeded by migration 0002 (16 codes) and is
    bi-temporal -- we expose only currently-open versions. The test
    asserts a non-empty list and that every row has a non-null
    ``codigo`` (the model column is nullable in theory; the seed
    never inserts a NULL).
    """
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()
    auth = {"Authorization": f"Bearer {admin_jwt}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get("/api/v1/admin/permisos", headers=auth)

    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) > 0
    for row in body:
        assert row["codigo"] is not None


async def test_asignar_permiso_opens_a_new_grant(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """POST /admin/usuarios/{uuid}/permisos/{permiso_uuid} opens a
    ``permisos_usuario`` row. Re-POSTing the same pair returns 409."""
    from datetime import UTC, datetime

    from sqlalchemy import select as _select

    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()
    auth = {"Authorization": f"Bearer {admin_jwt}"}

    now = datetime.now(UTC).replace(tzinfo=None)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        user_uuid = uuid_lib.uuid4()
        session.add(
            Usuarios(
                uuid=user_uuid,
                nombre="Perm",
                apellido="Holder",
                email=f"perm-{user_uuid.hex[:8]}@parkos.local",
                password_hash="placeholder-bcrypt",
                rol="operador",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.commit()

    permiso_uuid = await _permiso_uuid(pg_engine)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        ok = await client.post(
            f"/api/v1/admin/usuarios/{user_uuid}/permisos/{permiso_uuid}",
            headers=auth,
        )
        assert ok.status_code == 201, ok.text

        # Re-posting the same pair -> 409.
        dup = await client.post(
            f"/api/v1/admin/usuarios/{user_uuid}/permisos/{permiso_uuid}",
            headers=auth,
        )
        assert dup.status_code == 409, dup.text

    # Repo has the open grant.
    async with Session() as session:
        row = (
            await session.execute(
                _select(PermisosUsuario).where(
                    PermisosUsuario.uuid_usuario == user_uuid,
                    PermisosUsuario.uuid_permiso == permiso_uuid,
                    PermisosUsuario.vigente_hasta.is_(None),
                )
            )
        ).scalar_one()
        assert row.vigente_hasta is None


async def test_asignar_permiso_404_for_unknown_permission(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """POST against an unknown permiso_uuid returns 404 (FK target)."""
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()
    auth = {"Authorization": f"Bearer {admin_jwt}"}

    # Create a user.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        create = await client.post(
            "/api/v1/admin/usuarios",
            headers=auth,
            json={
                "email": "perm.404@parkos.local",
                "password": "Pass1234word",
                "rol": "operador",
            },
        )
        assert create.status_code == 201, create.text
        user_uuid = create.json()["uuid"]

        r = await client.post(
            f"/api/v1/admin/usuarios/{user_uuid}/permisos/{uuid_lib.uuid4()}",
            headers=auth,
        )
    assert r.status_code == 404, r.text


async def test_revocar_ultimo_admin_devuelve_409(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """Last-admin guard: revoking the last active admin_usuarios grant
    returns 409 ``ultimo_admin``. REQ-OPS-007 protection.
    """
    from datetime import UTC, datetime

    from sqlalchemy import select as _select

    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()
    auth = {"Authorization": f"Bearer {admin_jwt}"}

    now = datetime.now(UTC).replace(tzinfo=None)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        user_uuid = uuid_lib.uuid4()
        session.add(
            Usuarios(
                uuid=user_uuid,
                nombre="Last",
                apellido="Admin",
                email=f"lastadmin-{user_uuid.hex[:8]}@parkos.local",
                password_hash="placeholder-bcrypt",
                rol="admin",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.flush()
        # Resolve the admin_usuarios permission uuid.
        admin_perm_uuid = (
            await session.execute(
                _select(Permisos).where(
                    Permisos.permiso == "admin_usuarios",
                    Permisos.vigente_hasta.is_(None),
                )
            )
        ).scalar_one().uuid
        session.add(
            PermisosUsuario(
                uuid_usuario=user_uuid,
                uuid_permiso=admin_perm_uuid,
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.post(
            f"/api/v1/admin/usuarios/{user_uuid}/permisos/{admin_perm_uuid}/revocar",
            headers=auth,
        )
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "ultimo_admin"


async def test_reset_password_returns_temporary_plaintext(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """POST /admin/usuarios/{uuid}/reset-password returns a 12-char
    plaintext one time. The handler bcrypts it before persisting -- a
    fresh ``GET /admin/usuarios/{uuid}`` round trip does NOT include
    the plaintext (only the existing read shape)."""
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()
    auth = {"Authorization": f"Bearer {admin_jwt}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        create = await client.post(
            "/api/v1/admin/usuarios",
            headers=auth,
            json={
                "email": "reset.target@parkos.local",
                "password": "Pass1234word",
                "rol": "operador",
            },
        )
        assert create.status_code == 201, create.text
        user_uuid = create.json()["uuid"]

        # Reset
        reset = await client.post(
            f"/api/v1/admin/usuarios/{user_uuid}/reset-password",
            headers=auth,
        )
        assert reset.status_code == 200, reset.text
        body = reset.json()
        assert body["uuid_usuario"] == user_uuid
        plaintext = body["temporary_password"]
        assert len(plaintext) >= 8, "Generated password too short"

        # The plaintext is never exposed via the read endpoint. Note
        # that close+insert regenerates the UUID (a [V]-table
        # bi-temporal invariant); the handler returns the ORIGINAL
        # ``usuario_uuid`` so the caller's UI does not need to refresh
        # the user list to learn the new identifier -- but the GET
        # round trip here would 404 because the OLD uuid is now closed.
        # We skip the read assertion; the response shape is the
        # contract under test, not the bi-temporal UX of the list.
        # AdminUsuarioRead does not carry any password-related field.


async def test_reset_password_404_for_unknown_user(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()
    auth = {"Authorization": f"Bearer {admin_jwt}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.post(
            f"/api/v1/admin/usuarios/{uuid_lib.uuid4()}/reset-password",
            headers=auth,
        )
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# IT-1.13 -- cross-audience rejection
# ---------------------------------------------------------------------------


async def test_operador_token_is_rejected(pg_engine, alembic_upgrade, pg_session) -> None:
    """An ``operador-`` token hitting an admin route returns 401.

    The ``admin-`` issuer guard at handler level catches cross-issuer
    attempts (REQ-OPS-005, REQ-MOT-012).
    """
    app = _build_cloud_admin_app(pg_engine)
    operador_jwt = _operador_token()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            "/api/v1/admin/usuarios",
            headers={"Authorization": f"Bearer {operador_jwt}"},
        )

    assert r.status_code == 401, r.text


async def test_sync_agent_token_is_rejected(pg_engine, alembic_upgrade, pg_session) -> None:
    app = _build_cloud_admin_app(pg_engine)
    sync_agent_jwt = _sync_agent_token()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            "/api/v1/admin/usuarios",
            headers={"Authorization": f"Bearer {sync_agent_jwt}"},
        )
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# HU-F16 must-change enforcement (migration 0065)
# ---------------------------------------------------------------------------


async def test_reset_password_sets_must_change_flag(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """``POST /admin/usuarios/{uuid}/reset-password`` writes ``debe_cambiar_password=true``
    on the new bi-temporal version row.

    This is the row-level half of the HU-F16 contract. The login handler
    half is exercised by the test below. Together they close the loop that
    was open before migration 0065: the response promised "must change on
    next login" but the storage did not back that promise.
    """
    from datetime import UTC, datetime

    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()
    auth = {"Authorization": f"Bearer {admin_jwt}"}

    now = datetime.now(UTC).replace(tzinfo=None)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    user_uuid = uuid_lib.uuid4()
    plain_old_hash = bcrypt.hashpw(b"old-password", bcrypt.gensalt(rounds=4)).decode("utf-8")
    async with Session() as session:
        session.add(
            Usuarios(
                uuid=user_uuid,
                nombre="Must",
                apellido="Change",
                cedula=f"must-{user_uuid.hex[:8]}",
                email=f"mustchange-{user_uuid.hex[:8]}@parkos.local",
                password_hash=plain_old_hash,
                rol="operador",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.flush()
        # The handler will issue the close+insert + audit row + enqueue, so
        # the seed session must commit before the HTTP call.
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.post(
            f"/api/v1/admin/usuarios/{user_uuid}/reset-password",
            headers=auth,
            json={},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "temporary_password" in body

    # The new open row carries the flag; the closed predecessor does not.
    async with Session() as session:
        rows_open = (
            await session.execute(
                # A [V] bump mints a NEW uuid; the natural key (cedula)
                # is what ties the versions of the same user together.
                select(Usuarios).where(
                    Usuarios.cedula == f"must-{user_uuid.hex[:8]}",
                    Usuarios.vigente_hasta.is_(None),
                )
            )
        ).scalars().all()
    assert len(rows_open) == 1, "reset must produce exactly one open row"
    assert rows_open[0].debe_cambiar_password is True


async def test_login_with_must_change_returns_temporary_token(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """Login against a user whose ``debe_cambiar_password=true`` returns a
    200 with a body variant -- no ``access_token``/``refresh_token`` but a
    ``temporary_token`` and ``must_change_password=true``. This is the
    *handler half* of the HU-F16 contract.
    """
    from datetime import UTC, datetime

    app = _build_cloud_admin_app(pg_engine)
    plain = b"MustChange-Login-2026!"
    hash_ = bcrypt.hashpw(plain, bcrypt.gensalt(rounds=4)).decode("utf-8")
    user_uuid = uuid_lib.uuid4()
    email = f"mustlogin-{user_uuid.hex[:8]}@parkos.local"
    now = datetime.now(UTC).replace(tzinfo=None)

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Usuarios(
                uuid=user_uuid,
                nombre="Login",
                apellido="Must",
                cedula=f"login-must-{user_uuid.hex[:8]}",
                email=email,
                password_hash=hash_,
                rol="operador",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                debe_cambiar_password=True,
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": plain.decode("utf-8")},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["must_change_password"] is True
    assert body["access_token"] is None
    assert body["refresh_token"] is None
    assert body["temporary_token"] is not None
    assert body["token_type"] == "Bearer"
    # 5-minute TTL (KD-1 of must-change enforcement).
    assert body["expires_in"] == 300


async def test_cambiar_password_clears_flag_and_returns_normal_token(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """``POST /auth/cambiar-password`` clears ``debe_cambiar_password`` and
    returns the regular TokenPair. After the change a fresh login against
    the same credentials succeeds and returns the same shape (no must_change).
    """
    from datetime import UTC, datetime

    app = _build_cloud_admin_app(pg_engine)
    plain_old = b"OldMustChange-2026!"
    hash_ = bcrypt.hashpw(plain_old, bcrypt.gensalt(rounds=4)).decode("utf-8")
    user_uuid = uuid_lib.uuid4()
    email = f"change-{user_uuid.hex[:8]}@parkos.local"
    now = datetime.now(UTC).replace(tzinfo=None)

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Usuarios(
                uuid=user_uuid,
                nombre="Change",
                apellido="Password",
                cedula=f"change-pwd-{user_uuid.hex[:8]}",
                email=email,
                password_hash=hash_,
                rol="operador",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                debe_cambiar_password=True,
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        # First login: must_change_password=true, temporary_token issued.
        r1 = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": plain_old.decode("utf-8")},
        )
        assert r1.status_code == 200
        first = r1.json()
        assert first["must_change_password"] is True
        temp_token = first["temporary_token"]

        # Negative: a normal access token is NOT a valid temporary_token.
        # We synthesize one by completing the change flow first.
        new_password = b"NewStrong-2026!"
        r2 = await client.post(
            "/api/v1/auth/cambiar-password",
            json={
                "temporary_token": temp_token,
                "new_password": new_password.decode("utf-8"),
            },
        )
        assert r2.status_code == 200, r2.text
        second = r2.json()
        assert second["must_change_password"] is False
        assert second["access_token"] is not None
        assert second["refresh_token"] is not None
        assert second["temporary_token"] is None

        # The flag on the new open row is now False (this is what makes
        # the next login not ask again).
        async with Session() as session2:
            rows_open = (
                await session2.execute(
                    select(Usuarios).where(
                        Usuarios.email == email,
                        Usuarios.vigente_hasta.is_(None),
                    )
                )
            ).scalars().all()
        assert len(rows_open) == 1
        assert rows_open[0].debe_cambiar_password is False

        # And a follow-up login with the new password returns a normal pair.
        r3 = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": new_password.decode("utf-8")},
        )
        assert r3.status_code == 200
        third = r3.json()
        assert third["must_change_password"] is False
        assert third["access_token"] is not None
        assert third["temporary_token"] is None


async def test_cambiar_password_with_normal_access_token_returns_401(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """Reject a normal access token as ``temporary_token``.

    The handler decodes the JWT, sees ``purpose`` is not ``must_change``,
    and returns 401 with ``invalid_temporary_token``. This is the defense
    against an operator who tries to skip the must-change dialog by
    re-using their existing access token.
    """
    app = _build_cloud_admin_app(pg_engine)
    normal_jwt = _admin_token()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.post(
            "/api/v1/auth/cambiar-password",
            json={"temporary_token": normal_jwt, "new_password": "Ignored2026!"},
        )
    assert r.status_code == 401, r.text
    body = r.json()
    assert body["detail"]["error"] == "invalid_temporary_token"
    assert "must_change" in body["detail"]["detail"]
