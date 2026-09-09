"""test_identity_reconciler.py — T-PR5-001..005 acceptance for
``hooks/impls/identity_reconciler.py`` (D17, REQ-HOOK-010).

Real Postgres throughout (``pg_engine``/``alembic_upgrade``) — every case
exercises the FULL ``apply_row`` path (not just the raw hook callable) so
"nothing written" / "no UPDATE ever" / "informational sync_conflict" are
proven against actual persisted rows, not just the returned ``HookResult``.

Given the three ``bidirectional`` identity masters (here: ``clientes``,
representative of ``clientes_b2b``/``vehiculos`` — all three share the
exact same ``IdentityReconciler`` code path), when a row arrives whose
normalized natural key matches a currently-open local version, then the
motor classifies the arrival into exactly one of ``noop`` / ``forward`` /
``historical``, optionally flagging a ``divergent`` conflict — never
``MANUAL``, never blocking.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

from parkos_core.models.V.clientes import Clientes
from parkos_core.models.V.tipo_persona import TipoPersona
from parkos_core.sync.hooks.impls.identity_reconciler import identity_reconciler
from parkos_core.sync.motor.apply_row import apply_row
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000aa")


def _row_dict(row: object) -> dict[str, object]:
    """Every column of an ORM instance as a plain dict (open_version shape)."""
    mapper = sa_inspect(type(row))
    return {column.name: getattr(row, column.name) for column in mapper.columns}


async def _seed_tipo_persona(session, v_fixture_factory) -> uuid_lib.UUID:
    tipo = v_fixture_factory.build(TipoPersona, tipo="natural")
    session.add(tipo)
    await session.commit()
    return tipo.uuid


async def _seed_open_clientes(session, v_fixture_factory, **overrides) -> Clientes:
    if "uuid_tipo_persona" not in overrides:
        overrides["uuid_tipo_persona"] = await _seed_tipo_persona(session, v_fixture_factory)
    row = v_fixture_factory.build(
        Clientes,
        tipo_identificador="CC",
        numero_identificacion="1020",
        nombre="Ana",
        apellido="Gomez",
        telefono="3000000000",
        email="ana@example.co",
        registro=None,
        **overrides,
    )
    session.add(row)
    await session.commit()
    return row


def _clientes_count_stmt():
    from sqlalchemy import func

    return select(func.count()).select_from(Clientes)


async def test_noop_when_business_columns_identical(
    pg_engine, alembic_upgrade, v_fixture_factory, make_spec
) -> None:
    """T-PR5-001: business columns identical (ignoring uuid/created_at/created_by/sync_*)
    -> reconciliation='noop', APPLIED, nothing written."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        open_row = await _seed_open_clientes(session, v_fixture_factory)
        open_version = _row_dict(open_row)

        before_count = (await session.execute(_clientes_count_stmt())).scalar_one()

        spec = make_spec("clientes", hook_pre_insert=identity_reconciler)
        payload = {
            "uuid": uuid_lib.uuid4(),
            "tipo_identificador": "CC",
            "numero_identificacion": "1020",
            "nombre": "Ana",
            "apellido": "Gomez",
            "telefono": "3000000000",
            "email": "ana@example.co",
            "uuid_tipo_persona": open_row.uuid_tipo_persona,
            "registro": None,
            "vigente_desde": datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
        }

        result = await apply_row(
            session, spec, payload, actor_uuid=ACTOR_UUID, open_version=open_version
        )
        await session.commit()

        after_count = (await session.execute(_clientes_count_stmt())).scalar_one()

        assert result.status == "APPLIED"
        assert result.row_uuid == open_row.uuid
        assert after_count == before_count  # nothing written


