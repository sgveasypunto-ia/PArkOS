"""test_sync_sesion_cierre.py — SS1: the closing of a ``sesion`` reaches the cloud.

Root causes pinned here (real Docker evidence, 2026-10-07):

  1. ``sesion_enqueue_sync`` fired on INSERT only. Closing a sesion is an
     UPDATE of an [L-S] lifecycle row, so nothing was enqueued: the cloud kept
     the sesion ACTIVE forever, the same operator's next sesion violated
     ``uq_prod_sesion_one_active_per_user`` and every child row (arqueo,
     factura_pagos, ...) failed its FK until ``fallido``.
  2. ``fn_enqueue_sync`` stamped ``TG_TABLE_NAME`` — the PHYSICAL partition
     (``log_transaccional_p_2026_10``) — into ``sync_queue.tabla``; the cloud's
     own drain loop does not normalize it and settled it ``unknown_table``.

The "cloud" leg is simulated against the same schema: the branch leg runs inside
a transaction whose queue rows are captured and then rolled back (a rollback is
not a DELETE), and the captured payloads are re-enqueued — one commit each, as
the wire does — and drained by the REAL ``SyncCloudWorker`` apply loop.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from typing import Any

import pytest
from parkos_core.jobs.sync_cloud import SyncCloudWorker
from parkos_core.models.A.caja import Caja
from parkos_core.models.A.log_transaccional import LogTransaccional
from parkos_core.models.A.sync_queue import SyncQueue
from parkos_core.models.L_S.sesion import Sesion
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.repo import session_cycle
from parkos_core.repo import sync_queue as sq_helpers
from parkos_core.repo.hash_chain import _ensure_genesis_row
from parkos_core.runtime import engine_flag
from parkos_core.sync.motor import apply_guard
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.fixture(autouse=True)
def _catalog_engine_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
    engine_flag._reset_cache_for_tests()


async def _seed_sucursal_and_user(
    session: AsyncSession, v_fixture_factory: Any
) -> tuple[Sucursal, Usuarios]:
    sucursal = v_fixture_factory.build(Sucursal)
    session.add(sucursal)
    await session.commit()
    # Per-sucursal hash chain needs its own genesis row before any log write.
    await _ensure_genesis_row(session, LogTransaccional, sucursal.uuid)
    await session.commit()
    user = Usuarios(
        nombre="Ada",
        apellido="Lovelace",
        cedula=f"cd-{uuid_lib.uuid4().hex[:12]}",
        email=f"ada-{uuid_lib.uuid4().hex[:6]}@example.com",
        rol="operador",
    )
    session.add(user)
    await session.commit()
    return sucursal, user


async def _sesion_queue_rows(session: AsyncSession) -> list[SyncQueue]:
    rows = (
        (await session.execute(select(SyncQueue).where(SyncQueue.tabla == "sesion")))
        .scalars()
        .all()
    )
    return sorted(rows, key=lambda r: int(r.datos["seq"]))


async def test_closing_a_sesion_enqueues_an_update_row(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal, user = await _seed_sucursal_and_user(session, v_fixture_factory)
        actor = user.uuid
        sesion = await session_cycle.open_session(
            session,
            actor_uuid=actor,
            uuid_sucursal=sucursal.uuid,
            valor_inicial_efectivo=1000,
            valor_inicial_datafono=0,
            uuid_usuario=user.uuid,
        )
        await session_cycle.close_session_with_log(
            session, actor_uuid=actor, sesion_uuid=sesion.uuid
        )
        rows = [r for r in await _sesion_queue_rows(session) if r.uuid_registro == sesion.uuid]
        assert [r.operacion for r in rows] == ["INSERT", "UPDATE"]
        assert rows[0].datos["timestamp_cierre"] is None
        assert rows[1].datos["timestamp_cierre"] is not None
        assert rows[1].datos["estado"] == "cerrado"
        assert rows[1].uuid_sucursal == sucursal.uuid
        await session.rollback()


async def test_closing_a_sesion_applied_from_sync_does_not_echo(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    """The sync motor's own close (GUC set) must NOT re-enqueue: no ping-pong."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal, user = await _seed_sucursal_and_user(session, v_fixture_factory)
        actor = user.uuid
        await apply_guard.enable_echo_suppression(session)
        sesion = await session_cycle.open_session(
            session,
            actor_uuid=actor,
            uuid_sucursal=sucursal.uuid,
            valor_inicial_efectivo=1000,
            valor_inicial_datafono=0,
            uuid_usuario=user.uuid,
        )
        await session_cycle.close_session_with_log(
            session, actor_uuid=actor, sesion_uuid=sesion.uuid
        )
        rows = [r for r in await _sesion_queue_rows(session) if r.uuid_registro == sesion.uuid]
        assert rows == []
        await session.rollback()


