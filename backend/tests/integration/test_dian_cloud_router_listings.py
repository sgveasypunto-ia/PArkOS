"""Integration tests for HU-F13.4 — GET /envio-dian + GET /validacion-evento.

Exercises the 2 new cursor-paginated read-only listings added to
``parkos_core.dian.cloud_router`` against a real Postgres testcontainer.
These 2 cloud-only ``[L-W]`` tables previously had NO read endpoint
(``api/v1/workflows.py`` explicitly must not mount them, REQ-X3); this
module covers the new ``GET`` handlers end-to-end.

Coverage (mirrors ``test_caja_arqueo_admin.py``'s structure):

  - T1: ``estado`` filter restricts to matching rows (envio_dian).
  - T2: ``uuid_sucursal`` filter restricts to that branch only
    (validacion_evento).
  - T3: ``cursor`` paginates forward (limit=2 across 4 rows), DESC order.
  - T4: an ``estado`` value outside the real ER domain -> 422
    ``invalid_estado`` (not the plan.md-drifted 4-value set — see
    ``cloud_router.py``'s ``_ENVIO_DIAN_ESTADOS`` comment).
  - T5: malformed cursor -> 400 ``invalid_cursor``.
  - T6: ``operador-`` issuer is accepted (same guard as the sibling
    ``POST`` endpoints, ``_cloud_issuer_dep``).
"""
from __future__ import annotations

import os
import sys
import uuid as uuid_lib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fastapi import APIRouter, FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

# Import-time guard (REQ-X3) — same pattern as test_dian_round_trip.py /
# tests/unit/dian/conftest.py. ``cloud_router`` raises ImportError at
# module load when ``PARKOS_DEPLOY=branch``; force ``cloud`` for the
# duration of the import only.
_PREV_DEPLOY = os.environ.get("PARKOS_DEPLOY")
os.environ["PARKOS_DEPLOY"] = "cloud"
try:
    from parkos_core.dian import cloud_router
finally:
    if _PREV_DEPLOY is None:
        os.environ.pop("PARKOS_DEPLOY", None)
    else:
        os.environ["PARKOS_DEPLOY"] = _PREV_DEPLOY

from parkos_core.auth.tokens import issue_token  # noqa: E402
from parkos_core.db.engine import get_session  # noqa: E402
from parkos_core.models.L_W.envio_dian import EnvioDian  # noqa: E402
from parkos_core.models.L_W.validacion_evento import ValidacionEvento  # noqa: E402


def _build_cloud_admin_app(pg_engine) -> FastAPI:
    """Mount ``cloud_router.router`` under ``/api/v1`` (production shape)."""
    app = FastAPI()
    outer = APIRouter(prefix="/api/v1")
    outer.include_router(cloud_router.router)
    app.include_router(outer)

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async def _session_override() -> AsyncIterator:
        async with Session() as session:
            yield session

    app.dependency_overrides[get_session] = _session_override
    return app


def _admin_token(*, actor_uuid: uuid_lib.UUID | None = None) -> str:
    return issue_token(
        subject_uuid=actor_uuid or uuid_lib.uuid4(),
        issuer="admin-test",
        claims={"rol": "admin", "sucursales_permitidas": [str(uuid_lib.uuid4())]},
        expires_in=3600,
    )


def _operador_token(*, sucursal_uuid: uuid_lib.UUID) -> str:
    return issue_token(
        subject_uuid=uuid_lib.uuid4(),
        issuer="operador-test",
        claims={"rol": "operador", "sucursal": str(sucursal_uuid), "scope": "branch"},
        expires_in=3600,
    )


def _seed_envio_dian(
    session,
    *,
    uuid_sucursal: uuid_lib.UUID | None,
    estado: str,
    vigente_desde: datetime,
) -> EnvioDian:
    row = EnvioDian(
        uuid=uuid_lib.uuid4(),
        uuid_sucursal=uuid_sucursal,
        uuid_factura_electronica=None,
        uuid_resolucion_facturacion=None,
        payload=None,
        respuesta_proveedor=None,
        cufe=None,
        uuid_envio_padre=None,
        timestamp_evento=vigente_desde,
        fecha_retencion_hasta=None,
        vigente_desde=vigente_desde,
        vigente_hasta=None,
        estado=estado,
        created_at=vigente_desde,
        created_by=None,
        sync_status="pendiente",
    )
    session.add(row)
    return row


