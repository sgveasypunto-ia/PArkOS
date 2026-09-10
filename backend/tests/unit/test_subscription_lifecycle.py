"""test_subscription_lifecycle.py — T-PR5-010..012 acceptance for
``hooks/impls/subscription_lifecycle.py`` (REQ-HOOK-006).

Real Postgres throughout — every case exercises the full ``apply_row``
path so the ``CONFLICT``/``illegal_state_transition`` outcome AND the
``sync_conflict`` row it writes are proven end to end.
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
from parkos_core.sync.hooks.impls.subscription_lifecycle import subscription_lifecycle
from parkos_core.sync.motor.apply_row import apply_row
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000aa")


def uid() -> str:
    return uuid_lib.uuid4().hex[:8]


async def _seed_subscription(
    session, v_fixture_factory, *, cantidad_maxima_vehiculos: int | None = 5
) -> tuple[SubscripcionesCliente, TipoSubscripciones]:
    tipo_sucursal = v_fixture_factory.build(TipoSucursal, codigo="propia")
    session.add(tipo_sucursal)
    # uid()-suffixed — the literal "natural" collides with the canonical
    # migration-seeded row (0020, identity-reconciled) on this
    # session-scoped shared DB (conftest.py::pg_engine).
    tipo_persona = v_fixture_factory.build(TipoPersona, tipo=f"natural-{uid()}")
    session.add(tipo_persona)
    tipo_subscripcion = v_fixture_factory.build(
        TipoSubscripciones,
        tipo="mensual",
        cantidad_maxima_vehiculos=cantidad_maxima_vehiculos,
    )
    session.add(tipo_subscripcion)
    await session.commit()

    sucursal = v_fixture_factory.build(Sucursal, uuid_tipo_sucursal=tipo_sucursal.uuid)
    session.add(sucursal)
    cliente = v_fixture_factory.build(
        Clientes, tipo_identificador="CC", numero_identificacion="111",
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
    return subscripcion, tipo_subscripcion


async def _seed_vehiculo(session, v_fixture_factory, *, placa: str) -> Vehiculos:
    tipo_vehiculo = v_fixture_factory.build(TiposVehiculo, tipo="carro")
    session.add(tipo_vehiculo)
    await session.commit()
    vehiculo = v_fixture_factory.build(
        Vehiculos, placa=placa, uuid_tipo_vehiculo=tipo_vehiculo.uuid
    )
    session.add(vehiculo)
    await session.commit()
    return vehiculo


def _sync_conflict_model():
    from parkos_core.models.A.sync_conflict import SyncConflict

    return SyncConflict


async def test_illegal_transition_rejected(
    pg_engine, alembic_upgrade, v_fixture_factory, make_spec
) -> None:
    """T-PR5-010: a transition outside activa<->suspendida<->cancelada
    (terminal) -> proceed=False -> CONFLICT/illegal_state_transition +
    sync_conflict(politica='illegal_lifecycle')."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        subscripcion, _tipo = await _seed_subscription(session, v_fixture_factory)
        vehiculo = await _seed_vehiculo(session, v_fixture_factory, placa="ILL001")

        current = v_fixture_factory.build(
            SubscripcionVehiculos,
            uuid_subscripcion_cliente=subscripcion.uuid,
            uuid_vehiculo=vehiculo.uuid,
            estado="cancelada",  # terminal
        )
        session.add(current)
        await session.commit()

        spec = make_spec("subscripcion_vehiculos", hook_pre_insert=subscription_lifecycle)
        payload = {
            "current_uuid": current.uuid,
            "uuid_subscripcion_cliente": subscripcion.uuid,
            "uuid_vehiculo": vehiculo.uuid,
            "estado": "activa",  # illegal — cancelada is terminal
        }

        result = await apply_row(
            session, spec, payload, actor_uuid=ACTOR_UUID, log_tx=False
        )
        await session.commit()

        assert result.status == "CONFLICT"
        assert result.reason == "illegal_state_transition"

        conflicts = (
            await session.execute(
                select(_sync_conflict_model()).where(
                    _sync_conflict_model().uuid_registro == current.uuid
                )
            )
        ).scalars().all()
        assert len(conflicts) == 1
        assert conflicts[0].politica == "illegal_lifecycle"

        # No new junction row was inserted.
        rows = (
            await session.execute(
                select(SubscripcionVehiculos).where(
                    SubscripcionVehiculos.uuid_subscripcion_cliente == subscripcion.uuid
                )
            )
        ).scalars().all()
        assert len(rows) == 1


