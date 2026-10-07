"""D3 - an ingreso annulled by an EXECUTED ``tipo_anulable='ingreso'`` anulacion
is not active anywhere (list, estado, V8 guard, salida lookup), the same
verdict ``mv_ocupacion_diaria`` / the cupo label already give (migration 0091).

Reachable through the API: ``POST /workflows/anulaciones`` accepts
``tipo_anulable='ingreso'`` and the transition endpoints walk it to
``ejecutada``.
"""
from __future__ import annotations

import uuid as uuid_lib

from parkos_core.models.L_W.anulaciones import Anulaciones
from parkos_core.repo.ingreso import existe_ingreso_activo
from parkos_core.repo.salida import buscar_ingreso_activo_por_uuid
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_operacion_ingresos_list_activo import (
    _now_naive,
    _seed_branch,
    _seed_ingreso,
    _truncate,
)


async def _seed_anulacion_ingreso(
    pg_engine, *, uuid_ingreso: uuid_lib.UUID, uuid_sucursal: uuid_lib.UUID, estado: str
) -> None:
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Anulaciones(
                uuid=uuid_lib.uuid4(),
                fecha_retencion_hasta=now.date(),
                uuid_sucursal=uuid_sucursal,
                tipo_anulable="ingreso",
                uuid_ingreso=uuid_ingreso,
                uuid_salida=None,
                uuid_usuario=None,
                motivo="ingreso erroneo -- D3 test",
                uuid_anulacion_padre=None,
                timestamp_evento=now,
                vigente_desde=now,
                vigente_hasta=None,
                estado=estado,
            )
        )
        await session.commit()


async def test_ingreso_anulado_ejecutada_no_cuenta_como_activo_en_ningun_lado(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    tipo = await _seed_branch(pg_engine, uuid_sucursal=branch)
    vivo = await _seed_ingreso(
        pg_engine, placa="DDD111", uuid_sucursal=branch, uuid_tipo_vehiculo=tipo
    )
    anulado = await _seed_ingreso(
        pg_engine, placa="DDD222", uuid_sucursal=branch, uuid_tipo_vehiculo=tipo
    )
    en_curso = await _seed_ingreso(
        pg_engine, placa="DDD333", uuid_sucursal=branch, uuid_tipo_vehiculo=tipo
    )
    await _seed_anulacion_ingreso(
        pg_engine, uuid_ingreso=anulado, uuid_sucursal=branch, estado="ejecutada"
    )
    # An annulment that was only requested/authorized has not happened yet.
    await _seed_anulacion_ingreso(
        pg_engine, uuid_ingreso=en_curso, uuid_sucursal=branch, estado="iniciada"
    )

    token = mint_operador_jwt(actor_uuid=uuid_lib.uuid4(), sucursal_uuid=branch)
    headers = {"Authorization": f"Bearer {token}", "X-Sucursal-Context": str(branch)}

    listado = await client.get(
        f"/api/v1/operacion/ingresos?uuid_sucursal={branch}&activo=true", headers=headers
    )
    assert listado.status_code == 200, listado.text
    assert {i["uuid"] for i in listado.json()} == {str(vivo), str(en_curso)}

    estado = await client.get(f"/api/v1/operacion/ingresos/{anulado}/estado", headers=headers)
    assert estado.status_code == 200, estado.text
    assert estado.json()["estado"] == "anulada"
    vivo_estado = await client.get(f"/api/v1/operacion/ingresos/{vivo}/estado", headers=headers)
    assert vivo_estado.json()["estado"] == "abierto"
    en_curso_estado = await client.get(
        f"/api/v1/operacion/ingresos/{en_curso}/estado", headers=headers
    )
    assert en_curso_estado.json()["estado"] == "abierto"

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        assert await existe_ingreso_activo(session, uuid_sucursal=branch, placa="DDD222") is None
        assert await existe_ingreso_activo(session, uuid_sucursal=branch, placa="DDD333") == en_curso
        assert await buscar_ingreso_activo_por_uuid(session, uuid_ingreso=anulado) is None
        assert await buscar_ingreso_activo_por_uuid(session, uuid_ingreso=vivo) is not None
