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

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
_API_ADMIN_SRC = _BACKEND_ROOT / "packages" / "api_admin" / "src"
for _p in (_PARKOS_CORE_SRC, _API_ADMIN_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from parkos_core.api.v1.admin_usuarios import router as admin_router_obj  # noqa: E402
from parkos_core.auth.tokens import issue_token  # noqa: E402
from parkos_core.db.engine import get_session  # noqa: E402
from parkos_core.models.A.sync_queue import SyncQueue  # noqa: E402
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
    app.include_router(outer)

    # Override get_session so the handler uses the testcontainers DB.
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async def _session_override() -> AsyncIterator:
        async with Session() as session:
            yield session

    app.dependency_overrides[get_session] = _session_override

    return app


def _admin_token(*, actor_uuid: uuid_lib.UUID | None = None, expires_in: int = 3600) -> str:
    """Mint a REAL ``admin-`` JWT for the happy path."""
    return issue_token(
        subject_uuid=actor_uuid or uuid_lib.uuid4(),
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
        return row.uuid


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
                "TRUNCATE prod.usuarios_sucursal, prod.usuarios, "
                "prod.sync_queue, prod.sucursal CASCADE"
            )
        )
        await session.commit()
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
        deassign = await client.delete(
            f"/api/v1/admin/usuarios/{user_uuid}/sucursales/{sucursal_a}",
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

        # Deassign.
        deassign = await client.delete(
            f"/api/v1/admin/usuarios/{user_uuid}/sucursales/{sucursal_a}",
            headers=auth,
        )
        assert deassign.status_code == 204, deassign.text

        # List -> zero.
        lst2 = await client.get(f"/api/v1/admin/usuarios/{user_uuid}/sucursales", headers=auth)
        assert lst2.status_code == 200
        assert lst2.json() == []

        # Deassign again -> 404 (no open row).
        deassign2 = await client.delete(
            f"/api/v1/admin/usuarios/{user_uuid}/sucursales/{sucursal_a}",
            headers=auth,
        )
        assert deassign2.status_code == 404, deassign2.text


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
