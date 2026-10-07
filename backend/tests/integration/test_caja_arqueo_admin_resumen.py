"""Integration test for the F18.3 admin cross-branch resumen endpoint.

Exercises ``GET /api/v1/caja/arqueo/resumen-admin`` end-to-end.
Mirrors the operator's ``/caja/arqueo/resumen`` test shape but for
the admin-only path (``admin-`` issuer + ``audit_read`` permission).

  - T1: empty day -> 200 with ``items=[]`` (no arqueos).
  - T2: date with mixed branches -> 200 with one item per branch,
        each carrying ``uuid_sucursal`` + ``total_arqueos`` + the
        ``cierre_dia`` block when present.
"""

from __future__ import annotations

import sys
import uuid as uuid_lib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest_asyncio
from _seeds import grant_permission
from fastapi import APIRouter, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
_API_ADMIN_SRC = _BACKEND_ROOT / "packages" / "api_admin" / "src"
for _p in (_PARKOS_CORE_SRC, _API_ADMIN_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from parkos_core.api.v1.caja_arqueo import admin_router as caja_admin_arqueo_router  # noqa: E402
from parkos_core.auth.tokens import issue_token  # noqa: E402
from parkos_core.db.engine import get_session  # noqa: E402
from parkos_core.models.A.arqueo import Arqueo  # noqa: E402
from parkos_core.models.L_S.sesion import Sesion  # noqa: E402
from parkos_core.models.A.caja import Caja  # noqa: E402
from parkos_core.models.V.sucursal import Sucursal  # noqa: E402
from parkos_core.models.V.usuarios import Usuarios  # noqa: E402
from tests.conftest import VFixtureFactory  # noqa: E402
from parkos_core.models.V.tipo_arqueo import TipoArqueo  # noqa: E402
from parkos_core.repo import append_only  # noqa: E402


def _build_cloud_admin_app(pg_engine) -> tuple[FastAPI, callable]:
    """Mount the admin-only ``caja_arqueo`` router on a FastAPI app.

    The router carries prefix-less endpoints; the parent's
    ``/caja`` prefix attaches when ``caja.py`` mounts it. For the
    admin resumen path we mount BOTH routers on the same app via the
    ``admin_router`` so the testid path matches production.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    app = FastAPI()
    outer = APIRouter(prefix="/api/v1")
    # ``admin_router`` is prefix-less: ``api/v1/caja.py`` mounts it under ``/caja``
    # (``GET /api/v1/caja/arqueo/resumen-admin``).
    caja = APIRouter(prefix="/caja")
    caja.include_router(caja_admin_arqueo_router)
    outer.include_router(caja)
    app.include_router(outer)

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async def _session_override() -> AsyncIterator:
        async with Session() as session:
            yield session

    app.dependency_overrides[get_session] = _session_override
    return app


# The admin actor is a real, DB-backed user holding ``audit_read``:
# ``require_permission`` reads ``permisos_usuario``, never the JWT claims.
_ADMIN_ACTOR = uuid_lib.uuid4()


@pytest_asyncio.fixture(autouse=True)
async def _admin_actor_with_audit_read(pg_engine, alembic_upgrade):
    await grant_permission(pg_engine, _ADMIN_ACTOR, "audit_read")


def _admin_token(
    *,
    actor_uuid: uuid_lib.UUID | None = None,
    expires_in: int = 3600,
) -> str:
    return issue_token(
        subject_uuid=actor_uuid or _ADMIN_ACTOR,
        issuer="admin-test",
        claims={
            "rol": "admin",
            "sucursales_permitidas": [str(uuid_lib.uuid4())],
        },
        expires_in=expires_in,
    )


async def _seed_sucursal(session, *, nombre: str) -> Sucursal:
    """Insert a vigente ``prod.sucursal`` row.

    Sucursal is ``[V]`` (bi-temporal), but for this test we only
    need the vigente row to show up in the admin resumen. We set
    ``vigente_hasta=None`` server-side (we don't call
    ``close_and_insert`` here -- just an INSERT bypassing the
    versioning helpers, since the admin resumen is read-only and the
    row needs to look ``vigente`` to the query).
    """
    row = Sucursal(
        uuid_empresa=None,
        uuid_tipo_sucursal=None,
        nombre=nombre,
        direccion=None,
        telefono=None,
        prefijo_nombre="XX",
        ciudad=None,
        horario=None,
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
    *,
    uuid_sucursal: uuid_lib.UUID,
    fecha_apertura: datetime,
) -> Sesion:
    """Insert an OPEN sesion at the branch. The admin resumen joins
    on ``factura_pagos`` for the day's expected total; an open
    sesion with no payments renders ``esperado_efectivo=0``.
    """
    # ``sesion.uuid_usuario`` is a real FK.
    usuario = VFixtureFactory.build(Usuarios)
    session.add(usuario)
    await session.flush()
    row = Sesion(
        uuid_sucursal=uuid_sucursal,
        uuid_usuario=usuario.uuid,
        timestamp_apertura=fecha_apertura,
        timestamp_cierre=None,
        valor_inicial_efectivo=0,
        valor_inicial_datafono=0,
        created_at=fecha_apertura,
        created_by=None,
        sync_status="sincronizado",
    )
    session.add(row)
    await session.flush()
    return row


async def _seed_tipo_arqueo(session, *, codigo: str) -> TipoArqueo:
    row = TipoArqueo(
        codigo=codigo,
        descripcion="",
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


async def _seed_arqueo(
    session,
    *,
    uuid_sucursal: uuid_lib.UUID | None,
    uuid_tipo_arqueo: uuid_lib.UUID,
    uuid_sesion: uuid_lib.UUID | None = None,
    created_at: datetime,
    valor_efectivo_esperado: Decimal = Decimal("100"),
    valor_datafono_esperado: Decimal = Decimal("50"),
    valor_efectivo_reportado: Decimal = Decimal("100"),
    valor_datafono_reportado: Decimal = Decimal("50"),
) -> Arqueo:
    """Insert one ``prod.arqueo`` row via the canonical append-only
    path. ``fecha_retencion_hasta`` is server-defaulted.
    """
    attrs: dict = {
        "uuid_sucursal": uuid_sucursal,
        "uuid_tipo_arqueo": uuid_tipo_arqueo,
        "uuid_sesion": uuid_sesion,
        "valor_efectivo_esperado": valor_efectivo_esperado,
        "valor_datafono_esperado": valor_datafono_esperado,
        "valor_efectivo_reportado": valor_efectivo_reportado,
        "valor_datafono_reportado": valor_datafono_reportado,
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


async def test_t1_empty_day_returns_items_empty(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """T1: a date with no arqueos at any branch returns 200 with
    ``items=[]`` (NOT 404 -- "no arqueos for the day" is a valid
    result, not "branch not found").
    """
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            "/api/v1/caja/arqueo/resumen-admin?fecha=2026-10-01",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fecha"] == "2026-10-01"
    assert body["items"] == []


async def test_t2_mixed_branches_returns_one_item_per_branch(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """T2: three vigente ``prod.sucursal`` rows. Two get arqueos
    (regular + cierre_dia), one does not. Verify one item per
    branch with the expected totals + total_arqueos.

    Note on the ``Caja`` table: the admin resumen joins on
    ``factura_pagos`` through the active sesion, not the ``caja``
    table directly. With no payments the esperado totals are 0;
    verifying that the handler walks every branch is enough.
    """
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()

    today = datetime.now(UTC).replace(tzinfo=None)
    base = today.replace(hour=12, minute=0, second=0, microsecond=0)
    fecha = today.date().isoformat()

    # Three vigentes sucursales.
    s_a = await _seed_sucursal(pg_session, nombre="A")
    s_b = await _seed_sucursal(pg_session, nombre="B")
    s_c = await _seed_sucursal(pg_session, nombre="C")

    tipo_aud = await _seed_tipo_arqueo(pg_session, codigo="auditoria")
    tipo_ct = await _seed_tipo_arqueo(pg_session, codigo="cierre_turno")

    # Branch A: 2 regular arqueos (uuid_sesion NOT NULL).
    sesion_a = await _seed_sesion(
        pg_session,
        uuid_sucursal=s_a.uuid,
        fecha_apertura=base - timedelta(hours=2),
    )
    await _seed_arqueo(
        pg_session,
        uuid_sucursal=s_a.uuid,
        uuid_tipo_arqueo=tipo_aud.uuid,
        uuid_sesion=sesion_a.uuid,
        created_at=base - timedelta(hours=2),
    )
    await _seed_arqueo(
        pg_session,
        uuid_sucursal=s_a.uuid,
        uuid_tipo_arqueo=tipo_aud.uuid,
        uuid_sesion=sesion_a.uuid,
        created_at=base - timedelta(hours=1),
    )

    # Branch B: 1 cierre_dia (uuid_sesion IS NULL) on the day.
    await _seed_arqueo(
        pg_session,
        uuid_sucursal=s_b.uuid,
        uuid_tipo_arqueo=tipo_ct.uuid,
        uuid_sesion=None,
        created_at=base,
    )

    # Branch C: 0 arqueos.

    await pg_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            f"/api/v1/caja/arqueo/resumen-admin?fecha={fecha}",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fecha"] == fecha
    assert len(body["items"]) == 3

    by_uuid = {i["uuid_sucursal"]: i for i in body["items"]}
    assert by_uuid[str(s_a.uuid)]["total_arqueos"] == 2
    assert by_uuid[str(s_a.uuid)]["cierre_dia"] is None
    assert by_uuid[str(s_b.uuid)]["total_arqueos"] == 0  # cierre_dia IS NOT regular
    assert by_uuid[str(s_b.uuid)]["cierre_dia"] is not None
    assert by_uuid[str(s_c.uuid)]["total_arqueos"] == 0
    assert by_uuid[str(s_c.uuid)]["cierre_dia"] is None


async def test_t3_operador_token_is_rejected(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """T3: an ``operador-`` token gets 401 -- the admin resumen is
    admin-only. The operator rejects cross-branch by definition.
    """
    app = _build_cloud_admin_app(pg_engine)
    operador_jwt = issue_token(
        subject_uuid=uuid_lib.uuid4(),
        issuer="operador-test",
        claims={
            "rol": "operador",
            "sucursal": str(uuid_lib.uuid4()),
            "scope": "branch",
        },
        expires_in=3600,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            "/api/v1/caja/arqueo/resumen-admin?fecha=2026-10-01",
            headers={"Authorization": f"Bearer {operador_jwt}"},
        )

    assert r.status_code == 401, r.text


async def test_t4_missing_fecha_returns_422(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """T4: the ``fecha`` query param is required -- missing it
    yields the standard 422 Pydantic validation message."""
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            "/api/v1/caja/arqueo/resumen-admin",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert r.status_code == 422, r.text