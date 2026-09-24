"""Integration tests for ``GET /operacion/ingresos?activo=true``.

Bug (operador, 2026-09-24): el dashboard de "vehiculos dentro" listaba
vehiculos que ya habian salido -- ``VehiculosDentroList`` (FE) consume
este endpoint sin ningun filtro de estado y el backend nunca implemento
el query param ``activo`` que ``plan.md`` (HU-F6.1, linea 1518/2454) ya
documentaba como parte del contrato.

``activo=true`` debe excluir un ingreso que tiene una salida real (no
anulada) y REINCLUIR un ingreso cuya unica salida fue anulada (HU-F8.1:
el operador cerro el cobro sin pagar -> la salida se anula y el
vehiculo vuelve a estar "adentro"). Misma semantica de exclusion que
``V_INGRESO_ESTADO`` / ``repo/salida.py::buscar_ingreso_activo_por_uuid``.

Pattern: F1.6 precedent (``test_ingreso_create_db.py``).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

from parkos_core.models.A.salidas import Salidas
from parkos_core.models.L_E.ingreso import Ingreso
from parkos_core.models.L_W.anulaciones import Anulaciones
from parkos_core.models.V.cantidad_vehiculos_sucursal import (
    CantidadVehiculosSucursal,
)
from parkos_core.models.V.empresa import Empresa
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from sqlalchemy.ext.asyncio import async_sessionmaker


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _truncate(pg_dsn: str) -> None:
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE prod.alerta, prod.ingreso, prod.salidas, "
            "prod.anulaciones, prod.cantidad_vehiculos_sucursal, "
            "prod.tipos_vehiculo, prod.sucursal, prod.empresa CASCADE"
        )
        conn.commit()


async def _seed_branch(pg_engine, *, uuid_sucursal: uuid_lib.UUID) -> uuid_lib.UUID:
    """Seed empresa/sucursal/tipo_vehiculo/cupo. Returns uuid_tipo_vehiculo."""
    now = _now_naive()
    tipo_auto = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="F11 Test SA",
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
                nombre=f"Suc F11 {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"T{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle F11",
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
        session.add(
            TiposVehiculo(
                uuid=tipo_auto,
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
    async with Session() as session:
        session.add(
            CantidadVehiculosSucursal(
                uuid=uuid_lib.uuid4(),
                uuid_sucursal=uuid_sucursal,
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
        await session.commit()
    return tipo_auto


async def _seed_ingreso(
    pg_engine,
    *,
    placa: str,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
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


async def _seed_salida(
    pg_engine, *, uuid_ingreso: uuid_lib.UUID, uuid_sucursal: uuid_lib.UUID
) -> uuid_lib.UUID:
    now = _now_naive()
    salida_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Salidas(
                uuid=salida_uuid,
                fecha_retencion_hasta=now.date(),
                uuid_sucursal=uuid_sucursal,
                uuid_ingreso=uuid_ingreso,
                fecha_salida=now,
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return salida_uuid


async def _seed_anulacion_salida(
    pg_engine,
    *,
    uuid_salida: uuid_lib.UUID,
    uuid_ingreso: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
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
                uuid_ingreso=uuid_ingreso,
                uuid_salida=uuid_salida,
                # NULL: ``fk_anulaciones_uuid_usuario`` enforces referential
                # integrity against ``prod.usuarios`` when non-null and this
                # test doesn't seed a usuario row (irrelevant to the
                # activo=true filter under test).
                uuid_usuario=None,
                motivo="anulacion no pagada -- F11 test",
                uuid_anulacion_padre=None,
                timestamp_evento=now,
                vigente_desde=now,
                vigente_hasta=None,
                estado="ejecutada",
            )
        )
        await session.commit()


async def test_activo_true_excluye_ingresos_con_salida_no_anulada(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """activo=true excluye salida real, mantiene sin-salida, reincluye anulada."""
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = await _seed_branch(pg_engine, uuid_sucursal=branch)

    ing_abierto = await _seed_ingreso(
        pg_engine, placa="ABC111", uuid_sucursal=branch, uuid_tipo_vehiculo=tipo_auto
    )
    ing_cerrado = await _seed_ingreso(
        pg_engine, placa="ABC222", uuid_sucursal=branch, uuid_tipo_vehiculo=tipo_auto
    )
    await _seed_salida(pg_engine, uuid_ingreso=ing_cerrado, uuid_sucursal=branch)
    ing_reabierto = await _seed_ingreso(
        pg_engine, placa="ABC333", uuid_sucursal=branch, uuid_tipo_vehiculo=tipo_auto
    )
    salida_anulada = await _seed_salida(
        pg_engine, uuid_ingreso=ing_reabierto, uuid_sucursal=branch
    )
    await _seed_anulacion_salida(
        pg_engine,
        uuid_salida=salida_anulada,
        uuid_ingreso=ing_reabierto,
        uuid_sucursal=branch,
    )

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    resp = await client.get(
        f"/api/v1/operacion/ingresos?uuid_sucursal={branch}&activo=true",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch),
        },
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    uuids = {item["uuid"] for item in resp.json()}
    assert uuids == {str(ing_abierto), str(ing_reabierto)}, uuids


async def test_activo_omitido_devuelve_historico_completo_backward_compat(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """Sin ``activo``, el endpoint preserva el historico completo -- lo
    usan ``getIngresosByPlaca`` / ``buscarIngresoTolerante`` (FE) y no
    debe cambiar de comportamiento sin el query param explicito."""
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = await _seed_branch(pg_engine, uuid_sucursal=branch)

    ing_abierto = await _seed_ingreso(
        pg_engine, placa="XYZ111", uuid_sucursal=branch, uuid_tipo_vehiculo=tipo_auto
    )
    ing_cerrado = await _seed_ingreso(
        pg_engine, placa="XYZ222", uuid_sucursal=branch, uuid_tipo_vehiculo=tipo_auto
    )
    await _seed_salida(pg_engine, uuid_ingreso=ing_cerrado, uuid_sucursal=branch)

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    resp = await client.get(
        f"/api/v1/operacion/ingresos?uuid_sucursal={branch}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch),
        },
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    uuids = {item["uuid"] for item in resp.json()}
    assert uuids == {str(ing_abierto), str(ing_cerrado)}


__all__ = [
    "test_activo_omitido_devuelve_historico_completo_backward_compat",
    "test_activo_true_excluye_ingresos_con_salida_no_anulada",
]
