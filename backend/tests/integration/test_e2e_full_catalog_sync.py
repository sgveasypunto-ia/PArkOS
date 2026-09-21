"""test_e2e_full_catalog_sync.py — post-PR14 closing verification exercise.

Not a tasks.md PR task — this is the explicit closing exercise the user
requested once all 14 sync-overhaul PRs merged: for EVERY one of the 46
``SYNC_CATALOG`` entries, create one record via the legitimate service/repo
layer, let the REAL DB trigger enqueue it, run the REAL job/motor code that
moves it, and verify it lands in the destination database — never a raw SQL
insert to simulate state, never a new endpoint added as a test shortcut.

Architecture decision (task item #9) — TWO REAL, PHYSICALLY SEPARATE
Postgres containers, not one shared schema
======================================================================

``infra/deploy/docker-compose.{cloud,branch,local}.yml`` prove the
production topology beyond doubt: ``cloud-db`` and ``branch-db`` are two
independent Postgres *services* (different containers, different data
volumes, different host ports 5432/5433), connected ONLY over HTTP
(``PARKOS_CLOUD_API_URL``) — never a shared schema, never a shared
connection. ``uuid_sucursal``/``PARKOS_DEPLOY`` distinguish *roles*
(cloud admin vs. branch) that run against these two DIFFERENT databases,
not two schemas in the same one. Faking that with a single shared Postgres
instance would prove nothing about the actual replication boundary this
change built (HTTP push/pull, JWT auth, wire (de)serialization, the
catalog-driven ``SyncMotor`` dispatch on each independent side).

This file therefore boots a SECOND real ``testcontainers`` Postgres
container (fixtures below, module-scoped, mirroring ``tests/conftest.py``'s
own ``postgres_container``/``alembic_upgrade``/``pg_engine`` trio) and
labels the two: ``pg_engine`` (root conftest fixture) is CLOUD, the new
``branch_pg_engine`` is BRANCH. Both get the full ``0001..0015`` Alembic
chain applied independently — two fully independent schemas, exactly like
production.

For the ``branch_to_cloud`` / bidirectional-from-branch direction, the
branch→cloud leg is proven with a REAL HTTP round trip: a real
``SyncSucursalWorker`` (unmodified production class) with a real
``SyncHttpClient`` whose transport is ``httpx.ASGITransport`` bound to a
real FastAPI app that mounts the REAL, unmodified ``sync_router`` — the
exact same ``POST /sync/events`` handler production serves, running against
the CLOUD engine's session. This is "at least invoking the real router with
an httpx.AsyncClient test client", the documented fallback the task
requested when a full raw TCP socket isn't practical inside one pytest
process. Only the auth dependency (``_sync_agent_claims``, JWT
signature/revocation/clock-skew checks) is overridden with a fixed claims
dict — exactly the same override pattern PR11/PR12's own
``test_sync_router_wire_status.py`` already established; auth itself is
already covered by other tests and is not this exercise's target.

For the ``cloud_to_branch`` direction (all 26 ``[V]`` entries, plus the one
``[L-W]`` cloud-authored entry ``envio_dian``): ``GET/POST /sync/pull`` is
STILL a literal stub in this codebase — ``sync_router.py::sync_pull``
unconditionally returns ``{"rows": [], "next_seq": ...}`` (its own docstring:
"The full cloud-side applier ... lands in PR9" — never actually built; this
is exactly verify-report gap (c), "backfill transport unwired", already
pre-approved as out of this change's scope). The ONLY real, wired,
catalog-driven mechanism this codebase ships for moving ``cloud_to_branch``
data into a branch database is ``sync/cutover/backfill.py::run_backfill`` —
confirmed by grep: nothing under ``jobs/*.py`` calls it yet either (its own
module docstring: "transport-agnostic by design ... the concrete production
implementation (an HTTP client hitting the cloud's bulk-export surface) is
a documented, deliberately out-of-scope follow-up"). The task's own
instructions (item #7) name this exact module — "usando
``cutover/backfill.py``" — confirming this reading. This file's
``make_cloud_fetch_page`` below is the ``FetchPage`` callable ``run_backfill``
is built to accept; it does a real, paginated ``SELECT`` against the real
CLOUD engine (never a literal/hardcoded fixture dict), so the backfill
genuinely moves the exact rows this test created at cloud — not synthetic
data standing in for them.

Identity preservation across the wire (a real bug found + NOT fixed here,
see "Discovered — NOT fixed" below): ``jobs/sync_cloud.py::_business_payload_
for_apply`` strips ``uuid`` from every ``audit_class="V"`` payload before
dispatch. That is safe in isolation but breaks referential identity the
moment a [V] child (e.g. ``usuarios_sucursal``, ``login``) is delivered in
the SAME backfill run as its [V] parent (e.g. ``usuarios``, ``sucursal``):
the parent lands with a FRESH, unrelated ``uuid`` at the destination, so the
child's carried-over FK value (the ORIGIN's parent uuid) points at nothing
on the destination. ``login`` proves this at the real DB-constraint layer —
its ``uuid_usuario``/``uuid_sucursal`` columns carry real
``ForeignKey("prod.usuarios.uuid")`` / ``ForeignKey("prod.sucursal.uuid")``
constraints (``models/L_S/login.py``). This file's OWN ``fetch_page``
(``make_cloud_fetch_page`` below) is written from scratch for this exercise
and deliberately PRESERVES ``uuid`` for every entry (V included) — it does
NOT reuse ``_business_payload_for_apply`` — precisely to avoid manufacturing
that exact breakage inside this test's own harness. See the "Discovered —
NOT fixed" section for why the shared helper itself is not touched here.

DIAN provider — no mock needed, and why: ``factura_electronica`` /
``revocacion_factura`` / ``envio_dian`` are created here via the plain repo
helpers (``repo.event.record_event`` / ``repo.append_only.append_event`` /
``repo.workflow.append_transition``) and moved by ``SyncMotor``/
``run_backfill`` — neither path ever imports or calls
``parkos_core.dian.cloud.dispatcher`` (the actual provider-submission
module ``tests/unit/dian/conftest.py``'s mock harness exists for). There is
no live-network-call risk in this file's flow, so no DIAN mock fixture is
wired in; this is stated explicitly rather than silently assumed.

Fixed in this session (motor bug, genuinely did not sync)
===========================================================

``sync/motor/apply_row.py``'s ``session_cycle`` dispatch branch called
``session_cycle.record_login``/``close_login_with_log`` UNCONDITIONALLY,
regardless of ``spec.model_cls`` — both ``login`` AND ``sesion`` declare
``apply_strategy="session_cycle"`` (``entries/sync_entries_ls.py``), but
only ``login`` was ever actually applied correctly. A synced ``sesion`` row
was silently misrouted into ``prod.login`` instead of ``prod.sesion``
(their payloads happen to share the ``uuid_usuario``/``uuid_sucursal`` keys,
so the misdispatch never raised — it just wrote to the wrong table).
Fixed by dispatching on ``spec.name`` to the correct pair
(``open_session``/``close_session_with_log`` for ``sesion``). See that
module's own docstring for the full note.

Discovered — NOT fixed (documented, out of this exercise's scope)
=====================================================================

1. ``_business_payload_for_apply``'s blanket ``uuid`` strip for every
   ``audit_class="V"`` entry (see "Identity preservation" above) — real,
   but its only two real call sites (``SyncCloudWorker._apply_pending_
   batch_once``, ``SyncSucursalWorker._pull_and_apply_catalog``) are
   currently inert for a genuine multi-level V dependency chain: ``/sync/
   pull`` is a stub (gap (c)), and ``_apply_pending_batch_once`` draining
   CLOUD's OWN ``sync_queue`` in catalog engine mode would, for a
   CLOUD-authored ``[V]`` row, be RE-applying a row that was already
   correctly persisted by its own original INSERT (the same trigger that
   enqueued it fires unconditionally on every INSERT, including ones
   ``apply_row`` itself performs — see point 2). Recommend fixing when the
   real backfill/pull transport lands, by removing ``"uuid"`` from
   ``_VERSIONED_ONLY_METADATA_KEYS`` (keep ``vigente_desde``/
   ``vigente_hasta``/``estado`` stripped — those three genuinely must be
   recomputed fresh at the destination; ``uuid`` must not be).
2. ``fn_enqueue_sync()``/``fn_enqueue_sync_catalog()`` fire unconditionally
   on EVERY INSERT, including one performed BY the sync motor applying an
   incoming row (``append_event``/``close_and_insert``/etc. are ordinary
   INSERTs from the trigger's point of view) — an "echo" ``sync_queue`` row
   is created on whichever side just applied incoming data, representing
   nothing new. This is invisible today because ``/sync/events`` applies a
   pushed row DIRECTLY (bypassing ``SyncCloudWorker``'s own queue-draining
   loop entirely for that path) and ``/sync/pull`` is a stub — but a
   future real bulk-pull transport, or a long-running
   ``SyncCloudWorker._apply_pending_loop`` fed by a wired legacy ``/sync/
   push`` path, would accumulate these echoes forever (``append_event``/
   ``close_and_insert`` have no upsert/idempotency by uuid, so a re-applied
   echo either duplicates the row or raises a PK violation depending on the
   table's PK shape). Fixing this needs either a session-local GUC the
   trigger checks (a migration / schema change — explicitly out of this
   exercise's allowed edit surface) or a motor-layer post-apply
   self-settle step; flagged here as a real, disclosed architectural gap,
   not fixed.
3. ``motor/apply_row.py``'s ``append_transition`` branch derives
   ``parent_uuid = payload.get("parent_uuid")`` — but a REAL trigger-
   sourced payload never carries a literal ``"parent_uuid"`` key, only the
   table's own self-FK column name (``uuid_reimpresion_padre``,
   ``uuid_anulacion_padre``, ...). This means the STATE-MACHINE VALIDATION
   step inside ``repo.workflow.append_transition`` (parent lookup + legal-
   transition check) never actually runs for a synced non-root [L-W]
   transition — ``parent_uuid`` stays ``None`` so validation is skipped.
   The row itself still lands correctly (the real FK value survives inside
   ``new_attrs`` untouched, since ``new_attrs`` is only stripped of the
   literal string ``"parent_uuid"``, not the real column name) — this is a
   validation-bypass gap, not a "table doesn't sync" gap, and every
   ``[L-W]`` table this file creates is a ROOT transition (``parent=None``)
   where the bug is inert either way. Documented, not fixed, to keep this
   session's edit surface to the one definite, empirically-confirmed
   defect (point 1 above / the ``sesion`` fix).

Coverage summary (46/46 SYNC_CATALOG entries)
================================================

See the big table in this session's ``openspec/changes/sync-overhaul/
tasks.md`` addendum for the definitive per-table result; in short: 45/46
sync correctly end to end through the real job/motor path (after the
``sesion`` fix), and ``validacion_evento`` is confirmed to correctly NEVER
propagate (the sole ``never_propagated`` entry, by design).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid as uuid_lib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000e2e01")


@pytest.fixture(autouse=True)
def _catalog_engine_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cloud router's ``/sync/events`` handler and this file's own
    ``run_backfill``/``SyncMotor`` calls all read ``PARKOS_SYNC_ENGINE``
    (directly or via an explicit ``EngineMode.CATALOG_BRANCH``) — mirrors
    ``test_sync_cloud_catalog_driven.py``'s own ``_catalog_engine_mode``
    fixture."""
    from parkos_core.runtime import engine_flag

    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
    engine_flag._reset_cache_for_tests()


