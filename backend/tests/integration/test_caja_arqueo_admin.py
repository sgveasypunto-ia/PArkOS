"""Integration test for the F18.1 admin-side arqueo listing.

Exercises ``GET /api/v1/caja/arqueo`` end-to-end against a real
Postgres testcontainer. Real ``admin-`` JWTs (mint via the
``mint_admin_jwt`` fixture) hit the handler behind a FastAPI app
that mounts the dedicated ``caja_arqueo`` router.

Coverage:

  - T1: no selectors -> 200 with the most-recent ``limit`` arqueos.
  - T2: ``uuid_sucursal`` filter restricts to that branch only.
  - T3: ``fecha_desde + fecha_hasta`` range filter (inclusive bounds).
  - T4: ``uuid_tipo_arqueo`` filter restricts by arqueo code.
  - T5: ``cursor`` paginates forward (limit=2 across 4 inserted rows).
  - T6: malformed cursor -> 400 ``invalid_cursor``.
"""

from __future__ import annotations

import sys
import uuid as uuid_lib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest_asyncio
from _seeds import ensure_usuario, grant_admin_scope, grant_permission
from fastapi import APIRouter, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
_API_ADMIN_SRC = _BACKEND_ROOT / "packages" / "api_admin" / "src"
for _p in (_PARKOS_CORE_SRC, _API_ADMIN_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from parkos_core.api.v1.caja_arqueo import router as caja_arqueo_router_obj  # noqa: E402
from parkos_core.auth.tokens import issue_token  # noqa: E402
from parkos_core.db.engine import get_session  # noqa: E402
from parkos_core.models.A.arqueo import Arqueo  # noqa: E402
from parkos_core.models.A.caja import Caja  # noqa: E402
from parkos_core.models.V.tipo_arqueo import TipoArqueo  # noqa: E402
from parkos_core.models.L_S.sesion import Sesion  # noqa: E402
from parkos_core.repo import append_only  # noqa: E402


def _build_cloud_admin_app(pg_engine) -> tuple[FastAPI, callable]:
    """Mirror the production admin app shape, focused on the caja
    subtree. The admin GET /caja/arqueo handler is mounted on the
    dedicated router; the test mounts the same prefix the production
    router stack uses (``/caja``) so the path the FE calls
    (``GET /api/v1/caja/arqueo``) resolves here.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    app = FastAPI()
    outer = APIRouter(prefix="/api/v1")
    # The dedicated router is prefix-less: ``api/v1/caja.py`` mounts it under ``/caja``.
    caja = APIRouter(prefix="/caja")
    caja.include_router(caja_arqueo_router_obj)
    outer.include_router(caja)
    app.include_router(outer)

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async def _session_override() -> AsyncIterator:
        async with Session() as session:
            yield session

    app.dependency_overrides[get_session] = _session_override
    return app


# The admin actor is a real, DB-backed user holding ``audit_read``
# (``require_permission`` reads ``permisos_usuario``, never the JWT claims) and
# its branch scope is read from ``usuarios_sucursal``. A fresh actor per test
# keeps the listings of the other tests of the (shared) database out of scope.
@pytest_asyncio.fixture
async def admin_actor(pg_engine, alembic_upgrade) -> uuid_lib.UUID:
    actor = uuid_lib.uuid4()
    await grant_permission(pg_engine, actor, "audit_read")
    return actor


@pytest_asyncio.fixture(autouse=True)
async def _arqueo_table_empty(pg_dsn, alembic_upgrade):
    """The admin listing is GLOBAL (no tenant scope) and the tests assert exact
    counts, so they need ``prod.arqueo`` empty. [A] rows cannot be deleted, but
    the suite's own idiom (``TRUNCATE``) is fine; the root conftest restores the
    migration-seeded data after the module."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE prod.arqueo CASCADE")
        conn.commit()


async def _new_branch(pg_engine, admin_actor: uuid_lib.UUID) -> uuid_lib.UUID:
    """A real ``sucursal`` inside the admin's scope (arqueo.uuid_sucursal is a FK)."""
    sucursal = uuid_lib.uuid4()
    await grant_admin_scope(pg_engine, admin_actor, [sucursal])
    return sucursal


