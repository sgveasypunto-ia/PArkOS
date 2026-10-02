"""Integration tests for HU-F17.3 additions to ``api/v1/reporteria.py``.

Real Postgres + real handlers, same harness shape as
``test_reporteria_hu_f17_2.py`` (this file duplicates its seed helpers
rather than importing them -- same convention that file documents).

Three surfaces under test, one per "resolucion de columna" this HU adds:

- ``GET /admin/reporteria/facturas`` -- ``numero_completo`` (outer join to
  ``factura_electronica``, ``None`` when absent), ``iva`` (correlated
  ``SUM(factura_impuestos.valor)``), and ``estado`` (``EXISTS``
  anulaciones ejecutada on the factura's ``uuid_salida`` -> ``anulada``,
  else ``vigente``).
- ``GET /admin/reporteria/fe`` -- raw ``v_factura_electronica_acuse.
  estado`` (BR1), proving the real (8-value) domain is wider than
  plan.md's assumed 4 values, plus the 422 ``invalid_estado`` guard.
- ``GET /admin/reporteria/pagos`` -- pagos netted (pago - reverso) and
  grouped by ``(fecha, medio_pago)`` (BR2); a reverso is never filtered
  out, only subtracted.

Plus one 422 ``rango_fecha_invalido`` check (shared validation, HU-F17.2
precedent).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, datetime
from decimal import Decimal
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
from parkos_core.models.A.factura_impuestos import FacturaImpuestos  # noqa: E402
from parkos_core.models.A.factura_pagos import FacturaPagos  # noqa: E402
from parkos_core.models.L_E.factura_electronica import FacturaElectronica  # noqa: E402
from parkos_core.models.L_E.facturas import Facturas  # noqa: E402
from parkos_core.models.L_W.anulaciones import Anulaciones  # noqa: E402
from parkos_core.models.L_W.envio_dian import EnvioDian  # noqa: E402
from parkos_core.models.V.empresa import Empresa  # noqa: E402
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
                nombre="HU-F17.3 SA",
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
                nombre=f"Suc F17.3 {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"H{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle HU-F17.3",
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
                nombre="F17.3",
                apellido="Admin",
                cedula=f"A{actor_uuid.hex[:10]}",
                email=f"f17-3-{actor_uuid.hex[:8]}@parkos.local",
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


async def _seed_factura(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    created_at: datetime,
    subtotal: Decimal,
    descuento: Decimal,
    total: Decimal,
    uuid_salida: uuid_lib.UUID | None = None,
) -> uuid_lib.UUID:
    factura_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Facturas(
                uuid=factura_uuid,
                fecha_retencion_hasta=created_at.date(),
                uuid_sucursal=uuid_sucursal,
                subtotal=subtotal,
                descuento=descuento,
                total=total,
                uuid_ingreso=None,
                uuid_salida=uuid_salida,
                uuid_subscripcion_cliente=None,
                created_at=created_at,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return factura_uuid


async def _seed_anulacion_salida(
    pg_engine, *, uuid_sucursal: uuid_lib.UUID, uuid_salida: uuid_lib.UUID
) -> None:
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Anulaciones(
                uuid=uuid_lib.uuid4(),
                fecha_retencion_hasta=now.date(),
                uuid_sucursal=uuid_sucursal,
                tipo_anulable="salida",
                uuid_ingreso=None,
                uuid_salida=uuid_salida,
                uuid_usuario=None,
                motivo="test HU-F17.3",
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


async def _seed_factura_impuesto(
    pg_engine, *, uuid_sucursal: uuid_lib.UUID, uuid_factura: uuid_lib.UUID, valor: Decimal
) -> None:
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            FacturaImpuestos(
                uuid_sucursal=uuid_sucursal,
                uuid_factura=uuid_factura,
                uuid_impuesto=None,
                base_calculo=Decimal("100000"),
                porcentaje_aplicado=Decimal("19"),
                valor=valor,
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()


async def _seed_factura_electronica(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_factura: uuid_lib.UUID,
    prefijo: str,
    consecutivo: int,
    created_at: datetime,
    uuid_cliente: uuid_lib.UUID | None = None,
) -> uuid_lib.UUID:
    fe_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            FacturaElectronica(
                uuid=fe_uuid,
                uuid_sucursal=uuid_sucursal,
                uuid_factura=uuid_factura,
                uuid_cliente=uuid_cliente,
                uuid_resolucion_facturacion=None,
                prefijo=prefijo,
                consecutivo=consecutivo,
                descuento=None,
                created_at=created_at,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return fe_uuid


async def _seed_envio_dian(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_factura_electronica: uuid_lib.UUID,
    estado: str,
    cufe: str | None,
    timestamp_evento: datetime,
) -> None:
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            EnvioDian(
                uuid_sucursal=uuid_sucursal,
                uuid_factura_electronica=uuid_factura_electronica,
                uuid_resolucion_facturacion=None,
                payload=None,
                respuesta_proveedor=None,
                cufe=cufe,
                uuid_envio_padre=None,
                timestamp_evento=timestamp_evento,
                vigente_desde=now,
                vigente_hasta=None,
                estado=estado,
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()


async def _seed_factura_pago(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_factura: uuid_lib.UUID,
    medio_pago: str,
    valor: Decimal,
    tipo_movimiento: str,
    created_at: datetime,
    uuid_pago_revertido: uuid_lib.UUID | None = None,
) -> uuid_lib.UUID:
    pago_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            FacturaPagos(
                uuid=pago_uuid,
                fecha_retencion_hasta=created_at.date(),
                uuid_sucursal=uuid_sucursal,
                uuid_factura=uuid_factura,
                uuid_sesion=None,
                medio_pago=medio_pago,
                valor=valor,
                referencia=None,
                tipo_movimiento=tipo_movimiento,
                uuid_pago_revertido=uuid_pago_revertido,
                timestamp_evento=created_at,
                created_at=created_at,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return pago_uuid


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
            "prod.envio_dian, prod.factura_pagos, prod.factura_impuestos, "
            "prod.factura_otros_cobros, prod.factura_detalle, prod.facturas, "
            "prod.revocacion_factura, prod.factura_electronica, "
            "prod.usuarios_sucursal, prod.usuarios, prod.tipos_vehiculo, "
            "prod.cantidad_vehiculos_sucursal, prod.tarifas_sucursal, "
            "prod.subscripcion_vehiculos, prod.subscripciones_cliente, prod.vehiculos, "
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
async def test_facturas_resuelve_numero_completo_iva_y_estado(pg_engine, pg_dsn) -> None:
    """``GET /admin/reporteria/facturas`` resolves the 3 non-physical columns."""
    _truncate(pg_dsn)
    uuid_sucursal = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=uuid_sucursal)
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[uuid_sucursal])

    today = datetime.now(UTC).replace(tzinfo=None)

    # Factura 1: has FE (numero_completo resolves), no anulaciones -> vigente.
    factura_con_fe = await _seed_factura(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        created_at=today,
        subtotal=Decimal("100000"),
        descuento=Decimal("0"),
        total=Decimal("119000"),
    )
    await _seed_factura_electronica(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        uuid_factura=factura_con_fe,
        prefijo="SETP",
        consecutivo=42,
        created_at=today,
    )
    await _seed_factura_impuesto(
        pg_engine, uuid_sucursal=uuid_sucursal, uuid_factura=factura_con_fe, valor=Decimal("19000")
    )

    # Factura 2: no FE (numero_completo is None), anulada via its salida.
    salida_uuid = uuid_lib.uuid4()
    factura_anulada = await _seed_factura(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        created_at=today,
        subtotal=Decimal("50000"),
        descuento=Decimal("0"),
        total=Decimal("59500"),
        uuid_salida=salida_uuid,
    )
    await _seed_anulacion_salida(pg_engine, uuid_sucursal=uuid_sucursal, uuid_salida=salida_uuid)

    fastapi_app, token = _setup_app_and_token(
        pg_engine, admin_actor=admin_actor, permitidas=[uuid_sucursal]
    )
    resp = await _get(
        fastapi_app,
        f"/api/v1/admin/reporteria/facturas?uuid_sucursal={uuid_sucursal}"
        f"&desde={today.date().isoformat()}&hasta={today.date().isoformat()}",
        token=token,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    by_uuid = {item["uuid"]: item for item in body["items"]}

    con_fe = by_uuid[str(factura_con_fe)]
    assert con_fe["numero_completo"] == "SETP42"
    assert con_fe["iva"] == pytest.approx(19000.0)
    assert con_fe["estado"] == "vigente"

    anulada = by_uuid[str(factura_anulada)]
    assert anulada["numero_completo"] is None
    assert anulada["iva"] == pytest.approx(0.0)
    assert anulada["estado"] == "anulada"


@pytest.mark.asyncio
async def test_fe_expone_estado_dian_crudo_y_valida_dominio(pg_engine, pg_dsn) -> None:
    """``GET /admin/reporteria/fe`` surfaces the RAW acuse estado (BR1)."""
    _truncate(pg_dsn)
    uuid_sucursal = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=uuid_sucursal)
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[uuid_sucursal])

    today = datetime.now(UTC).replace(tzinfo=None)
    factura_uuid = await _seed_factura(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        created_at=today,
        subtotal=Decimal("10000"),
        descuento=Decimal("0"),
        total=Decimal("11900"),
    )
    fe_uuid = await _seed_factura_electronica(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        uuid_factura=factura_uuid,
        prefijo="SETP",
        consecutivo=7,
        created_at=today,
    )
    # Two envio_dian rows (retry chain) -- the view resolves the LATEST by
    # timestamp_evento. "aceptado" is NOT in plan.md's assumed 4-value
    # domain (pendiente|enviado|aceptado|rechazado is actually
    # FacturaDisplayFE's simplified projection) -- it IS a real
    # dispatcher.ESTADO_* value, confirming the wider real domain.
    await _seed_envio_dian(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        uuid_factura_electronica=fe_uuid,
        estado="pendiente",
        cufe=None,
        timestamp_evento=today.replace(hour=0, minute=0, second=0, microsecond=0),
    )
    await _seed_envio_dian(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        uuid_factura_electronica=fe_uuid,
        estado="aceptado",
        cufe="CUFE-TEST-123",
        timestamp_evento=today,
    )

    fastapi_app, token = _setup_app_and_token(
        pg_engine, admin_actor=admin_actor, permitidas=[uuid_sucursal]
    )

    resp = await _get(fastapi_app, "/api/v1/admin/reporteria/fe", token=token)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["uuid"] == str(fe_uuid)
    assert item["numero_completo"] == "SETP7"
    assert item["estado_dian"] == "aceptado"
    assert item["cufe"] == "CUFE-TEST-123"

    # Filtering by the real (latest) estado works.
    resp_filtered = await _get(
        fastapi_app, "/api/v1/admin/reporteria/fe?estado=aceptado", token=token
    )
    assert resp_filtered.status_code == 200
    assert len(resp_filtered.json()["items"]) == 1

    resp_empty = await _get(
        fastapi_app, "/api/v1/admin/reporteria/fe?estado=rechazado", token=token
    )
    assert resp_empty.status_code == 200
    assert resp_empty.json()["items"] == []

    # A value OUTSIDE the real 8-value domain -> 422 invalid_estado, NOT
    # plan.md's assumed 4-value domain (so "enviado" -- a REAL state
    # machine value -- must be accepted, not rejected).
    resp_422 = await _get(
        fastapi_app, "/api/v1/admin/reporteria/fe?estado=bogus_estado", token=token
    )
    assert resp_422.status_code == 422
    assert resp_422.json()["detail"]["error"] == "invalid_estado"

    resp_enviado = await _get(
        fastapi_app, "/api/v1/admin/reporteria/fe?estado=enviado", token=token
    )
    assert resp_enviado.status_code == 200


@pytest.mark.asyncio
async def test_pagos_netea_reverso_contra_pago_agrupado_por_medio(pg_engine, pg_dsn) -> None:
    """``GET /admin/reporteria/pagos`` nets reverso against pago (BR2)."""
    _truncate(pg_dsn)
    uuid_sucursal = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=uuid_sucursal)
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[uuid_sucursal])

    today = datetime.now(UTC).replace(tzinfo=None)
    factura_uuid = await _seed_factura(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        created_at=today,
        subtotal=Decimal("100000"),
        descuento=Decimal("0"),
        total=Decimal("100000"),
    )
    pago_efectivo = await _seed_factura_pago(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        uuid_factura=factura_uuid,
        medio_pago="efectivo",
        valor=Decimal("100000"),
        tipo_movimiento="pago",
        created_at=today,
    )
    # Reverso of part of the efectivo payment -- NEVER filtered out, only
    # subtracted (BR2).
    await _seed_factura_pago(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        uuid_factura=factura_uuid,
        medio_pago="efectivo",
        valor=Decimal("30000"),
        tipo_movimiento="reverso",
        created_at=today,
        uuid_pago_revertido=pago_efectivo,
    )
    # An unrelated datafono payment the same day -- its own bucket.
    await _seed_factura_pago(
        pg_engine,
        uuid_sucursal=uuid_sucursal,
        uuid_factura=factura_uuid,
        medio_pago="datafono",
        valor=Decimal("20000"),
        tipo_movimiento="pago",
        created_at=today,
    )

    fastapi_app, token = _setup_app_and_token(
        pg_engine, admin_actor=admin_actor, permitidas=[uuid_sucursal]
    )
    resp = await _get(
        fastapi_app,
        f"/api/v1/admin/reporteria/pagos?uuid_sucursal={uuid_sucursal}"
        f"&desde={today.date().isoformat()}&hasta={today.date().isoformat()}",
        token=token,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    by_medio = {item["medio_pago"]: item["monto_neto"] for item in body["items"]}
    assert by_medio["efectivo"] == pytest.approx(70000.0)  # 100000 - 30000
    assert by_medio["datafono"] == pytest.approx(20000.0)


@pytest.mark.asyncio
async def test_facturas_rango_fecha_invalido_422(pg_engine, pg_dsn) -> None:
    """``desde > hasta`` -> 422 ``rango_fecha_invalido`` (HU-F17.2 precedent)."""
    _truncate(pg_dsn)
    uuid_sucursal = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=uuid_sucursal)
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[uuid_sucursal])

    fastapi_app, token = _setup_app_and_token(
        pg_engine, admin_actor=admin_actor, permitidas=[uuid_sucursal]
    )
    resp = await _get(
        fastapi_app,
        f"/api/v1/admin/reporteria/facturas?uuid_sucursal={uuid_sucursal}"
        "&desde=2026-02-01&hasta=2026-01-01",
        token=token,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "rango_fecha_invalido"


@pytest.mark.asyncio
async def test_facturas_uuid_cliente_lista_cruzando_sucursales(pg_engine, pg_dsn) -> None:
    """HU-F20.1: ``uuid_cliente`` alone lists that cliente's facturas across
    EVERY branch the admin can see -- proving the read is deliberately
    cross-branch, not narrowed to a single ``uuid_sucursal`` (the filter is
    ``FacturaElectronica.uuid_cliente``; ``Facturas`` itself has no cliente
    column). A factura belonging to a DIFFERENT cliente in one of the same
    branches must not leak into the result.
    """
    _truncate(pg_dsn)
    uuid_sucursal_a = uuid_lib.uuid4()
    uuid_sucursal_b = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=uuid_sucursal_a)
    await _seed_sucursal(pg_engine, uuid_sucursal=uuid_sucursal_b)
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(
        pg_engine, actor_uuid=admin_actor, sucursales=[uuid_sucursal_a, uuid_sucursal_b]
    )

    today = datetime.now(UTC).replace(tzinfo=None)
    cliente_uuid = uuid_lib.uuid4()
    otro_cliente_uuid = uuid_lib.uuid4()

    # Factura 1: branch A, FE tied to the target cliente.
    factura_a = await _seed_factura(
        pg_engine,
        uuid_sucursal=uuid_sucursal_a,
        created_at=today,
        subtotal=Decimal("100000"),
        descuento=Decimal("0"),
        total=Decimal("119000"),
    )
    await _seed_factura_electronica(
        pg_engine,
        uuid_sucursal=uuid_sucursal_a,
        uuid_factura=factura_a,
        prefijo="SETA",
        consecutivo=1,
        created_at=today,
        uuid_cliente=cliente_uuid,
    )

    # Factura 2: branch B, ALSO tied to the target cliente -- the whole
    # point of HU-F20.1 is that this row must show up too.
    factura_b = await _seed_factura(
        pg_engine,
        uuid_sucursal=uuid_sucursal_b,
        created_at=today,
        subtotal=Decimal("50000"),
        descuento=Decimal("0"),
        total=Decimal("59500"),
    )
    await _seed_factura_electronica(
        pg_engine,
        uuid_sucursal=uuid_sucursal_b,
        uuid_factura=factura_b,
        prefijo="SETB",
        consecutivo=2,
        created_at=today,
        uuid_cliente=cliente_uuid,
    )

    # Factura 3: branch A, tied to a DIFFERENT cliente -- must NOT show up.
    factura_c = await _seed_factura(
        pg_engine,
        uuid_sucursal=uuid_sucursal_a,
        created_at=today,
        subtotal=Decimal("10000"),
        descuento=Decimal("0"),
        total=Decimal("11900"),
    )
    await _seed_factura_electronica(
        pg_engine,
        uuid_sucursal=uuid_sucursal_a,
        uuid_factura=factura_c,
        prefijo="SETC",
        consecutivo=3,
        created_at=today,
        uuid_cliente=otro_cliente_uuid,
    )

    fastapi_app, token = _setup_app_and_token(
        pg_engine, admin_actor=admin_actor, permitidas=[uuid_sucursal_a, uuid_sucursal_b]
    )
    resp = await _get(
        fastapi_app,
        f"/api/v1/admin/reporteria/facturas?uuid_cliente={cliente_uuid}",
        token=token,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Cross-branch mode: no single branch to report at the top level.
    assert body["uuid_sucursal"] is None

    by_uuid = {item["uuid"]: item for item in body["items"]}
    assert set(by_uuid) == {str(factura_a), str(factura_b)}
    assert by_uuid[str(factura_a)]["uuid_sucursal"] == str(uuid_sucursal_a)
    assert by_uuid[str(factura_b)]["uuid_sucursal"] == str(uuid_sucursal_b)


@pytest.mark.asyncio
async def test_facturas_sin_uuid_sucursal_ni_uuid_cliente_422_missing_filter(
    pg_engine, pg_dsn
) -> None:
    """HU-F20.1: neither filter given -> 422 ``missing_filter``."""
    _truncate(pg_dsn)
    uuid_sucursal = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, uuid_sucursal=uuid_sucursal)
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[uuid_sucursal])

    fastapi_app, token = _setup_app_and_token(
        pg_engine, admin_actor=admin_actor, permitidas=[uuid_sucursal]
    )
    resp = await _get(fastapi_app, "/api/v1/admin/reporteria/facturas", token=token)
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "missing_filter"
