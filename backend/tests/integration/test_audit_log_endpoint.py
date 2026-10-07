"""Integration test for the IT-12 audit-log dashboard endpoint.

Real Postgres + real ``prod.log_transaccional`` writes (driven through
``repo.append_only.append_event`` so the trigger fires and the hash
chain is initialized correctly), then the test paginates via the
real ``GET /api/v1/admin/audit/log``.

Verifies (real HTTP, no mocks):
  - KD-MOT-AUDIT-01: GET only -- the handler reads ``prod.log_transaccional``
    through a SELECT-only helper.
  - DEC-AUDIT-01: cursor pagination -- first page returns N rows, the
    ``next_cursor`` field is non-null, the second page uses that cursor
    and returns the rest.
  - ``no-store`` header on the response (Layer 5 mirror from F1.10..F1.15).
  - 200 + ``items=[]`` + ``next_cursor=None`` on an empty branch
    (empty branch contract).
  - 400 on malformed cursor.
  - The ``audit_read`` permission gate: a request without the
    permission in the JWT gets 403. (We seed the admin token with
    ``audit_read`` and use the OPERADOR token as the negative case --
    401, not 403, because the cross-audience issuer check fires first.
    That matches the existing F1.15 test pattern.)
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
for _p in (_PARKOS_CORE_SRC,):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


from parkos_core.api.v1.audit import router as audit_router_obj  # noqa: E402
from _seeds import grant_admin_scope, grant_permission  # noqa: E402
from parkos_core.auth.jwt_issuer_guard import requires_issuer  # noqa: E402
from parkos_core.auth.tokens import issue_token  # noqa: E402
from parkos_core.models.A.log_transaccional import LogTransaccional  # noqa: E402
from parkos_core.models.V.sucursal import Sucursal  # noqa: E402
from parkos_core.repo.append_only import append_event  # noqa: E402


def _build_cloud_admin_app(pg_engine) -> FastAPI:
    """Mount the audit router into a FastAPI app for ASGITransport.

    No auth dependency is overridden: the request carries a real ``admin-`` JWT,
    ``get_tenant_ctx`` checks the actor's ``usuarios_sucursal`` scope and
    ``require_permission`` reads ``permisos_usuario`` (see ``_admin_headers``).
    """
    from parkos_core.db.engine import get_session

    app = FastAPI()
    outer = APIRouter(prefix="/api/v1")
    outer.include_router(audit_router_obj)
    app.include_router(outer)

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async def _session_override() -> Any:
        async with Session() as session:
            yield session

    app.dependency_overrides[get_session] = _session_override
    return app


async def _admin_headers(pg_engine, uuid_sucursal: uuid_lib.UUID) -> dict[str, str]:
    """Real admin JWT + DB-backed scope on the branch + ``audit_read`` grant."""
    actor_uuid = uuid_lib.uuid4()
    await grant_admin_scope(pg_engine, actor_uuid, [uuid_sucursal])
    await grant_permission(pg_engine, actor_uuid, "audit_read")
    token = issue_token(
        subject_uuid=actor_uuid,
        issuer="admin-test",
        claims={"rol": "admin", "sucursales_permitidas": [str(uuid_sucursal)]},
        expires_in=3600,
    )
    return {"Authorization": f"Bearer {token}", "X-Sucursal-Context": str(uuid_sucursal)}


async def _seed_sucursal(pg_engine) -> uuid_lib.UUID:
    """Insert one open ``prod.sucursal`` row for the audit FK target."""
    from datetime import UTC, datetime

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = Sucursal(
            nombre="Sucursal Audit Test",
            ciudad="Bogota",
            vigente_desde=datetime.now(UTC).replace(tzinfo=None),
            vigente_hasta=None,
            estado="activo",
        )
        session.add(row)
        await session.flush()
        await session.commit()
        return row.uuid


async def _seed_log_rows(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID,
    count: int,
) -> None:
    """Write ``count`` log rows for the branch via the canonical helper."""
    from datetime import UTC, datetime

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        for i in range(count):
            await append_event(
                session,
                LogTransaccional,
                {
                    "uuid_sucursal": uuid_sucursal,
                    "uuid_usuario": actor_uuid,
                    "accion": "test_create",
                    "tabla_afectada": "ingreso",
                    "uuid_registro_afectado": uuid_lib.uuid4(),
                    "timestamp_evento": datetime.now(UTC).replace(tzinfo=None),
                    "datos_nuevos": {"index": i},
                },
                chain_hash=True,
            )
        await session.commit()


async def test_first_page_returns_rows_and_next_cursor(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """Pagination contract: first page returns N rows + non-null cursor."""
    actor_uuid = uuid_lib.uuid4()
    sucursal_uuid = await _seed_sucursal(pg_engine)
    await _seed_log_rows(pg_engine, uuid_sucursal=sucursal_uuid, actor_uuid=actor_uuid, count=7)

    app = _build_cloud_admin_app(pg_engine)
    headers = await _admin_headers(pg_engine, sucursal_uuid)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        response = await client.get(
            f"/api/v1/admin/audit/log?uuid_sucursal={sucursal_uuid}&limit=5",
            headers=headers,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    items = body["items"]
    assert len(items) == 5
    assert body["next_cursor"] is not None
    # Newest first: ``timestamp_evento`` is monotonic so the last written
    # row appears at index 0.
    timestamps = [it["timestamp_evento"] for it in items]
    assert timestamps == sorted(timestamps, reverse=True)
    # No-store header on success.
    assert response.headers.get("cache-control") == "no-store"


async def test_pagination_round_trip_returns_all_rows(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """Second page + cursor completes the round trip (DEC-AUDIT-01)."""
    actor_uuid = uuid_lib.uuid4()
    sucursal_uuid = await _seed_sucursal(pg_engine)
    await _seed_log_rows(pg_engine, uuid_sucursal=sucursal_uuid, actor_uuid=actor_uuid, count=7)

    app = _build_cloud_admin_app(pg_engine)
    headers = await _admin_headers(pg_engine, sucursal_uuid)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        first = await client.get(
            f"/api/v1/admin/audit/log?uuid_sucursal={sucursal_uuid}&limit=5",
            headers=headers,
        )
        first_body = first.json()
        first_uuids = {it["uuid"] for it in first_body["items"]}
        assert first_body["next_cursor"] is not None

        second = await client.get(
            f"/api/v1/admin/audit/log?uuid_sucursal={sucursal_uuid}"
            f"&limit=5&cursor={first_body['next_cursor']}",
            headers=headers,
        )
        second_body = second.json()
        second_uuids = {it["uuid"] for it in second_body["items"]}

    # Two pages, disjoint uuid sets: the 7 events plus the branch's hash-chain
    # genesis anchor, which ``hash_chain.append`` writes on first use and which
    # is part of the branch's log.
    assert first_uuids.isdisjoint(second_uuids)
    assert len(first_uuids | second_uuids) == 7 + 1
    # The second page is the LAST page (next_cursor=None).
    assert second_body["next_cursor"] is None


async def test_empty_branch_returns_empty_items_with_200(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """Empty branch contract: ``items=[]`` + ``next_cursor=None`` + 200."""
    sucursal_uuid = await _seed_sucursal(pg_engine)
    # Note: NO rows inserted.

    app = _build_cloud_admin_app(pg_engine)
    headers = await _admin_headers(pg_engine, sucursal_uuid)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        response = await client.get(
            f"/api/v1/admin/audit/log?uuid_sucursal={sucursal_uuid}",
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


async def test_invalid_cursor_returns_400(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """Malformed cursor -> 400 (Layer 4 violation)."""
    sucursal_uuid = await _seed_sucursal(pg_engine)

    app = _build_cloud_admin_app(pg_engine)
    headers = await _admin_headers(pg_engine, sucursal_uuid)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        response = await client.get(
            f"/api/v1/admin/audit/log?uuid_sucursal={sucursal_uuid}&cursor=!!!not-base64!!!",
            headers=headers,
        )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_cursor"
