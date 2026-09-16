"""HU-F1.6 / REQ-OPS-034..041 -- HTTP unit tests for ``POST /operacion/ingresos``.

Pattern: mirrors the F1.5 / F1.8 / F1.4 precedents in
``tests/unit/test_operacion_ocupacion.py`` -- real ``pg_engine`` plus
an ``httpx.AsyncClient`` bound via ``ASGITransport``. 8 parametrized
scenarios from ``design.md §9 File 1``.
"""
from __future__ import annotations

import json
import uuid as uuid_lib
from datetime import UTC, datetime

import pytest
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

pytestmark = pytest.mark.parametrize("app", ["sucursal"], indirect=True)


# ---------------------------------------------------------------------------
# Fixture-like helpers (per-scenario seeding; shared helper API with the F1.5
# test_operacion_ocupacion pattern).
# ---------------------------------------------------------------------------

def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _truncate_ingreso_tables(pg_dsn: str) -> None:
    """TRUNCATE every table the F1.6 chain reads/writes."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE prod.alerta, prod.ingreso, prod.salidas, "
            "prod.anulaciones, prod.cantidad_vehiculos_sucursal, "
            "prod.tipos_vehiculo, prod.subscripciones_cliente, "
            "prod.sucursal, prod.empresa CASCADE"
        )
        conn.commit()


async def _seed_sucursal(pg_engine, *, uuid_sucursal: uuid_lib.UUID) -> None:
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="F1.6 Test SA",
                nit=f"900{empresa_uuid.hex[:6]}",
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
                nombre=f"Sucursal F1.6 {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"F{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle F1.6 1",
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


async def _seed_tipos_y_cupo(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_auto: uuid_lib.UUID,
    uuid_tipo_moto: uuid_lib.UUID,
    cupo_auto: int = 50,
    cupo_moto: int = 20,
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
        session.add(
            TiposVehiculo(
                uuid=uuid_tipo_moto,
                tipo="Moto",
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
        session.add(
            CantidadVehiculosSucursal(
                uuid=uuid_lib.uuid4(),
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_moto,
                cantidad=cupo_moto,
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


async def _seed_prior_ingreso(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    placa: str,
) -> uuid_lib.UUID:
    now = _now_naive()
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


async def _seed_subscripcion(
    pg_engine,
    *,
    uuid_subscripcion: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    fecha_vencimiento=None,
    estado: str = "activo",
) -> None:
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            SubscripcionesCliente(
                uuid=uuid_subscripcion,
                uuid_cliente=uuid_lib.uuid4(),
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_subscripcion=uuid_lib.uuid4(),
                fecha_inicio_cobertura=now.date(),
                fecha_vencimiento=fecha_vencimiento,
                created_at=now,
                created_by=uuid_lib.uuid4(),
                vigente_desde=now,
                vigente_hasta=None,
                estado=estado,
                sync_status="pendiente",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()


async def _ensure_mv_exists(pg_engine) -> None:
    import psycopg

    dsn_sync = str(pg_engine.url).replace("postgresql+asyncpg://", "postgresql://")
    sql = """
    CREATE MATERIALIZED VIEW IF NOT EXISTS prod.mv_ocupacion_diaria AS
    SELECT i.uuid_sucursal, i.uuid_tipo_vehiculo, count(*) AS activos
    FROM prod.ingreso i
    WHERE i.uuid_tipo_vehiculo IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM prod.salidas s WHERE s.uuid_ingreso = i.uuid)
      AND NOT EXISTS (
        SELECT 1 FROM prod.anulaciones a
        WHERE a.uuid_ingreso = i.uuid
          AND a.estado = 'ejecutada'
          AND a.tipo_anulable IN ('ingreso', 'salida')
      )
    GROUP BY i.uuid_sucursal, i.uuid_tipo_vehiculo;
    """
    with psycopg.connect(dsn_sync) as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()


async def _refresh_mv(pg_engine) -> None:
    await _ensure_mv_exists(pg_engine)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await session.execute(text("REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria"))
        await session.commit()


# ---------------------------------------------------------------------------
# Tests (8 scenarios from design §9 File 1).
# ---------------------------------------------------------------------------


async def test_t1_rotacion_happy_path_returns_201(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """T1: ``{"placa": "ABC123"}`` -> 201 ``IngresoReadForzado{tipo_entrada: "ROTACION"}``."""
    await _truncate_ingreso_tables(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()

    await _seed_sucursal(pg_engine, uuid_sucursal=branch)
    await _seed_tipos_y_cupo(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_auto=tipo_auto,
        uuid_tipo_moto=uuid_lib.uuid4(),
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
    assert resp.status_code == 201, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["tipo_entrada"] == "ROTACION"
    assert body["forzado_en_creacion"] is False
    assert body["motivo_forzado"] is None
    assert body["placa"] == "ABC123"
    assert body["uuid_sucursal"] == str(branch)


async def test_t2_placa_lowercase_rechazada_con_422(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """T2: ``{"placa": "abc123"}`` -> 422 ``placa_formato_invalido``."""
    await _truncate_ingreso_tables(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()

    await _seed_sucursal(pg_engine, uuid_sucursal=branch)
    await _seed_tipos_y_cupo(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_auto=tipo_auto,
        uuid_tipo_moto=uuid_lib.uuid4(),
    )

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    resp = await client.post(
        "/api/v1/operacion/ingresos",
        json={"placa": "abc123"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch),
        },
    )
    assert resp.status_code == 422, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    detail = body.get("detail", body)
    assert detail["error"] == "placa_formato_invalido"
    assert "ABC123" in detail["formatos_aceptados"]


async def test_t3_subscripcion_vigente_retorna_mensualidad(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """T3: ``subscripcion vigente`` -> 201 ``tipo_entrada == "MENSUALIDAD"``."""
    from datetime import timedelta

    await _truncate_ingreso_tables(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()
    sub = uuid_lib.uuid4()

    await _seed_sucursal(pg_engine, uuid_sucursal=branch)
    await _seed_tipos_y_cupo(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_auto=tipo_auto,
        uuid_tipo_moto=uuid_lib.uuid4(),
    )
    await _seed_subscripcion(
        pg_engine,
        uuid_subscripcion=sub,
        uuid_sucursal=branch,
        fecha_vencimiento=datetime.now(UTC).date() + timedelta(days=30),
    )

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    resp = await client.post(
        "/api/v1/operacion/ingresos",
        json={"placa": "ABC123", "uuid_subscripcion_cliente": str(sub)},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch),
        },
    )
    assert resp.status_code == 201, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["tipo_entrada"] == "MENSUALIDAD"


async def test_t4_sin_subscripcion_es_rotacion(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """T4: ``{"placa": "ABC123"}`` (sin sub) -> 201 ``tipo_entrada == "ROTACION"``."""
    await _truncate_ingreso_tables(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()

    await _seed_sucursal(pg_engine, uuid_sucursal=branch)
    await _seed_tipos_y_cupo(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_auto=tipo_auto,
        uuid_tipo_moto=uuid_lib.uuid4(),
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
    assert resp.status_code == 201
    body = resp.json()
    assert body["tipo_entrada"] == "ROTACION"


async def test_t5_cupo_agotado_sin_forzado_rechazado_422(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """T5: cup filled + sin forzado -> 422 ``motivo_forzado_requerido``."""
    await _truncate_ingreso_tables(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()

    await _seed_sucursal(pg_engine, uuid_sucursal=branch)
    await _seed_tipos_y_cupo(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_auto=tipo_auto,
        uuid_tipo_moto=uuid_lib.uuid4(),
        cupo_auto=1,
    )
    await _seed_prior_ingreso(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_vehiculo=tipo_auto,
        placa="OTHER999",
    )
    await _refresh_mv(pg_engine)

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    resp = await client.post(
        "/api/v1/operacion/ingresos",
        json={"placa": "ABC123"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch),
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    detail = body.get("detail", body)
    assert detail["error"] == "motivo_forzado_requerido"
    assert detail["cupo_maximo"] == 1
    assert detail["activos"] == 1


async def test_t6_cupo_agotado_con_forzado_inserta_ingreso_y_alerta(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """T6: cup filled + prefix valido -> 201 + alerta ``capacidad_agotada_forzado``."""
    await _truncate_ingreso_tables(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()

    await _seed_sucursal(pg_engine, uuid_sucursal=branch)
    await _seed_tipos_y_cupo(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_auto=tipo_auto,
        uuid_tipo_moto=uuid_lib.uuid4(),
        cupo_auto=1,
    )
    await _seed_prior_ingreso(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_vehiculo=tipo_auto,
        placa="OTHER999",
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
    body = resp.json()
    assert body["forzado_en_creacion"] is True
    assert body["motivo_forzado"] == motivo

    # Verify the alerta row + jsonb payload (R5 same-TX commit).
    import psycopg

    dsn = str(pg_engine.url).replace("postgresql+asyncpg://", "postgresql://")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT tipo_alerta, datos_nuevos FROM prod.alerta "
            "WHERE uuid_sucursal = %s AND tipo_alerta = 'capacidad_agotada_forzado'",
            (str(branch),),
        )
        row = cur.fetchone()
    assert row is not None, "alerta INSERT must happen in same TX as ingreso"
    payload = row[1]
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert payload["motivo"] == motivo
    assert payload["uuid_ingreso"] == body["uuid"]


async def test_t7_placa_duplicada_activa_returns_409(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """T7: prior ingreso activo con misma placa -> 409 ``ingreso_activo_existente``."""
    await _truncate_ingreso_tables(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()

    await _seed_sucursal(pg_engine, uuid_sucursal=branch)
    await _seed_tipos_y_cupo(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_auto=tipo_auto,
        uuid_tipo_moto=uuid_lib.uuid4(),
    )
    prior_uuid = await _seed_prior_ingreso(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_vehiculo=tipo_auto,
        placa="ABC123",
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
    assert resp.status_code == 409, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    detail = body.get("detail", body)
    assert detail["error"] == "ingreso_activo_existente"
    assert detail["uuid_ingreso_existente"] == str(prior_uuid)


async def test_t8_placa_invalida_no_llega_subscripcion_inactiva(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """T8: placa invalida con sub vencida -> 422 ``placa_formato_invalido``
    (locks V5-before-V6 order; never ``subscripcion_inactiva_o_vencida``)."""
    from datetime import timedelta

    await _truncate_ingreso_tables(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()
    sub = uuid_lib.uuid4()

    await _seed_sucursal(pg_engine, uuid_sucursal=branch)
    await _seed_tipos_y_cupo(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_auto=tipo_auto,
        uuid_tipo_moto=uuid_lib.uuid4(),
    )
    await _seed_subscripcion(
        pg_engine,
        uuid_subscripcion=sub,
        uuid_sucursal=branch,
        fecha_vencimiento=datetime.now(UTC).date() - timedelta(days=1),
    )

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    resp = await client.post(
        "/api/v1/operacion/ingresos",
        json={"placa": "abc123", "uuid_subscripcion_cliente": str(sub)},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch),
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    detail = body.get("detail", body)
    assert detail["error"] == "placa_formato_invalido", (
        f"placa_formato_invalido must precede subscripcion_inactiva_o_vencida; "
        f"got {detail!r}"
    )


__all__ = [
    "test_t1_rotacion_happy_path_returns_201",
    "test_t2_placa_lowercase_rechazada_con_422",
    "test_t3_subscripcion_vigente_retorna_mensualidad",
    "test_t4_sin_subscripcion_es_rotacion",
    "test_t5_cupo_agotado_sin_forzado_rechazado_422",
    "test_t6_cupo_agotado_con_forzado_inserta_ingreso_y_alerta",
    "test_t7_placa_duplicada_activa_returns_409",
    "test_t8_placa_invalida_no_llega_subscripcion_inactiva",
]