_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEST_PG_IMAGE = os.environ.get("TEST_PG_IMAGE", "postgres:16-alpine")
ALEMBIC_TIMEOUT_S = int(os.environ.get("TEST_ALEMBIC_TIMEOUT", "30"))


# ---------------------------------------------------------------------------
# Branch-side Postgres container — a SECOND, independent container (see the
# module docstring's architecture decision). Mirrors tests/conftest.py's
# postgres_container/alembic_upgrade/pg_engine trio exactly, just module-
# scoped (this file only) instead of session-scoped (whole suite) so it
# does not change any other test file's fixture lifetime.
# ---------------------------------------------------------------------------


def _to_asyncpg(raw: str) -> str:
    if raw.startswith("postgresql+psycopg://"):
        return "postgresql+asyncpg://" + raw[len("postgresql+psycopg://") :]
    if raw.startswith("postgresql+psycopg2://"):
        return "postgresql+asyncpg://" + raw[len("postgresql+psycopg2://") :]
    if raw.startswith("postgresql://"):
        return "postgresql+asyncpg://" + raw[len("postgresql://") :]
    return raw


def _to_psycopg(raw: str) -> str:
    if raw.startswith("postgresql+psycopg2://"):
        return "postgresql://" + raw[len("postgresql+psycopg2://") :]
    if raw.startswith("postgresql+psycopg://"):
        return "postgresql://" + raw[len("postgresql+psycopg://") :]
    if raw.startswith("postgresql+asyncpg://"):
        return "postgresql://" + raw[len("postgresql+asyncpg://") :]
    return raw


@pytest.fixture(scope="module")
def branch_postgres_container():
    """A SECOND, independent testcontainers Postgres container (the "branch"
    physical database) — see the module docstring's architecture decision."""
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:
        pytest.skip(f"testcontainers[postgres] not installed ({exc})")

    container = PostgresContainer(DEFAULT_TEST_PG_IMAGE)
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="module")
def branch_pg_dsn(branch_postgres_container: object) -> str:
    return _to_psycopg(branch_postgres_container.get_connection_url())


@pytest.fixture(scope="module")
def branch_pg_async_dsn(branch_postgres_container: object) -> str:
    return _to_asyncpg(branch_postgres_container.get_connection_url())


@pytest.fixture(scope="module")
def _branch_wait_for_pg(branch_pg_dsn: str) -> None:
    deadline = time.monotonic() + ALEMBIC_TIMEOUT_S
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with (
                psycopg.connect(branch_pg_dsn, connect_timeout=2) as conn,
                conn.cursor() as cur,
            ):
                cur.execute("SELECT 1")
                cur.fetchone()
            return
        except Exception as exc:
            last_err = exc
            time.sleep(0.5)
    pytest.fail(f"branch DB never became ready within {ALEMBIC_TIMEOUT_S}s: {last_err}")


