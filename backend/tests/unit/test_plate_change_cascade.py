"""test_plate_change_cascade.py — T-PR5-013/014 acceptance for
``hooks/impls/plate_change_cascade.py`` (REQ-HOOK-005, re-targeted).

Real Postgres throughout — the cascade is exercised end to end via
``apply_row`` on ``vehiculos`` (``hook_post_insert``), whose returned
``cascade_rows`` the motor applies recursively through itself.
"""
from __future__ import annotations

import uuid as uuid_lib

from parkos_core.models.V.clientes import Clientes
from parkos_core.models.V.subscripcion_vehiculos import SubscripcionVehiculos
from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.tipo_persona import TipoPersona
from parkos_core.models.V.tipo_subscripciones import TipoSubscripciones
from parkos_core.models.V.tipo_sucursal import TipoSucursal
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from parkos_core.models.V.vehiculos import Vehiculos
from parkos_core.sync.hooks.impls.plate_change_cascade import plate_change_cascade
from parkos_core.sync.motor.apply_row import apply_row
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000aa")


async def test_closes_and_reopens_subscripcion_vehiculos(
    pg_engine, alembic_upgrade, v_fixture_factory, make_spec
) -> None:
    """T-PR5-013/014: a plate change closes every open subscripcion_vehiculos
    row pointing at the OLD vehiculos version and inserts replacements
    pointing at the NEW version; audit trail is log_transaccional, never
    reclamos; the vehiculos write itself proceeds regardless."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        tipo_vehiculo = v_fixture_factory.build(TiposVehiculo, tipo="carro")
        session.add(tipo_vehiculo)
        tipo_sucursal = v_fixture_factory.build(TipoSucursal, codigo="propia")
        session.add(tipo_sucursal)
        tipo_persona = v_fixture_factory.build(TipoPersona, tipo="natural")
        session.add(tipo_persona)
        tipo_subscripcion = v_fixture_factory.build(
            TipoSubscripciones, tipo="mensual", cantidad_maxima_vehiculos=5
        )
        session.add(tipo_subscripcion)
        await session.commit()

        old_vehiculo = v_fixture_factory.build(
            Vehiculos, placa="OLD-001", uuid_tipo_vehiculo=tipo_vehiculo.uuid
        )
        session.add(old_vehiculo)
        sucursal = v_fixture_factory.build(Sucursal, uuid_tipo_sucursal=tipo_sucursal.uuid)
        session.add(sucursal)
        cliente = v_fixture_factory.build(
            Clientes, tipo_identificador="CC", numero_identificacion="222",
            uuid_tipo_persona=tipo_persona.uuid,
        )
        session.add(cliente)
        await session.commit()

        subscripcion = v_fixture_factory.build(
            SubscripcionesCliente,
            uuid_cliente=cliente.uuid,
            uuid_sucursal=sucursal.uuid,
            uuid_tipo_subscripcion=tipo_subscripcion.uuid,
        )
        session.add(subscripcion)
        await session.commit()

        junction = v_fixture_factory.build(
            SubscripcionVehiculos,
            uuid_subscripcion_cliente=subscripcion.uuid,
            uuid_vehiculo=old_vehiculo.uuid,
            estado="activa",
        )
        session.add(junction)
        await session.commit()

        spec = make_spec("vehiculos", hook_post_insert=plate_change_cascade)
        new_uuid = uuid_lib.uuid4()
        payload = {
            "uuid": new_uuid,
            "current_uuid": old_vehiculo.uuid,
            "placa": "NEW-002",
            "uuid_tipo_vehiculo": tipo_vehiculo.uuid,
        }

        result = await apply_row(
            session, spec, payload, actor_uuid=ACTOR_UUID, log_tx=False
        )
        await session.commit()

        # The vehiculos write proceeds regardless of the cascade outcome.
        assert result.status == "APPLIED"
        assert result.row_uuid == new_uuid

        old_row = (
            await session.execute(select(Vehiculos).where(Vehiculos.uuid == old_vehiculo.uuid))
        ).scalar_one()
        assert old_row.vigente_hasta is not None

        # Old junction row is closed.
        old_junction = (
            await session.execute(
                select(SubscripcionVehiculos).where(SubscripcionVehiculos.uuid == junction.uuid)
            )
        ).scalar_one()
        assert old_junction.vigente_hasta is not None

        # A replacement junction row points at the NEW vehiculos version,
        # preserving the lifecycle estado.
        replacement = (
            await session.execute(
                select(SubscripcionVehiculos).where(
                    SubscripcionVehiculos.uuid_subscripcion_cliente == subscripcion.uuid,
                    SubscripcionVehiculos.vigente_hasta.is_(None),
                )
            )
        ).scalar_one()
        assert replacement.uuid_vehiculo == new_uuid
        assert replacement.estado == "activa"

        # Audit trail is log_transaccional, never reclamos.
        from parkos_core.models.L_W.reclamos import Reclamos

        reclamos = (await session.execute(select(Reclamos))).scalars().all()
        assert reclamos == []


async def test_no_cascade_on_brand_new_vehiculo(
    pg_engine, alembic_upgrade, v_fixture_factory, make_spec
) -> None:
    """A first-ever vehiculos insert (no current_uuid) has nothing to
    cascade — no-op, empty cascade_rows, ordinary APPLIED."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        tipo_vehiculo = v_fixture_factory.build(TiposVehiculo, tipo="carro")
        session.add(tipo_vehiculo)
        await session.commit()

        spec = make_spec("vehiculos", hook_post_insert=plate_change_cascade)
        payload = {
            "uuid": uuid_lib.uuid4(),
            "placa": "BRAND01",
            "uuid_tipo_vehiculo": tipo_vehiculo.uuid,
        }

        result = await apply_row(
            session, spec, payload, actor_uuid=ACTOR_UUID, log_tx=False
        )
        await session.commit()

        assert result.status == "APPLIED"
        assert result.metrics["hook_post_insert"] is True
