"""test_sync_cloud_concurrent_sessions.py — regression coverage for the
confirmed real-Docker-boot concurrency defect (2026-09-09).

``docker logs parkos-job-sync-cloud`` showed, right at container startup::

    [error] sync_cloud.verifier_loop_failed error='This session is
    provisioning a new connection; concurrent operations are not
    permitted (Background on this error at: https://sqlalche.me/e/20/isce)'

Root cause: ``SyncCloudWorker.__init__`` took ONE ``AsyncSession`` and
stored it as ``self._session``; ``cycle()`` starts ``_apply_pending_loop``
and ``_hash_chain_verifier_loop`` as TWO concurrent ``asyncio.create_task``
siblings, both reading/writing that SAME session instance. SQLAlchemy's
``AsyncSession`` is not safe for concurrent use across coroutines — whenever
both tasks' first query landed on the same event-loop tick (exactly what
happens at boot, since both tasks are created back to back on ``cycle()``'s
first iteration), the session raised the error above. The outer
``try/except`` in each loop swallowed it and kept the loop alive, so the
failure was silent in production — but it could make the hash-chain
verifier ("the most important defensive layer for DIAN compliance" per its
own docstring) skip an entire sweep on any iteration where the timing
coincided.

Fix: ``SyncCloudWorker`` accepts an optional ``session_factory``; when set,
each loop iteration opens (and commits) its OWN fresh session instead of
sharing ``self._session``. This test proves the fix the way the defect
actually manifested: it runs ONE apply iteration and ONE verify iteration —
each opening a genuinely independent session from the SAME factory, against
the SAME real Postgres container — truly in parallel via ``asyncio.gather``,
across several rounds to maximize the chance of the two sessions' first
queries landing on the same event-loop tick (the exact boot-time race).
Mocking a session cannot reproduce this: the defect is specific to
SQLAlchemy's real connection-provisioning state machine.
"""

from __future__ import annotations

import asyncio
import uuid as uuid_lib

import pytest
from parkos_core.jobs.sync_cloud import SyncCloudWorker
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.repo import sync_queue as sq_helpers
from parkos_core.runtime import engine_flag
from sqlalchemy.ext.asyncio import async_sessionmaker


@pytest.fixture(autouse=True)
def _catalog_engine_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """The apply side drains real sync_queue rows through SyncMotor —
    matches every other ``_apply_pending_batch_once`` integration test."""
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
    engine_flag._reset_cache_for_tests()


async def test_apply_and_verify_iterations_run_concurrently_without_session_conflict(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    """Real, DB-backed reproduction of the boot-time session race.

    Three rounds: each round seeds one real ``sync_queue`` row (so the
    apply-side iteration does genuine work — list_pending + apply, not an
    empty no-op query) and then runs one apply iteration and one verify
    iteration truly concurrently, each with its OWN session opened from the
    SAME ``session_factory``. Before the fix (a single shared
    ``self._session``), this exact pattern is what tripped SQLAlchemy's
    "concurrent operations are not permitted" guard.
    """
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as boot_session:
        worker = SyncCloudWorker(session=boot_session, session_factory=Session)

        async def _seed_one_pending_row() -> None:
            async with Session() as seed_session:
                sucursal = v_fixture_factory.build(Sucursal)
                seed_session.add(sucursal)
                await seed_session.commit()
                cedula = f"cd-{uuid_lib.uuid4().hex[:12]}"
                await sq_helpers.enqueue(
                    seed_session,
                    "insert",
                    "usuarios",
                    uuid_lib.uuid4(),
                    {
                        "nombre": "Concurrent",
                        "apellido": "Tester",
                        "cedula": cedula,
                        "email": f"{cedula}@example.com",
                        "rol": "operador",
                    },
                    None,
                )
                await seed_session.commit()

        async def _apply_iteration() -> None:
            async with worker._session_factory() as session:
                await worker._apply_pending_batch_once(session=session)

        async def _verify_iteration() -> None:
            async with worker._session_factory() as session:
                await worker._verify_hash_chains_once(session=session)
                await worker._verify_revocacion_factura_chain_once(session=session)
                await session.commit()

        for _ in range(3):
            await _seed_one_pending_row()

            # Genuinely concurrent — both coroutines issue their FIRST
            # session.execute() at essentially the same event-loop tick,
            # exactly the timing that tripped the bug at container boot.
            results = await asyncio.gather(
                _apply_iteration(), _verify_iteration(), return_exceptions=True
            )

            failures = [r for r in results if isinstance(r, BaseException)]
            assert failures == [], (
                "a concurrent loop iteration raised — the shared-session "
                f"regression may have reappeared: {failures!r}"
            )