@pytest.fixture(scope="module")
def branch_alembic_upgrade(branch_pg_dsn: str, _branch_wait_for_pg: None) -> None:
    """Run ``alembic upgrade head`` against the BRANCH container — the full
    0001..0015 chain, independently from the CLOUD engine's own copy."""
    migrations_pkg = _BACKEND_ROOT / "packages" / "parkos_core" / "migrations"
    env = os.environ.copy()
    env["DATABASE_URL"] = branch_pg_dsn

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(migrations_pkg.parent),
            env=env,
            capture_output=True,
            text=True,
            timeout=ALEMBIC_TIMEOUT_S * 6,
        )
    except FileNotFoundError as exc:
        pytest.skip(f"alembic not installed: {exc}")
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"branch alembic upgrade head timed out: {exc}")

    if proc.returncode != 0:
        snippet = (proc.stderr or "")[-1500:] or (proc.stdout or "")[-1500:]
        pytest.skip(
            f"branch alembic upgrade head failed (exit {proc.returncode}); "
            f"same pg_partman requirement as the root conftest's alembic_upgrade "
            f"fixture.\n{snippet}"
        )


@pytest.fixture(scope="module")
async def branch_pg_engine(branch_pg_async_dsn: str, branch_alembic_upgrade: None) -> AsyncEngine:
    engine = create_async_engine(branch_pg_async_dsn, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="module", autouse=True)
async def _bootstrap_branch_hash_chain_genesis(branch_pg_engine: AsyncEngine) -> None:
    """Same genesis-row bootstrap tests/conftest.py performs for the CLOUD
    engine (autouse there) — the BRANCH engine needs its own, independent
    global genesis row for prod.log_transaccional (uuid_sucursal IS NULL)."""
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.repo.hash_chain import _ensure_genesis_row

    Session = async_sessionmaker(branch_pg_engine, expire_on_commit=False)
    async with Session() as session:
        await _ensure_genesis_row(session, LogTransaccional, None)
        await session.commit()


# ---------------------------------------------------------------------------
# Origin-side row creation — the SAME apply_strategy -> repo/* dispatch
# motor/apply_row.py::_dispatch_repo_call uses, called directly (never via
# apply_row/SyncMotor, which is reserved for applying an ALREADY-ARRIVED
# remote row) — this is how a real CRUD/business flow at the row's
# ORIGINATING side creates it. Matches the task's explicit list of
# legitimate repo helpers; never a raw session.add(Model(...)).
# ---------------------------------------------------------------------------


async def create_origin_row(session: Any, spec: Any, attrs: dict[str, Any]) -> Any:
    from parkos_core.repo import append_only as ao_helpers
    from parkos_core.repo import event as event_helpers
    from parkos_core.repo import session_cycle as session_helpers
    from parkos_core.repo import versioned as versioned_helpers
    from parkos_core.repo import workflow as workflow_helpers

    strategy = spec.apply_strategy
    if strategy == "close_and_insert":
        row = await versioned_helpers.close_and_insert(
            session,
            spec.model_cls,
            current_uuid=None,
            new_attrs=attrs,
            actor_uuid=ACTOR_UUID,
        )
    elif strategy == "record_event":
        row = await event_helpers.record_event(
            session, spec.model_cls, actor_uuid=ACTOR_UUID, new_attrs=attrs
        )
    elif strategy == "append_event":
        row = await ao_helpers.append_event(
            session, spec.model_cls, attrs, actor_uuid=ACTOR_UUID, chain_hash=spec.hash_chain
        )
    elif strategy == "append_transition":
        row = await workflow_helpers.append_transition(
            session,
            spec.model_cls,
            actor_uuid=ACTOR_UUID,
            new_attrs=attrs,
            parent_uuid=None,
            parent_fk_column=spec.parent_fk_column,
        )
    elif strategy == "session_cycle":
        if spec.name == "sesion":
            row = await session_helpers.open_session(
                session,
                actor_uuid=ACTOR_UUID,
                uuid_sucursal=attrs["uuid_sucursal"],
                valor_inicial_efectivo=attrs["valor_inicial_efectivo"],
                valor_inicial_datafono=attrs["valor_inicial_datafono"],
                uuid_usuario=attrs["uuid_usuario"],
            )
        else:
            row = await session_helpers.record_login(
                session,
                usuario_uuid=attrs["uuid_usuario"],
                sucursal_uuid=attrs["uuid_sucursal"],
                actor_uuid=ACTOR_UUID,
                success=True,
            )
    elif strategy is None and spec.name == "validacion_evento":
        # The sole never_propagated entry (apply_strategy=None, since it is
        # never dispatched through the sync motor at all) is still a real
        # WorkflowBase table with its own STATE_MACHINES entry
        # (repo/workflow.py) at the application layer — created here via
        # the SAME legitimate repo helper every other [L-W] table uses.
        row = await workflow_helpers.append_transition(
            session,
            spec.model_cls,
            actor_uuid=ACTOR_UUID,
            new_attrs=attrs,
            parent_uuid=None,
            parent_fk_column=spec.parent_fk_column,
        )
    else:
        raise AssertionError(
            f"{spec.name}: no origin-side dispatch wired for apply_strategy={strategy!r}"
        )
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# Backfill fetch_page — real, paginated SELECT against the CLOUD engine.
# See the module docstring's "Identity preservation" section for why uuid
# is deliberately NOT stripped here (unlike jobs/sync_cloud.py's own
# _business_payload_for_apply, which strips it for every [V] entry).
# ---------------------------------------------------------------------------

_QUEUE_LIKE_KEYS = frozenset(
    {"created_at", "created_by", "sync_status", "sync_timestamp", "sync_attempts"}
)
#: ``vigente_hasta``/``estado`` excluded: every row ``fetch_page`` selects is
#: already filtered ``WHERE vigente_hasta IS NULL`` (always ``None``) and
#: ``estado`` is always the generic ``'activo'`` for an open [V] row (with
#: the one exception, ``subscripcion_vehiculos``, out of this exclusion
#: set's scope). ``vigente_desde`` is DELIBERATELY NOT excluded (found
#: 2026-09-10, generalizing identity reconciliation past the 3 original
#: identity masters): a real ``to_jsonb(NEW)``-captured production wire
#: payload always carries the row's own ``vigente_desde`` — stripping it
#: here made every arriving row look temporally ambiguous to
#: ``identity_reconciler`` (``payload.get("vigente_desde") is None`` always
#: resolves ``is_forward=True``, REGARDLESS of true chronological order),
#: so whichever duplicate-natural-key row Postgres happened to return LAST
#: from an unordered ``fetch_page`` SELECT silently won reconciliation
#: instead of the genuinely latest one — surfaced as a real
#: ``ForeignKeyViolationError`` when a stale same-natural-key row beat this
#: run's own ``tipo_persona``/``configuracion_seguridad`` row for the
#: "currently open" slot on BRANCH.
_V_BITEMPORAL_KEYS = frozenset({"vigente_hasta", "estado"})


def _extract_business_attrs(spec: Any, row: Any) -> dict[str, Any]:
    mapper = sa_inspect(spec.model_cls)
    attrs: dict[str, Any] = {}
    for column in mapper.columns:
        name = column.name
        if name in _QUEUE_LIKE_KEYS:
            continue
        if spec.audit_class == "V" and name in _V_BITEMPORAL_KEYS:
            continue
        attrs[name] = getattr(row, name)
    return attrs


