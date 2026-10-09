"""Pairing-tokens admin-issuer scope -- regression for the
listener-sabotage bug in ``extract_sucursales_permitidas_fresh``.

Real Postgres, real handlers, real ``admin-`` JWTs (no mocks). The
``do_orm_execute`` listener in ``db/tenancy.py`` auto-filters SELECTs by
the active tenant context. Before the 2026-10-09 fix, the SELECT inside
``extract_sucursales_permitidas_fresh`` was sabotaged when the caller
already had a tenant context bound (e.g. an admin request with
``X-Sucursal-Context: B`` set in ``get_tenant_ctx``): the listener added
``WHERE uuid_sucursal = B`` to the SELECT on ``prod.usuarios_sucursal``,
so the function returned ``[B]`` (or empty) instead of the admin's full
permitted set. Downstream ``BranchScope.permitidas`` was ``{B}`` and
``scope.allows(A)`` returned False, so legitimate multi-branch
operations got spurious 403 ``tenant_scope_violation``.

This file pins the contract end-to-end: an admin with N>=2 branches in
``usuarios_sucursal`` can issue/read/revoke tokens for any of them,
regardless of the ``X-Sucursal-Context`` header. An admin whose
``usuarios_sucursal`` is missing a branch gets a clean 403, and an
admin with an empty permitidas set gets a clean 403.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
for _p in (
    _BACKEND_ROOT / "packages" / "parkos_core" / "src",
    _BACKEND_ROOT / "packages" / "api_admin" / "src",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from parkos_core.api.v1 import pairing as _pairing  # noqa: E402
from parkos_core.auth.tokens import issue_token  # noqa: E402
from parkos_core.db.engine import get_session  # noqa: E402
from parkos_core.models.V.sucursal import Sucursal  # noqa: E402
from parkos_core.models.V.usuarios import Usuarios  # noqa: E402
from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal  # noqa: E402

_BASE = "/api/v1/admin/pairing-tokens"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _app(pg_engine) -> FastAPI:
    """Minimal app with the pairing router + a real-session override.

    The pairing router's 3 endpoints (POST issue, GET read, POST
    revoke) + the 4th (POST revoke-sync) are mounted. The other admin
    dependencies (issuer guard, permission guard, rate limiter) are
    not overridden -- they would block with 401 before the scope check
    ever runs. We swap them out for stubs that always pass.
    """
    from fastapi import APIRouter
    from parkos_core.api.deps import requires_issuer
    from parkos_core.api.rate_limit_pairing import default_limiter
    from parkos_core.auth.jwt_issuer_guard import requires_issuer as _r
    from parkos_core.auth.permissions import require_permission

    app = FastAPI()
    outer = APIRouter(prefix="/api/v1")
    outer.include_router(_pairing.router)
    outer.include_router(_pairing.sync_revoke_router)
    app.include_router(outer)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async def _override() -> AsyncIterator:
        async with Session() as session:
            yield session

    async def _issuer_stub() -> dict[str, str]:
        return {"sub": "", "iss": "admin-test"}

    async def _perm_stub() -> dict[str, str]:
        return {"sub": "", "iss": "admin-test"}

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[_pairing._admin_issuer_dep] = _issuer_stub
    app.dependency_overrides[_pairing._manage_perm_dep] = _perm_stub
    default_limiter.reset()
    return app


def _auth(actor: uuid_lib.UUID) -> dict[str, str]:
    """Mint a real admin- JWT. The ``sucursales_permitidas`` claim is a
    *login-time snapshot* and is deliberately UNRELATED to the
    actor's actual ``prod.usuarios_sucursal`` rows -- the test
    verifies that the DB is the source of truth, not the claim."""
    token = issue_token(
        subject_uuid=actor,
        issuer="admin-test",
        claims={"rol": "admin", "sucursales_permitidas": [str(uuid_lib.uuid4())]},
        expires_in=3600,
    )
    return {"Authorization": f"Bearer {token}"}


async def _seed_sucursal(Session, *, nombre: str) -> uuid_lib.UUID:
    async with Session() as s:
        row = Sucursal(
            nombre=nombre,
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
                nombre="Pairing",
                apellido="Scope",
                email=f"pairing-scope-{user_uuid.hex[:10]}@parkos.local",
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
    a: uuid_lib.UUID
    b: uuid_lib.UUID
    c: uuid_lib.UUID  # outside the global admin's permitidas set
    admin_global: uuid_lib.UUID
    admin_limited: uuid_lib.UUID  # only sees branch a
    admin_empty: uuid_lib.UUID  # no permitidas rows


@pytest_asyncio.fixture
async def world(pg_engine, alembic_upgrade) -> AsyncIterator[_World]:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(
            text(
                "TRUNCATE prod.usuarios_sucursal, prod.usuarios, "
                "prod.pairing_tokens, prod.sucursal CASCADE"
            )
        )
        await s.commit()
    w = _World()
    w.a = await _seed_sucursal(Session, nombre="Pairing-Scope-A")
    w.b = await _seed_sucursal(Session, nombre="Pairing-Scope-B")
    w.c = await _seed_sucursal(Session, nombre="Pairing-Scope-C")
    w.admin_global = await _seed_user(
        Session, rol="admin", branches=[w.a, w.b]
    )
    w.admin_limited = await _seed_user(Session, rol="admin", branches=[w.a])
    w.admin_empty = await _seed_user(Session, rol="admin", branches=[])
    yield w


def _client(pg_engine) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(pg_engine)),
        base_url="http://cloud",
    )


# ---------------------------------------------------------------------------
# POST /admin/pairing-tokens  (issue)
# ---------------------------------------------------------------------------


async def test_global_admin_can_issue_for_either_branch_with_any_header(
    pg_engine, world
) -> None:
    """Regression (2026-10-09): the do_orm_execute listener was
    sabotaging ``extract_sucursales_permitidas_fresh`` -- the SELECT
    on ``prod.usuarios_sucursal`` was being filtered by the admin's
    ``X-Sucursal-Context`` header, so ``BranchScope.permitidas``
    contained only the header branch and the other permitted branch
    was rejected with a spurious 403. With the suspend wrapped
    around the SELECT, the full permitted set is read regardless of
    the header."""
    async with _client(pg_engine) as c:
        for header_branch, body_branch in (
            (world.a, world.b),
            (world.b, world.a),
            (world.a, world.a),
            (world.b, world.b),
        ):
            r = await c.post(
                _BASE,
                headers={
                    **_auth(world.admin_global),
                    "X-Sucursal-Context": str(header_branch),
                },
                json={
                    "uuid_sucursal": str(body_branch),
                    "ttl_hours": 24,
                },
            )
            assert r.status_code == 201, (
                f"header={header_branch} body={body_branch} -> "
                f"{r.status_code} {r.text}"
            )
            body = r.json()
            assert body["uuid_sucursal"] == str(body_branch)
            assert "token" in body and len(body["token"]) == 43


async def test_global_admin_no_header_issues_for_either_branch(
    pg_engine, world
) -> None:
    """Admin global mode (no ``X-Sucursal-Context``): any permitted
    branch is fair game. ``ctx.sucursal_uuid`` is None, so
    ``set_tenant_context`` is never called and the listener never
    fires on the scope-defining SELECT. The pre-fix code happened to
    work in this path; the post-fix path also works."""
    async with _client(pg_engine) as c:
        for body_branch in (world.a, world.b):
            r = await c.post(
                _BASE,
                headers=_auth(world.admin_global),
                json={"uuid_sucursal": str(body_branch), "ttl_hours": 24},
            )
            assert r.status_code == 201, r.text


async def test_global_admin_rejects_branch_outside_permitidas(
    pg_engine, world
) -> None:
    """The admin has {a, b}; issuing for c (not in permitidas) is 403
    -- the OPPOSITE failure mode of the listener-sabotage bug.
    The fix must preserve the "reject genuinely out-of-scope" path."""
    async with _client(pg_engine) as c:
        r = await c.post(
            _BASE,
            headers={
                **_auth(world.admin_global),
                "X-Sucursal-Context": str(world.a),
            },
            json={"uuid_sucursal": str(world.c), "ttl_hours": 24},
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["error"] == "tenant_scope_violation"


async def test_limited_admin_with_header_outside_scope_raises_unauthorized_context(
    pg_engine, world
) -> None:
    """Admin_limited has only {a}. Sending ``X-Sucursal-Context: b``
    (not in permitidas) fails the *header* check in
    ``get_tenant_ctx`` with 403 ``unauthorized_sucursal_context``
    BEFORE the request body is even read. This is a separate guard
    from the body scope check and exists by design."""
    async with _client(pg_engine) as c:
        r = await c.post(
            _BASE,
            headers={
                **_auth(world.admin_limited),
                "X-Sucursal-Context": str(world.b),
            },
            json={"uuid_sucursal": str(world.a), "ttl_hours": 24},
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["error"] == "unauthorized_sucursal_context"


async def test_limited_admin_cannot_issue_for_branch_outside_permitidas(
    pg_engine, world
) -> None:
    """Admin_limited has only {a}; no header; body=b. Should 403 with
    ``tenant_scope_violation`` (not ``unauthorized_sucursal_context``,
    since the header is absent and the body's branch is genuinely
    outside the DB-permitted set)."""
    async with _client(pg_engine) as c:
        r = await c.post(
            _BASE,
            headers=_auth(world.admin_limited),
            json={"uuid_sucursal": str(world.b), "ttl_hours": 24},
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["error"] == "tenant_scope_violation"


# ---------------------------------------------------------------------------
# GET /admin/pairing-tokens/{uuid}  (read)
# ---------------------------------------------------------------------------


async def test_global_admin_can_read_a_token_for_either_branch_with_any_header(
    pg_engine, world
) -> None:
    """The GET endpoint re-applies the same scope check (post-read).
    An admin with {a, b} must be able to read a token for either
    branch, regardless of which branch the picker header points at."""
    async with _client(pg_engine) as c:
        # Issue for branch b (with header a)
        issue = await c.post(
            _BASE,
            headers={
                **_auth(world.admin_global),
                "X-Sucursal-Context": str(world.a),
            },
            json={"uuid_sucursal": str(world.b), "ttl_hours": 24},
        )
        assert issue.status_code == 201, issue.text
        token_uuid = issue.json()["pairing_token_uuid"]

        # Read with header a (same as issue)
        r = await c.get(
            f"{_BASE}/{token_uuid}",
            headers={
                **_auth(world.admin_global),
                "X-Sucursal-Context": str(world.a),
            },
        )
        assert r.status_code == 200, r.text

        # Read with header b (the branch the token is bound to)
        r = await c.get(
            f"{_BASE}/{token_uuid}",
            headers={
                **_auth(world.admin_global),
                "X-Sucursal-Context": str(world.b),
            },
        )
        assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# POST /admin/pairing-tokens/{uuid}/revoke
# ---------------------------------------------------------------------------


async def test_global_admin_can_revoke_a_token_for_either_branch_with_any_header(
    pg_engine, world
) -> None:
    async with _client(pg_engine) as c:
        # Issue for branch a (with header b)
        issue = await c.post(
            _BASE,
            headers={
                **_auth(world.admin_global),
                "X-Sucursal-Context": str(world.b),
            },
            json={"uuid_sucursal": str(world.a), "ttl_hours": 24},
        )
        assert issue.status_code == 201, issue.text
        token_uuid = issue.json()["pairing_token_uuid"]

        # Revoke with header b (the picker value, NOT the row's branch)
        r = await c.post(
            f"{_BASE}/{token_uuid}/revoke",
            headers={
                **_auth(world.admin_global),
                "X-Sucursal-Context": str(world.b),
            },
        )
        assert r.status_code == 204, r.text
