"""H6 -- a plate that exited through its subscription can be re-entered.

The MENSUALIDAD salida writes the same append-only ``prod.salidas`` row as a
rotation exit, so V8 (``existe_ingreso_activo``) and the ``?activo=true``
listing must treat the ingreso as closed. These tests drive the real
``POST /operacion/salidas`` + ``POST /operacion/ingresos`` chain against
Postgres (``TEST_PG_IMAGE=parkos-postgres:16-pgpartman`` for the testcontainer).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import timedelta

# Sibling helpers (tests/integration has no package; pytest's rootdir import
# mode puts this directory on sys.path).
from test_calcular_cotizacion_db import (
    _now_naive,
    _seed_minimal_happy_path,
    _seed_two_plate_subscription,
)

from parkos_core.models.L_E.ingreso import Ingreso
from parkos_core.models.V.cantidad_vehiculos_sucursal import (
    CantidadVehiculosSucursal,
)
from sqlalchemy.ext.asyncio import async_sessionmaker


async def _truncate(pg_dsn: str) -> None:
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE prod.alerta, prod.salidas, prod.ingreso, "
            "prod.anulaciones, prod.tarifas_sucursal, "
            "prod.cantidad_vehiculos_sucursal, prod.tipo_tarifa, "
            "prod.tipos_vehiculo, prod.subscripcion_vehiculos, "
            "prod.subscripciones_cliente, prod.vehiculos, prod.impuestos, "
            "prod.sucursal, prod.empresa CASCADE"
        )
        conn.commit()


async def test_salida_mensualidad_permite_reingreso_misma_placa(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, pg_dsn
) -> None:
    await _truncate(pg_dsn)

    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()
    placa = "HSM123"

    # empresa/sucursal/tipo/tarifa/IVA (+ a throwaway no-placa ingreso).
    await _seed_minimal_happy_path(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_vehiculo=tipo_auto,
        uuid_tipo_tarifa=uuid_lib.uuid4(),
        minutos_en_estacionamiento=5,
    )
    subscripcion, _ = await _seed_two_plate_subscription(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_vehiculo=tipo_auto,
        placa_a=placa,
        placa_b="HSM456",
    )

    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE prod.subscripciones_cliente "
            "SET fecha_inicio_cobertura = CURRENT_DATE - 1, "
            "    fecha_vencimiento = CURRENT_DATE + 30 WHERE uuid = %s",
            (str(subscripcion),),
        )
        conn.commit()

    now = _now_naive()
    ingreso_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            CantidadVehiculosSucursal(
                uuid=uuid_lib.uuid4(),
                uuid_sucursal=branch,
                uuid_tipo_vehiculo=tipo_auto,
                cantidad=50,
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
            Ingreso(
                uuid=ingreso_uuid,
                uuid_sucursal=branch,
                placa=placa,
                uuid_tipo_vehiculo=tipo_auto,
                uuid_subscripcion_cliente=None,
                fecha_ingreso=now - timedelta(minutes=20),
                observaciones=None,
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch),
    }

    salida = await client.post(
        "/api/v1/operacion/salidas",
        json={"uuid_ingreso": str(ingreso_uuid), "placa": placa},
        headers=headers,
    )
    assert salida.status_code == 201, f"{salida.status_code}: {salida.text}"
    assert salida.json()["tipo_salida"] == "MENSUALIDAD", salida.text

    activos = await client.get(
        "/api/v1/operacion/ingresos",
        params={"placa": placa, "activo": "true"},
        headers=headers,
    )
    assert activos.status_code == 200, activos.text
    assert activos.json() == [], (
        f"plate with a MENSUALIDAD salida must not be active: {activos.json()!r}"
    )

    reingreso = await client.post(
        "/api/v1/operacion/ingresos",
        json={"placa": placa, "uuid_subscripcion_cliente": str(subscripcion)},
        headers=headers,
    )
    assert reingreso.status_code == 201, (
        f"re-ingreso after MENSUALIDAD salida must succeed: "
        f"{reingreso.status_code}: {reingreso.text}"
    )
