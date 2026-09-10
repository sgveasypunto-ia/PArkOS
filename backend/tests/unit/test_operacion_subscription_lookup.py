"""test_operacion_subscription_lookup.py — T-PR5-016 acceptance
(REQ-CAT-017, addendum #2, design.md §2 Issue #11).

``resolve_active_subscription_for_exit`` (``api/v1/operacion.py``) is the
CU-03M exit-with-subscription validation query — defense in depth on top
of ``broadcast_policy="subscription"`` scoped sync (R22).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, timedelta

from parkos_core.api.v1.operacion import resolve_active_subscription_for_exit
from parkos_core.models.V.clientes import Clientes
from parkos_core.models.V.subscripcion_vehiculos import SubscripcionVehiculos
from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.tipo_persona import TipoPersona
from parkos_core.models.V.tipo_subscripciones import TipoSubscripciones
from parkos_core.models.V.tipo_sucursal import TipoSucursal
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from parkos_core.models.V.vehiculos import Vehiculos
from sqlalchemy.ext.asyncio import async_sessionmaker


def uid() -> str:
    return uuid_lib.uuid4().hex[:8]


async def _seed_subscription_at_branch(
    session, v_fixture_factory, *, placa: str, uuid_sucursal, fecha_vencimiento=None
) -> None:
    # uid()-suffixed — the literal "natural" collides with the canonical
    # migration-seeded row (0020, identity-reconciled) on this session-scoped
    # shared DB (conftest.py::pg_engine); only a valid FK target is needed.
    tipo_persona = v_fixture_factory.build(TipoPersona, tipo=f"natural-{uid()}")
    session.add(tipo_persona)
    tipo_subscripcion = v_fixture_factory.build(TipoSubscripciones, tipo="mensual")
    session.add(tipo_subscripcion)
    tipo_vehiculo = v_fixture_factory.build(TiposVehiculo, tipo="carro")
    session.add(tipo_vehiculo)
    await session.commit()

    cliente = v_fixture_factory.build(
        Clientes, tipo_identificador="CC", numero_identificacion="333",
        uuid_tipo_persona=tipo_persona.uuid,
    )
    session.add(cliente)
    vehiculo = v_fixture_factory.build(
        Vehiculos, placa=placa, uuid_tipo_vehiculo=tipo_vehiculo.uuid
    )
    session.add(vehiculo)
    await session.commit()

    subscripcion = v_fixture_factory.build(
        SubscripcionesCliente,
        uuid_cliente=cliente.uuid,
        uuid_sucursal=uuid_sucursal,
        uuid_tipo_subscripcion=tipo_subscripcion.uuid,
        fecha_vencimiento=fecha_vencimiento,
    )
    session.add(subscripcion)
    await session.commit()

    junction = v_fixture_factory.build(
        SubscripcionVehiculos,
        uuid_subscripcion_cliente=subscripcion.uuid,
        uuid_vehiculo=vehiculo.uuid,
        estado="activa",
    )
    session.add(junction)
    await session.commit()


async def _seed_branch(session, v_fixture_factory) -> uuid_lib.UUID:
    tipo_sucursal = v_fixture_factory.build(TipoSucursal, codigo="propia")
    session.add(tipo_sucursal)
    await session.commit()
    sucursal = v_fixture_factory.build(Sucursal, uuid_tipo_sucursal=tipo_sucursal.uuid)
    session.add(sucursal)
    await session.commit()
    return sucursal.uuid


async def test_finds_active_subscription_at_this_branch(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        branch_uuid = await _seed_branch(session, v_fixture_factory)
        await _seed_subscription_at_branch(
            session, v_fixture_factory, placa="SUB0001", uuid_sucursal=branch_uuid
        )

        result = await resolve_active_subscription_for_exit(
            session, placa="SUB0001", uuid_sucursal=branch_uuid
        )

    assert result.found is True
    assert result.subscripcion is not None


async def test_rejects_stale_row_for_another_branch(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    """R22 defense in depth: a row present locally for a DIFFERENT branch
    (simulating a stale/manually-inserted row) is rejected by the explicit
    uuid_sucursal filter, even though the row technically exists."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        selling_branch = await _seed_branch(session, v_fixture_factory)
        other_branch = await _seed_branch(session, v_fixture_factory)
        await _seed_subscription_at_branch(
            session, v_fixture_factory, placa="SUB0002", uuid_sucursal=selling_branch
        )

        result = await resolve_active_subscription_for_exit(
            session, placa="SUB0002", uuid_sucursal=other_branch
        )

    assert result.found is False
    assert result.message == "no subscription at this branch"


async def test_no_subscription_at_all(pg_engine, alembic_upgrade, v_fixture_factory) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        branch_uuid = await _seed_branch(session, v_fixture_factory)

        result = await resolve_active_subscription_for_exit(
            session, placa="NOSUB001", uuid_sucursal=branch_uuid
        )

    assert result.found is False
    assert result.message == "no subscription at this branch"


async def test_expired_subscription_distinct_message(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    """"subscription expired" is distinct from "no subscription at this
    branch" (design.md §2 Issue #11 point 4)."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        branch_uuid = await _seed_branch(session, v_fixture_factory)
        yesterday = date.today() - timedelta(days=1)
        await _seed_subscription_at_branch(
            session, v_fixture_factory, placa="SUB0003", uuid_sucursal=branch_uuid,
            fecha_vencimiento=yesterday,
        )

        result = await resolve_active_subscription_for_exit(
            session, placa="SUB0003", uuid_sucursal=branch_uuid
        )

    assert result.found is False
    assert result.message == "subscription expired"
    assert result.message != "no subscription at this branch"
