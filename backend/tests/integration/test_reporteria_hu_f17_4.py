"""Integration tests for HU-F17.4 additions to ``api/v1/reporteria.py``.

Real Postgres + real handlers, same harness shape as
``test_reporteria_hu_f17_3.py`` (this file duplicates its seed helpers
rather than importing them -- same convention that file documents).

Two surfaces under test, both served by the single new endpoint:

- ``GET /admin/reporteria/suscripciones/cohorte`` -- BR1's cohort
  retention math (group by month of ``fecha_inicio_cobertura``, %
  retained ``fecha_vencimiento >= inicio_cohorte + M meses``).
- The same response's ``proximas_a_vencer`` field -- the REQ-OPS-181
  ``dias_para_vencer`` criterion (vencidas excluded, ascending by
  ``fecha_vencimiento``), cross-branch admin equivalent of HU-F9.2's
  single-branch prior art.

Plus one 422 ``rango_fecha_invalido`` check (shared validation,
HU-F17.2/F17.3 precedent).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
for _p in (_PARKOS_CORE_SRC,):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import parkos_core.api.v1.reporteria as _reporteria_module  # noqa: E402
from parkos_core.api.v1.reporteria import router as reporteria_router_obj  # noqa: E402
from parkos_core.auth.tokens import issue_token  # noqa: E402
from parkos_core.models.V.empresa import Empresa  # noqa: E402
from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente  # noqa: E402
from parkos_core.models.V.sucursal import Sucursal  # noqa: E402


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seed_sucursal(pg_engine, *, uuid_sucursal: uuid_lib.UUID) -> uuid_lib.UUID:
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="HU-F17.4 SA",
                nit=f"906{empresa_uuid.hex[:6]}",
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
                nombre=f"Suc F17.4 {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"H{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle HU-F17.4",
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
    return uuid_sucursal


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
                nombre="F17.4",
                apellido="Admin",
                cedula=f"A{actor_uuid.hex[:10]}",
                email=f"f17-4-{actor_uuid.hex[:8]}@parkos.local",
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


async def _seed_subscripcion(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    fecha_inicio_cobertura: date,
    fecha_vencimiento: date | None,
    estado: str = "activo",
    vigente_hasta: datetime | None = None,
) -> uuid_lib.UUID:
    now = _now_naive()
    subscripcion_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            SubscripcionesCliente(
                uuid=subscripcion_uuid,
                uuid_cliente=uuid_lib.uuid4(),
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_subscripcion=None,
                fecha_inicio_cobertura=fecha_inicio_cobertura,
                fecha_vencimiento=fecha_vencimiento,
                vigente_desde=now,
                vigente_hasta=vigente_hasta,
                estado=estado,
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return subscripcion_uuid


def _build_app(pg_engine) -> tuple[FastAPI, callable]:
    from parkos_core.db.engine import get_session

    app = FastAPI()
    outer = APIRouter(prefix="/api/v1")
    outer.include_router(reporteria_router_obj)
    app.include_router(outer)

    issuer_dep = _reporteria_module._admin_issuer_dep
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
            "TRUNCATE prod.usuarios_sucursal, prod.usuarios, "
            "prod.subscripcion_vehiculos, prod.subscripciones_cliente, "
            "prod.sucursal, prod.empresa CASCADE"
        )
        conn.commit()


async def _get(fastapi_app: FastAPI, url: str, *, token: str) -> httpx.Response:
    transport = ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        return await c.get(url, headers={"Authorization": f"Bearer {token}"})


def _setup_app_and_token(
    pg_engine, *, admin_actor: uuid_lib.UUID, permitidas: list[uuid_lib.UUID]
) -> tuple[FastAPI, str]:
    fastapi_app, set_claims = _build_app(pg_engine)
    set_claims(
        {
            "sub": str(admin_actor),
            "rol": "admin",
            "iss": "admin-test",
            "sucursales_permitidas": [str(u) for u in permitidas],
        }
    )
    token = issue_token(
        subject_uuid=admin_actor,
        issuer="admin-test",
        claims={"rol": "admin", "sucursales_permitidas": [str(u) for u in permitidas]},
    )
    return fastapi_app, token


@pytest.mark.asyncio
async def test_cohorte_agrupa_por_mes_y_calcula_retencion_por_antiguedad(
    pg_engine, pg_dsn
) -> None:
    """BR1: cohort = month of ``fecha_inicio_cobertura``; retention at M
    months = % with ``fecha_vencimiento >= inicio_cohorte + M meses``.
    """
    _truncate(pg_dsn)
    uuid_sucursal = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=uuid_sucursal)
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[uuid_sucursal])

    # Cohort month: 3 months back from today, so M=0,1,2,3 are all
    # measurable (months_between(cohorte, hoy) >= 3).
    today = datetime.now(UTC).date()
    cohorte_mes = today.replace(day=1)
    for _ in range(3):
        cohorte_mes = (cohorte_mes.replace(day=1) - timedelta(days=1)).replace(day=1)

    # Member A: vencimiento far in the future -> retained at every offset.
    await _seed_subscripcion(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        fecha_inicio_cobertura=cohorte_mes.replace(day=5),
        fecha_vencimiento=cohorte_mes.replace(day=5) + timedelta(days=3650),
    )
    # Member B: short subscription, vencimiento still within the cohort
    # month -> retained at M=0 (inicio_cohorte itself) but NOT retained
    # from M=1 onward (its vencimiento never reaches the next month).
    vencimiento_b = (cohorte_mes.replace(day=28))
    await _seed_subscripcion(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        fecha_inicio_cobertura=cohorte_mes.replace(day=10),
        fecha_vencimiento=vencimiento_b,
    )

    fastapi_app, token = _setup_app_and_token(
        pg_engine, admin_actor=admin_actor, permitidas=[uuid_sucursal]
    )
    resp = await _get(
        fastapi_app,
        f"/api/v1/admin/reporteria/suscripciones/cohorte"
        f"?desde={cohorte_mes.isoformat()}&hasta={today.isoformat()}",
        token=token,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    cohortes_by_mes = {c["mes_cohorte"]: c for c in body["cohortes"]}
    assert cohortes_by_mes[cohorte_mes.isoformat()]["cohorte_size"] == 2

    cells = {
        (cell["mes_cohorte"], cell["mes_offset"]): cell
        for cell in body["data"]
        if cell["mes_cohorte"] == cohorte_mes.isoformat()
    }
    # M=0: both members still covered (fecha_inicio_cobertura <= vencimiento
    # for both) -> 100%.
    assert cells[(cohorte_mes.isoformat(), 0)]["porcentaje_retencion"] == pytest.approx(100.0)
    # M=2 (cohorte_mes + 2 months): member B's vencimiento (day 28 of the
    # cohort month) is before that threshold -> only member A retained,
    # 1/2 = 50%.
    assert cells[(cohorte_mes.isoformat(), 2)]["retenidos"] == 1
    assert cells[(cohorte_mes.isoformat(), 2)]["porcentaje_retencion"] == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_proximas_a_vencer_excluye_vencidas_y_ordena_ascendente(
    pg_engine, pg_dsn
) -> None:
    """``proximas_a_vencer`` reuses REQ-OPS-181: vencidas excluded, ASC."""
    _truncate(pg_dsn)
    uuid_sucursal = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=uuid_sucursal)
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[uuid_sucursal])

    today = datetime.now(UTC).date()

    # Vencida -- must NOT appear.
    await _seed_subscripcion(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        fecha_inicio_cobertura=today - timedelta(days=60),
        fecha_vencimiento=today - timedelta(days=5),
    )
    # Two upcoming, seeded out of order -> response must be ASC.
    uuid_en_10_dias = await _seed_subscripcion(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        fecha_inicio_cobertura=today - timedelta(days=20),
        fecha_vencimiento=today + timedelta(days=10),
    )
    uuid_en_2_dias = await _seed_subscripcion(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        fecha_inicio_cobertura=today - timedelta(days=28),
        fecha_vencimiento=today + timedelta(days=2),
    )
    # Deactivated (estado='inactivo') -- excluded from the alert list even
    # though it has not expired yet.
    await _seed_subscripcion(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        fecha_inicio_cobertura=today - timedelta(days=15),
        fecha_vencimiento=today + timedelta(days=1),
        estado="inactivo",
    )

    fastapi_app, token = _setup_app_and_token(
        pg_engine, admin_actor=admin_actor, permitidas=[uuid_sucursal]
    )
    resp = await _get(
        fastapi_app,
        f"/api/v1/admin/reporteria/suscripciones/cohorte"
        f"?desde={(today - timedelta(days=365)).isoformat()}&hasta={today.isoformat()}",
        token=token,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    por_vencer = body["proximas_a_vencer"]
    assert [item["uuid"] for item in por_vencer] == [
        str(uuid_en_2_dias),
        str(uuid_en_10_dias),
    ]
    assert por_vencer[0]["dias_para_vencer"] == 2
    assert por_vencer[1]["dias_para_vencer"] == 10


@pytest.mark.asyncio
async def test_suscripciones_cohorte_rango_fecha_invalido_422(pg_engine, pg_dsn) -> None:
    """``desde > hasta`` -> 422 ``rango_fecha_invalido`` (HU-F17.2/F17.3 precedent)."""
    _truncate(pg_dsn)
    uuid_sucursal = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=uuid_sucursal)
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[uuid_sucursal])

    fastapi_app, token = _setup_app_and_token(
        pg_engine, admin_actor=admin_actor, permitidas=[uuid_sucursal]
    )
    today = datetime.now(UTC).date()
    resp = await _get(
        fastapi_app,
        f"/api/v1/admin/reporteria/suscripciones/cohorte"
        f"?desde={today.isoformat()}&hasta={(today - timedelta(days=1)).isoformat()}",
        token=token,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "rango_fecha_invalido"