async def test_legal_transition_accepted(
    pg_engine, alembic_upgrade, v_fixture_factory, make_spec
) -> None:
    """activa -> suspendida is a legal transition (control/happy-path case)."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        subscripcion, _tipo = await _seed_subscription(session, v_fixture_factory)
        vehiculo = await _seed_vehiculo(session, v_fixture_factory, placa="LEG001")

        current = v_fixture_factory.build(
            SubscripcionVehiculos,
            uuid_subscripcion_cliente=subscripcion.uuid,
            uuid_vehiculo=vehiculo.uuid,
            estado="activa",
        )
        session.add(current)
        await session.commit()

        spec = make_spec("subscripcion_vehiculos", hook_pre_insert=subscription_lifecycle)
        payload = {
            "current_uuid": current.uuid,
            "uuid_subscripcion_cliente": subscripcion.uuid,
            "uuid_vehiculo": vehiculo.uuid,
            "estado": "suspendida",
        }

        result = await apply_row(
            session, spec, payload, actor_uuid=ACTOR_UUID, log_tx=False
        )
        await session.commit()

        assert result.status == "APPLIED"


async def test_vehicle_capacity_enforced(
    pg_engine, alembic_upgrade, v_fixture_factory, make_spec
) -> None:
    """T-PR5-011: adding a vehicle beyond cantidad_maxima_vehiculos is
    treated the same as an illegal transition."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        subscripcion, _tipo = await _seed_subscription(
            session, v_fixture_factory, cantidad_maxima_vehiculos=1
        )
        vehiculo1 = await _seed_vehiculo(session, v_fixture_factory, placa="CAP001")
        vehiculo2 = await _seed_vehiculo(session, v_fixture_factory, placa="CAP002")

        existing = v_fixture_factory.build(
            SubscripcionVehiculos,
            uuid_subscripcion_cliente=subscripcion.uuid,
            uuid_vehiculo=vehiculo1.uuid,
            estado="activa",
        )
        session.add(existing)
        await session.commit()

        spec = make_spec("subscripcion_vehiculos", hook_pre_insert=subscription_lifecycle)
        payload = {
            # No current_uuid — genuinely NEW association, would exceed
            # cantidad_maxima_vehiculos=1.
            "uuid_subscripcion_cliente": subscripcion.uuid,
            "uuid_vehiculo": vehiculo2.uuid,
            "estado": "activa",
        }

        result = await apply_row(
            session, spec, payload, actor_uuid=ACTOR_UUID, log_tx=False
        )
        await session.commit()

        assert result.status == "CONFLICT"
        assert result.reason == "illegal_state_transition"

        conflicts = (
            await session.execute(
                select(_sync_conflict_model()).where(
                    _sync_conflict_model().uuid_registro == subscripcion.uuid
                )
            )
        ).scalars().all()
        assert len(conflicts) == 1
        assert conflicts[0].politica == "illegal_lifecycle"


async def test_new_association_within_capacity_accepted(
    pg_engine, alembic_upgrade, v_fixture_factory, make_spec
) -> None:
    """Control case: a brand-new association within capacity is legal."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        subscripcion, _tipo = await _seed_subscription(
            session, v_fixture_factory, cantidad_maxima_vehiculos=2
        )
        vehiculo = await _seed_vehiculo(session, v_fixture_factory, placa="OK0001")

        spec = make_spec("subscripcion_vehiculos", hook_pre_insert=subscription_lifecycle)
        payload = {
            "uuid_subscripcion_cliente": subscripcion.uuid,
            "uuid_vehiculo": vehiculo.uuid,
            "estado": "activa",
        }

        result = await apply_row(
            session, spec, payload, actor_uuid=ACTOR_UUID, log_tx=False
        )
        await session.commit()

        assert result.status == "APPLIED"
