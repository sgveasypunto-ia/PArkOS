"""Integration tests for HU-F19.1 (``admin_views.py``).

Real Postgres + real handlers, same harness shape as
``test_admin_dashboard_resumen.py``. Three new read-only surfaces under
test:

- ``GET /api/v1/admin/sync/log`` (T1) -- cross-branch ``sync_log``
  history, cursor-paginated, ``desde``/``hasta`` date-range filter on
  ``timestamp_evento``.
- ``GET /api/v1/admin/sync/conflict`` (T2) -- cross-branch
  ``sync_conflict`` listing, cursor-paginated (BR2: ``datos_local`` /
  ``datos_cloud`` / ``resolucion`` surfaced as-is, no new resolution
  mechanism).
- ``GET /api/v1/admin/sync/estado`` (T3) -- one row per permitted branch,
  classified verde/amarillo/rojo at query time (BR1). Covers every BR1
  branch: verde (<60s), amarillo (60-300s), rojo by lag (>300s), rojo by
  a failed last cycle (``operaciones_fallidas > 0``, regardless of lag),
  and rojo for a branch that has never synced (no ``sync_log`` row).

Skips cleanly (via the ``alembic_upgrade`` fixture chain in
``conftest.py``) when the local Postgres image lacks ``pg_partman`` --
documented, expected limitation, not a regression to chase here.
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
from sqlalchemy.ext.asyncio import async_sessionmaker

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
for _p in (_PARKOS_CORE_SRC,):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import parkos_core.api.v1.admin_views as _admin_views_module  # noqa: E402
from parkos_core.api.v1.admin_views import router as admin_views_router_obj  # noqa: E402
from parkos_core.auth.tokens import issue_token  # noqa: E402
from parkos_core.models.A.sync_conflict import SyncConflict  # noqa: E402
from parkos_core.models.A.sync_log import SyncLog  # noqa: E402
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
                nombre="Sync SA",
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
                nombre=f"Suc Sync {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"S{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle Sync",
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
                nombre="Sync",
                apellido="Admin",
                cedula=f"A{actor_uuid.hex[:10]}",
                email=f"sync-{actor_uuid.hex[:8]}@parkos.local",
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


async def _seed_sync_log(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    timestamp_evento: datetime | None,
    created_at: datetime,
    operaciones_enviadas: int | None = 10,
    operaciones_exitosas: int | None = 10,
    operaciones_fallidas: int | None = 0,
    conflictos: int | None = 0,
    duracion_ms: int | None = 100,
) -> uuid_lib.UUID:
    row_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            SyncLog(
                uuid=row_uuid,
                fecha_retencion_hasta=created_at.date(),
                uuid_sucursal=uuid_sucursal,
                timestamp_evento=timestamp_evento,
                operaciones_enviadas=operaciones_enviadas,
                operaciones_exitosas=operaciones_exitosas,
                operaciones_fallidas=operaciones_fallidas,
                conflictos=conflictos,
                duracion_ms=duracion_ms,
                created_at=created_at,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return row_uuid


async def _seed_sync_conflict(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    created_at: datetime,
    tabla: str = "ingreso",
    datos_local: dict | None = None,
    datos_cloud: dict | None = None,
    politica: str = "cloud_wins",
    resolucion: str = "cloud_wins",
) -> uuid_lib.UUID:
    row_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            SyncConflict(
                uuid=row_uuid,
                uuid_sucursal=uuid_sucursal,
                tabla=tabla,
                uuid_registro=uuid_lib.uuid4(),
                datos_local=datos_local or {"placa": "LOCAL01"},
                datos_cloud=datos_cloud or {"placa": "CLOUD01"},
                politica=politica,
                resolucion=resolucion,
                timestamp_evento=created_at,
                fecha_retencion_hasta=None,
                created_at=created_at,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return row_uuid


def _build_app(pg_engine) -> tuple[FastAPI, Any]:
    """Mount ``admin_views.router`` with overrides; return (app, set_claims)."""
    from parkos_core.db.engine import get_session

    app = FastAPI()
    outer = APIRouter(prefix="/api/v1")
    outer.include_router(admin_views_router_obj)
    app.include_router(outer)

    issuer_dep = _admin_views_module._admin_issuer_dep
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


def _truncate(pg_dsn: str) -> None:
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE prod.sync_conflict, prod.sync_log, prod.usuarios_sucursal, "
            "prod.usuarios, prod.sucursal, prod.empresa CASCADE"
        )
        conn.commit()


async def _get(fastapi_app: FastAPI, url: str, token: str) -> httpx.Response:
    transport = ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        return await c.get(url, headers={"Authorization": f"Bearer {token}"})


def _set_claims_and_token(
    fastapi_app: FastAPI, set_claims, *, actor_uuid: uuid_lib.UUID, permitidas: list[uuid_lib.UUID]
) -> str:
    set_claims(
        {
            "sub": str(actor_uuid),
            "rol": "admin",
            "iss": "admin-test",
            "sucursales_permitidas": [str(u) for u in permitidas],
        }
    )
    return issue_token(
        subject_uuid=actor_uuid,
        issuer="admin-test",
        claims={"rol": "admin", "sucursales_permitidas": [str(u) for u in permitidas]},
    )


async def _setup_one_branch_admin(
    pg_engine, pg_dsn
) -> tuple[uuid_lib.UUID, uuid_lib.UUID, FastAPI, Any]:
    _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch])
    fastapi_app, set_claims = _build_app(pg_engine)
    return branch, admin_actor, fastapi_app, set_claims


# ---------------------------------------------------------------------------
# T3 / BR1: /admin/sync/estado -- verde/amarillo/rojo classification
# ---------------------------------------------------------------------------


async def test_sync_estado_verde_when_last_cycle_recent(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    """Lag < 60s on the latest successful cycle -> verde (BR1)."""
    branch, admin_actor, fastapi_app, set_claims = await _setup_one_branch_admin(pg_engine, pg_dsn)
    now = _now_naive()
    await _seed_sync_log(
        pg_engine,
        uuid_sucursal=branch,
        timestamp_evento=now - timedelta(seconds=10),
        created_at=now,
    )
    token = _set_claims_and_token(
        fastapi_app, set_claims, actor_uuid=admin_actor, permitidas=[branch]
    )

    resp = await _get(fastapi_app, "/api/v1/admin/sync/estado", token)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["uuid_sucursal"] == str(branch)
    assert items[0]["estado"] == "verde"
    assert items[0]["lag_seconds"] is not None
    assert items[0]["lag_seconds"] < 60


async def test_sync_estado_amarillo_when_lag_between_60_and_300(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    """60s <= lag <= 300s -> amarillo (BR1)."""
    branch, admin_actor, fastapi_app, set_claims = await _setup_one_branch_admin(pg_engine, pg_dsn)
    now = _now_naive()
    await _seed_sync_log(
        pg_engine,
        uuid_sucursal=branch,
        timestamp_evento=now - timedelta(seconds=150),
        created_at=now,
    )
    token = _set_claims_and_token(
        fastapi_app, set_claims, actor_uuid=admin_actor, permitidas=[branch]
    )

    resp = await _get(fastapi_app, "/api/v1/admin/sync/estado", token)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    items = resp.json()["items"]
    assert items[0]["estado"] == "amarillo"
    assert 60 <= items[0]["lag_seconds"] <= 300


async def test_sync_estado_rojo_when_lag_over_300(pg_engine, mint_operador_jwt, pg_dsn) -> None:
    """Lag > 300s since the last cycle -> rojo (BR1)."""
    branch, admin_actor, fastapi_app, set_claims = await _setup_one_branch_admin(pg_engine, pg_dsn)
    now = _now_naive()
    await _seed_sync_log(
        pg_engine,
        uuid_sucursal=branch,
        timestamp_evento=now - timedelta(seconds=600),
        created_at=now,
    )
    token = _set_claims_and_token(
        fastapi_app, set_claims, actor_uuid=admin_actor, permitidas=[branch]
    )

    resp = await _get(fastapi_app, "/api/v1/admin/sync/estado", token)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    items = resp.json()["items"]
    assert items[0]["estado"] == "rojo"
    assert items[0]["lag_seconds"] > 300


async def test_sync_estado_rojo_when_last_cycle_failed_even_if_recent(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    """A failed latest cycle is rojo regardless of lag (BR1 ``sync fallida``)."""
    branch, admin_actor, fastapi_app, set_claims = await _setup_one_branch_admin(pg_engine, pg_dsn)
    now = _now_naive()
    await _seed_sync_log(
        pg_engine,
        uuid_sucursal=branch,
        timestamp_evento=now - timedelta(seconds=5),
        created_at=now,
        operaciones_enviadas=10,
        operaciones_exitosas=7,
        operaciones_fallidas=3,
    )
    token = _set_claims_and_token(
        fastapi_app, set_claims, actor_uuid=admin_actor, permitidas=[branch]
    )

    resp = await _get(fastapi_app, "/api/v1/admin/sync/estado", token)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    items = resp.json()["items"]
    assert items[0]["estado"] == "rojo", "a failed cycle must be rojo even with a 5s lag"
    assert items[0]["lag_seconds"] < 60


async def test_sync_estado_rojo_when_never_synced(pg_engine, mint_operador_jwt, pg_dsn) -> None:
    """No ``sync_log`` row at all -> rojo, ``last_sync_at`` None (BR1)."""
    branch, admin_actor, fastapi_app, set_claims = await _setup_one_branch_admin(pg_engine, pg_dsn)
    token = _set_claims_and_token(
        fastapi_app, set_claims, actor_uuid=admin_actor, permitidas=[branch]
    )

    resp = await _get(fastapi_app, "/api/v1/admin/sync/estado", token)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["estado"] == "rojo"
    assert items[0]["last_sync_at"] is None
    assert items[0]["lag_seconds"] is None
    assert items[0]["queue_depth"] == 0


async def test_sync_estado_missing_scope_returns_400(pg_engine, mint_operador_jwt, pg_dsn) -> None:
    """An admin with no open ``usuarios_sucursal`` rows gets 400, not an empty 200."""
    _truncate(pg_dsn)
    admin_actor = uuid_lib.uuid4()
    fastapi_app, set_claims = _build_app(pg_engine)
    token = _set_claims_and_token(fastapi_app, set_claims, actor_uuid=admin_actor, permitidas=[])

    resp = await _get(fastapi_app, "/api/v1/admin/sync/estado", token)
    assert resp.status_code == 400, f"got {resp.status_code}: {resp.text}"
    assert resp.json()["detail"]["error"] == "missing_sucursal_context"


# ---------------------------------------------------------------------------
# T1: /admin/sync/log -- cursor pagination + date-range validation
# ---------------------------------------------------------------------------


async def test_sync_log_list_cursor_pagination_newest_first(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    branch, admin_actor, fastapi_app, set_claims = await _setup_one_branch_admin(pg_engine, pg_dsn)
    now = _now_naive()
    older = await _seed_sync_log(
        pg_engine, uuid_sucursal=branch, timestamp_evento=now, created_at=now - timedelta(minutes=2)
    )
    newer = await _seed_sync_log(
        pg_engine, uuid_sucursal=branch, timestamp_evento=now, created_at=now - timedelta(minutes=1)
    )
    token = _set_claims_and_token(
        fastapi_app, set_claims, actor_uuid=admin_actor, permitidas=[branch]
    )

    resp = await _get(fastapi_app, "/api/v1/admin/sync/log?limit=1", token)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["uuid"] == str(newer)
    assert body["next_cursor"] is not None

    resp2 = await _get(
        fastapi_app, f"/api/v1/admin/sync/log?limit=1&cursor={body['next_cursor']}", token
    )
    assert resp2.status_code == 200, f"got {resp2.status_code}: {resp2.text}"
    body2 = resp2.json()
    assert len(body2["items"]) == 1
    assert body2["items"][0]["uuid"] == str(older)
    assert body2["next_cursor"] is None


async def test_sync_log_list_rango_fecha_invalido_returns_422(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    branch, admin_actor, fastapi_app, set_claims = await _setup_one_branch_admin(pg_engine, pg_dsn)
    token = _set_claims_and_token(
        fastapi_app, set_claims, actor_uuid=admin_actor, permitidas=[branch]
    )

    resp = await _get(
        fastapi_app, "/api/v1/admin/sync/log?desde=2026-01-10&hasta=2026-01-01", token
    )
    assert resp.status_code == 422, f"got {resp.status_code}: {resp.text}"
    assert resp.json()["detail"]["error"] == "rango_fecha_invalido"


async def test_sync_log_list_unauthorized_branch_returns_403(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    branch, admin_actor, fastapi_app, set_claims = await _setup_one_branch_admin(pg_engine, pg_dsn)
    other_branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=other_branch)
    token = _set_claims_and_token(
        fastapi_app, set_claims, actor_uuid=admin_actor, permitidas=[branch]
    )

    resp = await _get(
        fastapi_app, f"/api/v1/admin/sync/log?uuid_sucursal={other_branch}", token
    )
    assert resp.status_code == 403, f"got {resp.status_code}: {resp.text}"
    assert resp.json()["detail"]["error"] == "unauthorized_sucursal_context"


# ---------------------------------------------------------------------------
# T2 / BR2: /admin/sync/conflict -- datos_local vs datos_cloud + resolucion
# ---------------------------------------------------------------------------


async def test_sync_conflict_list_shows_local_vs_cloud_and_resolucion(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    branch, admin_actor, fastapi_app, set_claims = await _setup_one_branch_admin(pg_engine, pg_dsn)
    now = _now_naive()
    await _seed_sync_conflict(
        pg_engine,
        uuid_sucursal=branch,
        created_at=now,
        datos_local={"placa": "LOCAL123"},
        datos_cloud={"placa": "CLOUD123"},
        politica="cloud_wins",
        resolucion="cloud_wins",
    )
    token = _set_claims_and_token(
        fastapi_app, set_claims, actor_uuid=admin_actor, permitidas=[branch]
    )

    resp = await _get(fastapi_app, "/api/v1/admin/sync/conflict", token)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["datos_local"] == {"placa": "LOCAL123"}
    assert items[0]["datos_cloud"] == {"placa": "CLOUD123"}
    assert items[0]["resolucion"] == "cloud_wins"


__all__ = [
    "test_sync_conflict_list_shows_local_vs_cloud_and_resolucion",
    "test_sync_estado_amarillo_when_lag_between_60_and_300",
    "test_sync_estado_missing_scope_returns_400",
    "test_sync_estado_rojo_when_lag_over_300",
    "test_sync_estado_rojo_when_last_cycle_failed_even_if_recent",
    "test_sync_estado_rojo_when_never_synced",
    "test_sync_estado_verde_when_last_cycle_recent",
    "test_sync_log_list_cursor_pagination_newest_first",
    "test_sync_log_list_rango_fecha_invalido_returns_422",
    "test_sync_log_list_unauthorized_branch_returns_403",
]
