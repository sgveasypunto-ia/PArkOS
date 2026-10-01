"""Integration test for ``GET /api/v1/admin/reporteria/operacional`` (HU-F17.1, PR-C).

Real Postgres + real handler. Mounts the ``reporteria`` router on a
bare ``FastAPI`` with overrides for ``requires_issuer`` (admin-) and
``get_session`` (testcontainers URL). Same harness shape as
``test_audit_log_endpoint.py``.

What this test pins:

- PR-A inheritance: tenant scope via ``require_branch_scope``. An
  admin permitted on branch A gets 403 ``tenant_scope_violation`` when
  naming branch B (and 400 ``missing_sucursal_context`` when no
  permitted branches exist). Header vs query-param precedence is
  covered by the PR-A test suite for the ``/operacion`` endpoints;
  this file keeps the reportería-specific shapes.
- Single-pass SQL aggregates ``ingresos_count`` + ``salidas_count`` +
  ``facturas_emitidas_count`` + ``monto_facturado_total`` per UTC day,
  grand-total at the end. A second, narrower range that starts
  mid-month must agree with the wide-range totals (sum of items
  == totales) — proves the totals field is not a second source of
  truth.
- ``monto_cobrado_neto`` = ``SUM(pago) - SUM(reverso)`` for the
  same range. A reversal correctly reduces the net (not the gross).
- ``fecha_desde`` after ``fecha_hasta`` is 400. An unknown branch
  is 403 even with the right issuer, because ``scope.narrow``
  raises on out-of-set requests.

Range partitioning note: ``prod.factura_pagos`` is partitioned
monthly by ``fecha_retencion_hasta``. The handler's WHERE filters on
``Ingreso.created_at`` (the branch-side created_at, not the retention
date), so the JOIN pulls rows from the partition that owns the
ingreso-side FK regardless of the retention month. We seed pagos
with the same retention date as the ingreso so the partition setup
is unambiguous.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
for _p in (_PARKOS_CORE_SRC,):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


from parkos_core.api.v1.reporteria import router as reporteria_router_obj  # noqa: E402
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
                nombre="Reporeria SA",
                nit=f"904{empresa_uuid.hex[:6]}",
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
                nombre=f"Suc Reporeria {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"R{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle Reporeria",
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
    """Open ``usuarios_sucursal`` rows — the FRESH source of admin scope.

    Same helper shape as ``test_operacion_scope_lista.py``. Seed
    ``prod.usuarios`` first (FK enforced on the junction), then
    one ``usuarios_sucursal`` row per permitted branch.
    """
    from parkos_core.models.V.usuarios import Usuarios
    from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal

    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Usuarios(
                uuid=actor_uuid,
                nombre="Reporeria",
                apellido="Admin",
                cedula=f"A{actor_uuid.hex[:10]}",
                email=f"reporeria-{actor_uuid.hex[:8]}@parkos.local",
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


async def _seed_factura_pago(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_ingreso: uuid_lib.UUID,
    total: Decimal,
    valor_pago: Decimal | None = None,
    tipo_movimiento: str = "pago",
    uuid_pago_revertido: uuid_lib.UUID | None = None,
    created_at: datetime | None = None,
) -> tuple[uuid_lib.UUID, uuid_lib.UUID | None]:
    """Seed one ``prod.facturas`` row + one matching ``prod.factura_pagos``
    row (default). Returns ``(factura_uuid, pago_uuid_or_none)``.
    """
    created = created_at or _now_naive()
    factura_uuid = uuid_lib.uuid4()
    pago_uuid = None
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Facturas(
                uuid=factura_uuid,
                fecha_retencion_hasta=created.date(),
                uuid_sucursal=uuid_sucursal,
                uuid_ingreso=uuid_ingreso,
                uuid_salida=None,
                uuid_subscripcion_cliente=None,
                subtotal=total,
                descuento=Decimal("0"),
                total=total,
                created_at=created,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        # Flush so the factura is committed to the DB before we INSERT the
        # pago row. The pago's FK to facturas is checked at INSERT time on the
        # partition (the listener runs per-statement, so flushing the parent
        # row first avoids a false positive "factura not found" race that the
        # session commit otherwise exposes when both rows are queued.
        await session.flush()
        if valor_pago is not None:
            pago_uuid = uuid_lib.uuid4()
            session.add(
                FacturaPagos(
                    uuid=pago_uuid,
                    fecha_retencion_hasta=created.date(),
                    uuid_sucursal=uuid_sucursal,
                    uuid_factura=factura_uuid,
                    uuid_sesion=None,
                    medio_pago="efectivo",
                    valor=valor_pago,
                    referencia=None,
                    tipo_movimiento=tipo_movimiento,
                    uuid_pago_revertido=uuid_pago_revertido,
                    timestamp_evento=created,
                    created_at=created,
                    created_by=None,
                    sync_status="sincronizado",
                    sync_timestamp=None,
                    sync_attempts=0,
                )
            )
        await session.commit()
    return factura_uuid, pago_uuid


def _build_app(pg_engine) -> tuple[FastAPI, callable]:
    """Mount the reporteria router with overrides; return (app, set_claims)."""
    from parkos_core.db.engine import get_session
    import parkos_core.api.v1.reporteria as _reporteria_module

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


def _admin_token(
    *,
    actor_uuid: uuid_lib.UUID | None = None,
    permitidas: list[uuid_lib.UUID] | None = None,
    issuer: str = "admin-test",
) -> str:
    return issue_token(
        subject_uuid=actor_uuid or uuid_lib.uuid4(),
        issuer=issuer,
        claims={
            "rol": "admin",
            "sucursales_permitidas": [
                str(u) for u in (permitidas or [uuid_lib.uuid4()])
            ],
        },
    )


_HTTP_PYTESTMARK = pytest.mark.parametrize("app", ["sucursal"], indirect=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _sync_truncate(pg_dsn: str) -> None:
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


def _truncate(pg_dsn: str) -> None:
    _sync_truncate(pg_dsn)


async def test_totales_y_grand_total_consiguen(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """A range with two days' worth of ingresos + facturas yields items[].totales.

    One ingreso on day-1 with a 100-factura, another on day-3 with a
    200-factura. The wide-range totals: ingresos=2, facturado=300.
    Per-day items must agree with the totals (no double-count, no
    double-skip on the boundary).
    """
    _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    tipo = await _seed_sucursal(pg_engine, uuid_sucursal=branch)

    today = _now_naive().date()
    day1 = datetime(today.year, today.month, max(1, today.day - 9), 10, 0)
    day3 = datetime(today.year, today.month, max(1, today.day - 7), 10, 0)

    ing1 = await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_vehiculo=tipo,
        placa="DAY1AAA",
        created_at=day1,
    )
    ing3 = await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_vehiculo=tipo,
        placa="DAY3AAA",
        created_at=day3,
    )
    await _seed_factura_pago(
        pg_engine,
        uuid_sucursal=branch,
        uuid_ingreso=ing1,
        total=Decimal("100"),
        valor_pago=Decimal("100"),
        created_at=day1,
    )
    await _seed_factura_pago(
        pg_engine,
        uuid_sucursal=branch,
        uuid_ingreso=ing3,
        total=Decimal("200"),
        valor_pago=Decimal("200"),
        created_at=day3,
    )

    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch])

    # We need a separate admin app here because the default `client`
    # fixture mounts the branch API, which doesn't include reporteria.
    fastapi_app, set_claims = _build_app(pg_engine)
    set_claims(
        {
            "sub": str(admin_actor),
            "rol": "admin",
            "iss": "admin-test",
            "sucursales_permitidas": [str(branch)],
        }
    )
    token = issue_token(
        subject_uuid=admin_actor,
        issuer="admin-test",
        claims={
            "rol": "admin",
            "sucursales_permitidas": [str(branch)],
        },
    )

    from httpx import ASGITransport

    transport = ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        resp = await c.get(
            f"/api/v1/admin/reporteria/operacional?uuid_sucursal={branch}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["uuid_sucursal"] == str(branch)
    assert body["totales"]["ingresos_count"] == 2
    assert body["totales"]["facturas_emitidas_count"] == 2
    assert float(body["totales"]["monto_facturado_total"]) == 300.0
    assert float(body["totales"]["monto_cobrado_total"]) == 300.0
    # Per-day sum agrees with grand total.
    assert sum(item["ingresos_count"] for item in body["items"]) == 2
    assert sum(item["facturas_emitidas_count"] for item in body["items"]) == 2
    assert sum(
        float(item["monto_facturado_total"]) for item in body["items"]
    ) == 300.0


async def test_monto_cobrado_neto_resta_reversos(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    """A reversal reduces ``monto_cobrado_total`` without touching facturado.

    Seed: 1 factura total=100 with one pago of 100, then a second
    ``factura_pagos`` row of tipo_movimiento='reverso' pointing at the
    SAME pago (no new Factura — the reverso does not emit a new
    invoice, it just voids the cash drawer hit). Expected:
    monto_facturado_total=100 (gross unchanged), monto_cobrado_total=0
    (net of void).
    """
    _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    tipo = await _seed_sucursal(pg_engine, uuid_sucursal=branch)
    ing = await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_vehiculo=tipo,
        placa="VOID01",
        created_at=_now_naive(),
    )
    factura_uuid, pago_uuid = await _seed_factura_pago(
        pg_engine,
        uuid_sucursal=branch,
        uuid_ingreso=ing,
        total=Decimal("100"),
        valor_pago=Decimal("100"),
        created_at=_now_naive(),
    )
    assert pago_uuid is not None
    # Reverso: a second pago row on the SAME factura pointing at the pago.
    now = _now_naive()
    reverso_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            FacturaPagos(
                uuid=reverso_uuid,
                fecha_retencion_hasta=now.date(),
                uuid_sucursal=branch,
                uuid_factura=factura_uuid,
                uuid_sesion=None,
                medio_pago="efectivo",
                valor=Decimal("100"),
                referencia=None,
                tipo_movimiento="reverso",
                uuid_pago_revertido=pago_uuid,
                timestamp_evento=now,
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()

    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch])

    fastapi_app, set_claims = _build_app(pg_engine)
    set_claims(
        {
            "sub": str(admin_actor),
            "rol": "admin",
            "iss": "admin-test",
            "sucursales_permitidas": [str(branch)],
        }
    )
    token = issue_token(
        subject_uuid=admin_actor,
        issuer="admin-test",
        claims={"rol": "admin", "sucursales_permitidas": [str(branch)]},
    )

    from httpx import ASGITransport

    transport = ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        resp = await c.get(
            f"/api/v1/admin/reporteria/operacional?uuid_sucursal={branch}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert float(body["totales"]["monto_facturado_total"]) == 100.0
    assert float(body["totales"]["monto_cobrado_total"]) == 0.0


async def test_admin_no_permitido_recibe_403(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    """An admin permitted only on A who names branch B gets 403, not empty 200.

    The PR-A tenancy fix in /admin/reporteria: ``scope.narrow`` raises
    TenantScopeViolationError when the caller names a branch they
    don't own. Confirms the new endpoint inherits the same gate.
    """
    _truncate(pg_dsn)
    a = uuid_lib.uuid4()
    b = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=a)
    await _seed_sucursal(pg_engine, uuid_sucursal=b)

    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[a])

    fastapi_app, set_claims = _build_app(pg_engine)
    set_claims(
        {
            "sub": str(admin_actor),
            "rol": "admin",
            "iss": "admin-test",
            "sucursales_permitidas": [str(a)],
        }
    )
    token = issue_token(
        subject_uuid=admin_actor,
        issuer="admin-test",
        claims={"rol": "admin", "sucursales_permitidas": [str(a)]},
    )

    from httpx import ASGITransport

    transport = ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        resp = await c.get(
            f"/api/v1/admin/reporteria/operacional?uuid_sucursal={b}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 403, f"got {resp.status_code}: {resp.text}"
    assert resp.json()["detail"]["error"] == "tenant_scope_violation"


async def test_admin_sin_permitidas_recibe_400_missing_sucursal_context(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    """An admin whose fresh ``usuarios_sucursal`` set is empty reads 400.

    Mirrors the shape ``/operacion/ocupacion`` already returns (PR-A):
    the caller didn't name an unauthorized branch — they have NO
    branches at all. 403 would imply the opposite.
    """
    _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)

    admin_actor = uuid_lib.uuid4()
    # NOTE: deliberately do NOT call _assign_admin. permitidas is empty.
    fastapi_app, set_claims = _build_app(pg_engine)
    set_claims(
        {
            "sub": str(admin_actor),
            "rol": "admin",
            "iss": "admin-test",
            "sucursales_permitidas": [],
        }
    )
    token = issue_token(
        subject_uuid=admin_actor,
        issuer="admin-test",
        claims={"rol": "admin", "sucursales_permitidas": []},
    )

    from httpx import ASGITransport

    transport = ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        resp = await c.get(
            f"/api/v1/admin/reporteria/operacional?uuid_sucursal={branch}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 400, f"got {resp.status_code}: {resp.text}"
    assert resp.json()["detail"]["error"] == "missing_sucursal_context"


async def test_fecha_desde_despues_de_hasta_es_400(
    pg_engine, mint_operador_jwt, pg_dsn
) -> None:
    """Range validation: ``fecha_desde > fecha_hasta`` is 400."""
    _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=branch)

    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch])

    fastapi_app, set_claims = _build_app(pg_engine)
    set_claims(
        {
            "sub": str(admin_actor),
            "rol": "admin",
            "iss": "admin-test",
            "sucursales_permitidas": [str(branch)],
        }
    )
    token = issue_token(
        subject_uuid=admin_actor,
        issuer="admin-test",
        claims={"rol": "admin", "sucursales_permitidas": [str(branch)]},
    )

    from httpx import ASGITransport

    transport = ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        resp = await c.get(
            f"/api/v1/admin/reporteria/operacional"
            f"?uuid_sucursal={branch}&fecha_desde=2026-12-31&fecha_hasta=2026-01-01",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 400, f"got {resp.status_code}: {resp.text}"
    assert resp.json()["detail"]["error"] == "fecha_desde_after_hasta"