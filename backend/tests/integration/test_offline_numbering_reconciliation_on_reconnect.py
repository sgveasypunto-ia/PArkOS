"""test_offline_numbering_reconciliation_on_reconnect.py — QA campaign
scenario 4.6.e ("numeracion offline con nodo central caido, reconciliada al
reconectar").

``test_branch_offline_flow.py`` already proves the LOCAL half of this
scenario (emit + number a ``factura_electronica`` completely offline, with a
REAL failed TCP connection attempt proving the cloud is unreachable) and
``test_consecutivo_assignment.py`` already proves sequential/no-gap/
idempotent numbering in isolation. Neither proves the RECONNECTION half:
that the offline-numbered invoices actually reach the central node without
collision or gap, and that the original document is never rewritten there —
only reconciled.

This test closes exactly that gap, real end to end:

1. Prove the CLOUD is genuinely unreachable (same real-socket-refusal
   mechanism as ``test_branch_offline_flow.py`` — ``SyncSucursalWorker.
   _detect_applier_mode()`` against a non-listening address).
2. While "offline", emit 3 ``factura_electronica`` at BRANCH with real local
   numbering (``repo.resolucion_facturacion.assign_consecutivo``).
3. "Reconnect" — build the REAL ``SyncSucursalWorker`` against a REAL
   FastAPI app mounting the unmodified ``sync_router`` (a second, physically
   separate real Postgres as the CLOUD side) and push every pending row via
   the real ``POST /sync/events`` -> ``SyncMotor.apply_row`` path.
4. At CLOUD: assert the 3 invoices landed with their EXACT origin consecutivo
   (no renumbering, no collision, no gap) and EXACT origin uuid (a fresh
   INSERT of the SAME row identity — never an update of a pre-existing one).

Architecture note: the container/backfill/push scaffolding below is
duplicated from ``test_e2e_full_catalog_sync.py`` rather than imported —
``tests/integration/`` has no ``__init__.py`` (only ``tests/`` itself is a
real package), so a relative import between sibling test modules raises
``ImportError: attempted relative import with no known parent package``
under this repo's pytest collection.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid as uuid_lib
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from fastapi import FastAPI
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000e2e03")
UNREACHABLE_CLOUD_URL = "http://127.0.0.1:1"

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEST_PG_IMAGE = os.environ.get("TEST_PG_IMAGE", "postgres:16-alpine")
ALEMBIC_TIMEOUT_S = int(os.environ.get("TEST_ALEMBIC_TIMEOUT", "30"))


@pytest.fixture(autouse=True)
def _catalog_engine_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from parkos_core.runtime import engine_flag

    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
    engine_flag._reset_cache_for_tests()


def uid() -> str:
    return uuid_lib.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# BRANCH-side Postgres container (mirrors test_e2e_full_catalog_sync.py).
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
            return
        except Exception as exc:
            last_err = exc
            time.sleep(0.5)
    pytest.fail(f"branch postgres never became ready: {last_err}")


@pytest.fixture(scope="module")
def branch_alembic_upgrade(branch_pg_dsn: str, _branch_wait_for_pg: None) -> None:
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
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.repo.hash_chain import _ensure_genesis_row

    Session = async_sessionmaker(branch_pg_engine, expire_on_commit=False)
    async with Session() as session:
        await _ensure_genesis_row(session, LogTransaccional, None)
        await session.commit()


# ---------------------------------------------------------------------------
# Real-service-layer row creation + real cross-node push.
# ---------------------------------------------------------------------------


async def create_origin_row(session: Any, spec: Any, attrs: dict[str, Any]) -> Any:
    from parkos_core.repo import append_only as ao_helpers
    from parkos_core.repo import event as event_helpers
    from parkos_core.repo import versioned as versioned_helpers

    strategy = spec.apply_strategy
    if strategy == "close_and_insert":
        row = await versioned_helpers.close_and_insert(
            session, spec.model_cls, current_uuid=None, new_attrs=attrs, actor_uuid=ACTOR_UUID
        )
    elif strategy == "record_event":
        row = await event_helpers.record_event(
            session, spec.model_cls, actor_uuid=ACTOR_UUID, new_attrs=attrs
        )
    elif strategy == "append_event":
        row = await ao_helpers.append_event(
            session, spec.model_cls, attrs, actor_uuid=ACTOR_UUID, chain_hash=spec.hash_chain
        )
    else:
        raise AssertionError(f"{spec.name}: no origin dispatch for apply_strategy={strategy!r}")
    await session.flush()
    return row


_QUEUE_LIKE_KEYS = frozenset(
    {"created_at", "created_by", "sync_status", "sync_timestamp", "sync_attempts"}
)
_V_BITEMPORAL_KEYS = frozenset({"vigente_desde", "vigente_hasta", "estado"})


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


def make_cloud_fetch_page(cloud_pg_engine: AsyncEngine, *, known_uuids: set[Any] | None = None):
    """Build a real ``FetchPage`` reading from the CLOUD engine.

    ``known_uuids`` scopes every fetch to rows THIS test itself created.
    Without it, on the shared, session-scoped ``pg_engine``
    (``conftest.py``), a fetch of ``clientes`` picks up another test's own
    open cliente row — one whose ``uuid_tipo_persona`` this test's own
    ``backfill_catalog`` never carries to the branch — a real
    ``ForeignKeyViolationError`` (confirmed real: same mechanism already
    fixed in ``test_snapshot_columns_immutable_on_catalog_mutation.py``,
    this file had its own separate copy of the helper still unscoped,
    2026-09-10 full-suite run).
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
            if known_uuids is not None:
                stmt = stmt.where(spec.model_cls.uuid.in_(known_uuids))
            rows = (await session.execute(stmt)).scalars().all()
        page_rows = tuple(_extract_business_attrs(spec, row) for row in rows)
        return BackfillPage(rows=page_rows, next_cursor=None, has_more=False)

    return fetch_page