def _admin_token(
    *,
    actor_uuid: uuid_lib.UUID | None = None,
    sucursales_permitidas: list[uuid_lib.UUID] | None = None,
    expires_in: int = 3600,
) -> str:
    """Mint a real ``admin-`` JWT for the happy path. The audit_read
    grant is implicit via the migration 0053+``0054`` permission doc;
    here the test does not assert that, it only asserts the handler
    accepts admin- tokens (cross-audience rejection is exercised in
    ``test_admin_usuarios_db.py``)."""
    return issue_token(
        subject_uuid=actor_uuid or uuid_lib.uuid4(),
        issuer="admin-test",
        claims={
            "rol": "admin",
            "sucursales_permitidas": [
                str(u) for u in (sucursales_permitidas or [uuid_lib.uuid4()])
            ],
        },
        expires_in=expires_in,
    )


def _operador_token(*, sucursal_uuid: uuid_lib.UUID) -> str:
    """Mint a real ``operador-`` JWT to assert cross-audience rejection
    on the new admin endpoint. ``operador-`` tokens never reach the
    handler -- the issuer dep raises 401."""
    return issue_token(
        subject_uuid=uuid_lib.uuid4(),
        issuer="operador-test",
        claims={
            "rol": "operador",
            "sucursal": str(sucursal_uuid),
            "scope": "branch",
        },
        expires_in=3600,
    )


async def _seed_tipo_arqueo(
    session, *, codigo: str, descripcion: str = ""
) -> TipoArqueo:
    """Insert a vigente ``prod.tipo_arqueo`` row and flush so the
    caller gets the assigned ``uuid`` back. The handler's repo helper
    looks up the tipo by uuid, so the uuid MUST be server-defaulted
    rather than client-supplied (no exception path on the
    production side either)."""
    row = TipoArqueo(
        codigo=codigo,
        descripcion=descripcion,
        vigente_desde=datetime.now(UTC).replace(tzinfo=None),
        vigente_hasta=None,
        estado="activo",
        created_at=datetime.now(UTC).replace(tzinfo=None),
        created_by=None,
        sync_status="sincronizado",
    )
    session.add(row)
    await session.flush()
    return row


async def _seed_sesion(
    session,
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    fecha_apertura: datetime,
    valor_inicial_efectivo=0,
    valor_inicial_datafono=0,
) -> Sesion:
    """Insert an OPEN sesion at the branch. ``timestamp_cierre IS NULL``
    is the contract for "open" (the same one the production repo
    asserts at Step 4 of the arqueo handler)."""
    row = Sesion(
        uuid_sucursal=uuid_sucursal,
        uuid_usuario=await ensure_usuario(pg_engine, uuid_lib.uuid4()),
        timestamp_apertura=fecha_apertura,
        timestamp_cierre=None,
        valor_inicial_efectivo=valor_inicial_efectivo,
        valor_inicial_datafono=valor_inicial_datafono,
        created_at=fecha_apertura,
        created_by=None,
        sync_status="sincronizado",
    )
    session.add(row)
    await session.flush()
    return row


