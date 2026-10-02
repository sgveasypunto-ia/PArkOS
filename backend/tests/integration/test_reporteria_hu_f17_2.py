"""Integration tests for HU-F17.2 additions to ``api/v1/reporteria.py``.

Real Postgres + real handlers, same harness shape as
``test_reporteria_operacional.py`` (this file duplicates its seed helpers
rather than importing them -- same convention as
``test_admin_dashboard_resumen.py``, which does the same thing for its
own module).

Two surfaces under test:

- ``GET /admin/reporteria/operacional`` additions (BR1 + filters +
  cursor): ``tiempos_estancia`` only counts completed stays (a non-
  anulada ``salidas`` row), ``uuid_tipo_vehiculo`` narrows ``ingresos``,
  and the ``ingresos`` list is cursor-paginated (page 1 + page 2 cover
  every seeded row exactly once).
- ``GET /admin/reporteria/ocupacion`` (new, HU-F17.2): cross-branch
  heatmap + BR2's aggregate ratio, and its own 422/400 error shapes.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, datetime
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

import parkos_core.api.v1.reporteria as _reporteria_module  # noqa: E402
from parkos_core.api.v1.reporteria import router as reporteria_router_obj  # noqa: E402
from parkos_core.auth.tokens import issue_token  # noqa: E402
from parkos_core.models.A.salidas import Salidas  # noqa: E402
from parkos_core.models.L_E.ingreso import Ingreso  # noqa: E402
from parkos_core.models.L_W.anulaciones import Anulaciones  # noqa: E402
from parkos_core.models.V.cantidad_vehiculos_sucursal import (  # noqa: E402
    CantidadVehiculosSucursal,
)
from parkos_core.models.V.empresa import Empresa  # noqa: E402
from parkos_core.models.V.sucursal import Sucursal  # noqa: E402
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo  # noqa: E402


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
                nombre="HU-F17.2 SA",
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
                nombre=f"Suc F17.2 {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"H{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle HU-F17.2",
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


async def _seed_tipo_vehiculo(pg_engine, *, tipo: str = "carro") -> uuid_lib.UUID:
    now = _now_naive()
    tipo_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            TiposVehiculo(
                uuid=tipo_uuid,
                tipo=tipo,
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
    return tipo_uuid


async def _seed_capacidad(
    pg_engine, *, uuid_sucursal: uuid_lib.UUID, uuid_tipo_vehiculo: uuid_lib.UUID, cantidad: int
) -> None:
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            CantidadVehiculosSucursal(
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_vehiculo,
                cantidad=cantidad,
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
                nombre="F17.2",
                apellido="Admin",
                cedula=f"A{actor_uuid.hex[:10]}",
                email=f"f17-2-{actor_uuid.hex[:8]}@parkos.local",
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


async def _seed_ingreso(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    placa: str,
    fecha_ingreso: datetime,
    created_at: datetime | None = None,
) -> uuid_lib.UUID:
    ingreso_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Ingreso(
                uuid=ingreso_uuid,
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_vehiculo,
                placa=placa,
                uuid_subscripcion_cliente=None,
                fecha_ingreso=fecha_ingreso,
                observaciones=None,
                created_at=created_at or fecha_ingreso,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return ingreso_uuid


async def _seed_salida(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_ingreso: uuid_lib.UUID,
    fecha_salida: datetime,
    anulada: bool = False,
) -> uuid_lib.UUID:
    salida_uuid = uuid_lib.uuid4()
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Salidas(
                uuid=salida_uuid,
                fecha_retencion_hasta=now.date(),
                uuid_sucursal=uuid_sucursal,
                uuid_ingreso=uuid_ingreso,
                fecha_salida=fecha_salida,
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.flush()
        if anulada:
            session.add(
                Anulaciones(
                    uuid=uuid_lib.uuid4(),
                    fecha_retencion_hasta=now.date(),
                    uuid_sucursal=uuid_sucursal,
                    tipo_anulable="salida",
                    uuid_ingreso=None,
                    uuid_salida=salida_uuid,
                    uuid_usuario=None,
                    motivo="test",
                    timestamp_evento=now,
                    created_at=now,
                    created_by=None,
                    sync_status="sincronizado",
                    sync_timestamp=None,
                    sync_attempts=0,
                    estado="ejecutada",
                )
            )
        await session.commit()
    return salida_uuid


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
            "TRUNCATE prod.alerta, prod.ingreso, prod.salidas, prod.anulaciones, "
            "prod.factura_pagos, prod.factura_impuestos, prod.factura_otros_cobros, "
            "prod.factura_detalle, prod.facturas, prod.revocacion_factura, "
            "prod.factura_electronica, prod.usuarios_sucursal, prod.usuarios, "
            "prod.tipos_vehiculo, prod.cantidad_vehiculos_sucursal, prod.tarifas_sucursal, "
            "prod.subscripcion_vehiculos, prod.subscripciones_cliente, prod.vehiculos, "
            "prod.sucursal, prod.empresa CASCADE"
        )
        conn.commit()


async def _get(
    fastapi_app: FastAPI, url: str, *, token: str
) -> httpx.Response:
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


# ---------------------------------------------------------------------------
# /admin/reporteria/operacional -- BR1 (tiempos de estancia) + filters + cursor
# ---------------------------------------------------------------------------


async def test_tiempos_estancia_solo_cuenta_estancias_completas(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    """BR1: only a non-anulada ``salidas`` row contributes a stay-time sample.

    Seeds 3 ingresos on the same day: one completed in 1h (3600s), one
    still parked (no salida -> excluded), one with an ANULADA salida
    (excluded, same as a still-parked one). Expect exactly one
    ``tiempos_estancia`` bucket with ``muestras=1`` and
    promedio/maximo/minimo == 3600.
    """
    _truncate(pg_dsn)
    branch = await _seed_sucursal(pg_engine, uuid_sucursal=uuid_lib.uuid4())
    tipo = await _seed_tipo_vehiculo(pg_engine)

    day = _now_naive().replace(hour=8, minute=0, second=0, microsecond=0)

    completed = await _seed_ingreso(
        pg_engine, uuid_sucursal=branch, uuid_tipo_vehiculo=tipo, placa="EST001", fecha_ingreso=day
    )
    await _seed_salida(
        pg_engine,
        uuid_sucursal=branch,
        uuid_ingreso=completed,
        fecha_salida=day.replace(hour=9),
    )

    still_parked = await _seed_ingreso(
        pg_engine, uuid_sucursal=branch, uuid_tipo_vehiculo=tipo, placa="EST002", fecha_ingreso=day
    )
    assert still_parked is not None  # no salida seeded -- stays "active"

    anulada_exit = await _seed_ingreso(
        pg_engine, uuid_sucursal=branch, uuid_tipo_vehiculo=tipo, placa="EST003", fecha_ingreso=day
    )
    await _seed_salida(
        pg_engine,
        uuid_sucursal=branch,
        uuid_ingreso=anulada_exit,
        fecha_salida=day.replace(hour=10),
        anulada=True,
    )

    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch])
    fastapi_app, token = _setup_app_and_token(
        pg_engine, admin_actor=admin_actor, permitidas=[branch]
    )

    resp = await _get(
        fastapi_app,
        f"/api/v1/admin/reporteria/operacional?uuid_sucursal={branch}",
        token=token,
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()

    assert len(body["tiempos_estancia"]) == 1
    bucket = body["tiempos_estancia"][0]
    assert bucket["muestras"] == 1
    assert bucket["promedio_segundos"] == 3600.0
    assert bucket["maximo_segundos"] == 3600.0
    assert bucket["minimo_segundos"] == 3600.0

    # Ingresos list: 3 rows total, only the completed one carries a
    # non-null tiempo_estancia_segundos.
    by_placa = {row["placa"]: row for row in body["ingresos"]}
    assert len(by_placa) == 3
    assert by_placa["EST001"]["tiempo_estancia_segundos"] == 3600.0
    assert by_placa["EST002"]["tiempo_estancia_segundos"] is None
    assert by_placa["EST003"]["tiempo_estancia_segundos"] is None


async def test_uuid_tipo_vehiculo_filtra_ingresos(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    """``uuid_tipo_vehiculo`` narrows both ``ingresos`` and ``tiempos_estancia``."""
    _truncate(pg_dsn)
    branch = await _seed_sucursal(pg_engine, uuid_sucursal=uuid_lib.uuid4())
    tipo_carro = await _seed_tipo_vehiculo(pg_engine, tipo="carro")
    tipo_moto = await _seed_tipo_vehiculo(pg_engine, tipo="moto")

    day = _now_naive().replace(hour=8, minute=0, second=0, microsecond=0)
    await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_vehiculo=tipo_carro,
        placa="CARRO1",
        fecha_ingreso=day,
    )
    await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_vehiculo=tipo_moto,
        placa="MOTO01",
        fecha_ingreso=day,
    )

    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch])
    fastapi_app, token = _setup_app_and_token(
        pg_engine, admin_actor=admin_actor, permitidas=[branch]
    )

    resp = await _get(
        fastapi_app,
        f"/api/v1/admin/reporteria/operacional?uuid_sucursal={branch}&uuid_tipo_vehiculo={tipo_moto}",
        token=token,
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert len(body["ingresos"]) == 1
    assert body["ingresos"][0]["placa"] == "MOTO01"


async def test_ingresos_cursor_pagina_sin_duplicados(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    """``limit=1`` over 2 ingresos: page 1 + page 2 cover both, no overlap."""
    _truncate(pg_dsn)
    branch = await _seed_sucursal(pg_engine, uuid_sucursal=uuid_lib.uuid4())
    tipo = await _seed_tipo_vehiculo(pg_engine)

    day = _now_naive().replace(hour=8, minute=0, second=0, microsecond=0)
    await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_vehiculo=tipo,
        placa="PAG001",
        fecha_ingreso=day,
        created_at=day,
    )
    await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_vehiculo=tipo,
        placa="PAG002",
        fecha_ingreso=day,
        created_at=day.replace(hour=9),
    )

    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch])
    fastapi_app, token = _setup_app_and_token(
        pg_engine, admin_actor=admin_actor, permitidas=[branch]
    )

    resp1 = await _get(
        fastapi_app,
        f"/api/v1/admin/reporteria/operacional?uuid_sucursal={branch}&limit=1",
        token=token,
    )
    assert resp1.status_code == 200, f"got {resp1.status_code}: {resp1.text}"
    body1 = resp1.json()
    assert len(body1["ingresos"]) == 1
    assert body1["ingresos_next_cursor"] is not None
    # created_at DESC -- the later ingreso (PAG002) comes first.
    assert body1["ingresos"][0]["placa"] == "PAG002"

    resp2 = await _get(
        fastapi_app,
        f"/api/v1/admin/reporteria/operacional?uuid_sucursal={branch}&limit=1"
        f"&cursor={body1['ingresos_next_cursor']}",
        token=token,
    )
    assert resp2.status_code == 200, f"got {resp2.status_code}: {resp2.text}"
    body2 = resp2.json()
    assert len(body2["ingresos"]) == 1
    assert body2["ingresos"][0]["placa"] == "PAG001"
    assert body2["ingresos_next_cursor"] is None


# ---------------------------------------------------------------------------
# /admin/reporteria/ocupacion -- heatmap + BR2 ratio
# ---------------------------------------------------------------------------


async def test_ocupacion_heatmap_cross_branch_y_ratio_br2(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    """Cross-branch heatmap covers every permitted branch + BR2 ratio.

    One active ingreso (no salida) against a capacity of 2 -> 50%.
    """
    _truncate(pg_dsn)
    branch_a = await _seed_sucursal(pg_engine, uuid_sucursal=uuid_lib.uuid4())
    branch_b = await _seed_sucursal(pg_engine, uuid_sucursal=uuid_lib.uuid4())
    tipo = await _seed_tipo_vehiculo(pg_engine)
    await _seed_capacidad(pg_engine, uuid_sucursal=branch_a, uuid_tipo_vehiculo=tipo, cantidad=2)

    today = _now_naive().replace(hour=10, minute=0, second=0, microsecond=0)
    await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch_a,
        uuid_tipo_vehiculo=tipo,
        placa="OCU001",
        fecha_ingreso=today,
    )
    await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch_b,
        uuid_tipo_vehiculo=tipo,
        placa="OCU002",
        fecha_ingreso=today,
    )

    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch_a, branch_b])
    fastapi_app, token = _setup_app_and_token(
        pg_engine, admin_actor=admin_actor, permitidas=[branch_a, branch_b]
    )

    resp = await _get(
        fastapi_app,
        "/api/v1/admin/reporteria/ocupacion",
        token=token,
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()

    assert {s["uuid"] for s in body["sucursales"]} == {str(branch_a), str(branch_b)}
    cells_by_branch = {cell["uuid_sucursal"] for cell in body["data"]}
    assert str(branch_a) in cells_by_branch
    assert str(branch_b) in cells_by_branch

    assert body["ocupacion_agregada"]["ocupados"] == 2
    assert body["ocupacion_agregada"]["capacidad"] == 2
    assert body["ocupacion_agregada"]["porcentaje"] == 100.0


async def test_ocupacion_rango_invalido_es_422(pg_engine, mint_operador_jwt, pg_dsn) -> None:
    _truncate(pg_dsn)
    branch = await _seed_sucursal(pg_engine, uuid_sucursal=uuid_lib.uuid4())
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch])
    fastapi_app, token = _setup_app_and_token(
        pg_engine, admin_actor=admin_actor, permitidas=[branch]
    )

    resp = await _get(
        fastapi_app,
        "/api/v1/admin/reporteria/ocupacion?desde=2026-12-31&hasta=2026-01-01",
        token=token,
    )
    assert resp.status_code == 422, f"got {resp.status_code}: {resp.text}"
    assert resp.json()["detail"]["error"] == "rango_fecha_invalido"


async def test_ocupacion_sin_permitidas_es_400(pg_engine, mint_operador_jwt, pg_dsn) -> None:
    _truncate(pg_dsn)
    admin_actor = uuid_lib.uuid4()
    fastapi_app, token = _setup_app_and_token(pg_engine, admin_actor=admin_actor, permitidas=[])

    resp = await _get(fastapi_app, "/api/v1/admin/reporteria/ocupacion", token=token)
    assert resp.status_code == 400, f"got {resp.status_code}: {resp.text}"
    assert resp.json()["detail"]["error"] == "missing_sucursal_context"
