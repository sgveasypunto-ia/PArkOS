"""Integration tests for HU-F19.6 — ``POST /api/v1/validacion-evento`` ``estado``.

Exercises the new explicit ``estado`` field on ``ValidacionEventoCreate``
(previously impossible to set -- ``extra='forbid'`` always forced every
transition to ``'validado'``) end-to-end against a real Postgres
testcontainer, mirroring ``test_dian_cloud_router_listings.py``'s fixture
setup (``pg_engine``/``alembic_upgrade``/``pg_session``, cloud-only import
guard, admin JWT helper).

Coverage:

  - T1: ``estado='rechazado'`` without ``observaciones`` -> 422 (Pydantic
    ``model_validator`` rejects before any DB hit).
  - T2: a transition out of an already-terminal chain tip (``'validado'``)
    -> 409 ``validacion_evento_transicion_ilegal`` (``IllegalTransitionError``
    mapped at the endpoint layer, mirroring
    ``workflows_alerta.descartar_alerta``'s 409 shape -- there is no shared
    FastAPI exception handler anywhere in this codebase).
  - T3: a legal ``'rechazado'`` transition with real ``observaciones``
    succeeds (201), proving REQ-25's ``pendiente -> rechazado`` path is now
    reachable via the API (it previously never was).

NOTE (known, non-blocking, already-documented gap -- see
``tests/conftest.py``'s own docstring): these tests require a Postgres
testcontainer image with ``pg_partman`` pre-installed. On an image that
lacks it, ``alembic_upgrade``/``pg_engine`` best-effort no-op and these
tests cannot exercise a real DB; they still define the correct contract.
"""
from __future__ import annotations

import os
import sys
import uuid as uuid_lib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

# Import-time guard (REQ-X3) -- same pattern as
# test_dian_cloud_router_listings.py. ``cloud_router`` raises ImportError
# at module load when ``PARKOS_DEPLOY=branch``; force ``cloud`` for the
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

from _seeds import seed_sucursales  # noqa: E402
from parkos_core.auth.tokens import issue_token  # noqa: E402
from parkos_core.db.engine import get_session  # noqa: E402
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


async def test_t1_rechazado_sin_observaciones_returns_422(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """T1: ``estado='rechazado'`` without ``observaciones`` -> 422.

    Pure Pydantic ``model_validator`` rejection -- never reaches the DB.
    """
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()

    now = datetime.now(UTC).replace(tzinfo=None)
    sucursal = uuid_lib.uuid4()
    await seed_sucursales(pg_engine, sucursal)
    root = _seed_validacion_evento(
        pg_session, uuid_sucursal=sucursal, estado="pendiente", vigente_desde=now
    )
    await pg_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.post(
            "/api/v1/validacion-evento",
            json={
                "uuid_validacion_padre": str(root.uuid),
                "estado": "rechazado",
            },
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert r.status_code == 422, r.text


async def test_t2_transicion_ilegal_returns_409(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """T2: transitioning out of an already-terminal 'validado' tip -> 409.

    ``repo.workflow.STATE_MACHINES['validacion_evento']['validado'] == []``
    (terminal) -- ``append_transition`` raises ``IllegalTransitionError``,
    mapped by the endpoint to 409 ``validacion_evento_transicion_ilegal``.
    """
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()

    now = datetime.now(UTC).replace(tzinfo=None)
    sucursal = uuid_lib.uuid4()
    await seed_sucursales(pg_engine, sucursal)
    terminal_tip = _seed_validacion_evento(
        pg_session, uuid_sucursal=sucursal, estado="validado", vigente_desde=now
    )
    await pg_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.post(
            "/api/v1/validacion-evento",
            json={
                "uuid_validacion_padre": str(terminal_tip.uuid),
                "estado": "rechazado",
                "observaciones": "Intento de reabrir una validacion ya terminal",
            },
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"]["error"] == "validacion_evento_transicion_ilegal"


async def test_t3_rechazado_legal_con_observaciones_returns_201(
    pg_engine, alembic_upgrade, pg_session
) -> None:
    """T3: a legal 'pendiente' -> 'rechazado' transition with real
    ``observaciones`` succeeds (201) -- REQ-25's reject path is now
    reachable via the API (it previously never was)."""
    app = _build_cloud_admin_app(pg_engine)
    admin_jwt = _admin_token()

    now = datetime.now(UTC).replace(tzinfo=None)
    sucursal = uuid_lib.uuid4()
    await seed_sucursales(pg_engine, sucursal)
    root = _seed_validacion_evento(
        pg_session, uuid_sucursal=sucursal, estado="pendiente", vigente_desde=now
    )
    await pg_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as client:
        r = await client.post(
            "/api/v1/validacion-evento",
            json={
                "uuid_validacion_padre": str(root.uuid),
                "estado": "rechazado",
                "observaciones": "Hash no coincide con el payload auditado",
            },
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )

    assert r.status_code == 201, r.text
    assert "uuid" in r.json()