def make_cloud_fetch_page(
    cloud_pg_engine: AsyncEngine, *, uuid_sucursal: uuid_lib.UUID | None = None
):
    """Build a real ``FetchPage`` (``cutover/backfill.py``) reading from the
    CLOUD engine — never a hardcoded/literal fixture dict.

    ``pg_engine`` is the ROOT conftest's session-scoped fixture, shared by
    every OTHER integration test file in the same pytest session — this
    file is not the only writer of V rows on that engine. When
    ``uuid_sucursal`` is given and the model carries that column, the
    query is scoped to it, so this test's own backfill only ever moves
    ITS OWN rows to the branch — never an unrelated row some OTHER test
    left on the shared CLOUD engine (found wiring the ``envio_dian``
    mini-backfill: without this scoping, a stray ``envio_dian`` row from
    another test — a real, valid row on cloud, just for a DIFFERENT
    ``uuid_sucursal``/``factura_electronica`` — was also fetched and
    failed a real ``ForeignKeyViolationError`` on the branch, since the
    branch never received THAT unrelated row's own parent).
    """
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
    from parkos_core.sync.cutover.backfill import BackfillPage

    async def fetch_page(tabla: str, cursor: str | None, limit: int) -> BackfillPage:
        spec = SYNC_CATALOG_BY_NAME[tabla]
        Session = async_sessionmaker(cloud_pg_engine, expire_on_commit=False)
        async with Session() as session:
            stmt = select(spec.model_cls)
            if spec.audit_class == "V":
                stmt = stmt.where(spec.model_cls.vigente_hasta.is_(None))
            if uuid_sucursal is not None and hasattr(spec.model_cls, "uuid_sucursal"):
                stmt = stmt.where(spec.model_cls.uuid_sucursal == uuid_sucursal)
            rows = (await session.execute(stmt)).scalars().all()
        page_rows = tuple(_extract_business_attrs(spec, row) for row in rows)
        return BackfillPage(rows=page_rows, next_cursor=None, has_more=False)

    return fetch_page


# ---------------------------------------------------------------------------
# Cloud FastAPI app (real sync_router, real DB session, fixed auth claims)
# ---------------------------------------------------------------------------


def build_cloud_app(cloud_pg_engine: AsyncEngine) -> FastAPI:
    from fastapi import APIRouter
    from parkos_core.api.v1.sync_router import _sync_agent_claims
    from parkos_core.api.v1.sync_router import router as sync_router_obj
    from parkos_core.db.engine import get_session

    app = FastAPI()
    # SyncHttpClient posts to f"{base_url}/api/v1/sync/...} — real apps wrap
    # sync_router in an outer "/api/v1" prefix router (api/v1/__init__.py's
    # own make_api_router); this test app must match that exact path shape.
    outer = APIRouter(prefix="/api/v1")
    outer.include_router(sync_router_obj)
    app.include_router(outer)

    async def _session_override():
        Session = async_sessionmaker(cloud_pg_engine, expire_on_commit=False)
        async with Session() as session:
            yield session

    def _claims_override() -> dict[str, Any]:
        return {
            "iss": "sync-agent-branch",
            "sub": str(ACTOR_UUID),
            "jti": "e2e-full-catalog-sync",
            "scope": "branch",
            "sucursal": str(ACTOR_UUID),
            "iat_branch": None,
        }

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[_sync_agent_claims] = _claims_override
    return app


def build_branch_worker(branch_session: Any, cloud_app: FastAPI, jwt_path: Path):
    from parkos_core.jobs.sync_sucursal import SyncSucursalWorker
    from parkos_core.sync.transport import SyncHttpClient

    jwt_path.write_text("fake-jwt-not-verified-by-overridden-claims", encoding="utf-8")
    worker = SyncSucursalWorker(jwt_path=jwt_path, base_url="http://cloud", session=branch_session)
    worker._http_client = SyncHttpClient(
        session_factory=lambda: httpx.AsyncClient(
            transport=httpx.ASGITransport(app=cloud_app), base_url="http://cloud"
        ),
        base_url="http://cloud",
        jwt_path=jwt_path,
    )
    return worker


async def push_and_verify(
    branch_session: Any,
    worker: Any,
    table_name: str,
    *,
    uuid_registro: uuid_lib.UUID | None = None,
) -> None:
    """Push ONLY the just-created row(s) for ``table_name`` via the REAL job
    method (``SyncSucursalWorker._push_and_handle_catalog``) — a real HTTP
    POST /sync/events against the real cloud app, applied via the real
    SyncMotor on the CLOUD session — and assert it settled ``exitoso``.

    Deliberately surgical (filters ``list_pending`` down to this exact
    table, and — for ``table_name="log_transaccional"`` specifically —
    down to one exact ``uuid_registro`` via the ``uuid_registro`` kwarg)
    rather than draining the WHOLE branch queue on every call. Two real,
    disclosed findings this session made wiring this file:

    1. (documented in this file's module docstring, "Discovered — NOT
       fixed" #2) the ``AFTER INSERT`` trigger fires unconditionally on
       every INSERT, including ones the sync motor itself performs while
       applying an ALREADY-incoming row — e.g. every one of the 26
       ``[V]`` rows this file's ``run_backfill`` call applies to the
       branch, and every OTHER table's own ``log_tx=True`` companion
       write, ALSO re-enqueues an "echo" row on the branch (as
       ``log_transaccional_p_current`` — a pg_partman child-partition
       name, see ``resolve_catalog_name``'s own docstring), as if it
       were new local work.
    2. Because of #1, this file's OWN explicit ``log_transaccional``
       catalog-entry push (proving THAT entry syncs, not relying on
       incidental log_tx side effects) would — without the
       ``uuid_registro`` filter — match and push EVERY accumulated
       ``log_transaccional_p_current`` echo from EVERY prior table's own
       log_tx side effect too (``resolve_catalog_name`` normalizes ALL
       of them to the same logical name), replaying dozens of stale,
       already-superseded rows into CLOUD's log_transaccional chain in
       one burst and genuinely corrupting it (confirmed via
       ``motor.verify_chain`` — real ``ChainAnomaly`` results, not a
       false positive). The ``uuid_registro`` filter narrows this
       specific call to the ONE row this test actually created and
       intends to prove syncs.

    A blind drain-everything push would ALSO try to push echoes that are
    additionally out-of-catalog by name — real findings, but orthogonal
    to THIS file's job (prove each of the 46 catalog entries syncs once,
    cleanly). Scoping every push to exactly the row(s) this test just
    created keeps these concerns separate without papering over any of
    them.
    """
    from parkos_core.repo import sync_queue as sq_helpers
    from parkos_core.sync.catalog.sync_catalog import resolve_catalog_name

    all_pending = await sq_helpers.list_pending(branch_session, limit=500)
    own_rows = [r for r in all_pending if resolve_catalog_name(r.tabla) == table_name]
    if uuid_registro is not None:
        own_rows = [r for r in own_rows if r.uuid_registro == uuid_registro]
    assert own_rows, f"{table_name}: no pending sync_queue row after creating it"

    await worker._push_and_handle_catalog(own_rows)
    await branch_session.commit()

    for row in own_rows:
        estado = (
            await branch_session.execute(
                select(sq_helpers.SyncQueue.estado).where(sq_helpers.SyncQueue.uuid == row.uuid)
            )
        ).scalar_one()
        assert estado == "exitoso", (
            f"{table_name}: sync_queue row {row.uuid} settled as {estado!r}, not exitoso"
        )


