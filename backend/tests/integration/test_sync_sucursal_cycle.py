"""Integration — ``job_sync_sucursal`` worker CYCLE against a real router.

Complements the unit files (``test_sync_sucursal_catalog_push.py``,
``test_sync_sucursal_helpers.py``) and the 2-container e2e
(``test_e2e_full_catalog_sync.py``). The e2e proves each of the 46 catalog
entries syncs across TWO real physical Postgres containers; THIS file proves
the publisher worker's *cycle mechanics* + *real wire round trips* against a
real ``sync_router`` FastAPI app.

Scope decision — shared DB (disclosed, deliberate):

- Branch-side database and cloud-side database are the SAME physical
  Postgres in this file (root conftest's session-scoped ``pg_engine``),
  unlike the e2e's two containers. This makes the PULL leg of a ``[V]`` row
  safe (the ``apply_guard.row_already_present`` guard at
  ``sync_motor.apply_row`` — plus ``_pull_and_apply_catalog``'s own
  ``uuid_registro`` check — dedup against the same physical rows), but makes
  the PUSH leg of an ``[A]``/``[L-*]`` row UNSOUND by construction (the
  cloud-side receiver would re-insert the SAME ``uuid`` into the SAME
  physical table → PK collision that exists only because branch and cloud
  are one database; the e2e's second container is the honest home for those).
- Consequence: the full ``cycle()`` is asserted on an EMPTY (drained) queue,
  and the push leg is exercised only with ``[V]`` rows (the wire strips
  ``uuid`` for ``[V]``, so the cloud insert always lands a fresh uuid and
  never collides on the shared table).

Observed while wiring this file (disclosed — NOT fixed here):

1. ``repo.sync_queue.list_pending``'s WHERE clause evaluated ONLY
   ``estado = 'pendiente'`` (Bug 8, FIXED in
   ``fix/sync-jwt-queue-wire``): a row re-queued by ``mark_failed`` with a
   future ``next_retry_at`` was picked straight back up next cycle, making
   the backoff schedule decorative. Covered by
   ``TestBackoffRespectedByListPending``.
2. ``_business_payload_for_apply`` (jobs/sync_cloud.py) strips ``uuid``
   from every ``[V]`` payload before it goes on the wire (Bug 2). On a real
   two-DB deployment that alone breaks identity; on this shared-DB file it
   means a ``[V]`` push never proves "same uuid arrived" — the two Bug 2
   tests below pin the DESIRED contract as strict xfails (fixed in
   ``fix/sync-catalog-identity``).

Session idiom: follows the DB integration files (e.g.
``test_apply_pending_no_self_duplicate.py``) — tests take ``pg_engine`` /
``alembic_upgrade`` as arguments and open inline sessions, never a
function-scoped async fixture (pytest-asyncio 1.4.0 rejects nested runners
on the session loop).
"""

from __future__ import annotations

import asyncio
import time
import uuid as uuid_lib
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from parkos_core.models.V.clientes import Clientes
from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.tipo_subscripciones import TipoSubscripciones
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from parkos_core.repo import sync_queue as sq_helpers
from parkos_core.sync.motor import apply_guard
from parkos_core.sync.transport import PullResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000c0001")