async def _seed_arqueo(
    session,
    *,
    uuid_sucursal: uuid_lib.UUID | None,
    uuid_tipo_arqueo: uuid_lib.UUID,
    uuid_sesion: uuid_lib.UUID | None = None,
    created_at: datetime,
    valor_efectivo_esperado=100,
    valor_efectivo_reportado=100,
) -> Arqueo:
    """Insert one ``prod.arqueo`` row via the canonical append-only path.

    Goes through ``repo.append_only.append_event`` (the [A] writer) so
    the DB-layer ``fn_arqueo_inmutable`` trigger registers the insertion
    -- same path the production POST handler uses. ``fecha_retencion_hasta``
    is server-defaulted to ``current_date()``."""
    attrs: dict = {
        "uuid_sucursal": uuid_sucursal,
        "uuid_tipo_arqueo": uuid_tipo_arqueo,
        "uuid_sesion": uuid_sesion,
        "valor_efectivo_esperado": valor_efectivo_esperado,
        "valor_datafono_esperado": 0,
        "valor_efectivo_reportado": valor_efectivo_reportado,
        "valor_datafono_reportado": 0,
        "created_at": created_at,
    }
    return await append_only.append_event(
        session,
        Arqueo,
        attrs,
        actor_uuid=uuid_lib.uuid4(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_t1_no_selectors_returns_most_recent(
    pg_engine, alembic_upgrade, pg_session, admin_actor
) -> None:
    """T1: without any filter the endpoint returns the most-recent
    ``limit=20`` arqueos ordered DESC by ``created_at``. With only 3
    seeded rows we get all three (the page is the last one)."""
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token(actor_uuid=admin_actor)

    now = datetime.now(UTC).replace(tzinfo=None)
    tipo = await _seed_tipo_arqueo(pg_session, codigo="auditoria")
    for offset_minutes in (5, 4, 3):
        await _seed_arqueo(
            pg_session,
            uuid_sucursal=await _new_branch(pg_engine, admin_actor),
            uuid_tipo_arqueo=tipo.uuid,
            created_at=now - timedelta(minutes=offset_minutes),
        )
    await pg_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            "/api/v1/caja/arqueo",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 3
    assert body["next_cursor"] is None
    # DESC order -- most recent first.
    timestamps = [item["created_at"] for item in body["items"]]
    assert timestamps == sorted(timestamps, reverse=True)


async def test_t2_uuid_sucursal_filter_restricts_to_branch(
    pg_engine, alembic_upgrade, pg_session, admin_actor
) -> None:
    """T2: ``uuid_sucursal`` filter restricts the listing to that branch
    only. Two arqueos at ``sucursal_a``, one at ``sucursal_b`` -> with
    ``uuid_sucursal=sucursal_a`` the response carries only the two
    branch-A rows.
    """
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token(actor_uuid=admin_actor)

    now = datetime.now(UTC).replace(tzinfo=None)
    tipo = await _seed_tipo_arqueo(pg_session, codigo="auditoria")
    sucursal_a = await _new_branch(pg_engine, admin_actor)
    sucursal_b = await _new_branch(pg_engine, admin_actor)
    for _ in range(2):
        await _seed_arqueo(
            pg_session,
            uuid_sucursal=sucursal_a,
            uuid_tipo_arqueo=tipo.uuid,
            created_at=now - timedelta(minutes=10),
        )
    await _seed_arqueo(
        pg_session,
        uuid_sucursal=sucursal_b,
        uuid_tipo_arqueo=tipo.uuid,
        created_at=now - timedelta(minutes=5),
    )
    await pg_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            f"/api/v1/caja/arqueo?uuid_sucursal={sucursal_a}",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 2
    assert {item["uuid_sucursal"] for item in body["items"]} == {str(sucursal_a)}


async def test_t3_fecha_desde_y_fecha_hasta_range_filter(
    pg_engine, alembic_upgrade, pg_session, admin_actor
) -> None:
    """T3: ``fecha_desde + fecha_hasta`` apply as an inclusive date
    filter on ``created_at::date``. We seed 5 rows across 5 days and
    expect the date range to slice them.
    """
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token(actor_uuid=admin_actor)

    today = datetime.now(UTC).replace(tzinfo=None)
    # Anchor at noon to dodge TZ-day-flip edge cases when the test runs
    # near midnight UTC.
    base = today.replace(hour=12, minute=0, second=0, microsecond=0)
    tipo = await _seed_tipo_arqueo(pg_session, codigo="auditoria")
    for day_offset in range(5):
        await _seed_arqueo(
            pg_session,
            uuid_sucursal=await _new_branch(pg_engine, admin_actor),
            uuid_tipo_arqueo=tipo.uuid,
            # date - 4, 3, 2, 1, 0 (today)
            created_at=base - timedelta(days=4 - day_offset),
        )
    await pg_session.commit()

    # Range covers days 3..1 (today minus 3..1, i.e. 3 rows).
    fecha_desde = (today - timedelta(days=2)).date().isoformat()
    fecha_hasta = today.date().isoformat()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            f"/api/v1/caja/arqueo?fecha_desde={fecha_desde}&fecha_hasta={fecha_hasta}",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    # The fixture stamps `created_at = today - timedelta(days=4..0)` with
    # hour=12; ``date(created_at)`` spans days today-4..today. The range
    # ``[today-2, today]`` (inclusive) cuts off the two oldest (days -4, -3)
    # and keeps days -2, -1, 0 -> 3 rows.
    assert len(body["items"]) == 3


async def test_t4_uuid_tipo_arqueo_filter(
    pg_engine, alembic_upgrade, pg_session, admin_actor
) -> None:
    """T4: ``uuid_tipo_arqueo`` filter restricts the listing by arqueo
    code. Two ``auditoria`` rows, one ``cierre_turno`` -> with the
    ``auditoria`` uuid the response carries only the two matching rows.
    """
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token(actor_uuid=admin_actor)

    now = datetime.now(UTC).replace(tzinfo=None)
    tipo_aud = await _seed_tipo_arqueo(pg_session, codigo="auditoria")
    tipo_ct = await _seed_tipo_arqueo(pg_session, codigo="cierre_turno")
    await _seed_arqueo(
        pg_session,
        uuid_sucursal=await _new_branch(pg_engine, admin_actor),
        uuid_tipo_arqueo=tipo_aud.uuid,
        created_at=now - timedelta(minutes=4),
    )
    await _seed_arqueo(
        pg_session,
        uuid_sucursal=await _new_branch(pg_engine, admin_actor),
        uuid_tipo_arqueo=tipo_aud.uuid,
        created_at=now - timedelta(minutes=3),
    )
    await _seed_arqueo(
        pg_session,
        uuid_sucursal=await _new_branch(pg_engine, admin_actor),
        uuid_tipo_arqueo=tipo_ct.uuid,
        created_at=now - timedelta(minutes=2),
    )
    await pg_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            f"/api/v1/caja/arqueo?uuid_tipo_arqueo={tipo_aud.uuid}",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 2
    assert {item["uuid_tipo_arqueo"] for item in body["items"]} == {str(tipo_aud.uuid)}


async def test_t5_cursor_pagination(
    pg_engine, alembic_upgrade, pg_session, admin_actor
) -> None:
    """T5: with ``limit=2`` and 4 seeded rows the first response
    contains 2 items + a ``next_cursor``; following the cursor returns
    the remaining 2 rows with ``next_cursor`` None (EOF)."""
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token(actor_uuid=admin_actor)

    now = datetime.now(UTC).replace(tzinfo=None)
    tipo = await _seed_tipo_arqueo(pg_session, codigo="auditoria")
    for minute in (5, 4, 3, 2):
        await _seed_arqueo(
            pg_session,
            uuid_sucursal=await _new_branch(pg_engine, admin_actor),
            uuid_tipo_arqueo=tipo.uuid,
            created_at=now - timedelta(minutes=minute),
        )
    await pg_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        # Page 1.
        r1 = await client.get(
            "/api/v1/caja/arqueo?limit=2",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )
        assert r1.status_code == 200
        page1 = r1.json()
        assert len(page1["items"]) == 2
        assert page1["next_cursor"] is not None

        # Page 2 -- follow the cursor.
        r2 = await client.get(
            f"/api/v1/caja/arqueo?limit=2&cursor={page1['next_cursor']}",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )
        assert r2.status_code == 200
        page2 = r2.json()
        assert len(page2["items"]) == 2
        # EOF on the second page.
        assert page2["next_cursor"] is None

        # No overlap between pages.
        page1_uuids = {i["uuid"] for i in page1["items"]}
        page2_uuids = {i["uuid"] for i in page2["items"]}
        assert page1_uuids.isdisjoint(page2_uuids)


async def test_t6_malformed_cursor_returns_400(
    pg_engine, alembic_upgrade, pg_session, admin_actor
) -> None:
    """T6: a malformed cursor payload yields ``400 invalid_cursor``
    with the typed error body. Same wire shape as the audit endpoint's
    cursor validation (audit.py::list_audit_log)."""
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token(actor_uuid=admin_actor)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            "/api/v1/caja/arqueo?cursor=not-a-valid-cursor",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert r.status_code == 400, r.text
    body = r.json()
    assert body["detail"]["error"] == "invalid_cursor"


async def test_t7_operador_issuer_is_rejected(
    pg_engine, alembic_upgrade, pg_session, admin_actor
) -> None:
    """T7: an ``operador-`` token gets 401 -- the new endpoint is
    admin-only. Operators do NOT list arqueos (they POST their own);
    cross-audience rejection is the same ``CrossIssuerError`` path the
    admin_usuarios handler exercises in ``test_admin_usuarios_db.py``.
    """
    app = _build_cloud_admin_app(pg_engine)
    operador_jwt = _operador_token(sucursal_uuid=uuid_lib.uuid4())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            "/api/v1/caja/arqueo",
            headers={"Authorization": f"Bearer {operador_jwt}"},
        )

    assert r.status_code == 401, r.text