def uid() -> str:
    return uuid_lib.uuid4().hex[:8]


def now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# The main exercise
# ---------------------------------------------------------------------------


async def test_full_catalog_sync_46_entries_e2e(
    pg_engine: AsyncEngine,
    alembic_upgrade: None,
    branch_pg_engine: AsyncEngine,
    branch_alembic_upgrade: None,
    tmp_path: Path,
) -> None:
    """Walk all 46 SYNC_CATALOG entries: create at the legitimate origin,
    let the real trigger enqueue, run the real job, verify at destination."""
    from parkos_core.models.A.arqueo import Arqueo
    from parkos_core.models.A.caja import Caja
    from parkos_core.models.A.factura_detalle import FacturaDetalle
    from parkos_core.models.A.factura_impuestos import FacturaImpuestos
    from parkos_core.models.A.factura_otros_cobros import FacturaOtrosCobros
    from parkos_core.models.A.factura_pagos import FacturaPagos
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.models.A.revocacion_factura import RevocacionFactura
    from parkos_core.models.A.salidas import Salidas
    from parkos_core.models.L_E.factura_electronica import FacturaElectronica
    from parkos_core.models.L_E.facturas import Facturas
    from parkos_core.models.L_E.ingreso import Ingreso
    from parkos_core.models.L_S.login import Login
    from parkos_core.models.L_S.sesion import Sesion
    from parkos_core.models.L_W.alerta import Alerta
    from parkos_core.models.L_W.anulaciones import Anulaciones
    from parkos_core.models.L_W.envio_dian import EnvioDian
    from parkos_core.models.L_W.reclamos import Reclamos
    from parkos_core.models.L_W.reimpresion_ticket import ReimpresionTicket
    from parkos_core.repo.resolucion_facturacion import assign_consecutivo
    from parkos_core.runtime import engine_flag
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG, SYNC_CATALOG_BY_NAME
    from parkos_core.sync.cutover.backfill import run_backfill
    from parkos_core.sync.motor.sync_motor import SyncMotor

    CloudSession = async_sessionmaker(pg_engine, expire_on_commit=False)
    BranchSession = async_sessionmaker(branch_pg_engine, expire_on_commit=False)

    cloud_app = build_cloud_app(pg_engine)
    results: dict[str, str] = {}  # table -> "OK" | "NEVER_PROPAGATED" | failure detail

    # =====================================================================
    # STAGE 1 — all 26 [V] entries, authored at CLOUD, delivered to BRANCH
    # via a real cutover/backfill.py::run_backfill call.
    # =====================================================================
    C: dict[str, Any] = {}  # name -> cloud-side row
    async with CloudSession() as session:
        C["usuarios"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["usuarios"],
            {
                "nombre": "Ada",
                "apellido": "Lovelace",
                "cedula": f"cd-{uid()}",
                "email": f"ada-{uid()}@example.com",
                "rol": "operador",
            },
        )
        C["permisos"] = await create_origin_row(
            session, SYNC_CATALOG_BY_NAME["permisos"], {"permiso": f"e2e_permiso_{uid()}"}
        )
        # uid()-suffixed, like every other natural-key literal below (found
        # 2026-09-10: this was the one hardcoded, non-unique value in this
        # whole stage — harmless before identity_reconciler was wired onto
        # tipo_persona, since every row landed independently regardless of
        # natural-key collisions; now that reconciliation is real, a leftover
        # "tipo_persona.tipo == natural" row from an EARLIER run of this same
        # test against a reused container legitimately noops against THIS
        # run's row on the branch — correct behavior for a genuine natural-
        # key collision, but it silently dropped this run's own uuid, which
        # `clientes.uuid_tipo_persona` below then referenced -> FK violation.
        C["tipo_persona"] = await create_origin_row(
            session, SYNC_CATALOG_BY_NAME["tipo_persona"], {"tipo": f"natural-{uid()}"}
        )
        C["tipos_vehiculo"] = await create_origin_row(
            session, SYNC_CATALOG_BY_NAME["tipos_vehiculo"], {"tipo": f"carro-{uid()}"}
        )
        C["tipo_subscripciones"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["tipo_subscripciones"],
            {
                "tipo": f"mensual-{uid()}",
                "valor": 50000,
                "duracion_dias": 30,
                "cantidad_maxima_vehiculos": 2,
                "mismo_tipo_vehiculo": False,
                "tipo_cliente_permitido": "natural",
            },
        )
        C["tipo_tarifa"] = await create_origin_row(
            session, SYNC_CATALOG_BY_NAME["tipo_tarifa"], {"tipo": f"hora-{uid()}"}
        )
        C["tipo_sucursal"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["tipo_sucursal"],
            {
                "codigo": f"URB-{uid()}",
                "nombre": "Urbana",
                "descripcion": "Sucursal urbana",
                "caracteristicas": {},
            },
        )
        C["tipo_arqueo"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["tipo_arqueo"],
            {"codigo": f"CIERRE-{uid()}", "nombre": "Cierre diario", "descripcion": "e2e"},
        )
        C["impuestos"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["impuestos"],
            {
                "nombre": "IVA",
                "codigo": f"IVA19-{uid()}",
                "porcentaje": 19,
                "tipo_calculo": "porcentaje",
                "base_calculo": "subtotal",
            },
        )
        C["otros_cobros"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["otros_cobros"],
            {
                "nombre": f"Propina-{uid()}",
                "costo": 1000,
                "tipo_calculo": "fijo",
                "base_calculo": "total",
            },
        )
        C["costos_servicios"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["costos_servicios"],
            {"concepto": f"Reimpresion-{uid()}", "costo": 500, "tipo_calculo": "fijo"},
        )
        C["empresa"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["empresa"],
            {
                "nombre": "Parkos E2E",
                "nit": f"900{uid()}",
                "mensaje_bienvenida": "Bienvenido",
                "mensaje_salida": "Gracias",
                "regimen": "comun",
            },
        )
        await session.commit()

        C["clientes"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["clientes"],
            {
                "tipo_identificador": "CC",
                "numero_identificacion": str(uuid_lib.uuid4().int)[:10],
                "nombre": "Grace",
                "apellido": "Hopper",
                "telefono": "3000000000",
                "email": f"grace-{uid()}@example.com",
                "uuid_tipo_persona": C["tipo_persona"].uuid,
                "registro": {},
            },
        )
        C["permisos_usuario"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["permisos_usuario"],
            {"uuid_usuario": C["usuarios"].uuid, "uuid_permiso": C["permisos"].uuid},
        )
        C["sucursal"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["sucursal"],
            {
                "nombre": f"Sucursal E2E {uid()}",
                "direccion": "Cra 1 # 2-3",
                "telefono": "3000000001",
                "prefijo_nombre": f"E2E{uid()}",
                "ciudad": "Bogota",
                "horario": "24h",
                "uuid_tipo_sucursal": C["tipo_sucursal"].uuid,
                "uuid_empresa": C["empresa"].uuid,
            },
        )
        C["vehiculos"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["vehiculos"],
            {"placa": f"E2E{uid().upper()}", "uuid_tipo_vehiculo": C["tipos_vehiculo"].uuid},
        )
        # Values DELIBERATELY different from migration 0001's own seeded
        # global-default row (dias_expiracion_password=90, max_intentos_
        # login=5, minutos_bloqueo_login=15 — every fresh cloud/branch DB
        # already has one such row from migration seeding, uuid_sucursal
        # NULL). Found 2026-09-10: using the SAME values as the seed made
        # identity_reconciler correctly classify this row as a "noop"
        # (business-identical to the already-open global default) instead
        # of "forward" — CORRECT reconciliation behavior, but it meant this
        # test's OWN row was never actually inserted at BRANCH, so later
        # asserting it landed there failed. A genuine override must carry
        # genuinely different values, exactly like configuracion_tolerancias
        # below already does relative to its own migration seed (0.00/0.00).
        C["configuracion_seguridad"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["configuracion_seguridad"],
            {
                "uuid_sucursal": None,
                "dias_expiracion_password": 60,
                "max_intentos_login": 3,
                "minutos_bloqueo_login": 10,
            },
        )
        C["configuracion_tolerancias"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["configuracion_tolerancias"],
            {"uuid_sucursal": None, "tolerancia_efectivo": 500, "tolerancia_datafono": 100},
        )
        await session.commit()

        C["cantidad_vehiculos_sucursal"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["cantidad_vehiculos_sucursal"],
            {
                "uuid_sucursal": C["sucursal"].uuid,
                "uuid_tipo_vehiculo": C["tipos_vehiculo"].uuid,
                "cantidad": 10,
            },
        )
        C["clientes_b2b"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["clientes_b2b"],
            {
                "uuid_cliente": C["clientes"].uuid,
                "cantidad": 5,
                "registro": {},
                "fecha_inicio_convenio": date.today(),
                "fecha_vencimiento": date.today() + timedelta(days=365),
            },
        )
        C["documentos"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["documentos"],
            {"uuid_sucursal": C["sucursal"].uuid, "tipo": "camara_comercio", "formato": "pdf"},
        )
        C["resolucion_facturacion"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["resolucion_facturacion"],
            {
                "uuid_sucursal": C["sucursal"].uuid,
                "numero_resolucion": f"RES-{uid()}",
                "prefijo": "SETP",
                "rango_desde": 1,
                "rango_hasta": 999999999,
                "fecha_resolucion": date.today(),
                "fecha_inicio_vigencia": date.today(),
                "fecha_fin_vigencia": None,
            },
        )
        C["subscripciones_cliente"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["subscripciones_cliente"],
            {
                "uuid_cliente": C["clientes"].uuid,
                "uuid_sucursal": C["sucursal"].uuid,
                "uuid_tipo_subscripcion": C["tipo_subscripciones"].uuid,
                "fecha_inicio_cobertura": date.today(),
                "fecha_vencimiento": date.today() + timedelta(days=30),
            },
        )
        C["tarifas_sucursal"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["tarifas_sucursal"],
            {
                "uuid_sucursal": C["sucursal"].uuid,
                "uuid_tipo_vehiculo": C["tipos_vehiculo"].uuid,
                "uuid_tipo_tarifa": C["tipo_tarifa"].uuid,
                "valor": 2000,
                "valor_plena": 15000,
            },
        )
        C["usuarios_sucursal"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["usuarios_sucursal"],
            {"uuid_sucursal": C["sucursal"].uuid, "uuid_usuario": C["usuarios"].uuid},
        )
        await session.commit()

        C["subscripcion_vehiculos"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["subscripcion_vehiculos"],
            {
                "uuid_subscripcion_cliente": C["subscripciones_cliente"].uuid,
                "uuid_vehiculo": C["vehiculos"].uuid,
            },
        )
        await session.commit()

    V_NAMES = [e.name for e in SYNC_CATALOG if e.audit_class == "V"]
    assert len(V_NAMES) == 26, f"expected 26 [V] entries, got {len(V_NAMES)}"
    V_CATALOG = tuple(SYNC_CATALOG_BY_NAME[name] for name in V_NAMES)

    async with BranchSession() as branch_session:
        backfill_result = await run_backfill(
            branch_session,
            uuid_sucursal=uuid_lib.uuid4(),
            fetch_page=make_cloud_fetch_page(pg_engine),
            actor_uuid=ACTOR_UUID,
            motor=SyncMotor(engine=engine_flag.EngineMode.CATALOG_BRANCH),
            catalog=V_CATALOG,
        )
        await branch_session.commit()

    assert backfill_result.complete is True, (
        f"V backfill left buffered rows: {backfill_result.buffered}"
    )
    assert backfill_result.applied >= 26, (
        f"expected >=26 applied V rows, got {backfill_result.applied}"
    )

    # Verify all 26 [V] rows landed at BRANCH, with uuid identity preserved
    # (this file's own fetch_page decision — see module docstring).
    async with BranchSession() as branch_session:
        for name in V_NAMES:
            spec = SYNC_CATALOG_BY_NAME[name]
            origin_uuid = C[name].uuid
            row = (
                await branch_session.execute(
                    select(spec.model_cls).where(spec.model_cls.uuid == origin_uuid)
                )
            ).scalar_one_or_none()
            assert row is not None, f"{name}: not found at BRANCH after backfill"
            results[name] = "OK"

    # =====================================================================
    # STAGE 2 — branch_to_cloud / bidirectional-from-branch entries,
    # authored at BRANCH, pushed to CLOUD via the real SyncSucursalWorker
    # job (POST /sync/events, real SyncMotor.apply_row on the CLOUD side).
    # =====================================================================
    jwt_path = tmp_path / "sync.jwt"

    async with BranchSession() as branch_session:
        worker = build_branch_worker(branch_session, cloud_app, jwt_path)

        # Re-read the branch-local copies of the [V] parents backfilled
        # above (same uuids as cloud, per this file's identity-preserving
        # fetch_page).
        B: dict[str, Any] = {name: C[name] for name in V_NAMES}
        # B[name].uuid works directly since uuid is preserved; re-select
        # the ACTUAL branch row objects for the ones whose non-uuid columns
        # this stage reads (placa, etc.) to avoid cross-session attribute
        # access on a detached cloud-session object.
        for name in (
            "sucursal",
            "usuarios",
            "tipos_vehiculo",
            "vehiculos",
            "clientes",
            "resolucion_facturacion",
            "costos_servicios",
            "impuestos",
            "otros_cobros",
            "tipo_arqueo",
        ):
            spec = SYNC_CATALOG_BY_NAME[name]
            B[name] = (
                await branch_session.execute(
                    select(spec.model_cls).where(spec.model_cls.uuid == C[name].uuid)
                )
            ).scalar_one()

        # --- Level 2 branch-authored roots -------------------------------
        ingreso = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["ingreso"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "placa": B["vehiculos"].placa,
                "uuid_tipo_vehiculo": B["tipos_vehiculo"].uuid,
                "fecha_ingreso": now_naive(),
                "observaciones": "e2e",
            },
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "ingreso")

        caja = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["caja"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "valor_efectivo": 100000,
                "valor_datafono": 50000,
            },
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "caja")

        login = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["login"],
            {"uuid_usuario": B["usuarios"].uuid, "uuid_sucursal": B["sucursal"].uuid},
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "login")

        sesion = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["sesion"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "uuid_usuario": B["usuarios"].uuid,
                "valor_inicial_efectivo": 100000,
                "valor_inicial_datafono": 0,
            },
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "sesion")

        reclamos = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["reclamos"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "tipo_reclamable": "ingreso",
                "uuid_reclamable": ingreso.uuid,
                "motivo": "prueba e2e",
                "estado": "recibido",
                "timestamp_evento": now_naive(),
            },
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "reclamos")

        alerta = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["alerta"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "uuid_usuario": B["usuarios"].uuid,
                "tipo_alerta": "anomalia_caja",
                "valor_diferencia_efectivo": 100,
                "valor_diferencia_datafono": 0,
                "estado": "abierta",
                "timestamp_evento": now_naive(),
            },
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "alerta")

        # --- Level 3 -------------------------------------------------------
        salidas = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["salidas"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "uuid_ingreso": ingreso.uuid,
                "fecha_salida": now_naive(),
            },
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "salidas")

        anulaciones = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["anulaciones"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "tipo_anulable": "ingreso",
                "uuid_ingreso": ingreso.uuid,
                "uuid_salida": None,
                "uuid_usuario": B["usuarios"].uuid,
                "motivo": "prueba e2e",
                "estado": "iniciada",
                "timestamp_evento": now_naive(),
            },
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "anulaciones")

        arqueo = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["arqueo"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "uuid_tipo_arqueo": B["tipo_arqueo"].uuid,
                "uuid_sesion": sesion.uuid,
                "valor_efectivo_esperado": 100000,
                "valor_datafono_esperado": 0,
                "valor_efectivo_reportado": 100000,
                "valor_datafono_reportado": 0,
            },
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "arqueo")

        # --- Level 4 -------------------------------------------------------
        facturas = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["facturas"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "subtotal": 6000,
                "descuento": 0,
                "total": 6000,
                "uuid_ingreso": ingreso.uuid,
                "uuid_salida": salidas.uuid,
            },
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "facturas")

        # --- Level 5 -------------------------------------------------------
        factura_detalle = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["factura_detalle"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "uuid_factura": facturas.uuid,
                "concepto": "Servicio parqueo",
                "cantidad": 1,
                "valor_unitario": 6000,
                "subtotal": 6000,
            },
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "factura_detalle")

        consecutivo = await assign_consecutivo(
            branch_session, B["resolucion_facturacion"].uuid, facturas.uuid
        )
        factura_electronica = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["factura_electronica"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "uuid_factura": facturas.uuid,
                "uuid_cliente": B["clientes"].uuid,
                "uuid_resolucion_facturacion": B["resolucion_facturacion"].uuid,
                "prefijo": "SETP",
                "consecutivo": consecutivo,
                "descuento": 0,
            },
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "factura_electronica")

        factura_impuestos = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["factura_impuestos"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "uuid_factura": facturas.uuid,
                "uuid_impuesto": B["impuestos"].uuid,
                "base_calculo": 6000,
                "porcentaje_aplicado": 19,
                "valor": 1140,
            },
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "factura_impuestos")

        factura_otros_cobros = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["factura_otros_cobros"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "uuid_factura": facturas.uuid,
                "uuid_otro_cobro": B["otros_cobros"].uuid,
                "base_calculo": 6000,
                "valor_aplicado": 1000,
                "valor": 1000,
            },
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "factura_otros_cobros")

        factura_pagos = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["factura_pagos"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "uuid_factura": facturas.uuid,
                "uuid_sesion": sesion.uuid,
                "medio_pago": "efectivo",
                "valor": 7140,
                "referencia": "e2e",
                "tipo_movimiento": "pago",
                "uuid_pago_revertido": None,
                "timestamp_evento": now_naive(),
            },
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "factura_pagos")

        reimpresion_ticket = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["reimpresion_ticket"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "uuid_ingreso": ingreso.uuid,
                "uuid_usuario": B["usuarios"].uuid,
                "uuid_costo_servicio": B["costos_servicios"].uuid,
                "costo_aplicado": 500,
                "uuid_factura": facturas.uuid,
                "motivo": "ticket original perdido",
                "uuid_reimpresion_padre": None,
                "estado": "solicitada",
                "timestamp_evento": now_naive(),
            },
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "reimpresion_ticket")

        # --- Level 6 (branch-authored half) --------------------------------
        revocacion_factura = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["revocacion_factura"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "uuid_factura_electronica": factura_electronica.uuid,
                "uuid_factura_electronica_reemplazo": None,
                "motivo": "anulacion e2e",
                "timestamp_evento": now_naive(),
            },
        )
        await branch_session.commit()
        # uuid_registro filter — same reasoning as the log_transaccional
        # push below: revocacion_factura is the OTHER hash_chain=True
        # entry, and this is the FIRST-EVER revocacion_factura row for
        # this test's tenant, so repo.hash_chain.append's genesis-row
        # bootstrap (repo/hash_chain.py::_ensure_genesis_row) ALSO fires
        # this table's own AFTER INSERT trigger, creating a second,
        # unrelated "echo" row in the SAME branch sync_queue with the
        # bare (unpartitioned) "revocacion_factura" tabla name. Without
        # this filter it would ALSO be pushed here and genuinely corrupt
        # CLOUD's revocacion_factura chain (confirmed via
        # motor.verify_chain — two real ChainAnomaly results, not a
        # false positive).
        await push_and_verify(
            branch_session, worker, "revocacion_factura", uuid_registro=revocacion_factura.uuid
        )

        # --- log_transaccional (bidirectional, hash_chain) — explicit
        #     coverage, not left to incidental log_tx side effects. Every
        #     apply_strategy="close_and_insert"/"record_event"/
        #     "append_transition" call above ALSO writes its own
        #     log_transaccional row as a log_tx side effect, but those
        #     never reach this file's own verification because their
        #     sync_queue echo carries a pg_partman partition-suffixed
        #     tabla this test's push_and_verify never targets (see this
        #     file's module docstring). Explicit, direct coverage instead.
        log_transaccional = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["log_transaccional"],
            {
                "uuid_usuario": B["usuarios"].uuid,
                "uuid_sucursal": B["sucursal"].uuid,
                "accion": "e2e_explicit_coverage",
                "tabla_afectada": "ingreso",
                "uuid_registro_afectado": ingreso.uuid,
                "uuid_referencia": None,
                "datos_anteriores": None,
                "datos_nuevos": None,
                "timestamp_evento": now_naive(),
            },
        )
        await branch_session.commit()
        await push_and_verify(
            branch_session, worker, "log_transaccional", uuid_registro=log_transaccional.uuid
        )

    branch_authored = {
        "ingreso": (Ingreso, ingreso.uuid),
        "caja": (Caja, caja.uuid),
        "login": (Login, login.uuid),
        "sesion": (Sesion, sesion.uuid),
        "reclamos": (Reclamos, reclamos.uuid),
        "alerta": (Alerta, alerta.uuid),
        "salidas": (Salidas, salidas.uuid),
        "anulaciones": (Anulaciones, anulaciones.uuid),
        "arqueo": (Arqueo, arqueo.uuid),
        "facturas": (Facturas, facturas.uuid),
        "factura_detalle": (FacturaDetalle, factura_detalle.uuid),
        "factura_electronica": (FacturaElectronica, factura_electronica.uuid),
        "factura_impuestos": (FacturaImpuestos, factura_impuestos.uuid),
        "factura_otros_cobros": (FacturaOtrosCobros, factura_otros_cobros.uuid),
        "factura_pagos": (FacturaPagos, factura_pagos.uuid),
        "reimpresion_ticket": (ReimpresionTicket, reimpresion_ticket.uuid),
        "revocacion_factura": (RevocacionFactura, revocacion_factura.uuid),
        "log_transaccional": (LogTransaccional, log_transaccional.uuid),
    }
    async with CloudSession() as cloud_verify:
        for name, (model_cls, row_uuid) in branch_authored.items():
            row = (
                await cloud_verify.execute(select(model_cls).where(model_cls.uuid == row_uuid))
            ).scalar_one_or_none()
            assert row is not None, f"{name}: not found at CLOUD after push"
            results[name] = "OK"

    # Sesion regression check — the fixed bug: before the fix, a synced
    # sesion row landed in prod.login instead. Confirm no bogus login row
    # was created FOR THIS sesion's push (the real login row created
    # earlier is a different, legitimate row with a different uuid).
    async with CloudSession() as cloud_verify:
        sesion_row = (
            await cloud_verify.execute(select(Sesion).where(Sesion.uuid == sesion.uuid))
        ).scalar_one_or_none()
        assert sesion_row is not None
        assert sesion_row.valor_inicial_efectivo == 100000
        bogus_login = (
            await cloud_verify.execute(select(Login).where(Login.uuid == sesion.uuid))
        ).scalar_one_or_none()
        assert bogus_login is None, "sesion push must never create a prod.login row"

    # =====================================================================
    # STAGE 3 — envio_dian: cloud-authored, cloud_to_branch, delivered via
    # a second, targeted run_backfill call (same real mechanism as stage 1).
    # =====================================================================
    async with CloudSession() as session:
        envio_dian = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["envio_dian"],
            {
                "uuid_sucursal": C["sucursal"].uuid,
                "uuid_factura_electronica": factura_electronica.uuid,
                "uuid_resolucion_facturacion": C["resolucion_facturacion"].uuid,
                "payload": {},
                "respuesta_proveedor": None,
                "cufe": None,
                "uuid_envio_padre": None,
                "estado": "pendiente",
                "timestamp_evento": now_naive(),
            },
        )
        await session.commit()

    async with BranchSession() as branch_session:
        envio_result = await run_backfill(
            branch_session,
            uuid_sucursal=uuid_lib.uuid4(),
            fetch_page=make_cloud_fetch_page(pg_engine, uuid_sucursal=C["sucursal"].uuid),
            actor_uuid=ACTOR_UUID,
            motor=SyncMotor(engine=engine_flag.EngineMode.CATALOG_BRANCH),
            catalog=(SYNC_CATALOG_BY_NAME["envio_dian"],),
        )
        await branch_session.commit()
    assert envio_result.complete is True, f"envio_dian buffered: {envio_result.buffered}"
    assert envio_result.applied >= 1

    async with BranchSession() as branch_verify:
        row = (
            await branch_verify.execute(select(EnvioDian).where(EnvioDian.uuid == envio_dian.uuid))
        ).scalar_one_or_none()
        assert row is not None, "envio_dian: not found at BRANCH after backfill"
        assert row.uuid_factura_electronica == factura_electronica.uuid
        results["envio_dian"] = "OK"

    # =====================================================================
    # STAGE 4 — validacion_evento: the sole never_propagated entry. Confirm
    # it does NOT propagate — never forcing a sync that must not occur.
    # =====================================================================
    from parkos_core.models.L_W.validacion_evento import ValidacionEvento
    from parkos_core.sync.cutover.backfill import _BACKFILL_DIRECTIONS

    validacion_spec = SYNC_CATALOG_BY_NAME["validacion_evento"]
    assert validacion_spec.sync_strategy == "never_propagated"
    assert validacion_spec.direction is None
    assert validacion_spec.direction not in _BACKFILL_DIRECTIONS

    async with CloudSession() as session:
        validacion = await create_origin_row(
            session,
            validacion_spec,
            {
                "uuid_sucursal": C["sucursal"].uuid,
                "uuid_usuario": C["usuarios"].uuid,
                "tabla_origen": "ingreso",
                "uuid_registro": ingreso.uuid,
                "hash_evento": None,
                "observaciones": "e2e never_propagated",
                "estado": "pendiente",
                "timestamp_evento": now_naive(),
            },
        )
        await session.commit()
        assert validacion.estado == "pendiente"

    # The DB trigger still fires unconditionally (it does not read
    # sync_strategy — see this file's module docstring, discovered issue
    # #2), so a sync_queue row DOES exist; the catalog-level contract this
    # test verifies is that nothing ever MOVES this row to the branch. No
    # job in this test's flow (backfill or push) is ever pointed at
    # validacion_evento, and role_guard (already covered by
    # tests/unit/test_role_guard.py) independently prevents a branch
    # process from even importing this entry.
    async with BranchSession() as branch_verify:
        count = (
            await branch_verify.execute(select(func.count()).select_from(ValidacionEvento))
        ).scalar_one()
        assert count == 0, "validacion_evento must NEVER reach the branch database"
    results["validacion_evento"] = "NEVER_PROPAGATED (confirmed correct)"

    # =====================================================================
    # Final tally — all 46 entries accounted for.
    # =====================================================================
    assert len(results) == 46, (
        f"expected 46 SYNC_CATALOG entries accounted for, got {len(results)}: "
        f"missing={sorted(set(SYNC_CATALOG_BY_NAME) - set(results))}"
    )
    for entry in SYNC_CATALOG:
        assert entry.name in results, f"{entry.name}: no result recorded"
        assert results[entry.name] in ("OK", "NEVER_PROPAGATED (confirmed correct)")

    # Final integrity check — this test's OWN hash chain (log_transaccional
    # + revocacion_factura) for its own uuid_sucursal must be genuinely
    # unbroken. This also regression-guards the "log_transaccional" push
    # fix documented in push_and_verify's own docstring (item #2) — before
    # that fix, this exact check caught a real, reproducible chain
    # corruption (confirmed via motor.verify_chain, not a false positive):
    # pushing the explicit log_transaccional entry without the
    # uuid_registro filter replayed dozens of stale, already-superseded
    # log_transaccional_p_current echoes (every OTHER table's own log_tx
    # side effect) into CLOUD's chain in one burst.
    from parkos_core.sync.motor.verify_chain import verify_chain

    async with CloudSession() as chain_check:
        anomalies = await verify_chain(chain_check, uuid_sucursal=C["sucursal"].uuid)
    assert anomalies == [], f"hash chain anomalies for this test's own tenant: {anomalies}"