@pytest.fixture(autouse=True)
def _catalog_engine_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirror the e2e/``test_sync_cloud_catalog_driven.py`` fixture so the
    SAME ``PARKOS_SYNC_ENGINE`` flag is honored consistently in this file."""
    from parkos_core.runtime import engine_flag

    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
    engine_flag._reset_cache_for_tests()


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _pristine_log_transaccional(pg_engine: AsyncEngine) -> None:
    """Start this module with a pristine sync infrastructure.

    The file's tests append to the shared-DB hash chain under
    ``uuid_sucursal IS NULL`` (the worker's own ``_record_event``). Rows
    committed by an EARLIER module or partial run persist in the
    session-scoped engine's shared Postgres and make the chain head (and
    the genesis uuid the worker's ``_read_prior_hash`` re-bootstraps) NOT
    equal what a fresh producer run would build — a second attempt to
    flush the SAME pending row into that state surfaces as
    ``UniqueViolationError ... log_transaccional_p_current_pkey``.

    The queue tables are truncated for the same isolation reason: leftover
    ``sync_queue`` rows from EARLIER modules replay through this file's
    ``_drain_pending`` and can carry raw payload columns that the cloud
    ``close_and_insert`` refuses (``TypeError: 'k' is an invalid keyword
    argument for Usuarios``). This file's contract is that ITS OWN rows
    reach the cloud exactly once — draining other modules' leftovers is
    out of scope, matching the per-module TRUNCATE idiom the sibling
    integration files already use. The conftest's autouse bootstrap
    re-creates genesis on demand, so a pristine state is deterministic
    for every test in this file AND for the files that follow.
    """
    from sqlalchemy import text

    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE prod.sync_queue, prod.sync_log, prod.sync_conflict, "
                "prod.log_transaccional"
            )
        )


@pytest.fixture
def jwt_file(tmp_path: Path) -> Path:
    p = tmp_path / "sync.jwt"
    p.write_text("test-jwt-token", encoding="utf-8")
    return p


def _branch_session(pg_engine: AsyncEngine):
    """Inline branch-side session (repo idiom — no async function-scoped
    fixture, which pytest-asyncio 1.4.0 cannot set up on the session loop)."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    return Session()


def _build_cloud_app(pg_engine: AsyncEngine):
    """Real ``sync_router`` with a real session on the shared engine and
    fixed sync-agent claims — the e2e's ``build_cloud_app`` shape."""
    from fastapi import APIRouter, FastAPI
    from parkos_core.api.v1.sync_router import _sync_agent_claims
    from parkos_core.api.v1.sync_router import router as sync_router_obj
    from parkos_core.db.engine import get_session

    app = FastAPI()
    outer = APIRouter(prefix="/api/v1")
    outer.include_router(sync_router_obj)
    app.include_router(outer)

    async def _session_override():
        Session = async_sessionmaker(pg_engine, expire_on_commit=False)
        async with Session() as session:
            yield session

    def _claims_override() -> dict[str, object]:
        return {
            "iss": "sync-agent-branch",
            "sub": str(ACTOR_UUID),
            "jti": f"cycle-{uuid_lib.uuid4().hex}",
            "scope": "branch",
            "sucursal": str(ACTOR_UUID),
            "iat_branch": None,
        }

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[_sync_agent_claims] = _claims_override
    return app


def _build_branch_worker(session, cloud_app, *, jwt_path, mode) -> object:
    """Real worker bound to a real ``SyncHttpClient`` over the in-process
    ASGI cloud app. The applier-mode cache is PRESET so ``cycle()`` never
    depends on the live handshake's version negotiation (the detect/TTL
    logic itself is covered at unit level); the preset mirrors the result a
    healthy handshake would have cached."""
    from parkos_core.jobs.sync_sucursal import SyncSucursalWorker
    from parkos_core.sync.transport import SyncHttpClient

    worker = SyncSucursalWorker(
        jwt_path=jwt_path,
        base_url="http://cloud",
        session=session,
    )
    worker._http_client = SyncHttpClient(
        session_factory=lambda: httpx.AsyncClient(
            transport=httpx.ASGITransport(app=cloud_app), base_url="http://cloud"
        ),
        base_url="http://cloud",
        jwt_path=jwt_path,
    )
    worker._applier_cache = (mode, time.monotonic())
    return worker


# ---------------------------------------------------------------------------
# Shared seeding helpers
# ---------------------------------------------------------------------------


def uid() -> str:
    return uuid_lib.uuid4().hex[:8]


def now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seed_sucursal(session, *, suffix: str | None = None) -> uuid_lib.UUID:
    """Insert a ``sucursal`` row (echo-suppressed so it never re-resyncs)
    and return its uuid."""
    s = Sucursal(
        uuid=uuid_lib.uuid4(),
        nombre=f"Sucursal {suffix or uid()}",
        prefijo_nombre=f"ciclo-{suffix or uid()}",
        direccion="Av 1",
        ciudad="Bogota",
        vigente_desde=now_naive(),
        vigente_hasta=None,
        estado="activo",
    )
    await apply_guard.enable_echo_suppression(session)
    session.add(s)
    await session.commit()
    return s.uuid


async def _seed_tipo_subscripcion(session) -> uuid_lib.UUID:
    ts = TipoSubscripciones(
        uuid=uuid_lib.uuid4(),
        tipo=f"mensual-{uid()}",
        valor=50000,
        duracion_dias=30,
        cantidad_maxima_vehiculos=2,
        mismo_tipo_vehiculo=False,
        tipo_cliente_permitido="natural",
        vigente_desde=now_naive(),
        vigente_hasta=None,
        estado="activo",
    )
    await apply_guard.enable_echo_suppression(session)
    session.add(ts)
    await session.commit()
    return ts.uuid


async def _drain_pending(session, worker) -> None:
    """Settle any leftover pending rows (from EARLIER test files that share
    the session-scoped engine) through the real router, THEN commit, so a
    following full-cycle ``list_pending`` is deterministic. Leftovers are
    real, already-superseded rows — pushing them through the real router is
    harmless (they settle dispatched/failed, never crash the cycle)."""
    remaining = await sq_helpers.list_pending(session, limit=500)
    if not remaining:
        return
    await worker._push_and_handle_catalog(remaining)
    await session.commit()


# ---------------------------------------------------------------------------
# C1 — full worker cycle, empty queue (mechanics against the real router)
# ---------------------------------------------------------------------------


class TestFullCycleMechanics:
    async def test_cycle_empty_queue_pulls_commits_heartbeats_and_sleeps(
        self,
        pg_engine: AsyncEngine,
        alembic_upgrade: None,
        jwt_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """One full ``cycle()`` against the REAL cloud app on the shared DB
        with an empty (drained) queue: detect(preset) → poll → push(none) →
        pull(real stub) → ``commit()`` → heartbeat(real POST) →
        ``asyncio.sleep``. Nothing may raise."""
        from parkos_core.jobs.sync_sucursal import ApplierMode

        Session = async_sessionmaker(pg_engine, expire_on_commit=False)
        async with Session() as branch_session:
            app = _build_cloud_app(pg_engine)
            worker = _build_branch_worker(
                branch_session, app, jwt_path=jwt_file, mode=ApplierMode.CATALOG
            )
            await _drain_pending(branch_session, worker)

            pull_mock = AsyncMock(return_value=PullResponse(status=200, rows=[], next_seq=0))
            worker._http_client.pull = pull_mock  # real stub endpoint delivers []

            sleep_mock = AsyncMock()
            monkeypatch.setattr(asyncio, "sleep", sleep_mock)

            await worker.cycle()

            sleep_mock.assert_awaited_once()
            pull_mock.assert_awaited_once_with(since_seq=0)


# ---------------------------------------------------------------------------
# C1b — Bug 2 (single [V] row identity must survive the wire)
# ---------------------------------------------------------------------------


class TestBug2SingleRowIdentityPreserved:
    async def test_pushed_v_row_keeps_its_uuid_on_the_cloud_side(
        self,
        pg_engine: AsyncEngine,
        alembic_upgrade: None,
        jwt_file: Path,
    ) -> None:
        from parkos_core.jobs.sync_sucursal import ApplierMode

        Session = async_sessionmaker(pg_engine, expire_on_commit=False)
        async with Session() as branch_session:
            app = _build_cloud_app(pg_engine)
            worker = _build_branch_worker(
                branch_session, app, jwt_path=jwt_file, mode=ApplierMode.CATALOG
            )
            await _drain_pending(branch_session, worker)

            R = uuid_lib.uuid4()
            tipo = f"carro-{uid()}"
            await sq_helpers.enqueue(
                branch_session,
                "insert",
                "tipos_vehiculo",
                R,
                {"uuid": str(R), "tipo": tipo, "estado": "activo", "vigente_desde": now_naive().isoformat()},
                uuid_sucursal=None,
                prioridad=10,
            )
            await branch_session.commit()

            own_rows = await sq_helpers.list_pending(branch_session, limit=500)
            own_rows = [r for r in own_rows if r.uuid_registro == R]
            await worker._push_and_handle_catalog(own_rows)
            await branch_session.commit()

            # Identity-preservation contract: the SAME uuid lands at the
            # receiver (Bug 2 fixed — uuid is no longer stripped on wire).
            found = (
                await branch_session.execute(
                    select(TiposVehiculo.uuid).where(TiposVehiculo.tipo == tipo).limit(1)
                )
            ).scalar_one_or_none()
            assert found == R


# ---------------------------------------------------------------------------
# C2 — catalog pull is idempotent across repeated cycles
# ---------------------------------------------------------------------------


class TestCatalogPullIdempotent:
    async def test_two_catalog_pulls_never_duplicate_and_never_echo(
        self,
        pg_engine: AsyncEngine,
        alembic_upgrade: None,
        jwt_file: Path,
    ) -> None:
        """Two back-to-back ``_pull_and_apply_catalog`` calls delivering the
        SAME remote row must land exactly one local row (uuid preserved, so
        the ``uuid_registro`` dedup + ``apply_guard.row_already_present``
        guard skip the second time) and enqueue zero echo rows."""
        from parkos_core.jobs.sync_sucursal import SyncSucursalWorker

        Session = async_sessionmaker(pg_engine, expire_on_commit=False)
        async with Session() as branch_session:
            worker = SyncSucursalWorker(
                jwt_path=jwt_file,
                base_url="http://cloud",
                session=branch_session,
            )
            T1 = uuid_lib.uuid4()
            tipo = f"moto-{uid()}"
            worker._http_client = MagicMock()
            worker._http_client.pull = AsyncMock(
                return_value=PullResponse(
                    status=200,
                    rows=[
                        {
                            "tabla": "tipos_vehiculo",
                            "uuid_registro": str(T1),
                            "datos": {"uuid": str(T1), "tipo": tipo},
                        }
                    ],
                    next_seq=1,
                )
            )

            await worker._pull_and_apply_catalog()
            await worker._pull_and_apply_catalog()
            await branch_session.commit()

            fresh = async_sessionmaker(pg_engine, expire_on_commit=False)
            async with fresh() as session:
                count = (
                    await session.execute(
                        select(func.count(TiposVehiculo.uuid)).where(TiposVehiculo.tipo == tipo)
                    )
                ).scalar_one()
                echo = (
                    await session.execute(
                        select(func.count(sq_helpers.SyncQueue.uuid)).where(
                            sq_helpers.SyncQueue.uuid_registro == T1
                        )
                    )
                ).scalar_one()
            assert count == 1, "the remote row must be applied exactly once"
            assert echo == 0, "apply_guard must suppress the branch enqueue echo"


# ---------------------------------------------------------------------------
# C3 — Bug 8 (fixed): backoff must actually hold the row out of list_pending
# ---------------------------------------------------------------------------


class TestBackoffRespectedByListPending:
    async def test_511_marked_row_stays_out_of_list_pending_until_retry_at(
        self,
        pg_engine: AsyncEngine,
        alembic_upgrade: None,
        jwt_file: Path,
    ) -> None:
        """A 5xx push failure re-queues the row with a FUTURE
        ``next_retry_at`` AND must exclude it from ``list_pending`` until
        that time arrives. The first half holds today; the second does not —
        the xfail pin is the missing ``next_retry_at`` predicate."""
        from parkos_core.jobs.sync_sucursal import SyncSucursalWorker
        from parkos_core.sync.transport import EventsPushResponse

        Session = async_sessionmaker(pg_engine, expire_on_commit=False)
        async with Session() as branch_session:
            worker = SyncSucursalWorker(
                jwt_path=jwt_file,
                base_url="http://cloud",
                session=branch_session,
            )
            worker._http_client = MagicMock()
            worker._http_client.push_events = AsyncMock(
                return_value=EventsPushResponse(status=503, results=[])
            )

            R = uuid_lib.uuid4()
            await sq_helpers.enqueue(
                branch_session,
                "insert",
                "caja",
                R,
                {"uuid": str(R), "valor_efectivo": 100, "valor_datafono": 0},
                uuid_sucursal=None,
                prioridad=10,
            )
            await branch_session.commit()

            own = [
                r
                for r in await sq_helpers.list_pending(branch_session, limit=500)
                if r.uuid_registro == R
            ]
            await worker._push_and_handle_catalog(own)
            await branch_session.commit()

            fresh = async_sessionmaker(pg_engine, expire_on_commit=False)
            async with fresh() as session:
                row = (
                    await session.execute(
                        select(sq_helpers.SyncQueue).where(sq_helpers.SyncQueue.uuid == own[0].uuid)
                    )
                ).scalar_one()

            # mark_failed re-queues with a future retry window.
            assert row.estado == "pendiente"
            assert row.next_retry_at is not None
            assert row.next_retry_at > now_naive()

            # Bug 8 fix holds: the future window MUST gate list_pending.
            still_pending = await sq_helpers.list_pending(branch_session, limit=500)
            assert all(r.uuid != row.uuid for r in still_pending)


# ---------------------------------------------------------------------------
# C4 — Bug 6 (fixed): missing JWT must not abort the cycle before pull+commit
# ---------------------------------------------------------------------------


class TestMissingJwtKeepsCycleAlive:
    async def test_cycle_still_pulls_when_push_jwt_is_missing(
        self,
        pg_engine: AsyncEngine,
        alembic_upgrade: None,
        tmp_path: Path,
    ) -> None:
        from parkos_core.jobs.sync_sucursal import ApplierMode, SyncSucursalWorker
        from parkos_core.sync.transport import SyncHttpClient

        Session = async_sessionmaker(pg_engine, expire_on_commit=False)
        async with Session() as branch_session:
            missing_jwt = tmp_path / "never-written.jwt"  # does NOT exist
            app = _build_cloud_app(pg_engine)
            worker = SyncSucursalWorker(
                jwt_path=missing_jwt,
                base_url="http://cloud",
                session=branch_session,
                poll_interval_s=0,
            )
            worker._http_client = SyncHttpClient(
                session_factory=lambda: httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://cloud"
                ),
                base_url="http://cloud",
                jwt_path=missing_jwt,
            )
            worker._applier_cache = (ApplierMode.CATALOG, time.monotonic())
            pull_mock = AsyncMock(return_value=PullResponse(status=200, rows=[], next_seq=0))
            worker._http_client.pull = pull_mock
            sleep_mock = AsyncMock()

            R = uuid_lib.uuid4()
            await sq_helpers.enqueue(
                branch_session,
                "insert",
                "caja",
                R,
                {"uuid": str(R), "valor_efectivo": 1, "valor_datafono": 0},
                uuid_sucursal=None,
            )
            await branch_session.commit()

            with _patch_sleep(sleep_mock):
                try:
                    await worker.cycle()
                except Exception:
                    sleep_mock.assert_not_awaited()  # today the cycle dies early
                    pass

            # Desired contract: despite the failed push, the pull step ran.
            # Today it never does (the RuntimeError aborts before pull) →
            # XFAIL.
            pull_mock.assert_awaited()


def _patch_sleep(sleep_mock: AsyncMock):
    return __import__("unittest.mock", fromlist=["patch"]).patch("asyncio.sleep", sleep_mock)


# ---------------------------------------------------------------------------
# C5 — Bug 4 probe: legacy pull re-imports the same row (no preset xfail)
# ---------------------------------------------------------------------------


class TestLegacyPullTwiceNoDuplicate:
    async def test_legacy_pull_delivers_a_remote_row_exactly_once(
        self,
        pg_engine: AsyncEngine,
        alembic_upgrade: None,
        jwt_file: Path,
    ) -> None:
        """Bug 4 contract: the legacy ``_pull_and_apply`` path must deliver
        a remote row exactly once under its own uuid. The pre-PR7-era
        prober (that twice-delivered rows previously landed the SAME
        remote row TWICE under fresh uuids, or — after PR7's pure-decision
        shim — ZERO times) is now fixed: the legacy pull dedups by
        ``uuid_registro`` and applies through ``SyncMotor.apply_batch``,
        which preserves the incoming ``uuid``."""
        from parkos_core.jobs.sync_sucursal import SyncSucursalWorker

        Session = async_sessionmaker(pg_engine, expire_on_commit=False)
        async with Session() as branch_session:
            worker = SyncSucursalWorker(
                jwt_path=jwt_file,
                base_url="http://cloud",
                session=branch_session,
            )
            LEG = uuid_lib.uuid4()
            remote_row = {
                "tabla": "tipos_vehiculo",
                "uuid_registro": str(LEG),
                "datos": {"uuid": str(LEG), "tipo": f"legacy-{uid()}"},
                "uuid_sucursal": None,
                "timestamp_evento": now_naive(),
            }
            worker._http_client = MagicMock()
            worker._http_client.pull = AsyncMock(
                return_value=PullResponse(status=200, rows=[remote_row], next_seq=0)
            )

            await worker._pull_and_apply()
            await worker._pull_and_apply()
            await branch_session.commit()

            fresh = async_sessionmaker(pg_engine, expire_on_commit=False)
            async with fresh() as session:
                count = (
                    await session.execute(
                        select(func.count(TiposVehiculo.uuid)).where(TiposVehiculo.uuid == LEG)
                    )
                ).scalar_one()
            assert count == 1, "the remote row must land exactly once under its own uuid"


# ---------------------------------------------------------------------------
# C6 — Bug 2 (parent+child): child must reference the LANDED parent uuid
# ---------------------------------------------------------------------------


class TestBug2ChildIdentityTracksLandedParent:
    async def test_child_subscription_lands_pointing_at_the_landed_parent(
        self,
        pg_engine: AsyncEngine,
        alembic_upgrade: None,
        jwt_file: Path,
    ) -> None:
        from parkos_core.jobs.sync_sucursal import ApplierMode

        Session = async_sessionmaker(pg_engine, expire_on_commit=False)
        async with Session() as branch_session:
            app = _build_cloud_app(pg_engine)
            worker = _build_branch_worker(
                branch_session, app, jwt_path=jwt_file, mode=ApplierMode.CATALOG
            )
            await _drain_pending(branch_session, worker)

            S = await _seed_sucursal(branch_session, suffix="c6")
            TS = await _seed_tipo_subscripcion(branch_session)

            P0 = uuid_lib.uuid4()
            C0 = uuid_lib.uuid4()
            ident = f"cc-{uid()}"
            await sq_helpers.enqueue(
                branch_session,
                "insert",
                "clientes",
                P0,
                {
                    "uuid": str(P0),
                    "tipo_identificador": "CC",
                    "numero_identificacion": ident,
                    "nombre": "Pepe",
                    "apellido": "Perez",
                    "estado": "activo",
                    "vigente_desde": now_naive().isoformat(),
                },
                uuid_sucursal=None,
            )
            await sq_helpers.enqueue(
                branch_session,
                "insert",
                "subscripciones_cliente",
                C0,
                {
                    "uuid": str(C0),
                    "uuid_cliente": str(P0),  # the ORIGIN parent uuid
                    "uuid_sucursal": str(S),
                    "uuid_tipo_subscripcion": str(TS),
                    "fecha_inicio_cobertura": "2026-01-01",
                    "fecha_vencimiento": "2026-12-31",
                    "estado": "activo",
                    "vigente_desde": now_naive().isoformat(),
                },
                uuid_sucursal=None,
            )
            await branch_session.commit()

            own = [
                r
                for r in await sq_helpers.list_pending(branch_session, limit=500)
                if r.uuid_registro in (P0, C0)
            ]
            await worker._push_and_handle_catalog(own)
            await branch_session.commit()

            fresh = async_sessionmaker(pg_engine, expire_on_commit=False)
            async with fresh() as session:
                landed_parent = (
                    await session.execute(
                        select(Clientes.uuid).where(
                            Clientes.numero_identificacion == ident
                        ).limit(1)
                    )
                ).scalar_one_or_none()
                child_estado = (
                    await session.execute(
                        select(sq_helpers.SyncQueue.estado).where(
                            sq_helpers.SyncQueue.uuid_registro == C0
                        )
                    )
                ).scalar_one_or_none()

            # Bug 2 fixed: the parent lands under its ORIGIN uuid, so the
            # child's uuid_cliente FK matches and both legs settle exitoso.
            assert landed_parent is not None, "parent clientes never landed"
            assert child_estado == "exitoso", f"child settled {child_estado!r}"
            async with fresh() as session:
                child_points = (
                    await session.execute(
                        select(func.count(SubscripcionesCliente.uuid)).where(
                            SubscripcionesCliente.uuid_cliente == landed_parent
                        )
                    )
                ).scalar_one()
            assert child_points == 1, (
                f"no subscripcion_cliente references landed parent {landed_parent}"
            )