def build_cloud_app(cloud_pg_engine: AsyncEngine) -> FastAPI:
    from fastapi import APIRouter
    from parkos_core.api.v1.sync_router import _sync_agent_claims
    from parkos_core.api.v1.sync_router import router as sync_router_obj
    from parkos_core.db.engine import get_session

    app = FastAPI()
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
            "jti": "offline-numbering-reconnect",
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
    branch_session: Any, worker: Any, table_name: str, *, uuid_registro: uuid_lib.UUID | None = None
) -> None:
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
        assert estado == "exitoso", f"{table_name}: {row.uuid} settled as {estado!r}, not exitoso"


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------


async def test_offline_numbering_reconciles_without_collision_on_reconnect(
    pg_engine: AsyncEngine,
    alembic_upgrade: None,
    branch_pg_engine: AsyncEngine,
    branch_alembic_upgrade: None,
    tmp_path: Path,
) -> None:
    from parkos_core.jobs.sync_sucursal import ApplierMode, SyncSucursalWorker
    from parkos_core.models.L_E.factura_electronica import FacturaElectronica
    from parkos_core.repo.resolucion_facturacion import assign_consecutivo
    from parkos_core.runtime import engine_flag
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
    from parkos_core.sync.cutover.backfill import run_backfill
    from parkos_core.sync.motor.sync_motor import SyncMotor
    from parkos_core.sync.transport import SyncHttpClient

    CloudSession = async_sessionmaker(pg_engine, expire_on_commit=False)
    BranchSession = async_sessionmaker(branch_pg_engine, expire_on_commit=False)
    cloud_app = build_cloud_app(pg_engine)

    # =====================================================================
    # 0. Prove the cloud is genuinely unreachable — a REAL failed socket
    #    attempt (mirrors test_branch_offline_flow.py step 0).
    # =====================================================================
    jwt_path = tmp_path / "sync.jwt"
    jwt_path.write_text("fake-jwt", encoding="utf-8")
    async with BranchSession() as probe_session:
        probe_worker = SyncSucursalWorker(
            jwt_path=jwt_path, base_url=UNREACHABLE_CLOUD_URL, session=probe_session
        )
        probe_worker._http_client = SyncHttpClient(
            base_url=probe_worker.base_url, jwt_path=probe_worker.jwt_path, timeout_s=2.0
        )
        mode = await probe_worker._detect_applier_mode()
        assert mode is ApplierMode.LEGACY, "a real unreachable cloud must fail-safe to legacy"
    with pytest.raises((httpx.ConnectError, httpx.ConnectTimeout, OSError)):
        async with httpx.AsyncClient(timeout=1.0) as client:
            await client.get(f"{UNREACHABLE_CLOUD_URL}/api/v1/sync/hello")

    # =====================================================================
    # 1. Minimal V-catalog prerequisites (cloud->branch, real backfill).
    # =====================================================================
    C: dict[str, Any] = {}
    async with CloudSession() as session:
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
        await session.commit()
        C["sucursal"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["sucursal"],
            {
                "nombre": f"Sucursal Offline {uid()}",
                "direccion": "Cra 1 # 2-3",
                "telefono": "3000000001",
                "prefijo_nombre": "OFF",
                "ciudad": "Bogota",
                "horario": "24h",
                "uuid_tipo_sucursal": C["tipo_sucursal"].uuid,
            },
        )
        # uid()-suffixed — a literal "natural" collides with the canonical
        # migration-seeded row (now identity-reconciled, T-PR12-011/D17) and
        # with any other test's own "natural" row in this session-scoped
        # shared DB (conftest.py::pg_engine). Same fix already applied in
        # test_e2e_full_catalog_sync.py for the identical reason.
        C["tipo_persona"] = await create_origin_row(
            session, SYNC_CATALOG_BY_NAME["tipo_persona"], {"tipo": f"natural-{uid()}"}
        )
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
            },
        )
        await session.commit()
        C["resolucion_facturacion"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["resolucion_facturacion"],
            {
                "uuid_sucursal": C["sucursal"].uuid,
                "numero_resolucion": f"RES-{uid()}",
                "prefijo": "OFF",
                "rango_desde": 1,
                "rango_hasta": 10,
                "fecha_resolucion": date.today(),
                "fecha_inicio_vigencia": date.today(),
                "fecha_fin_vigencia": None,
            },
        )
        await session.commit()

    backfill_catalog = tuple(
        SYNC_CATALOG_BY_NAME[name]
        for name in (
            "tipo_sucursal",
            "sucursal",
            "tipo_persona",
            "clientes",
            "resolucion_facturacion",
        )
    )
    async with BranchSession() as branch_session:
        result = await run_backfill(
            branch_session,
            uuid_sucursal=C["sucursal"].uuid,
            fetch_page=make_cloud_fetch_page(pg_engine, known_uuids={row.uuid for row in C.values()}),
            actor_uuid=ACTOR_UUID,
            motor=SyncMotor(engine=engine_flag.EngineMode.CATALOG_BRANCH),
            catalog=backfill_catalog,
        )
        await branch_session.commit()
    assert result.complete is True, f"backfill left buffered rows: {result.buffered}"

    # =====================================================================
    # 2. OFFLINE: emit 3 factura_electronica at BRANCH — no push, no cloud
    #    call of any kind happens in this section.
    # =====================================================================
    origin: dict[uuid_lib.UUID, dict[str, Any]] = {}
    async with BranchSession() as branch_session:
        origin_uuid_by_name = {
            "sucursal": C["sucursal"].uuid,
            "clientes": C["clientes"].uuid,
            "resolucion_facturacion": C["resolucion_facturacion"].uuid,
        }
        B: dict[str, Any] = {}
        for name, origin_uuid in origin_uuid_by_name.items():
            spec = SYNC_CATALOG_BY_NAME[name]
            B[name] = (
                await branch_session.execute(
                    select(spec.model_cls).where(spec.model_cls.uuid == origin_uuid)
                )
            ).scalar_one()

        emitted_consecutivos: list[int] = []
        for i in range(3):
            facturas = await create_origin_row(
                branch_session,
                SYNC_CATALOG_BY_NAME["facturas"],
                {
                    "uuid_sucursal": B["sucursal"].uuid,
                    "subtotal": 1000 * (i + 1),
                    "descuento": 0,
                    "total": 1000 * (i + 1),
                    "uuid_ingreso": None,
                    "uuid_salida": None,
                },
            )
            await branch_session.commit()

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
                    "prefijo": "OFF",
                    "consecutivo": consecutivo,
                    "descuento": 0,
                },
            )
            await branch_session.commit()
            emitted_consecutivos.append(consecutivo)
            origin[factura_electronica.uuid] = {
                "uuid_factura": facturas.uuid,
                "uuid_cliente": B["clientes"].uuid,
                "prefijo": "OFF",
                "consecutivo": consecutivo,
                "descuento": 0,
            }

        assert emitted_consecutivos == [1, 2, 3], (
            f"offline numbering was not sequential/no-gap: {emitted_consecutivos}"
        )

    # =====================================================================
    # 3. RECONNECT: real worker, real cloud app, push everything pending.
    # =====================================================================
    async with BranchSession() as branch_session:
        worker = build_branch_worker(branch_session, cloud_app, jwt_path)
        for fe_uuid, attrs in origin.items():
            await push_and_verify(
                branch_session, worker, "facturas", uuid_registro=attrs["uuid_factura"]
            )
            await push_and_verify(
                branch_session, worker, "factura_electronica", uuid_registro=fe_uuid
            )

    # =====================================================================
    # 4. Verify at CLOUD: no collision, no gap, identity preserved, and the
    #    row is a fresh insert of the SAME identity (never an update of a
    #    pre-existing central-side document).
    # =====================================================================
    async with CloudSession() as session:
        rows = (
            (
                await session.execute(
                    select(FacturaElectronica)
                    .where(
                        FacturaElectronica.uuid_resolucion_facturacion
                        == C["resolucion_facturacion"].uuid
                    )
                    .order_by(FacturaElectronica.consecutivo)
                )
            )
            .scalars()
            .all()
        )

        assert len(rows) == 3, f"expected 3 reconciled invoices at CLOUD, found {len(rows)}"
        assert [r.consecutivo for r in rows] == [1, 2, 3], (
            f"consecutivo sequence corrupted on reconciliation: {[r.consecutivo for r in rows]}"
        )
        assert len({r.consecutivo for r in rows}) == 3, "duplicate consecutivo landed at CLOUD"
        assert len({r.uuid for r in rows}) == 3, "duplicate uuid landed at CLOUD"

        for row in rows:
            expected = origin[row.uuid]
            assert row.uuid_factura == expected["uuid_factura"]
            assert row.uuid_cliente == expected["uuid_cliente"]
            assert row.prefijo == expected["prefijo"]
            assert row.consecutivo == expected["consecutivo"]
