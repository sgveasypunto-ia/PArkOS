"""test_record_event_log_transaccional_fk.py — regression coverage for a
real defect found doing manual QA against the live Docker branch stack
(qa-e2e audit session, 2026-09-10): every ``[L-E]`` event's own
``log_transaccional`` audit row was written with ``uuid_registro_afectado``
NULL — the very column meant to say WHICH row the entry attests to.

Confirmed live: ``POST /api/v1/operacion/ingresos`` against the running
branch, then reading back ``log_transaccional`` for that ``uuid_sucursal``
showed the row for this ingreso with an empty ``uuid_registro_afectado``.

Root cause: ``repo.event.record_event`` builds
``log_attrs["uuid_registro_afectado"] = getattr(new_row, "uuid", None)``
before ever flushing ``new_row`` — ``uuid`` is
``server_default=func.gen_random_uuid()`` (models/base.py), a DB-side
default never populated on the Python object until a flush round-trips it.
``repo.versioned.close_and_insert`` already flushes before reading
``new_row.uuid`` for the exact same reason; ``record_event`` now mirrors it.

``tests/unit/test_event_record.py`` covers the mocked-session dispatch
shape (flush is now called once); this file proves the actual DB-visible
effect end-to-end, over real HTTP, against a real Postgres session — the
mocked-session test cannot, since a mock's ``flush()`` does not actually
populate a server-generated column.
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_ingreso_log_transaccional_row_has_real_fk(
    client, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.models.V.sucursal import Sucursal
    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor_uuid = uuid_lib.uuid4()
    sucursal_ctx = uuid_lib.uuid4()
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[sucursal_ctx])
    headers = {"Authorization": f"Bearer {token}", "X-Sucursal-Context": str(sucursal_ctx)}

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(Sucursal(uuid=sucursal_ctx, nombre="Test", prefijo_nombre="TST"))
        tipo_vehiculo_uuid = uuid_lib.uuid4()
        session.add(TiposVehiculo(uuid=tipo_vehiculo_uuid, tipo="carro"))
        await session.commit()

    placa = f"AUD{uuid_lib.uuid4().hex[:5].upper()}"
    resp = await client.post(
        "/api/v1/operacion/ingresos",
        json={
            "placa": placa,
            "uuid_sucursal": str(sucursal_ctx),
            "uuid_tipo_vehiculo": str(tipo_vehiculo_uuid),
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    ingreso_uuid = uuid_lib.UUID(resp.json()["uuid"])

    async with Session() as session:
        log_row = (
            await session.execute(
                select(LogTransaccional).where(
                    LogTransaccional.tabla_afectada == "ingreso",
                    LogTransaccional.uuid_registro_afectado == ingreso_uuid,
                )
            )
        ).scalar_one_or_none()
        assert log_row is not None, (
            "log_transaccional must carry the real ingreso uuid in "
            "uuid_registro_afectado, not leave it NULL"
        )
        assert log_row.uuid_sucursal == sucursal_ctx
        assert log_row.accion == "crear"
