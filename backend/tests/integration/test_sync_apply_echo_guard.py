"""test_sync_apply_echo_guard.py — regression coverage for the echo-
amplification fix (post-PR14 real-Docker closing exercise, real defect #3;
migration ``0016_add_sync_apply_guard``, ``sync.motor.apply_guard``).

Confirmed against the REAL Docker deployment (not testcontainers, see
``openspec/changes/sync-overhaul/tasks.md``'s post-PR14 closing exercise):
``fn_enqueue_sync()``/``fn_enqueue_sync_catalog()`` fired unconditionally on
every INSERT, including the ones the sync motor itself performed while
applying an event that had already arrived via sync — the echo row got
re-applied by ``job-sync-cloud``'s own apply loop, extending the
``log_transaccional``/``revocacion_factura`` SHA-256 hash chain a SECOND time
for the same logical event (``motor.verify_chain`` confirmed dozens of real
``ChainAnomaly`` breaks).

Three levels of proof, against a real Postgres container:

  1. ``fn_enqueue_sync_catalog()`` (the 18-table ``[V]`` function, ``usuarios``
     as the fixture table) — a plain INSERT still enqueues normally; the SAME
     INSERT with ``parkos.sync_apply_in_progress`` set does NOT.
  2. ``fn_enqueue_sync()`` (the 30-table legacy function, ``caja`` as the
     fixture table — an ``[A]`` table, proving the fix covers BOTH functions,
     not just the newer catalog one).
  3. End to end through the REAL wired call site
     (``SyncCloudWorker._apply_pending_batch_once``): a manually-enqueued
     ``usuarios`` row is applied, and the resulting REAL ``usuarios`` row
     (found by its unique ``cedula``) produces ZERO echo ``sync_queue`` rows —
     the exact symptom confirmed in Docker, now closed.
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
from parkos_core.sync.motor import apply_guard
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker


@pytest.fixture(autouse=True)
def _catalog_engine_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """The end-to-end test drives ``SyncCloudWorker`` through the catalog
    engine, matching every other ``test_sync_cloud_catalog_driven.py`` test."""
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
    engine_flag._reset_cache_for_tests()


async def test_fn_enqueue_sync_catalog_skips_when_guard_active(pg_engine, alembic_upgrade) -> None:
    """``fn_enqueue_sync_catalog()`` (0014, 18-table [V] function): a plain
    INSERT into ``usuarios`` still enqueues normally (regression — the guard
    must NOT break a genuinely new, locally-originated write); the SAME
    INSERT with ``parkos.sync_apply_in_progress='true'`` set does NOT."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    # 1. No guard active — a "new business row" (e.g. an admin creating a
    #    user from the UI) must enqueue exactly as before this fix.
    async with Session() as session:
        cedula_normal = f"cd-{uuid_lib.uuid4().hex[:12]}"
        row = Usuarios(
            nombre="Ada",
            apellido="Lovelace",
            cedula=cedula_normal,
            email="ada@example.com",
            rol="operador",
        )
        session.add(row)
        await session.flush()
        new_uuid = row.uuid

        queued_count = (
            await session.execute(
                select(func.count())
                .select_from(SyncQueue)
                .where(SyncQueue.tabla == "usuarios", SyncQueue.uuid_registro == new_uuid)
            )
        ).scalar_one()
        assert queued_count == 1, "a normal INSERT must still enqueue (no regression)"
        await session.rollback()

    # 2. Guard active — the SAME shape of INSERT must NOT enqueue.
    async with Session() as session:
        await apply_guard.enable_echo_suppression(session)

        cedula_echo = f"cd-{uuid_lib.uuid4().hex[:12]}"
        row = Usuarios(
            nombre="Grace",
            apellido="Hopper",
            cedula=cedula_echo,
            email="grace@example.com",
            rol="operador",
        )
        session.add(row)
        await session.flush()
        new_uuid = row.uuid

        queued_count = (
            await session.execute(
                select(func.count())
                .select_from(SyncQueue)
                .where(SyncQueue.tabla == "usuarios", SyncQueue.uuid_registro == new_uuid)
            )
        ).scalar_one()
        assert queued_count == 0, "the echo-suppression GUC must skip the enqueue"
        await session.rollback()