def _seed_validacion_evento(
    session,
    *,
    uuid_sucursal: uuid_lib.UUID | None,
    estado: str,
    vigente_desde: datetime,
) -> ValidacionEvento:
    row = ValidacionEvento(
        uuid=uuid_lib.uuid4(),
        uuid_sucursal=uuid_sucursal,
        uuid_usuario=None,
        tabla_origen=None,
        uuid_registro=None,
        hash_evento=None,
        observaciones=None,
        uuid_validacion_padre=None,
        timestamp_evento=vigente_desde,
        vigente_desde=vigente_desde,
        vigente_hasta=None,
        estado=estado,
        created_at=vigente_desde,
        created_by=None,
        sync_status="pendiente",
    )
    session.add(row)
    return row


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_t1_envio_dian_estado_filter_restricts_to_matching_rows(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """T1: ``estado`` filter on ``GET /api/v1/envio-dian`` restricts to
    matching rows only. 2 ``pendiente`` + 1 ``ack`` seeded -> filtering
    by ``estado=ack`` returns exactly the 1 matching row (``ack`` is a
    real STATE_MACHINES value, NOT one of plan.md's drifted 4)."""
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()

    now = datetime.now(UTC).replace(tzinfo=None)
    for minute in (5, 4):
        _seed_envio_dian(
            pg_session,
            uuid_sucursal=uuid_lib.uuid4(),
            estado="pendiente",
            vigente_desde=now - timedelta(minutes=minute),
        )
    ack_row = _seed_envio_dian(
        pg_session,
        uuid_sucursal=uuid_lib.uuid4(),
        estado="ack",
        vigente_desde=now - timedelta(minutes=3),
    )
    await pg_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            "/api/v1/envio-dian?estado=ack",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["uuid"] == str(ack_row.uuid)
    assert body["items"][0]["estado"] == "ack"


async def test_t2_validacion_evento_uuid_sucursal_filter(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """T2: ``uuid_sucursal`` filter on ``GET /api/v1/validacion-evento``
    restricts to that branch only."""
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()

    now = datetime.now(UTC).replace(tzinfo=None)
    sucursal_a = uuid_lib.uuid4()
    sucursal_b = uuid_lib.uuid4()
    for _ in range(2):
        _seed_validacion_evento(
            pg_session,
            uuid_sucursal=sucursal_a,
            estado="pendiente",
            vigente_desde=now - timedelta(minutes=10),
        )
    _seed_validacion_evento(
        pg_session,
        uuid_sucursal=sucursal_b,
        estado="pendiente",
        vigente_desde=now - timedelta(minutes=5),
    )
    await pg_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            f"/api/v1/validacion-evento?uuid_sucursal={sucursal_a}",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 2
    assert {item["uuid_sucursal"] for item in body["items"]} == {str(sucursal_a)}


async def test_t3_cursor_pagination_envio_dian(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """T3: ``limit=2`` across 4 rows -> page 1 has 2 items + next_cursor;
    page 2 has the remaining 2 + next_cursor=None (EOF). DESC order by
    ``vigente_desde``."""
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()

    now = datetime.now(UTC).replace(tzinfo=None)
    for minute in (5, 4, 3, 2):
        _seed_envio_dian(
            pg_session,
            uuid_sucursal=uuid_lib.uuid4(),
            estado="pendiente",
            vigente_desde=now - timedelta(minutes=minute),
        )
    await pg_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r1 = await client.get(
            "/api/v1/envio-dian?limit=2",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )
        assert r1.status_code == 200, r1.text
        page1 = r1.json()
        assert len(page1["items"]) == 2
        assert page1["next_cursor"] is not None
        timestamps = [item["vigente_desde"] for item in page1["items"]]
        assert timestamps == sorted(timestamps, reverse=True)

        r2 = await client.get(
            f"/api/v1/envio-dian?limit=2&cursor={page1['next_cursor']}",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )
        assert r2.status_code == 200, r2.text
        page2 = r2.json()
        assert len(page2["items"]) == 2
        assert page2["next_cursor"] is None

        page1_uuids = {i["uuid"] for i in page1["items"]}
        page2_uuids = {i["uuid"] for i in page2["items"]}
        assert page1_uuids.isdisjoint(page2_uuids)


async def test_t4_invalid_estado_returns_422(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """T4: an ``estado`` outside the real ER domain -> 422
    ``invalid_estado``. ``aceptado`` alone is NOT a real raw
    ``envio_dian.estado`` value in isolation from the dispatcher's
    vocabulary — but IS accepted (it's in the union); a nonsense value
    is rejected."""
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            "/api/v1/envio-dian?estado=no-such-estado",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert r.status_code == 422, r.text
    body = r.json()
    assert body["detail"]["error"] == "invalid_estado"


async def test_t4b_validacion_evento_recibido_is_rejected(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """T4b: plan.md's HU-F13.4 BR2 names ``recibido`` as a real
    ``validacion_evento`` estado — it is NOT (drift: ``recibido`` is a
    ``reclamos`` state in ``repo.workflow.STATE_MACHINES``, never a
    ``validacion_evento`` one). Must 422, pinning the real ER domain."""
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            "/api/v1/validacion-evento?estado=recibido",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"] == "invalid_estado"


async def test_t5_malformed_cursor_returns_400(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """T5: a malformed cursor -> 400 ``invalid_cursor`` (same
    ``repo.pagination.InvalidCursorError`` contract as the rest of the
    system)."""
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            "/api/v1/validacion-evento?cursor=not-a-valid-cursor",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert r.status_code == 400, r.text
    assert r.json()["detail"]["error"] == "invalid_cursor"


async def test_t6_operador_issuer_is_accepted(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """T6: ``operador-`` tokens are accepted (same ``_cloud_issuer_dep``
    guard — ``admin-,operador-`` — as the existing POST siblings)."""
    app = _build_cloud_admin_app(pg_engine)
    sucursal_uuid = uuid_lib.uuid4()
    operador_jwt = _operador_token(sucursal_uuid=sucursal_uuid)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.get(
            "/api/v1/envio-dian",
            headers={"Authorization": f"Bearer {operador_jwt}"},
        )

    assert r.status_code == 200, r.text
