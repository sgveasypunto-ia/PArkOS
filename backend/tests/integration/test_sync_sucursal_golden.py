"""Integration — golden invariants for the ``job_sync_sucursal`` publisher.

Two things this file pins that the unit files cannot:

- D1  The outbox is a GOLDEN ledger: whatever wire status the cloud returns
      (``applied`` / ``events_*`` / ``http_5xx`` / ``result_count_mismatch``),
      a ``sync_queue`` row is never duplicated, never lost, and only ever
      sits in ``{exitoso, pendiente}``. Failures re-queue (``mark_failed``
      sets ``pendiente`` + a future ``next_retry_at``, never a terminal
      ``fallido``), so the same logical row keeps the same ``uuid`` forever.
- D2  A catalog pull of rows that arrive via sync must (a) apply each remote
      ``uuid`` EXACTLY once and (b) never echo itself back into ``sync_queue``
      (the ``parkos.sync_apply_in_progress`` GUC, ``apply_guard``).

Same shared-DB scope decision as ``test_sync_sucursal_cycle.py``: these
tests drive the dual-protocol checkout paths through mocks, so the shared
engine only ever sees branch-side state and never crosses the physical
boundary (the 2-container e2e owns that half).
"""

from __future__ import annotations

import uuid as uuid_lib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.models.V.clientes import Clientes
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from parkos_core.repo import sync_queue as sq_helpers
from parkos_core.sync.transport import EventsPushResponse, PullResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


@pytest.fixture(autouse=True)
def _catalog_engine_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from parkos_core.runtime import engine_flag

    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
    engine_flag._reset_cache_for_tests()


@pytest.fixture
def jwt_file(tmp_path: Path) -> Path:
    p = tmp_path / "sync.jwt"
    p.write_text("test-jwt-token", encoding="utf-8")
    return p


def uid() -> str:
    return uuid_lib.uuid4().hex[:8]


def _make_worker(branch_session, jwt_file: Path):
    from parkos_core.jobs.sync_sucursal import SyncSucursalWorker

    return SyncSucursalWorker(
        jwt_path=jwt_file,
        base_url="http://cloud",
        session=branch_session,
    )


def _enqueue_caja_row(session, *, determinista: str | None = None) -> uuid_lib.UUID:
    """Enqueue one branded ``caja`` row (mock-driven push; never hits a DB
    receiver on the shared engine, so no sucursal parent is required)."""
    R = uuid_lib.uuid4()
    return R


# ---------------------------------------------------------------------------
# D1 — the outbox is a golden ledger across every wire status
# ---------------------------------------------------------------------------


class TestGoldenOutboxInvariant:
    async def test_rows_are_never_duplicated_lost_or_terminally_failed(
        self,
        pg_engine: AsyncEngine,
        alembic_upgrade: None,
        jwt_file: Path,
    ) -> None:
        """Three rows survive a hostile status playbook WITHOUT ever being
        duplicated, lost, or parked in an illegal state. Each round re-picks
        exactly the still-pending rows through the REAL ``list_pending``
        selection the worker uses, then settles them against a mocked wire.
        The invariant holds after EVERY round: same 3 uuids, states ⊆
        {exitoso, pendiente}, count == 3."""
        Session = async_sessionmaker(pg_engine, expire_on_commit=False)
        async with Session() as branch_session:
            worker = _make_worker(branch_session, jwt_file)
            worker._http_client = MagicMock()
            push_mock = AsyncMock(
                side_effect=[
                    # Round 1 — three rows: applied / applied / unknown_table
                    EventsPushResponse(
                        status=207,
                        results=[
                            {"event_type": "caja", "status": "applied"},
                            {"event_type": "caja", "status": "applied"},
                            {"event_type": "caja", "status": "events_unknown_table"},
                        ],
                    ),
                    # Round 2 — the one failure above re-picked: hard 5xx
                    EventsPushResponse(status=503, results=[]),
                    # Round 3 — 207 with a SHORTER results list than rows
                    # sent (result_count_mismatch must never guess a
                    # correlation)
                    EventsPushResponse(status=207, results=[]),
                    # Round 4 — recovery
                    EventsPushResponse(
                        status=207,
                        results=[{"event_type": "caja", "status": "applied"}],
                    ),
                ]
            )
            worker._http_client.push_events = push_mock

            uuids: set[uuid_lib.UUID] = set()
            for _ in range(3):
                R = _enqueue_caja_row(branch_session, determinista=uid())
                uuids.add(R)
                await sq_helpers.enqueue(
                    branch_session,
                    "insert",
                    "caja",
                    R,
                    {"uuid": str(R), "valor_efectivo": 1, "valor_datafono": 0},
                    uuid_sucursal=None,
                )
            await branch_session.commit()

            # ===== Rounds: replay the real worker selection each time =====
            for _ in range(14):
                # Bug 8's fix makes list_pending gate on next_retry_at, so a
                # mark_failed row would stay OUT of the selection mid-backoff.
                # To replay the playbook (each round re-settles whatever the
                # REAL selection returns) we advance the clock explicitly:
                # clear next_retry_at for our tracked rows so the backoff
                # window counts as elapsed.
                await branch_session.execute(
                    update(sq_helpers.SyncQueue)
                    .where(sq_helpers.SyncQueue.uuid_registro.in_(uuids))  # type: ignore[arg-type]
                    .values(next_retry_at=None)
                )
                await branch_session.commit()

                pending = await sq_helpers.list_pending(branch_session, limit=500)
                own = [r for r in pending if r.uuid_registro in uuids]
                if not own:
                    break  # every round settled — nothing left to push
                await worker._push_and_handle_catalog(own)
                await branch_session.commit()

                fresh = async_sessionmaker(pg_engine, expire_on_commit=False)
                async with fresh() as session:
                    rows = (
                        await session.execute(
                            select(sq_helpers.SyncQueue).where(
                                sq_helpers.SyncQueue.uuid_registro.in_(uuids)  # type: ignore[arg-type]
                            )
                        )
                    ).scalars().all()
                assert len(rows) == len(uuids), "a row was duplicated or lost"
                states = {r.estado for r in rows}
                assert states <= {"exitoso", "pendiente"}, (
                    f"illegal terminal state(s): {states - {'exitoso', 'pendiente'}}"
                )
                assert len({r.uuid_registro for r in rows}) == len(uuids), (
                    "the same logical uuid appeared more than once"
                )

            # Final state: the playbook's last round is recovery → all three
            # queued rows are exitoso exactly once each.
            fresh = async_sessionmaker(pg_engine, expire_on_commit=False)
            async with fresh() as session:
                final = (
                    await session.execute(
                        select(sq_helpers.SyncQueue.estado).where(
                            sq_helpers.SyncQueue.uuid_registro.in_(uuids)  # type: ignore[arg-type]
                        )
                    )
                ).scalars().all()
            assert set(final) == {"exitoso"}
            assert len(final) == 3