async def test_forward_when_later_vigente_desde(
    pg_engine, alembic_upgrade, v_fixture_factory, make_spec
) -> None:
    """T-PR5-002: later vigente_desde -> ordinary close_and_insert; arriving
    uuid becomes current."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        open_row = await _seed_open_clientes(session, v_fixture_factory)
        open_version = _row_dict(open_row)

        spec = make_spec("clientes", hook_pre_insert=identity_reconciler)
        arriving_uuid = uuid_lib.uuid4()
        payload = {
            "uuid": arriving_uuid,
            "tipo_identificador": "CC",
            "numero_identificacion": "10-20",  # raw format differs, normalizes the same
            "nombre": "Ana",
            "apellido": "Gomez",
            "telefono": "3000000000",
            "email": "ana@example.co",
            "uuid_tipo_persona": open_row.uuid_tipo_persona,
            "registro": None,
            "vigente_desde": open_row.vigente_desde + timedelta(days=1),
        }

        result = await apply_row(
            session, spec, payload, actor_uuid=ACTOR_UUID, open_version=open_version, log_tx=False
        )
        await session.commit()

        assert result.status == "APPLIED"
        assert result.row_uuid == arriving_uuid

        # The old version is now closed; the arriving row is the new open one.
        old_row = (
            await session.execute(select(Clientes).where(Clientes.uuid == open_row.uuid))
        ).scalar_one()
        assert old_row.vigente_hasta is not None

        new_row = (
            await session.execute(select(Clientes).where(Clientes.uuid == arriving_uuid))
        ).scalar_one()
        assert new_row.vigente_hasta is None
        assert new_row.numero_identificacion == "10-20"

        # No divergence conflict — every material column matched.
        conflicts = (
            await session.execute(
                select(_sync_conflict_model()).where(
                    _sync_conflict_model().uuid_registro == open_row.uuid
                )
            )
        ).scalars().all()
        assert conflicts == []


async def test_historical_when_earlier_vigente_desde(
    pg_engine, alembic_upgrade, v_fixture_factory, make_spec
) -> None:
    """T-PR5-003: earlier vigente_desde -> inserted as an already-closed
    version; current version untouched; no UPDATE ever."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        open_row = await _seed_open_clientes(session, v_fixture_factory)
        open_version = _row_dict(open_row)

        spec = make_spec("clientes", hook_pre_insert=identity_reconciler)
        arriving_uuid = uuid_lib.uuid4()
        earlier_desde = open_row.vigente_desde - timedelta(days=1)
        payload = {
            "uuid": arriving_uuid,
            "tipo_identificador": "CC",
            # Raw format differs from the seeded "1020" (normalizes the
            # same) so business-column comparison is NOT identical —
            # forcing timing classification instead of "noop" (design.md's
            # noop rule has no timing qualifier: identical business columns
            # ALWAYS classify as noop regardless of vigente_desde ordering).
            "numero_identificacion": "10-20",
            "nombre": "Ana",
            "apellido": "Gomez",
            "telefono": "3000000000",
            "email": "ana@example.co",
            "uuid_tipo_persona": open_row.uuid_tipo_persona,
            "registro": None,
            "vigente_desde": earlier_desde,
        }

        result = await apply_row(
            session, spec, payload, actor_uuid=ACTOR_UUID, open_version=open_version, log_tx=False
        )
        await session.commit()

        assert result.status == "APPLIED"
        assert result.row_uuid == arriving_uuid

        # Current (open) version is UNTOUCHED — same vigente_hasta as before.
        current_row = (
            await session.execute(select(Clientes).where(Clientes.uuid == open_row.uuid))
        ).scalar_one()
        assert current_row.vigente_hasta is None

        # The arriving row was inserted as an ALREADY-CLOSED version.
        historical_row = (
            await session.execute(select(Clientes).where(Clientes.uuid == arriving_uuid))
        ).scalar_one()
        assert historical_row.vigente_hasta == open_row.vigente_desde
        assert historical_row.estado == "inactivo"


async def test_divergent_data_writes_informational_conflict(
    pg_engine, alembic_upgrade, v_fixture_factory, make_spec
) -> None:
    """T-PR5-004: forward/historical + a material column differs -> ALSO
    writes an informational sync_conflict (politica='identity_divergence');
    apply still succeeds, never MANUAL."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        open_row = await _seed_open_clientes(session, v_fixture_factory)
        open_version = _row_dict(open_row)

        spec = make_spec("clientes", hook_pre_insert=identity_reconciler)
        arriving_uuid = uuid_lib.uuid4()
        payload = {
            "uuid": arriving_uuid,
            "tipo_identificador": "CC",
            "numero_identificacion": "1020",
            "nombre": "Ana",
            "apellido": "Gomez",
            "telefono": "3019999999",  # material column diverges
            "email": "ana@example.co",
            "uuid_tipo_persona": open_row.uuid_tipo_persona,
            "registro": None,
            "vigente_desde": open_row.vigente_desde + timedelta(days=1),
        }

        result = await apply_row(
            session, spec, payload, actor_uuid=ACTOR_UUID, open_version=open_version, log_tx=False
        )
        await session.commit()

        assert result.status == "APPLIED"  # never MANUAL

        conflicts = (
            await session.execute(
                select(_sync_conflict_model()).where(
                    _sync_conflict_model().uuid_registro == open_row.uuid
                )
            )
        ).scalars().all()
        assert len(conflicts) == 1
        assert conflicts[0].politica == "identity_divergence"


def _sync_conflict_model():
    from parkos_core.models.A.sync_conflict import SyncConflict

    return SyncConflict
