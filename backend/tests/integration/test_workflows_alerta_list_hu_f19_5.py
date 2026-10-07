"""Integration tests for HU-F19.5 / T1 (``workflows_alerta.py`` GET surface).

Real Postgres + real handlers, same harness shape as
``test_admin_sync_hu_f19_1.py`` (HU-F19.1 precedent for a hand-built,
cross-branch, cursor-paginated list endpoint). Covers:

- BR4: ``severity`` is ``null`` when ``tipo_alerta`` has no matching
  ``prod.alert_types`` row (LEFT JOIN), and populated when it does.
- Cross-branch ``admin-`` read via ``extract_sucursales_permitidas_fresh``
  (every branch the admin is assigned to, in one call) + the
  ``unauthorized_sucursal_context`` 403 when a filter names a branch
  outside that set.
- ``operador-`` stays pinned to its own branch even when other branches'
  alerts exist in the DB (no cross-branch leak).
- Cursor pagination (``{items, next_cursor}``, newest ``vigente_desde``
  first).
- ``GET /{uuid}`` (current_version, same router).

``prod.alerta`` IS pg_partman range-partitioned (monthly, by
``fecha_retencion_hasta`` -- see ``models/L_W/alerta.py``), so this suite
skips cleanly (via the ``alembic_upgrade``/``pg_engine`` fixture chain in
``conftest.py``) when the local Postgres image lacks ``pg_partman`` --
same documented, expected limitation as ``test_admin_sync_hu_f19_1.py``,
not a regression to chase here.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport
from _seeds import ensure_usuario
from sqlalchemy.ext.asyncio import async_sessionmaker

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
for _p in (_PARKOS_CORE_SRC,):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import parkos_core.api.v1.workflows_alerta as _workflows_alerta_module  # noqa: E402
from parkos_core.api.v1.workflows_alerta import router as workflows_alerta_router_obj  # noqa: E402
from parkos_core.auth.tokens import issue_token  # noqa: E402
from parkos_core.models.A.alert_types import AlertTypes  # noqa: E402
from parkos_core.models.L_W.alerta import Alerta  # noqa: E402
from parkos_core.models.V.empresa import Empresa  # noqa: E402
from parkos_core.models.V.sucursal import Sucursal  # noqa: E402


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seed_sucursal(pg_engine, *, uuid_sucursal: uuid_lib.UUID) -> None:
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Alertas SA",
                nit=f"905{empresa_uuid.hex[:6]}",
                mensaje_bienvenida="hola",
                mensaje_salida="bye",
                regimen="comun",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.flush()
        session.add(
            Sucursal(
                uuid=uuid_sucursal,
                uuid_empresa=empresa_uuid,
                uuid_tipo_sucursal=None,
                nombre=f"Suc Alerta {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"S{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle Alerta",
                telefono="+575555",
                horario="24/7",
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


async def _assign_admin(
    pg_engine, *, actor_uuid: uuid_lib.UUID, sucursales: list[uuid_lib.UUID]
) -> None:
    from parkos_core.models.V.usuarios import Usuarios
    from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal

    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Usuarios(
                uuid=actor_uuid,
                nombre="Alerta",
                apellido="Admin",
                cedula=f"A{actor_uuid.hex[:10]}",
                email=f"alerta-{actor_uuid.hex[:8]}@parkos.local",
                password_hash="$2b$12$not-a-real-hash-for-jwt-only-tests",
                rol="admin",
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
        for sucursal in sucursales:
            session.add(
                UsuariosSucursal(
                    uuid_sucursal=sucursal,
                    uuid_usuario=actor_uuid,
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


async def _seed_alert_type(pg_engine, *, tipo_alerta: str, severity: str) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            AlertTypes(
                tipo_alerta=tipo_alerta,
                descripcion=f"Tipo {tipo_alerta}",
                severity=severity,
                created_at=_now_naive(),
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()


async def _seed_alerta(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    tipo_alerta: str = "descuadre_critico",
    estado: str = "abierta",
    vigente_desde: datetime | None = None,
    timestamp_evento: datetime | None = None,
) -> uuid_lib.UUID:
    now = vigente_desde or _now_naive()
    autor = await ensure_usuario(pg_engine, uuid_lib.uuid4())
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        alerta = Alerta(
            uuid_sucursal=uuid_sucursal,
            uuid_usuario=autor,  # alerta.uuid_usuario is a real FK
            uuid_arqueo=None,
            tipo_alerta=tipo_alerta,
            estado=estado,
            timestamp_evento=timestamp_evento or now,
            vigente_desde=now,
            vigente_hasta=None,
        )
        session.add(alerta)
        await session.commit()
        await session.refresh(alerta)
        return alerta.uuid


def _build_app(pg_engine) -> tuple[FastAPI, Any]:
    """Mount ``workflows_alerta.router`` with overrides; return (app, set_claims)."""
    from parkos_core.db.engine import get_session

    app = FastAPI()
    outer = APIRouter(prefix="/api/v1")
    outer.include_router(workflows_alerta_router_obj)
    app.include_router(outer)

    issuer_dep = _workflows_alerta_module._alerta_read_issuer_dep
    captured: dict = {"value": None}

    def _override_claims() -> dict:
        if captured["value"] is None:
            raise RuntimeError("set_claims() before request")
        return captured["value"]

    app.dependency_overrides[issuer_dep] = _override_claims

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async def _session_override() -> Any:
        async with Session() as session:
            yield session

    app.dependency_overrides[get_session] = _session_override
    return app, lambda c: captured.__setitem__("value", c)


async def _get(fastapi_app: FastAPI, url: str, token: str) -> httpx.Response:
    transport = ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        return await c.get(url, headers={"Authorization": f"Bearer {token}"})


def _admin_token_and_claims(
    fastapi_app: FastAPI, set_claims, *, actor_uuid: uuid_lib.UUID
) -> str:
    set_claims({"sub": str(actor_uuid), "iss": "admin-test", "rol": "admin"})
    return issue_token(subject_uuid=actor_uuid, issuer="admin-test", claims={"rol": "admin"})


def _operador_token_and_claims(
    fastapi_app: FastAPI, set_claims, *, actor_uuid: uuid_lib.UUID, sucursal_uuid: uuid_lib.UUID
) -> str:
    set_claims(
        {
            "sub": str(actor_uuid),
            "iss": "operador-test",
            "sucursal": str(sucursal_uuid),
            "rol": "operador",
        }
    )
    return issue_token(
        subject_uuid=actor_uuid,
        issuer="operador-test",
        claims={"rol": "operador", "sucursal": str(sucursal_uuid)},
    )


# ---------------------------------------------------------------------------
# admin- cross-branch list + unauthorized-branch 403
# ---------------------------------------------------------------------------


async def test_list_alertas_admin_sees_every_permitted_branch(pg_engine, pg_dsn) -> None:
    branch_a, branch_b = uuid_lib.uuid4(), uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch_a)
    await _seed_sucursal(pg_engine, uuid_sucursal=branch_b)
    await _seed_alerta(pg_engine, uuid_sucursal=branch_a)
    await _seed_alerta(pg_engine, uuid_sucursal=branch_b)
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch_a, branch_b])
    fastapi_app, set_claims = _build_app(pg_engine)
    token = _admin_token_and_claims(fastapi_app, set_claims, actor_uuid=admin_actor)

    resp = await _get(fastapi_app, "/api/v1/workflows/alerta", token)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    items = resp.json()["items"]
    assert len(items) == 2
    seen_branches = {item["uuid_sucursal"] for item in items}
    assert seen_branches == {str(branch_a), str(branch_b)}


async def test_list_alertas_admin_unauthorized_branch_filter_returns_403(pg_engine, pg_dsn) -> None:
    branch_a = uuid_lib.uuid4()
    other_branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch_a)
    await _seed_sucursal(pg_engine, uuid_sucursal=other_branch)
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch_a])
    fastapi_app, set_claims = _build_app(pg_engine)
    token = _admin_token_and_claims(fastapi_app, set_claims, actor_uuid=admin_actor)

    resp = await _get(
        fastapi_app, f"/api/v1/workflows/alerta?uuid_sucursal={other_branch}", token
    )
    assert resp.status_code == 403, f"got {resp.status_code}: {resp.text}"
    assert resp.json()["detail"]["error"] == "unauthorized_sucursal_context"


# ---------------------------------------------------------------------------
# BR4: LEFT JOIN prod.alert_types for severity
# ---------------------------------------------------------------------------


async def test_list_alertas_severity_null_when_tipo_alerta_not_in_catalog(
    pg_engine, pg_dsn
) -> None:
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)
    await _seed_alerta(pg_engine, uuid_sucursal=branch, tipo_alerta="sin_catalogo_xyz")
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch])
    fastapi_app, set_claims = _build_app(pg_engine)
    token = _admin_token_and_claims(fastapi_app, set_claims, actor_uuid=admin_actor)

    resp = await _get(fastapi_app, "/api/v1/workflows/alerta", token)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["severity"] is None


async def test_list_alertas_severity_populated_from_alert_types(pg_engine, pg_dsn) -> None:
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)
    # A tipo of its own: ``alert_types`` is append-only and seeded by the
    # migrations, so the test registers a fresh code instead of wiping the table.
    tipo = f"tipo_critico_{uuid_lib.uuid4().hex[:8]}"
    await _seed_alert_type(pg_engine, tipo_alerta=tipo, severity="critical")
    await _seed_alerta(pg_engine, uuid_sucursal=branch, tipo_alerta=tipo)
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch])
    fastapi_app, set_claims = _build_app(pg_engine)
    token = _admin_token_and_claims(fastapi_app, set_claims, actor_uuid=admin_actor)

    resp = await _get(
        fastapi_app, "/api/v1/workflows/alerta?severidad=critical", token
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["severity"] == "critical"


# ---------------------------------------------------------------------------
# operador- stays pinned to its own branch (no cross-branch leak)
# ---------------------------------------------------------------------------


async def test_list_alertas_operador_only_sees_own_branch(pg_engine, pg_dsn) -> None:
    own_branch, other_branch = uuid_lib.uuid4(), uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=own_branch)
    await _seed_sucursal(pg_engine, uuid_sucursal=other_branch)
    own_alerta = await _seed_alerta(pg_engine, uuid_sucursal=own_branch)
    await _seed_alerta(pg_engine, uuid_sucursal=other_branch)
    fastapi_app, set_claims = _build_app(pg_engine)
    operador_actor = uuid_lib.uuid4()
    token = _operador_token_and_claims(
        fastapi_app, set_claims, actor_uuid=operador_actor, sucursal_uuid=own_branch
    )

    resp = await _get(fastapi_app, "/api/v1/workflows/alerta", token)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["uuid"] == str(own_alerta)
    assert items[0]["uuid_sucursal"] == str(own_branch)


async def test_list_alertas_operador_cross_branch_filter_returns_403(pg_engine, pg_dsn) -> None:
    own_branch, other_branch = uuid_lib.uuid4(), uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=own_branch)
    await _seed_sucursal(pg_engine, uuid_sucursal=other_branch)
    fastapi_app, set_claims = _build_app(pg_engine)
    operador_actor = uuid_lib.uuid4()
    token = _operador_token_and_claims(
        fastapi_app, set_claims, actor_uuid=operador_actor, sucursal_uuid=own_branch
    )

    resp = await _get(
        fastapi_app, f"/api/v1/workflows/alerta?uuid_sucursal={other_branch}", token
    )
    assert resp.status_code == 403, f"got {resp.status_code}: {resp.text}"
    assert resp.json()["detail"]["error"] == "tenant_scope_violation"


# ---------------------------------------------------------------------------
# estado filter + cursor pagination (newest vigente_desde first)
# ---------------------------------------------------------------------------


async def test_list_alertas_estado_filter(pg_engine, pg_dsn) -> None:
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)
    await _seed_alerta(pg_engine, uuid_sucursal=branch, estado="abierta")
    resuelta_uuid = await _seed_alerta(pg_engine, uuid_sucursal=branch, estado="resuelta")
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch])
    fastapi_app, set_claims = _build_app(pg_engine)
    token = _admin_token_and_claims(fastapi_app, set_claims, actor_uuid=admin_actor)

    resp = await _get(fastapi_app, "/api/v1/workflows/alerta?estado=resuelta", token)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["uuid"] == str(resuelta_uuid)
    assert items[0]["estado"] == "resuelta"


async def test_list_alertas_cursor_pagination_newest_first(pg_engine, pg_dsn) -> None:
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)
    now = _now_naive()
    older = await _seed_alerta(
        pg_engine, uuid_sucursal=branch, vigente_desde=now - timedelta(minutes=2)
    )
    newer = await _seed_alerta(
        pg_engine, uuid_sucursal=branch, vigente_desde=now - timedelta(minutes=1)
    )
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch])
    fastapi_app, set_claims = _build_app(pg_engine)
    token = _admin_token_and_claims(fastapi_app, set_claims, actor_uuid=admin_actor)

    resp = await _get(fastapi_app, "/api/v1/workflows/alerta?limit=1", token)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["uuid"] == str(newer)
    assert body["next_cursor"] is not None

    resp2 = await _get(
        fastapi_app, f"/api/v1/workflows/alerta?limit=1&cursor={body['next_cursor']}", token
    )
    assert resp2.status_code == 200, f"got {resp2.status_code}: {resp2.text}"
    body2 = resp2.json()
    assert len(body2["items"]) == 1
    assert body2["items"][0]["uuid"] == str(older)
    assert body2["next_cursor"] is None


# ---------------------------------------------------------------------------
# GET /{uuid} -- same router, current_version
# ---------------------------------------------------------------------------


async def test_get_alerta_by_uuid_returns_current_version(pg_engine, pg_dsn) -> None:
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)
    alerta_uuid = await _seed_alerta(pg_engine, uuid_sucursal=branch)
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch])
    fastapi_app, set_claims = _build_app(pg_engine)
    token = _admin_token_and_claims(fastapi_app, set_claims, actor_uuid=admin_actor)

    resp = await _get(fastapi_app, f"/api/v1/workflows/alerta/{alerta_uuid}", token)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    assert resp.json()["uuid"] == str(alerta_uuid)


__all__ = [
    "test_get_alerta_by_uuid_returns_current_version",
    "test_list_alertas_admin_sees_every_permitted_branch",
    "test_list_alertas_admin_unauthorized_branch_filter_returns_403",
    "test_list_alertas_cursor_pagination_newest_first",
    "test_list_alertas_estado_filter",
    "test_list_alertas_operador_cross_branch_filter_returns_403",
    "test_list_alertas_operador_only_sees_own_branch",
    "test_list_alertas_severity_null_when_tipo_alerta_not_in_catalog",
    "test_list_alertas_severity_populated_from_alert_types",
]