# ---------------------------------------------------------------------------
# D2 — a catalog pull applies each row once and echoes nothing back
# ---------------------------------------------------------------------------


class TestCatalogPullEchoSweep:
    async def test_two_entries_applied_once_and_zero_echo_rows(
        self,
        pg_engine: AsyncEngine,
        alembic_upgrade: None,
        jwt_file: Path,
    ) -> None:
        """Push-cloud rows for TWO different catalog entries delivered twice
        must land exactly one local row each, and ``sync_queue`` must show
        ZERO echo rows for those ``uuid_registro`` values after the full
        cycle commits (the GUC suppresses the branch enqueue trigger on the
        motor's own inserts)."""
        Session = async_sessionmaker(pg_engine, expire_on_commit=False)
        async with Session() as branch_session:
            worker = _make_worker(branch_session, jwt_file)
            worker._http_client = MagicMock()

            T1 = uuid_lib.uuid4()
            C1 = uuid_lib.uuid4()
            tipo = f"moto-{uid()}"
            nid = f"cc-{uid()}"
            rows = [
                {
                    "tabla": "tipos_vehiculo",
                    "uuid_registro": str(T1),
                    "datos": {"uuid": str(T1), "tipo": tipo},
                },
                {
                    "tabla": "clientes",
                    "uuid_registro": str(C1),
                    "datos": {
                        "uuid": str(C1),
                        "tipo_identificador": "CC",
                        "numero_identificacion": nid,
                        "nombre": "Ana",
                        "apellido": "Lopez",
                    },
                },
            ]
            worker._http_client.pull = AsyncMock(
                return_value=PullResponse(status=200, rows=rows, next_seq=1)
            )

            await worker._pull_and_apply_catalog()
            await worker._pull_and_apply_catalog()
            await branch_session.commit()

            fresh = async_sessionmaker(pg_engine, expire_on_commit=False)
            async with fresh() as session:
                tipov_count = (
                    await session.execute(
                        select(func.count(TiposVehiculo.uuid)).where(TiposVehiculo.tipo == tipo)
                    )
                ).scalar_one()
                cliente_count = (
                    await session.execute(
                        select(func.count(Clientes.uuid)).where(
                            Clientes.numero_identificacion == nid
                        )
                    )
                ).scalar_one()
                echo = (
                    await session.execute(
                        select(func.count(sq_helpers.SyncQueue.uuid)).where(
                            sq_helpers.SyncQueue.uuid_registro.in_([T1, C1])  # type: ignore[arg-type]
                        )
                    )
                ).scalar_one()

            assert tipov_count == 1
            assert cliente_count == 1
            assert echo == 0, "the pull must never echo its own applied rows"