"""Integration tests for HU-F17.1 (``admin_views.py``).

Real Postgres + real handlers, same harness shape as
``test_reporteria_operacional.py``. Two surfaces under test:

- ``GET /api/v1/admin/sucursales/{uuid}/dashboard`` -- pins down that
  ``ingresos_monto_total`` is the REAL sum of ``facturas.total`` joined on
  ``facturas.uuid_ingreso -> ingreso.uuid`` (BR1), not the historical
  ``0.0`` placeholder. No prior integration test covered this; the only
  existing coverage (``tests/unit/test_dashboard_aggregation.py``) runs
  against an unreachable dummy DB and skips the 200-path assertions.
- ``GET /api/v1/admin/dashboard/resumen`` -- the new cross-branch summary
  (BR2). Covers the partial-failure contract (an unauthorized/unknown
  branch in ``?sucursales=`` is reported in ``errores`` instead of failing
  the whole request) and one real aggregation end to end
  (``top_sucursales``) as a representative proof that the 6 cards compute
  directly off real tables.

Skips cleanly (via the ``pg_engine``/``alembic_upgrade`` fixture chain in
``conftest.py``) when the local Postgres image lacks ``pg_partman`` --
documented, expected limitation, not a regression to chase here.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, datetime
from decimal import Decimal
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
from parkos_core.models.A.factura_pagos import FacturaPagos  # noqa: E402
from parkos_core.models.L_E.facturas import Facturas  # noqa: E402
from parkos_core.models.L_E.ingreso import Ingreso  # noqa: E402
from parkos_core.models.V.empresa import Empresa  # noqa: E402
from parkos_core.models.V.sucursal import Sucursal  # noqa: E402


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seed_sucursal(pg_engine, *, uuid_sucursal: uuid_lib.UUID) -> uuid_lib.UUID:
    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo

    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Dashboard SA",
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
                nombre=f"Suc Dashboard {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"D{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle Dashboard",
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
        tipo = uuid_lib.uuid4()
        session.add(
            TiposVehiculo(
                uuid=tipo,
                tipo="carro",
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
    return tipo


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
                nombre="Dashboard",
                apellido="Admin",
                cedula=f"A{actor_uuid.hex[:10]}",
                email=f"dashboard-{actor_uuid.hex[:8]}@parkos.local",
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
    created_at: datetime,
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
                fecha_ingreso=created_at,
                observaciones=None,
                created_at=created_at,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return ingreso_uuid


async def _seed_factura(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_ingreso: uuid_lib.UUID,
    total: Decimal,
    created_at: datetime,
    medio_pago: str | None = None,
) -> uuid_lib.UUID:
    """Seed one ``prod.facturas`` row, optionally with a matching ``pago``."""
    factura_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Facturas(
                uuid=factura_uuid,
                fecha_retencion_hasta=created_at.date(),
                uuid_sucursal=uuid_sucursal,
                uuid_ingreso=uuid_ingreso,
                uuid_salida=None,
                uuid_subscripcion_cliente=None,
                subtotal=total,
                descuento=Decimal("0"),
                total=total,
                created_at=created_at,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.flush()
        if medio_pago is not None:
            session.add(
                FacturaPagos(
                    uuid=uuid_lib.uuid4(),
                    fecha_retencion_hasta=created_at.date(),
                    uuid_sucursal=uuid_sucursal,
                    uuid_factura=factura_uuid,
                    uuid_sesion=None,
                    medio_pago=medio_pago,
                    valor=total,
                    referencia=None,
                    tipo_movimiento="pago",
                    uuid_pago_revertido=None,
                    timestamp_evento=created_at,
                    created_at=created_at,
                    created_by=None,
                    sync_status="sincronizado",
                    sync_timestamp=None,
                    sync_attempts=0,
                )
            )
        await session.commit()
    return factura_uuid


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
            "TRUNCATE prod.alerta, prod.ingreso, prod.salidas, prod.anulaciones, "
            "prod.factura_pagos, prod.factura_impuestos, prod.factura_otros_cobros, "
            "prod.factura_detalle, prod.facturas, prod.revocacion_factura, "
            "prod.factura_electronica, prod.usuarios_sucursal, prod.usuarios, "
            "prod.tipos_vehiculo, prod.cantidad_vehiculos_sucursal, prod.tarifas_sucursal, "
            "prod.subscripcion_vehiculos, prod.subscripciones_cliente, prod.vehiculos, "
            "prod.sucursal, prod.empresa CASCADE"
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


# ---------------------------------------------------------------------------
# BR1: ingresos_monto_total is the REAL sum, not the historical 0.0 placeholder
# ---------------------------------------------------------------------------


async def test_branch_dashboard_ingresos_monto_total_is_real_sum(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    """Two facturas today for the branch sum to the real total (BR1).

    Chain verified against the real ORM models before writing this test:
    ``facturas.uuid_ingreso`` (prod.facturas) -> ``ingreso.uuid``
    (prod.ingreso) -- plan.md's assumed FK name matches the real column,
    no drift here. ``branch_dashboard`` filters on
    ``func.date(Ingreso.created_at) == today`` so both facturas must be
    dated today.
    """
    _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    tipo = await _seed_sucursal(pg_engine, uuid_sucursal=branch)
    today_naive = _now_naive()

    ing1 = await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_vehiculo=tipo,
        placa="REAL001",
        created_at=today_naive,
    )
    ing2 = await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_vehiculo=tipo,
        placa="REAL002",
        created_at=today_naive,
    )
    await _seed_factura(
        pg_engine,
        uuid_sucursal=branch,
        uuid_ingreso=ing1,
        total=Decimal("45000"),
        created_at=today_naive,
    )
    await _seed_factura(
        pg_engine,
        uuid_sucursal=branch,
        uuid_ingreso=ing2,
        total=Decimal("30500.50"),
        created_at=today_naive,
    )

    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch])

    fastapi_app, set_claims = _build_app(pg_engine)
    token = _set_claims_and_token(
        fastapi_app, set_claims, actor_uuid=admin_actor, permitidas=[branch]
    )

    # X-Sucursal-Context is required by this endpoint -- the shared ``_get``
    # helper only sets auth, so build the request directly here.
    transport = ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        resp = await c.get(
            f"/api/v1/admin/sucursales/{branch}/dashboard",
            headers={"Authorization": f"Bearer {token}", "X-Sucursal-Context": str(branch)},
        )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert float(body["ingresos_monto_total"]) == 75500.5, (
        f"expected the real sum 75500.5, got {body['ingresos_monto_total']} "
        "(0.0 would mean the placeholder regressed)"
    )
    assert body["ingresos_monto_total"] != 0.0


# ---------------------------------------------------------------------------
# BR2: /admin/dashboard/resumen -- partial failure + one real aggregation
# ---------------------------------------------------------------------------


async def test_dashboard_resumen_missing_scope_returns_400(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    """An admin with no open ``usuarios_sucursal`` rows gets 400, not an empty 200."""
    _truncate(pg_dsn)
    admin_actor = uuid_lib.uuid4()
    fastapi_app, set_claims = _build_app(pg_engine)
    token = _set_claims_and_token(fastapi_app, set_claims, actor_uuid=admin_actor, permitidas=[])

    resp = await _get(fastapi_app, "/api/v1/admin/dashboard/resumen", token)
    assert resp.status_code == 400, f"got {resp.status_code}: {resp.text}"
    assert resp.json()["detail"]["error"] == "missing_sucursal_context"


async def test_dashboard_resumen_unauthorized_branch_is_a_partial_error(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    """Naming a branch outside scope is a soft error, not a 403 for the whole request (BR2)."""
    _truncate(pg_dsn)
    a = uuid_lib.uuid4()
    b = uuid_lib.uuid4()  # exists, but NOT assigned to this admin
    tipo = await _seed_sucursal(pg_engine, uuid_sucursal=a)
    await _seed_sucursal(pg_engine, uuid_sucursal=b)

    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[a])
    fastapi_app, set_claims = _build_app(pg_engine)
    token = _set_claims_and_token(fastapi_app, set_claims, actor_uuid=admin_actor, permitidas=[a])

    resp = await _get(
        fastapi_app,
        f"/api/v1/admin/dashboard/resumen?sucursales={a},{b}",
        token,
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["sucursales"] == [str(a)]
    errores = body["errores"]
    assert len(errores) == 1
    assert errores[0]["uuid_sucursal"] == str(b)
    assert errores[0]["motivo"] == "sucursal_no_autorizada"
    _ = tipo  # unused beyond seeding the branch's vehicle type catalog row


async def test_dashboard_resumen_top_sucursales_real_aggregation(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    """``top_sucursales`` ranks branches by real ``facturas.total`` (BR2).

    Branch A gets one 500 factura, branch B gets one 1200 factura -- B
    must rank first. Proves the card is a direct aggregate over
    ``prod.facturas`` (grouped by ``uuid_sucursal``), not a placeholder.
    """
    _truncate(pg_dsn)
    a = uuid_lib.uuid4()
    b = uuid_lib.uuid4()
    tipo_a = await _seed_sucursal(pg_engine, uuid_sucursal=a)
    tipo_b = await _seed_sucursal(pg_engine, uuid_sucursal=b)
    now = _now_naive()

    ing_a = await _seed_ingreso(
        pg_engine, uuid_sucursal=a, uuid_tipo_vehiculo=tipo_a, placa="TOPA001", created_at=now
    )
    ing_b = await _seed_ingreso(
        pg_engine, uuid_sucursal=b, uuid_tipo_vehiculo=tipo_b, placa="TOPB001", created_at=now
    )
    await _seed_factura(
        pg_engine,
        uuid_sucursal=a,
        uuid_ingreso=ing_a,
        total=Decimal("500"),
        created_at=now,
        medio_pago="efectivo",
    )
    await _seed_factura(
        pg_engine,
        uuid_sucursal=b,
        uuid_ingreso=ing_b,
        total=Decimal("1200"),
        created_at=now,
        medio_pago="tarjeta",
    )

    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[a, b])
    fastapi_app, set_claims = _build_app(pg_engine)
    token = _set_claims_and_token(
        fastapi_app, set_claims, actor_uuid=admin_actor, permitidas=[a, b]
    )

    resp = await _get(fastapi_app, "/api/v1/admin/dashboard/resumen", token)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["errores"] == []
    top = body["top_sucursales"]
    assert len(top) == 2
    assert top[0]["uuid_sucursal"] == str(b)
    assert float(top[0]["monto_total"]) == 1200.0
    assert top[1]["uuid_sucursal"] == str(a)
    assert float(top[1]["monto_total"]) == 500.0

    medios = {item["medio_pago"]: float(item["monto_total"]) for item in body["medios_pago_dia"]}
    assert medios.get("efectivo") == 500.0
    assert medios.get("tarjeta") == 1200.0


__all__ = [
    "test_branch_dashboard_ingresos_monto_total_is_real_sum",
    "test_dashboard_resumen_missing_scope_returns_400",
    "test_dashboard_resumen_top_sucursales_real_aggregation",
    "test_dashboard_resumen_unauthorized_branch_is_a_partial_error",
]
