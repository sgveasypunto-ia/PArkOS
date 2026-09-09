"""test_sync_cloud_catalog_driven.py — T-PR11-001 acceptance (REQ-MOT-011,
REQ-MOT-015, D21 guard 2 / REQ-OPS-014).

``SyncCloudWorker._apply_pending_batch_once`` (the new catalog-driven apply
loop this PR wires) drains ``prod.sync_queue`` and applies the batch through
``SyncMotor.apply_batch``, end to end against a real Postgres container:

  - a ``[V]`` fixture row (``usuarios``, ``close_and_insert``) applies
    correctly and the ``sync_queue`` row settles ``estado='exitoso'``.
  - an ``[A]`` fixture row (``caja``, ``append_event``) applies correctly
    and settles the same way.
  - an out-of-catalog infra row (``tabla="sync_log"``) is skipped —
    D21 guard 2 — settling WITHOUT ever being marked failed.
  - an unrecognized, non-infra ``tabla`` is marked failed, never silently
    dropped.
  - one poisoned row in an otherwise-good batch does not block its
    sibling row (the per-row fallback ``apply_batch`` failure triggers).

Distinct from ``tests/unit/test_motor_apply_batch.py`` (PR4, pure-mock
``SyncMotor.apply_batch`` unit coverage) and
``tests/unit/test_sync_cloud_scenarios.py`` (PR9b, mocked-session hash-chain
verifier coverage, unchanged by this PR) — this file is the real,
testcontainers-backed, end-to-end proof T-PR11-001's acceptance criterion
asks for.
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest
from parkos_core.jobs.sync_cloud import SyncCloudWorker
from parkos_core.models.A.caja import Caja
from parkos_core.models.A.sync_queue import SyncQueue
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.repo import sync_queue as sq_helpers
from parkos_core.runtime import engine_flag
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker


@pytest.fixture(autouse=True)
def _catalog_engine_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-PR11-001's apply loop reads PARKOS_SYNC_ENGINE via SyncMotor."""
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
    engine_flag._reset_cache_for_tests()


async def test_apply_loop_applies_v_and_a_fixture_rows_end_to_end(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    """A [V] and an [A] fixture row apply correctly end to end (T-PR11-001)."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal = v_fixture_factory.build(Sucursal)
        session.add(sucursal)
        await session.commit()

        cedula = f"cd-{uuid_lib.uuid4().hex[:12]}"
        usuarios_queue_row = await sq_helpers.enqueue(
            session,
            "insert",
            "usuarios",
            uuid_lib.uuid4(),
            {
                "nombre": "Ada",
                "apellido": "Lovelace",
                "cedula": cedula,
                "email": "ada@example.com",
                "rol": "operador",
            },
            None,
        )
        caja_queue_row = await sq_helpers.enqueue(
            session,
            "insert",
            "caja",
            uuid_lib.uuid4(),
            {
                "uuid_sucursal": str(sucursal.uuid),
                "valor_efectivo": "100.00",
                "valor_datafono": "50.00",
            },
            sucursal.uuid,
        )
        await session.commit()

        worker = SyncCloudWorker(session=session)
        # pg_engine/alembic_upgrade are session-scoped (tests/conftest.py) —
        # prior tests in the same session may leave other 'pendiente' rows
        # (e.g. migration-seeded global [V] config defaults) in the SAME
        # sync_queue; this asserts on OUR two fixture rows specifically,
        # not on an exact total this test does not fully control.
        settled = await worker._apply_pending_batch_once()
        await session.commit()

        assert settled >= 2

        usuarios_count = (
            await session.execute(
                select(func.count()).select_from(Usuarios).where(Usuarios.cedula == cedula)
            )
        ).scalar_one()
        assert usuarios_count == 1

        caja_count = (
            await session.execute(
                select(func.count())
                .select_from(Caja)
                .where(Caja.uuid_sucursal == sucursal.uuid)
            )
        ).scalar_one()
        assert caja_count == 1

        for row_uuid in (usuarios_queue_row.uuid, caja_queue_row.uuid):
            estado = (
                await session.execute(
                    select(SyncQueue.estado).where(SyncQueue.uuid == row_uuid)
                )
            ).scalar_one()
            assert estado == "exitoso"


async def test_apply_loop_skips_infra_table_row_without_marking_failed(
    pg_engine, alembic_upgrade
) -> None:
    """D21 guard 2 (REQ-OPS-014): an out-of-catalog infra row is skipped,
    settling ``estado='exitoso'`` — never ``mark_failed``."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        infra_row = await sq_helpers.enqueue(
            session,
            "insert",
            "sync_log",
            uuid_lib.uuid4(),
            {"anything": "goes"},
            None,
        )
        await session.commit()

        worker = SyncCloudWorker(session=session)
        settled = await worker._apply_pending_batch_once()
        await session.commit()

        assert settled >= 1

        row = (
            await session.execute(
                select(SyncQueue.estado, SyncQueue.intentos, SyncQueue.ultimo_error).where(
                    SyncQueue.uuid == infra_row.uuid
                )
            )
        ).one()
        estado, intentos, ultimo_error = row
        assert estado == "exitoso"
        assert not intentos
        assert ultimo_error is None


