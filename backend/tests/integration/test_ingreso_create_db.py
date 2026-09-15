"""HU-F1.6 / T3.3 -- DB integration tests for ``POST /operacion/ingresos``.

Runs against a real Postgres (testcontainers via ``PARKOS_DOCKER_TEST=1``,
``pg_engine`` fixture). Verifies R5 (same-TX commit of ingreso + alerta),
V8 (duplicate rechazo), V6 (sub vencida).

Pattern: F1.4 / F1.5 precedent (``tests/integration/test_r22_non_selling_branch.py``).
"""
from __future__ import annotations

import json
import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

from parkos_core.models.L_E.ingreso import Ingreso
from parkos_core.models.V.cantidad_vehiculos_sucursal import (
    CantidadVehiculosSucursal,
)
from parkos_core.models.V.empresa import Empresa
from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _truncate(pg_dsn: str) -> None:
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE prod.alerta, prod.ingreso, prod.salidas, "
            "prod.anulaciones, prod.cantidad_vehiculos_sucursal, "
            "prod.tipos_vehiculo, prod.subscripciones_cliente, "
            "prod.sucursal, prod.empresa CASCADE"
        )
        conn.commit()


async def _seed_branch(pg_engine, *, uuid_sucursal: uuid_lib.UUID) -> None:
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="T3.3 Test SA",
                nit=f"901{empresa_uuid.hex[:6]}",
                mensaje_bienvenida="hi",
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
                nombre=f"Suc T3.3 {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"T{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle T3.3",
                telefono="+57111111",
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


async def _seed_full_chain(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_auto: uuid_lib.UUID,
    cupo_auto: int,
) -> None:
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            TiposVehiculo(
                uuid=uuid_tipo_auto,
                tipo="Auto",
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
    async with Session() as session:
        session.add(
            CantidadVehiculosSucursal(
                uuid=uuid_lib.uuid4(),
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_auto,
                cantidad=cupo_auto,
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


async def _seed_prior(pg_engine, *, placa: str, uuid_sucursal: uuid_lib.UUID,
                     uuid_tipo_auto: uuid_lib.UUID) -> uuid_lib.UUID:
    now = _now_naive()
    ingreso_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Ingreso(
                uuid=ingreso_uuid,
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_auto,
                placa=placa,
                uuid_subscripcion_cliente=None,
                fecha_ingreso=now,
                observaciones=None,
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return ingreso_uuid


async def _refresh_mv(pg_engine) -> None:
    import psycopg

    dsn_sync = str(pg_engine.url).replace("postgresql+asyncpg://", "postgresql://")
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        mv_sql = """
        CREATE MATERIALIZED VIEW IF NOT EXISTS prod.mv_ocupacion_diaria AS
        SELECT i.uuid_sucursal, i.uuid_tipo_vehiculo, count(*) AS activos
        FROM prod.ingreso i
        WHERE i.uuid_tipo_vehiculo IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM prod.salidas s WHERE s.uuid_ingreso = i.uuid)
          AND NOT EXISTS (SELECT 1 FROM prod.anulaciones a WHERE a.uuid_ingreso = i.uuid)
        GROUP BY i.uuid_sucursal, i.uuid_tipo_vehiculo;
        """
        await session.execute(text(mv_sql))
        await session.commit()
    with psycopg.connect(dsn_sync) as conn, conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria")
        conn.commit()


# ---------------------------------------------------------------------------
# T1: ingreso + alerta committed in same TX (R5)
# ---------------------------------------------------------------------------


async def test_insert_ingreso_con_alerta_capacidad_agotada_same_tx(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """R5 verification: bypass cup fills + alerta INSERT share the commit."""
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()

    await _seed_branch(pg_engine, uuid_sucursal=branch)
    await _seed_full_chain(
        pg_engine, uuid_sucursal=branch, uuid_tipo_auto=tipo_auto, cupo_auto=1
    )
    await _seed_prior(
        pg_engine,
        placa="PRIOR01",
        uuid_sucursal=branch,
        uuid_tipo_auto=tipo_auto,
    )
    await _refresh_mv(pg_engine)

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    motivo = "cliente con cita medica urgente 2026-09-14"
    resp = await client.post(
        "/api/v1/operacion/ingresos",
        json={
            "placa": "ABC123",
            "forzado": True,
            "observaciones": f"[FORZADO: {motivo}]",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch),
        },
    )
    assert resp.status_code == 201, f"got {resp.status_code}: {resp.text}"

    import psycopg

    dsn = str(pg_engine.url).replace("postgresql+asyncpg://", "postgresql://")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM prod.ingreso WHERE uuid_sucursal = %s",
            (str(branch),),
        )
        ingreso_count = cur.fetchone()[0]
        cur.execute(
            "SELECT tipo_alerta, datos_nuevos FROM prod.alerta "
            "WHERE uuid_sucursal = %s AND tipo_alerta = 'capacidad_agotada_forzado'",
            (str(branch),),
        )
        alerta_row = cur.fetchone()
    assert ingreso_count == 2, "ingreso INSERT must succeed despite cup agotado"
    assert alerta_row is not None, "alerta INSERT must share the same commit"
    payload = alerta_row[1]
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert payload["motivo"] == motivo


# ---------------------------------------------------------------------------
# T2: V8 duplicate rechazo (REQ-OPS-040)
# ---------------------------------------------------------------------------


async def test_duplicado_activo_rechazado_con_uuid_ingreso_existente(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """V8: prior ingreso activo -> 409 with the prior UUID."""
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()

    await _seed_branch(pg_engine, uuid_sucursal=branch)
    await _seed_full_chain(
        pg_engine, uuid_sucursal=branch, uuid_tipo_auto=tipo_auto, cupo_auto=50
    )
    prior = await _seed_prior(
        pg_engine,
        placa="ABC123",
        uuid_sucursal=branch,
        uuid_tipo_auto=tipo_auto,
    )

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    resp = await client.post(
        "/api/v1/operacion/ingresos",
        json={"placa": "ABC123"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch),
        },
    )
    assert resp.status_code == 409
    body = resp.json()
    detail = body.get("detail", body)
    assert detail["error"] == "ingreso_activo_existente"
    assert detail["uuid_ingreso_existente"] == str(prior)


# ---------------------------------------------------------------------------
# T3: V6 sub vencida returns 422 (REQ-OPS-039)
# ---------------------------------------------------------------------------


async def test_subscripcion_vencida_returns_422_sin_forzado(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """V6: fecha_vencimiento < today + forzado=False -> 422."""
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()
    sub = uuid_lib.uuid4()

    await _seed_branch(pg_engine, uuid_sucursal=branch)
    await _seed_full_chain(
        pg_engine, uuid_sucursal=branch, uuid_tipo_auto=tipo_auto, cupo_auto=50
    )

    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            SubscripcionesCliente(
                uuid=sub,
                uuid_cliente=uuid_lib.uuid4(),
                uuid_sucursal=branch,
                uuid_tipo_subscripcion=uuid_lib.uuid4(),
                fecha_inicio_cobertura=now.date() - timedelta(days=60),
                fecha_vencimiento=now.date() - timedelta(days=1),  # past
                created_at=now,
                created_by=uuid_lib.uuid4(),
                vigente_desde=now - timedelta(days=60),
                vigente_hasta=None,
                estado="activo",
                sync_status="pendiente",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    resp = await client.post(
        "/api/v1/operacion/ingresos",
        json={"placa": "ABC123", "uuid_subscripcion_cliente": str(sub)},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch),
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    detail = body.get("detail", body)
    assert detail["error"] == "subscripcion_inactiva_o_vencida"


__all__ = [
    "test_duplicado_activo_rechazado_con_uuid_ingreso_existente",
    "test_insert_ingreso_con_alerta_capacidad_agotada_same_tx",
    "test_subscripcion_vencida_returns_422_sin_forzado",
]
