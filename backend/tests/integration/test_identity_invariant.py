"""test_identity_invariant.py — T-PR5-009 acceptance (R17, REQ-OPS-015).

CI invariant: at most one OPEN version per normalized natural key, for each
of the three identity masters (``clientes``, ``clientes_b2b``,
``vehiculos``). Design.md §2 Issue #10 deliberately does NOT enforce this
with a ``UNIQUE`` index (a constraint violation would raise on the
applying transaction and block an invoice at the counter — exactly what
D17 case 4 forbids); the invariant is proven here, in CI, instead.

Exercises the full ``noop`` / ``forward`` / ``historical`` / divergent
``IdentityReconciler`` paths (through ``apply_row``) and asserts the
invariant holds after each — a reconciler bug that lets two open versions
coexist for the SAME normalized natural key must fail THIS test, not rely
on a database constraint that does not exist.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

from parkos_core.models.V.clientes import Clientes
from parkos_core.models.V.clientes_b2b import ClientesB2B
from parkos_core.models.V.tipo_persona import TipoPersona
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from parkos_core.models.V.vehiculos import Vehiculos
from parkos_core.sync.hooks.impls.identity_reconciler import identity_reconciler
from parkos_core.sync.motor.apply_row import apply_row
from sqlalchemy import func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import async_sessionmaker

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000aa")


def uid() -> str:
    return uuid_lib.uuid4().hex[:8]


def _row_dict(row: object) -> dict[str, object]:
    mapper = sa_inspect(type(row))
    return {column.name: getattr(row, column.name) for column in mapper.columns}


async def _assert_at_most_one_open_version(session, model_cls, *natural_key_where) -> None:
    """R17 invariant: COUNT(*) WHERE vigente_hasta IS NULL <= 1 for this key."""
    count = (
        await session.execute(
            select(func.count())
            .select_from(model_cls)
            .where(model_cls.vigente_hasta.is_(None), *natural_key_where)
        )
    ).scalar_one()
    assert count <= 1, (
        f"R17 violation: {count} open versions found for {model_cls.__tablename__} "
        "on the same normalized natural key"
    )


async def test_clientes_invariant_across_all_reconciliation_outcomes(
    pg_engine, alembic_upgrade, v_fixture_factory, make_spec
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        # uid()-suffixed — the literal "natural" collides with the
        # canonical migration-seeded row (0020, identity-reconciled) and
        # with any other test's own "natural" row on this session-scoped
        # shared DB (conftest.py::pg_engine); this test only needs a valid
        # FK target, never asserts on the tipo_persona value itself.
        tipo = v_fixture_factory.build(TipoPersona, tipo=f"natural-{uid()}")
        session.add(tipo)
        await session.commit()

        spec = make_spec("clientes", hook_pre_insert=identity_reconciler)
        now = datetime.now(UTC).replace(tzinfo=None)

        open_row = v_fixture_factory.build(
            Clientes,
            tipo_identificador="CC",
            numero_identificacion="7070",
            nombre="Ana",
            apellido="Gomez",
            telefono="3000000000",
            email="ana@example.co",
            uuid_tipo_persona=tipo.uuid,
            registro=None,
            vigente_desde=now,
            vigente_hasta=None,
        )
        session.add(open_row)
        await session.commit()
        open_version = _row_dict(open_row)

        # Scoped to THIS test's specific normalized natural key — the
        # shared session-scoped DB may carry open "CC" rows from other
        # tests in the same run, which a bare tipo_identificador filter
        # would also (incorrectly) count.
        where = (
            Clientes.tipo_identificador == "CC",
            func.regexp_replace(
                Clientes.numero_identificacion, "[^0-9A-Za-z]", "", "g"
            )
            == "7070",
        )
        await _assert_at_most_one_open_version(session, Clientes, *where)

        # noop
        noop_payload = {
            "uuid": uuid_lib.uuid4(),
            "tipo_identificador": "CC",
            "numero_identificacion": "7070",
            "nombre": "Ana",
            "apellido": "Gomez",
            "telefono": "3000000000",
            "email": "ana@example.co",
            "uuid_tipo_persona": tipo.uuid,
            "registro": None,
            "vigente_desde": now + timedelta(hours=1),
        }
        result = await apply_row(
            session, spec, noop_payload, actor_uuid=ACTOR_UUID, open_version=open_version,
            log_tx=False,
        )
        await session.commit()
        assert result.status == "APPLIED"
        await _assert_at_most_one_open_version(session, Clientes, *where)

        # forward — re-fetch open_version (unchanged, since noop wrote nothing)
        forward_payload = {
            "uuid": uuid_lib.uuid4(),
            "tipo_identificador": "CC",
            "numero_identificacion": "70-70",
            "nombre": "Ana",
            "apellido": "Gomez2",  # material divergence, exercises that path too
            "telefono": "3000000000",
            "email": "ana@example.co",
            "uuid_tipo_persona": tipo.uuid,
            "registro": None,
            "vigente_desde": now + timedelta(hours=2),
        }
        result = await apply_row(
            session, spec, forward_payload, actor_uuid=ACTOR_UUID, open_version=open_version,
            log_tx=False,
        )
        await session.commit()
        assert result.status == "APPLIED"
        await _assert_at_most_one_open_version(session, Clientes, *where)

        # historical — against the NEW open version (forward_payload's row)
        new_open_version = {**forward_payload, "uuid": result.row_uuid}
        historical_payload = {
            "uuid": uuid_lib.uuid4(),
            "tipo_identificador": "CC",
            "numero_identificacion": "707-0",
            "nombre": "Ana",
            "apellido": "Gomez2",
            "telefono": "3000000000",
            "email": "ana@example.co",
            "uuid_tipo_persona": tipo.uuid,
            "registro": None,
            "vigente_desde": now - timedelta(hours=1),  # earlier than the current open version
        }
        result = await apply_row(
            session, spec, historical_payload, actor_uuid=ACTOR_UUID,
            open_version=new_open_version, log_tx=False,
        )
        await session.commit()
        assert result.status == "APPLIED"
        await _assert_at_most_one_open_version(session, Clientes, *where)


async def test_clientes_b2b_invariant(
    pg_engine, alembic_upgrade, v_fixture_factory, make_spec
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        # Same reasoning as test_clientes_invariant_across_all_reconciliation_outcomes above.
        tipo = v_fixture_factory.build(TipoPersona, tipo=f"natural-{uid()}")
        session.add(tipo)
        await session.commit()

        cliente = v_fixture_factory.build(
            Clientes,
            tipo_identificador="CC",
            numero_identificacion="8080",
            uuid_tipo_persona=tipo.uuid,
        )
        session.add(cliente)
        await session.commit()

        now = datetime.now(UTC).replace(tzinfo=None)
        open_row = v_fixture_factory.build(
            ClientesB2B,
            uuid_cliente=cliente.uuid,
            cantidad=3,
            vigente_desde=now,
            vigente_hasta=None,
        )
        session.add(open_row)
        await session.commit()
        open_version = _row_dict(open_row)

        spec = make_spec("clientes_b2b", hook_pre_insert=identity_reconciler)
        payload = {
            "uuid": uuid_lib.uuid4(),
            "uuid_cliente": cliente.uuid,
            "cantidad": 5,  # material divergence
            "registro": None,
            "fecha_inicio_convenio": None,
            "fecha_vencimiento": None,
            "vigente_desde": now + timedelta(hours=1),
        }
        result = await apply_row(
            session, spec, payload, actor_uuid=ACTOR_UUID, open_version=open_version,
            log_tx=False,
        )
        await session.commit()
        assert result.status == "APPLIED"

        await _assert_at_most_one_open_version(
            session, ClientesB2B, ClientesB2B.uuid_cliente == cliente.uuid
        )


async def test_vehiculos_invariant(
    pg_engine, alembic_upgrade, v_fixture_factory, make_spec
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        tipo_vehiculo = v_fixture_factory.build(TiposVehiculo, tipo="carro")
        session.add(tipo_vehiculo)
        await session.commit()

        now = datetime.now(UTC).replace(tzinfo=None)
        open_row = v_fixture_factory.build(
            Vehiculos,
            placa="9090",
            uuid_tipo_vehiculo=tipo_vehiculo.uuid,
            vigente_desde=now,
            vigente_hasta=None,
        )
        session.add(open_row)
        await session.commit()
        open_version = _row_dict(open_row)

        tipo_vehiculo_2 = v_fixture_factory.build(TiposVehiculo, tipo="moto")
        session.add(tipo_vehiculo_2)
        await session.commit()

        spec = make_spec("vehiculos", hook_pre_insert=identity_reconciler)
        payload = {
            "uuid": uuid_lib.uuid4(),
            "placa": "90-90",
            "uuid_tipo_vehiculo": tipo_vehiculo_2.uuid,  # material divergence
            "vigente_desde": now + timedelta(hours=1),
        }
        result = await apply_row(
            session, spec, payload, actor_uuid=ACTOR_UUID, open_version=open_version,
            log_tx=False,
        )
        await session.commit()
        assert result.status == "APPLIED"

        await _assert_at_most_one_open_version(
            session, Vehiculos, Vehiculos.placa.in_(["9090", "90-90"])
        )