async def test_apply_loop_marks_unknown_table_row_failed_not_silent(
    pg_engine, alembic_upgrade
) -> None:
    """A tabla outside the catalog AND outside OUT_OF_CATALOG is a real
    anomaly — mark_failed, never a silent drop."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        unknown_row = await sq_helpers.enqueue(
            session,
            "insert",
            "not_a_real_table",
            uuid_lib.uuid4(),
            {},
            None,
        )
        await session.commit()

        worker = SyncCloudWorker(session=session)
        settled = await worker._apply_pending_batch_once()
        await session.commit()

        assert settled >= 1

        estado, ultimo_error = (
            await session.execute(
                select(SyncQueue.estado, SyncQueue.ultimo_error).where(
                    SyncQueue.uuid == unknown_row.uuid
                )
            )
        ).one()
        # mark_failed re-queues as 'pendiente' with the error recorded
        # (repo.sync_queue.mark_failed's documented contract) — never
        # silently dropped or left unexplained.
        assert estado == "pendiente"
        assert ultimo_error == "unknown_table"


async def test_apply_loop_isolates_one_poisoned_row_via_per_row_fallback(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    """A real, pre-existing gap discovered wiring this loop against a real
    shared test DB: some OTHER row already 'pendiente' in the same session-
    scoped ``sync_queue`` can carry a payload ``apply_row`` cannot bind
    (e.g. a stray key), which aborts ``apply_batch`` for the WHOLE batch.
    One poisoned row must not block a genuinely applicable sibling row in
    the same batch — the fallback settles both, isolating the bad one."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal = v_fixture_factory.build(Sucursal)
        session.add(sucursal)
        await session.commit()

        cedula = f"cd-{uuid_lib.uuid4().hex[:12]}"
        good_row = await sq_helpers.enqueue(
            session,
            "insert",
            "usuarios",
            uuid_lib.uuid4(),
            {
                "nombre": "Grace",
                "apellido": "Hopper",
                "cedula": cedula,
                "email": "grace@example.com",
                "rol": "operador",
            },
            None,
        )
        poisoned_row = await sq_helpers.enqueue(
            session,
            "insert",
            "caja",
            uuid_lib.uuid4(),
            {
                "uuid_sucursal": str(sucursal.uuid),
                "valor_efectivo": "10.00",
                "valor_datafono": "0.00",
                # Not a real Caja column and not stripped by
                # _business_payload_for_apply — forces model_cls(**payload)
                # to raise TypeError for THIS row only.
                "not_a_real_caja_column": "poison",
            },
            sucursal.uuid,
        )
        await session.commit()

        worker = SyncCloudWorker(session=session)
        settled = await worker._apply_pending_batch_once()
        await session.commit()

        assert settled >= 2

        usuarios_count = (
            await session.execute(
                select(func.count()).select_from(Usuarios).where(Usuarios.cedula == cedula)
            )
        ).scalar_one()
        assert usuarios_count == 1

        good_estado = (
            await session.execute(
                select(SyncQueue.estado).where(SyncQueue.uuid == good_row.uuid)
            )
        ).scalar_one()
        assert good_estado == "exitoso"

        poisoned_estado, poisoned_error = (
            await session.execute(
                select(SyncQueue.estado, SyncQueue.ultimo_error).where(
                    SyncQueue.uuid == poisoned_row.uuid
                )
            )
        ).one()
        assert poisoned_estado == "pendiente"
        assert poisoned_error is not None