async def test_fn_enqueue_sync_skips_when_guard_active(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    """``fn_enqueue_sync()`` (0001, 30-table legacy function): same proof as
    above, exercised via ``caja`` ([A], one of the ``CASE``-listed tables) —
    confirms the fix covers BOTH trigger functions, not just the newer one."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        sucursal = v_fixture_factory.build(Sucursal)
        session.add(sucursal)
        await session.commit()

        # 1. No guard — normal INSERT enqueues.
        caja_normal = Caja(
            uuid_sucursal=sucursal.uuid,
            valor_efectivo="100.00",
            valor_datafono="50.00",
        )
        session.add(caja_normal)
        await session.flush()
        normal_uuid = caja_normal.uuid

        # NOT filtered by `tabla == "caja"` — `caja` is one of the 8
        # pg_partman-partitioned tables, so `TG_TABLE_NAME` (and therefore
        # `sync_queue.tabla`) is the CHILD partition's name (e.g.
        # `caja_p_current`), not the parent `caja`
        # (`catalog/sync_catalog.py::resolve_catalog_name`'s own docstring).
        # `uuid_registro` alone is already a precise, unique filter here.
        queued_count = (
            await session.execute(
                select(func.count())
                .select_from(SyncQueue)
                .where(SyncQueue.uuid_registro == normal_uuid)
            )
        ).scalar_one()
        assert queued_count == 1, "a normal INSERT must still enqueue (no regression)"

        # 2. Guard active — same shape of INSERT must NOT enqueue.
        await apply_guard.enable_echo_suppression(session)

        caja_echo = Caja(
            uuid_sucursal=sucursal.uuid,
            valor_efectivo="10.00",
            valor_datafono="0.00",
        )
        session.add(caja_echo)
        await session.flush()
        echo_uuid = caja_echo.uuid

        queued_count = (
            await session.execute(
                select(func.count())
                .select_from(SyncQueue)
                .where(SyncQueue.uuid_registro == echo_uuid)
            )
        ).scalar_one()
        assert queued_count == 0, "the echo-suppression GUC must skip the enqueue"

        await session.rollback()


async def test_apply_pending_batch_once_does_not_echo_reapplied_row(
    pg_engine, alembic_upgrade
) -> None:
    """End to end through the REAL wired call site
    (``SyncCloudWorker._apply_pending_batch_once``, ``jobs/sync_cloud.py``):
    applying an incoming ``usuarios`` row must NOT produce an echo
    ``sync_queue`` row for the newly-applied row — the exact symptom
    confirmed against real Docker containers (dozens of ``ChainAnomaly``
    breaks on ``log_transaccional``/``revocacion_factura`` before this fix)."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        cedula = f"cd-{uuid_lib.uuid4().hex[:12]}"
        queue_row = await sq_helpers.enqueue(
            session,
            "insert",
            "usuarios",
            uuid_lib.uuid4(),
            {
                "nombre": "Katherine",
                "apellido": "Johnson",
                "cedula": cedula,
                "email": "katherine@example.com",
                "rol": "operador",
            },
            None,
        )
        await session.commit()

        worker = SyncCloudWorker(session=session)
        settled = await worker._apply_pending_batch_once()
        await session.commit()
        assert settled >= 1

        # The row really was applied (unchanged behavior).
        new_uuid = (
            await session.execute(select(Usuarios.uuid).where(Usuarios.cedula == cedula))
        ).scalar_one()

        estado = (
            await session.execute(
                select(SyncQueue.estado).where(SyncQueue.uuid == queue_row.uuid)
            )
        ).scalar_one()
        assert estado == "exitoso"

        # The fix: the trigger fired again on the motor's own write into
        # `usuarios` (AFTER INSERT), but with the echo-suppression GUC
        # active for the whole `_apply_pending_batch_once` call, it must
        # NOT have enqueued another `sync_queue` row for this real new uuid.
        echo_count = (
            await session.execute(
                select(func.count())
                .select_from(SyncQueue)
                .where(SyncQueue.tabla == "usuarios", SyncQueue.uuid_registro == new_uuid)
            )
        ).scalar_one()
        assert echo_count == 0, "the motor's own apply must not re-enqueue an echo row"
