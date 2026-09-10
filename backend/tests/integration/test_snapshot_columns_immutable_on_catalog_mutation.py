"""test_snapshot_columns_immutable_on_catalog_mutation.py — QA campaign
scenario 4.6.d ("tablas con columnas de foto/snapshot que no deben
recalcularse").

Real DBs, real service layer, real cross-node sync (POST /sync/events
against a real cloud FastAPI app, real SyncMotor apply, TWO physically
separate Postgres containers) — no mocks, no raw SQL to simulate state.

Architecture note: this file boots its OWN second real ``testcontainers``
Postgres (BRANCH), mirroring ``test_e2e_full_catalog_sync.py``'s own
documented decision (module-scoped, per-file — never a shared schema, never
changes another test file's fixture lifetime). The container/backfill/push
scaffolding below is intentionally duplicated from that file rather than
imported, because ``tests/integration/`` has no ``__init__.py`` (only
``tests/`` itself is a real package) — a relative import between sibling
test modules raises ``ImportError: attempted relative import with no known
parent package`` under this repo's pytest collection.

``models/V/impuestos.py``'s own docstring already CLAIMS "the invoice
NEVER reads this catalog live — it copies a snapshot to factura_impuestos
... This preserves the historical tax rate even when the catalog version
closes." This test is the actual end-to-end proof the QA campaign requires
instead of accepting that docstring's claim on faith:

1. BRANCH emits ``facturas`` + ``factura_impuestos`` + ``factura_otros_cobros``
   snapshotting the CURRENT (v1) ``impuestos``/``otros_cobros`` values.
2. Those rows are pushed to CLOUD via the real ``SyncSucursalWorker`` job
   (real HTTP POST /sync/events, real ``SyncMotor.apply_row`` on the CLOUD
   session).
3. AFTER that lands, the CLOUD catalog origin (``impuestos``, ``otros_cobros``)
   is mutated to a v2 via the real ``repo.versioned.close_and_insert``
   bi-temporal writer (the same writer every real catalog-update API path
   uses) — proven real by asserting ``current_version`` actually flipped.
4. The ALREADY-SYNCED ``factura_impuestos``/``factura_otros_cobros`` rows,
   re-read from BOTH nodes, must still show the ORIGINAL (v1) values —
   never the v2 ones — even though the v2 catalog row now coexists in the
   same database.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid as uuid_lib
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from fastapi import FastAPI
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000e2e02")

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
# Real-service-layer row creation + real cross-node push (mirrors
# test_e2e_full_catalog_sync.py's own create_origin_row / push_and_verify).
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


def make_cloud_fetch_page(cloud_pg_engine: AsyncEngine):
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
    from parkos_core.sync.cutover.backfill import BackfillPage

    async def fetch_page(tabla: str, cursor: str | None, limit: int) -> BackfillPage:
        spec = SYNC_CATALOG_BY_NAME[tabla]
        Session = async_sessionmaker(cloud_pg_engine, expire_on_commit=False)
        async with Session() as session:
            stmt = select(spec.model_cls)
            if spec.audit_class == "V":
                stmt = stmt.where(spec.model_cls.vigente_hasta.is_(None))
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
            "jti": "snapshot-immutable",
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


async def test_snapshot_columns_survive_catalog_mutation_on_both_nodes(
    pg_engine: AsyncEngine,
    alembic_upgrade: None,
    branch_pg_engine: AsyncEngine,
    branch_alembic_upgrade: None,
    tmp_path: Path,
) -> None:
    from parkos_core.models.A.factura_impuestos import FacturaImpuestos
    from parkos_core.models.A.factura_otros_cobros import FacturaOtrosCobros
    from parkos_core.models.V.impuestos import Impuestos
    from parkos_core.models.V.otros_cobros import OtrosCobros
    from parkos_core.repo.versioned import close_and_insert, current_version
    from parkos_core.runtime import engine_flag
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
    from parkos_core.sync.cutover.backfill import run_backfill
    from parkos_core.sync.motor.sync_motor import SyncMotor

    CloudSession = async_sessionmaker(pg_engine, expire_on_commit=False)
    BranchSession = async_sessionmaker(branch_pg_engine, expire_on_commit=False)
    cloud_app = build_cloud_app(pg_engine)

    # =====================================================================
    # 1. Minimal V-catalog prerequisites, created at CLOUD, delivered to
    #    BRANCH via the real cutover backfill.
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
                "nombre": f"Sucursal Snapshot {uid()}",
                "direccion": "Cra 1 # 2-3",
                "telefono": "3000000001",
                "prefijo_nombre": "SNP",
                "ciudad": "Bogota",
                "horario": "24h",
                "uuid_tipo_sucursal": C["tipo_sucursal"].uuid,
            },
        )
        C["impuestos_v1"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["impuestos"],
            {
                "nombre": "IVA",
                "codigo": f"IVA-{uid()}",
                "porcentaje": 19,
                "tipo_calculo": "porcentaje",
                "base_calculo": "subtotal",
            },
        )
        C["otros_cobros_v1"] = await create_origin_row(
            session,
            SYNC_CATALOG_BY_NAME["otros_cobros"],
            {"nombre": "Propina", "costo": 1000, "tipo_calculo": "fijo", "base_calculo": "total"},
        )
        await session.commit()

    backfill_catalog = tuple(
        SYNC_CATALOG_BY_NAME[name]
        for name in ("tipo_sucursal", "sucursal", "impuestos", "otros_cobros")
    )
    async with BranchSession() as branch_session:
        result = await run_backfill(
            branch_session,
            uuid_sucursal=C["sucursal"].uuid,
            fetch_page=make_cloud_fetch_page(pg_engine),
            actor_uuid=ACTOR_UUID,
            motor=SyncMotor(engine=engine_flag.EngineMode.CATALOG_BRANCH),
            catalog=backfill_catalog,
        )
        await branch_session.commit()
    assert result.complete is True, f"backfill left buffered rows: {result.buffered}"

    # =====================================================================
    # 2. BRANCH emits facturas + factura_impuestos + factura_otros_cobros,
    #    snapshotting the v1 catalog values.
    # =====================================================================
    jwt_path = tmp_path / "sync.jwt"
    async with BranchSession() as branch_session:
        worker = build_branch_worker(branch_session, cloud_app, jwt_path)

        origin_uuid_by_name = {
            "sucursal": C["sucursal"].uuid,
            "impuestos": C["impuestos_v1"].uuid,
            "otros_cobros": C["otros_cobros_v1"].uuid,
        }
        B: dict[str, Any] = {}
        for name, origin_uuid in origin_uuid_by_name.items():
            spec = SYNC_CATALOG_BY_NAME[name]
            B[name] = (
                await branch_session.execute(
                    select(spec.model_cls).where(spec.model_cls.uuid == origin_uuid)
                )
            ).scalar_one()

        facturas = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["facturas"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "subtotal": 6000,
                "descuento": 0,
                "total": 7140,
                "uuid_ingreso": None,
                "uuid_salida": None,
            },
        )
        await branch_session.commit()
        await push_and_verify(branch_session, worker, "facturas")

        ORIGINAL_IMPUESTO = {"base_calculo": 6000.0, "porcentaje_aplicado": 19.0, "valor": 1140.0}
        factura_impuestos = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["factura_impuestos"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "uuid_factura": facturas.uuid,
                "uuid_impuesto": B["impuestos"].uuid,
                **ORIGINAL_IMPUESTO,
            },
        )
        await branch_session.commit()
        await push_and_verify(
            branch_session, worker, "factura_impuestos", uuid_registro=factura_impuestos.uuid
        )

        ORIGINAL_OTRO_COBRO = {"base_calculo": 6000.0, "valor_aplicado": 1000.0, "valor": 1000.0}
        factura_otros_cobros = await create_origin_row(
            branch_session,
            SYNC_CATALOG_BY_NAME["factura_otros_cobros"],
            {
                "uuid_sucursal": B["sucursal"].uuid,
                "uuid_factura": facturas.uuid,
                "uuid_otro_cobro": B["otros_cobros"].uuid,
                **ORIGINAL_OTRO_COBRO,
            },
        )
        await branch_session.commit()
        await push_and_verify(
            branch_session, worker, "factura_otros_cobros", uuid_registro=factura_otros_cobros.uuid
        )

    # =====================================================================
    # 3. Mutate the CLOUD catalog origin to a v2 — real bi-temporal writer,
    #    proven real via current_version() before/after.
    # =====================================================================
    async with CloudSession() as session:
        before = await current_version(session, Impuestos, C["impuestos_v1"].uuid)
        assert before is not None
        assert float(before.porcentaje) == 19
        impuestos_v2 = await close_and_insert(
            session,
            Impuestos,
            current_uuid=C["impuestos_v1"].uuid,
            new_attrs={
                "nombre": "IVA",
                "codigo": before.codigo,
                "porcentaje": 21,
                "tipo_calculo": "porcentaje",
                "base_calculo": "subtotal",
            },
            actor_uuid=ACTOR_UUID,
        )
        await session.commit()
        after = await current_version(session, Impuestos, impuestos_v2.uuid)
        assert after is not None, (
            "sanity check failed: the catalog mutation itself did not take effect"
        )
        assert float(after.porcentaje) == 21

        otro_before = await current_version(session, OtrosCobros, C["otros_cobros_v1"].uuid)
        otros_cobros_v2 = await close_and_insert(
            session,
            OtrosCobros,
            current_uuid=C["otros_cobros_v1"].uuid,
            new_attrs={
                "nombre": otro_before.nombre,
                "costo": 2500,
                "tipo_calculo": otro_before.tipo_calculo,
                "base_calculo": otro_before.base_calculo,
            },
            actor_uuid=ACTOR_UUID,
        )
        await session.commit()
        otro_after = await current_version(session, OtrosCobros, otros_cobros_v2.uuid)
        assert otro_after is not None
        assert float(otro_after.costo) == 2500

    # =====================================================================
    # 4. The ALREADY-SYNCED snapshot rows must be untouched by the
    #    mutation — on BOTH nodes.
    # =====================================================================
    for Session, node in ((CloudSession, "CLOUD"), (BranchSession, "BRANCH")):
        async with Session() as session:
            fi = (
                await session.execute(
                    select(FacturaImpuestos).where(FacturaImpuestos.uuid == factura_impuestos.uuid)
                )
            ).scalar_one_or_none()
            assert fi is not None, f"factura_impuestos missing on {node} after sync"
            assert float(fi.porcentaje_aplicado) == 19.0, (
                f"{node}: factura_impuestos.porcentaje_aplicado recalculated to "
                f"{fi.porcentaje_aplicado} from the mutated catalog (was 19.0 originally)"
            )
            assert float(fi.valor) == 1140.0, f"{node}: factura_impuestos.valor recalculated"
            assert float(fi.base_calculo) == 6000.0

            fo = (
                await session.execute(
                    select(FacturaOtrosCobros).where(
                        FacturaOtrosCobros.uuid == factura_otros_cobros.uuid
                    )
                )
            ).scalar_one_or_none()
            assert fo is not None, f"factura_otros_cobros missing on {node} after sync"
            assert float(fo.valor) == 1000.0, (
                f"{node}: factura_otros_cobros.valor recalculated to {fo.valor} "
                "from the mutated catalog (was 1000.0 originally)"
            )
            assert float(fo.valor_aplicado) == 1000.0