async def test_partitioned_table_rows_are_enqueued_with_the_parent_name(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    """``TG_TABLE_NAME`` on a partition is the child name; the queue must carry
    the logical table (``caja``), never ``caja_p_...`` / ``caja_default``."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal = v_fixture_factory.build(Sucursal)
        session.add(sucursal)
        await session.commit()
        caja = Caja(uuid_sucursal=sucursal.uuid, valor_efectivo="100.00", valor_datafono="0.00")
        session.add(caja)
        await session.flush()
        tablas = (
            (
                await session.execute(
                    select(SyncQueue.tabla).where(SyncQueue.uuid_registro == caja.uuid)
                )
            )
            .scalars()
            .all()
        )
        assert tablas == ["caja"]
        await session.rollback()


async def _capture_branch_leg(
    pg_engine, v_fixture_factory
) -> tuple[Sucursal, Usuarios, list[dict[str, Any]], list[uuid_lib.UUID]]:
    """Branch leg: open S1, close S1, open S2 (same user). Returns the captured
    wire rows in seq order, then rolls the whole transaction back."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal, user = await _seed_sucursal_and_user(session, v_fixture_factory)
    async with Session() as session:
        actor = user.uuid
        s1 = await session_cycle.open_session(
            session,
            actor_uuid=actor,
            uuid_sucursal=sucursal.uuid,
            valor_inicial_efectivo=1000,
            valor_inicial_datafono=0,
            uuid_usuario=user.uuid,
        )
        await session_cycle.close_session_with_log(session, actor_uuid=actor, sesion_uuid=s1.uuid)
        s2 = await session_cycle.open_session(
            session,
            actor_uuid=actor,
            uuid_sucursal=sucursal.uuid,
            valor_inicial_efectivo=2000,
            valor_inicial_datafono=0,
            uuid_usuario=user.uuid,
        )
        rows = [
            {"operacion": r.operacion, "uuid_registro": r.uuid_registro, "datos": dict(r.datos)}
            for r in await _sesion_queue_rows(session)
            if r.uuid_registro in (s1.uuid, s2.uuid)
        ]
        await session.rollback()
    return sucursal, user, rows, [s1.uuid, s2.uuid]


async def _replay_on_cloud(pg_engine, sucursal: Sucursal, rows: list[dict[str, Any]]) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    for row in rows:
        async with Session() as session:
            await sq_helpers.enqueue(
                session,
                row["operacion"].lower(),
                "sesion",
                row["uuid_registro"],
                row["datos"],
                sucursal.uuid,
                # Same priority the DB trigger stamps (1) for every sesion event.
                prioridad=1,
            )
            await session.commit()
    async with Session() as session:
        worker = SyncCloudWorker(session=session, apply_batch_limit=100_000)
        for _ in range(3):  # one pass settles; extra passes prove idempotence
            await worker._apply_pending_batch_once()
            await session.commit()


async def test_sesion_open_close_reopen_converges_on_the_cloud(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    sucursal, user, rows, (s1, s2) = await _capture_branch_leg(pg_engine, v_fixture_factory)
    assert [r["operacion"] for r in rows] == ["INSERT", "UPDATE", "INSERT"]

    await _replay_on_cloud(pg_engine, sucursal, rows)

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        first = (await session.execute(select(Sesion).where(Sesion.uuid == s1))).scalar_one()
        second = (await session.execute(select(Sesion).where(Sesion.uuid == s2))).scalar_one()
        # The cloud shows the sesion CLOSED, at the ORIGIN's closing time.
        assert first.timestamp_cierre is not None
        assert first.estado == "cerrado"
        assert first.timestamp_cierre == datetime.fromisoformat(rows[1]["datos"]["timestamp_cierre"])
        assert first.timestamp_apertura == datetime.fromisoformat(
            rows[0]["datos"]["timestamp_apertura"]
        )
        # ... and the next sesion of the same user was accepted (still open).
        assert second.timestamp_cierre is None
        queue = (
            (await session.execute(select(SyncQueue).where(SyncQueue.tabla == "sesion")))
            .scalars()
            .all()
        )
        mine = [q for q in queue if q.uuid_registro in (s1, s2)]
        assert len(mine) == 3
        assert {q.estado for q in mine} == {"exitoso"}, [q.ultimo_error for q in mine]


async def test_sesion_close_replayed_before_its_open_is_retried_not_lost(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    """A close that outruns its open fails ``not found`` and stays retryable
    (``pendiente``); once the open lands, a re-run closes it."""
    sucursal, _user, rows, (s1, _s2) = await _capture_branch_leg(pg_engine, v_fixture_factory)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    await _replay_on_cloud(pg_engine, sucursal, [rows[1]])
    async with Session() as session:
        q = (
            await session.execute(select(SyncQueue).where(SyncQueue.uuid_registro == s1))
        ).scalar_one()
        assert q.estado == "pendiente"
        assert q.intentos == 1


async def test_partition_named_self_origin_row_is_settled_not_unknown_table(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    """Rows written by the pre-0092 trigger carry the PHYSICAL partition name.
    The cloud drain normalizes it and, because the row's own uuid already exists
    here (it originated on this node), settles it instead of ``unknown_table``
    — and never re-applies it (that would extend the hash chain twice)."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal, _user = await _seed_sucursal_and_user(session, v_fixture_factory)
        log_uuid = (
            await session.execute(
                select(LogTransaccional.uuid).where(
                    LogTransaccional.uuid_sucursal == sucursal.uuid
                )
            )
        ).scalars().first()
        assert log_uuid is not None
        before = len(
            (await session.execute(select(LogTransaccional.uuid))).scalars().all()
        )
        stale = await sq_helpers.enqueue(
            session,
            "insert",
            "log_transaccional_p_2026_10",
            log_uuid,
            {"uuid": str(log_uuid), "accion": "crear", "tabla_afectada": "sesion"},
            sucursal.uuid,
            prioridad=1,
        )
        await session.commit()

        await SyncCloudWorker(
            session=session, apply_batch_limit=100_000
        )._apply_pending_batch_once()
        await session.commit()

        row = (
            await session.execute(select(SyncQueue).where(SyncQueue.uuid == stale.uuid))
        ).scalar_one()
        assert row.estado == "exitoso", row.ultimo_error
        after = len((await session.execute(select(LogTransaccional.uuid))).scalars().all())
        assert after == before, "a self-origin log row must never be re-applied"
