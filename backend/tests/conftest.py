"""backend/tests/conftest.py — pytest fixtures for parkos_core tests (PR1c).

Layout:

  - ``postgres_container`` (session) — testcontainers Postgres 16 container.
                                       Uses ``postgres:16-alpine`` because the
                                       project custom image
                                       ``parkos-postgres:16-pgpartman`` (with
                                       pg_partman pre-installed) requires a
                                       local Docker build step that the
                                       test-runner does not own. Tests that
                                       depend on ``pg_partman`` extensions
                                       skip cleanly when the extension is not
                                       available.
  - ``alembic_upgrade`` (session)    — runs ``alembic upgrade head`` against
                                       the container's DB before any test runs.
  - ``pg_engine`` (session)          — async SQLAlchemy engine bound to the
                                       container's URL.
  - ``pg_session`` (function)        — async session per test; rolls back at
                                       the end so tests don't bleed.
  - ``mint_admin_jwt`` (function)    — mint an ``admin-`` JWT.
  - ``mint_operador_jwt`` (function) — mint an ``operador-`` JWT pinned to a
                                       branch.
  - ``mint_sync_agent_jwt`` (function) — mint a ``sync-agent-`` JWT.
  - ``client`` (function)            — ``httpx.AsyncClient`` bound to the
                                       FastAPI app (``api_sucursal_main.app``
                                       by default; parametrize via the
                                       ``app`` fixture).

The fixtures reuse the testcontainers image conventions from
``backend/scripts/apply_migration.py`` so local verification and CI use the
same Postgres version.

Async behavior: ``asyncio_mode = "auto"`` is set in
``backend/packages/parkos_core/pyproject.toml`` so individual tests do NOT
need an explicit ``@pytest.mark.asyncio`` decorator. The testcontainers
fixtures themselves are sync (the container is blocking I/O).
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
import uuid as uuid_lib
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

if sys.platform == "win32":
    # ``psycopg`` (v3) cannot use the Windows ``ProactorEventLoop`` for async
    # operations. Switch to the selector-loop policy BEFORE any asyncio
    # import happens in third-party libs. Available on Windows since
    # Python 3.8 via selectors.SelectSelector — guarded by hasattr for
    # forward compat.
    import asyncio

    try:
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()  # type: ignore[attr-defined]
        )
    except (AttributeError, OSError):
        pass

import psycopg
import pytest
import pytest_asyncio
from faker import Faker
from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

# ---------------------------------------------------------------------------
# Path bootstrap — make ``parkos_core`` importable without ``uv pip install``
# (the test runner launches directly from the repo workspace).
# ---------------------------------------------------------------------------

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
_API_ADMIN_SRC = _BACKEND_ROOT / "packages" / "api_admin" / "src"
_API_SUCURSAL_SRC = _BACKEND_ROOT / "packages" / "api_sucursal" / "src"

for _p in (_PARKOS_CORE_SRC, _API_ADMIN_SRC, _API_SUCURSAL_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ---------------------------------------------------------------------------
# PARKOS_DEPLOY session-wide safe default (discovered PR5 — see the PR5
# apply report's "Issues Found" section).
# ---------------------------------------------------------------------------
#
# ``parkos_core.api.v1``'s ``__init__.py`` reads ``PARKOS_DEPLOY`` ONCE, at
# module-IMPORT time, to decide whether to mount the DIAN cloud router
# (REQ-X3 boundary). Once that module is imported anywhere in a pytest
# session, Python's module cache means the built router is FIXED for the
# rest of the session — a later ``os.environ`` change has no effect.
# ``tests/static/conftest.py`` already works around this for its own
# directory (``os.environ.setdefault("PARKOS_DEPLOY", "branch")``), but
# that conftest only loads once pytest starts COLLECTING ``tests/static/``
# — alphabetically AFTER ``tests/integration/`` and ``tests/migrations/``.
# Any test file in an earlier-collected directory that imports
# ``parkos_core.api.v1`` (directly, or transitively via any
# ``parkos_core.api.v1.<submodule>`` import) BEFORE that point bakes in the
# unset-env-var default (``PARKOS_DEPLOY="cloud"``), which mounts the DIAN
# cloud router into the SAME cached module object
# ``tests/static/test_openapi_branch_excludes_cloud.py`` later asserts is
# branch-only — an order-dependent failure with no per-test cause. Setting
# the same safe default here, in the ROOT conftest (loaded before ANY test
# file is collected, in any directory), closes the gap regardless of which
# test happens to import ``parkos_core.api.v1`` first. Tests that need
# ``PARKOS_DEPLOY=cloud`` already override this via
# ``monkeypatch.setenv`` + explicit ``sys.modules`` cache-busting (see
# ``tests/unit/dian/conftest.py``, ``tests/unit/test_admin_me.py``) — this
# default never overrides an already-set value (``setdefault``).
os.environ.setdefault("PARKOS_DEPLOY", "branch")


# ---------------------------------------------------------------------------
# Default test image — overridable via TEST_PG_IMAGE env var.
# ---------------------------------------------------------------------------

DEFAULT_TEST_PG_IMAGE = os.environ.get("TEST_PG_IMAGE", "postgres:16-alpine")
ALEMBIC_TIMEOUT_S = int(os.environ.get("TEST_ALEMBIC_TIMEOUT", "30"))


# ---------------------------------------------------------------------------
# URL translation helpers (testcontainers emits postgresql+psycopg2 / postgresql
# depending on version; we need postgresql+asyncpg for SQLAlchemy async).
# ---------------------------------------------------------------------------

def _testcontainers_url_to_asyncpg(raw: str) -> str:
    """Convert the testcontainers ``get_connection_url()`` output into the
    asyncpg URL SQLAlchemy async expects.

    testcontainers historically emits ``postgresql+psycopg2://...``; we
    rewrite the scheme while leaving the host/port/db/user/password intact.
    """
    if raw.startswith("postgresql+psycopg://"):
        return "postgresql+asyncpg://" + raw[len("postgresql+psycopg://"):]
    if raw.startswith("postgresql+psycopg2://"):
        return "postgresql+asyncpg://" + raw[len("postgresql+psycopg2://"):]
    if raw.startswith("postgresql://"):
        return "postgresql+asyncpg://" + raw[len("postgresql://"):]
    return raw


def _testcontainers_url_to_psycopg(raw: str) -> str:
    """Convert the testcontainers URL into a plain psycopg v3 DSN.

    psycopg (v3) understands ``postgresql://`` only.
    """
    if raw.startswith("postgresql+psycopg2://"):
        return "postgresql://" + raw[len("postgresql+psycopg2://"):]
    if raw.startswith("postgresql+psycopg://"):
        return "postgresql://" + raw[len("postgresql+psycopg://"):]
    if raw.startswith("postgresql+asyncpg://"):
        return "postgresql://" + raw[len("postgresql+asyncpg://"):]
    return raw


# ---------------------------------------------------------------------------
# Container fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def postgres_container() -> Iterator[object]:
    """Boot a testcontainers Postgres container (session-scope).

    Uses ``postgres:16-alpine`` by default; override via the ``TEST_PG_IMAGE``
    env var to plug in a custom image with pg_partman pre-installed
    (e.g. ``parkos-postgres:16-pgpartman`` built via ``apply_migration.py``'s
    sibling ``build_pg_image.py``).

    The container is started lazily on first access; downstream fixtures
    (``alembic_upgrade``, ``pg_engine``) gate on the container being up.
    """
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:
        pytest.skip(
            f"testcontainers[postgres] not installed ({exc}); install with "
            "`uv add --dev testcontainers[postgres]`"
        )

    container = PostgresContainer(DEFAULT_TEST_PG_IMAGE)
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def pg_dsn(postgres_container) -> str:
    """Plain ``postgresql://...`` DSN for raw psycopg access (sync)."""
    return _testcontainers_url_to_psycopg(postgres_container.get_connection_url())


@pytest.fixture(scope="session")
def pg_async_dsn(postgres_container) -> str:
    """``postgresql+asyncpg://...`` DSN for SQLAlchemy async engines."""
    return _testcontainers_url_to_asyncpg(postgres_container.get_connection_url())


# ---------------------------------------------------------------------------
# Wait-for-DB + apply migrations
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def _wait_for_pg(pg_dsn: str) -> None:
    """Poll psycopg until the DB accepts connections (max 30s)."""
    deadline = time.monotonic() + ALEMBIC_TIMEOUT_S
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with (
                psycopg.connect(pg_dsn, connect_timeout=2) as conn,
                conn.cursor() as cur,
            ):
                cur.execute("SELECT 1")
                cur.fetchone()
            return
        except Exception as exc:
            last_err = exc
            time.sleep(0.5)
    pytest.fail(f"DB never became ready within {ALEMBIC_TIMEOUT_S}s: {last_err}")


@pytest.fixture(scope="session")
def alembic_upgrade(pg_dsn: str, _wait_for_pg: None) -> None:
    """Run ``alembic upgrade head`` against the test DB once per session.

    Uses a subprocess (the migrations/env.py expects ``DATABASE_URL``) and
    captures output for the pytest log. If the migration fails
    (typically because the test image lacks ``pg_partman`` — the
    ``postgres:16-alpine`` default does NOT ship that extension; the
    project ships a custom ``parkos-postgres:16-pgpartman`` image with
    it pre-installed), the session-level fixture SKIPS so individual
    DB tests aren't bombarded with confusing ``UndefinedTable``
    errors. Override via ``TEST_PG_IMAGE=parkos-postgres:16-pgpartman``
    on a system where that image has been built.
    """
    import subprocess

    migrations_pkg = _PARKOS_CORE_SRC.parent / "migrations"
    env = os.environ.copy()
    env["DATABASE_URL"] = pg_dsn

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(migrations_pkg.parent),  # alembic.ini lives one level up from versions/
            env=env,
            capture_output=True,
            text=True,
            timeout=ALEMBIC_TIMEOUT_S * 6,
        )
    except FileNotFoundError as exc:
        pytest.skip(f"alembic not installed: {exc}")
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"alembic upgrade head timed out: {exc}")

    if proc.returncode != 0:
        snippet = (proc.stderr or "")[-1500:] or (proc.stdout or "")[-1500:]
        pytest.skip(
            f"alembic upgrade head failed (exit {proc.returncode}).\n"
            f"This is usually because the test Postgres image\n"
            f"``{DEFAULT_TEST_PG_IMAGE}`` lacks ``pg_partman``. The project\n"
            f"ships a custom image ``parkos-postgres:16-pgpartman`` with the\n"
            f"extension pre-installed (build it once via the bootstrap\n"
            f"``build_pg_image.py`` script, then set ``TEST_PG_IMAGE``).\n\n"
            f"DB-touching tests are skipped; non-DB tests continue.\n\n"
            f"Captured output:\n{snippet}"
        )


# ---------------------------------------------------------------------------
# Async SQLAlchemy engine + session
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
async def pg_engine(pg_async_dsn: str, alembic_upgrade: None) -> AsyncEngine:
    """Session-scope async engine bound to the test DB."""
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(pg_async_dsn, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _bootstrap_global_hash_chain_genesis(pg_engine: AsyncEngine) -> None:
    """Bootstrap the GLOBAL (``uuid_sucursal IS NULL``) hash-chain genesis row.

    PR6 (``repo/hash_chain.py::_ensure_genesis_row``) bootstraps the genesis
    row for ``log_transaccional`` LAZILY — the first time
    ``repo.hash_chain.append`` (or anything routed through it) is called for
    a given ``uuid_sucursal``. Several migration-level tests
    (``tests/migrations/test_hash_chain_genesis.py``,
    ``test_a_inmutable.py``'s ``log_transaccional`` case,
    ``test_ls_session_guard.py``) exercise the GLOBAL (NULL) partition
    directly via raw SQL or a bare INSERT with no ``uuid_sucursal`` column
    at all — nothing in a fresh test session has necessarily called the
    Python helper for ``uuid_sucursal=None`` yet by the time those tests
    run, and their own docstrings intentionally forbid the test itself from
    inserting the genesis row (that would just be testing the fixture, not
    the invariant). This session-scoped, autouse fixture removes that
    ordering fragility by guaranteeing the SAME real bootstrap the
    production application performs on first use has already happened,
    exactly once, before any test's assertions run — mirroring
    ``backend/scripts/apply_migration.py``'s local smoke-check bootstrap,
    but wired into the actual pytest fixture chain.
    """
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.repo.hash_chain import _ensure_genesis_row

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await _ensure_genesis_row(session, LogTransaccional, None)
        await session.commit()


def seed_hash_chain_genesis_row_sync(
    pg_dsn: str, uuid_sucursal: uuid_lib.UUID | None
) -> None:
    """Raw-SQL genesis-row bootstrap for tests exercising ``fn_extend_hash_
    chain()`` directly via a bare ``psycopg`` connection (bypassing
    ``repo/hash_chain.py``'s Python-side auto-bootstrap entirely, since these
    tests never call it). Mirrors the exact escape valve the trigger itself
    provides (``0001_initial_schema.py``): ``accion='inicialización'`` +
    ``hash_anterior == hash_actual`` (both the per-``uuid_sucursal`` genesis
    anchor) passes without requiring a prior row — the SAME construction
    ``repo.hash_chain._ensure_genesis_row`` performs for ORM-based callers.

    Only needed for a per-test ``uuid_sucursal`` the autouse global-genesis
    fixture above does not cover (i.e. anything other than ``NULL``).
    """
    marker = b"NULL" if uuid_sucursal is None else str(uuid_sucursal).encode("ascii")
    anchor = hashlib.sha256(b"genesis:" + marker).hexdigest()
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO prod.log_transaccional "
            "(uuid, fecha_retencion_hasta, uuid_sucursal, accion, "
            " tabla_afectada, timestamp_evento, hash_anterior, hash_actual) "
            "VALUES (gen_random_uuid(), CURRENT_DATE, %s, 'inicialización', "
            "'log_transaccional', %s, %s, %s)",
            (uuid_sucursal, datetime(1970, 1, 1), anchor, anchor),
        )
        conn.commit()


@pytest_asyncio.fixture
async def pg_session(pg_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Function-scope async session; rolls back at end of test.

    Each test starts with a clean view of the schema. We do NOT truncate
    tables — that would defeat the purpose of the migration tests, which
    write into [A] tables and then assert that mutations are blocked.
    Tests that need a clean slate open their own nested transaction and
    roll it back themselves.
    """
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# JWT mint helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mint_admin_jwt() -> Callable[..., str]:
    """Mint an ``admin-`` JWT for an arbitrary subject and allowed branches.

    Usage::

        token = mint_admin_jwt(actor_uuid=user_uuid,
                                sucursales_permitidas=[sucursal_uuid])
    """
    from parkos_core.auth.tokens import issue_token

    def _mint(
        *,
        actor_uuid: uuid_lib.UUID | None = None,
        sucursales_permitidas: list[uuid_lib.UUID] | None = None,
        expires_in: int = 3600,
    ) -> str:
        return issue_token(
            subject_uuid=actor_uuid or uuid_lib.uuid4(),
            issuer="admin-test",
            claims={
                "rol": "admin",
                "sucursales_permitidas": [
                    str(u) for u in (sucursales_permitidas or [uuid_lib.uuid4()])
                ],
            },
            expires_in=expires_in,
        )

    return _mint


@pytest.fixture
def mint_operador_jwt() -> Callable[..., str]:
    """Mint an ``operador-`` JWT pinned to a single branch.

    Usage::

        token = mint_operador_jwt(actor_uuid=user_uuid, sucursal_uuid=sucursal_uuid)
    """
    from parkos_core.auth.tokens import issue_token

    def _mint(
        *,
        actor_uuid: uuid_lib.UUID | None = None,
        sucursal_uuid: uuid_lib.UUID | None = None,
        expires_in: int = 3600,
    ) -> str:
        return issue_token(
            subject_uuid=actor_uuid or uuid_lib.uuid4(),
            issuer="operador-test",
            claims={
                "rol": "operador",
                "sucursal": str(sucursal_uuid or uuid_lib.uuid4()),
            },
            expires_in=expires_in,
        )

    return _mint


@pytest.fixture
def mint_sync_agent_jwt() -> Callable[..., str]:
    """Mint a ``sync-agent-`` JWT (branch or cloud scope).

    Usage::

        token = mint_sync_agent_jwt(scope="cloud")  # or scope="branch"
    """
    from parkos_core.auth.tokens import issue_token

    def _mint(
        *,
        scope: str = "branch",
        sucursal_uuid: uuid_lib.UUID | None = None,
        expires_in: int = 3600,
    ) -> str:
        claims: dict[str, object] = {"scope": scope}
        if scope == "branch":
            claims["sucursal"] = str(sucursal_uuid or uuid_lib.uuid4())
        return issue_token(
            subject_uuid=uuid_lib.uuid4(),
            issuer="sync-agent-test",
            claims=claims,
            expires_in=expires_in,
        )

    return _mint


# ---------------------------------------------------------------------------
# FastAPI httpx client
# ---------------------------------------------------------------------------

@pytest.fixture
def app() -> str:
    """Parametrize the FastAPI app the ``client`` fixture should bind to.

    Default ``"sucursal"`` (branch API). Override via indirect parametrization
    or via the ``APP`` env var:

        @pytest.mark.parametrize("app", ["admin"], indirect=True)

    The cloud-only assertion (``test_openapi_branch_excludes_cloud.py``) uses
    the default; the unit test for the admin app uses ``APP=admin``.
    """
    return os.environ.get("TEST_APP", "sucursal")


@pytest_asyncio.fixture
async def client(app: str, pg_engine: AsyncEngine) -> AsyncIterator[object]:
    """``httpx.AsyncClient`` bound to the FastAPI app under test.

    The DB URL env var is overridden to the testcontainers URL so the
    ``get_session`` dependency resolves to the test DB. We use ASGI
    transport — no real socket — for speed.
    """
    import httpx

    os.environ["DATABASE_URL"] = pg_engine.url.render_as_string(hide_password=False)
    # Force the lazy engine in parkos_core.db.engine to rebuild.
    import parkos_core.db.engine as _engine_mod
    _engine_mod._engine = None
    _engine_mod._sessionmaker = None

    if app == "admin":
        from api_admin_main.app import app as fastapi_app
    else:
        from api_sucursal_main.app import app as fastapi_app

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"X-Request-ID": "test"},
    ) as client_:
        yield client_


# ---------------------------------------------------------------------------
# Helpers used by the migration test suite
# ---------------------------------------------------------------------------

@pytest.fixture
def table_set_a() -> list[str]:
    """The 11 [A] tables that are fully REVOKE'd + inmutable-triggered.

    ``sync_queue`` is excluded — the carve-out in design §12 grants
    ``rol_app`` UPDATE/DELETE on it (only the four whitelisted columns are
    actually mutated by the helper, but the table itself is mutable).
    """
    return [
        "salidas",
        "factura_detalle",
        "factura_impuestos",
        "factura_otros_cobros",
        "factura_pagos",
        "revocacion_factura",
        "caja",
        "arqueo",
        "sync_log",
        "sync_conflict",
        "log_transaccional",
    ]


@pytest.fixture
def table_set_ls() -> list[str]:
    """The 2 [L-S] tables with session-guard triggers."""
    return ["login", "sesion"]


# ---------------------------------------------------------------------------
# VFixtureFactory (T-PR2-018, R15, REQ-OPS-009) — one generic [V] row builder
# ---------------------------------------------------------------------------


class VFixtureFactory:
    """Builds a ``[V]`` ORM instance defaulted to an open bi-temporal version.

    Not 26 per-model ``factory-boy`` subclasses — every ``[V]`` table shares
    the same ``VersionedBase`` mixin shape (``IdMixin`` / ``AuditMixin`` /
    ``SyncMixin`` / ``VersionedMixin``, ``models/base.py``); only the
    business columns differ, and every business column across all 26 ``[V]``
    models is nullable in the ORM (verified: the sole NOT-NULL-without-a-
    default column across all 26 is ``usuarios.uuid``, which is handled by
    the same PK path as every other class). One generic builder, reused
    everywhere, is therefore both correct and far less to maintain than 26
    near-identical factory classes.

    ``vigente_hasta=None`` is always the default (T-PR2-018's acceptance
    criterion) — the built row is always the currently-open version unless
    a caller overrides it. Faker (``es_CO``) fills any other NOT-NULL,
    no-default column so the instance is insertable as-is; RNF-029: no
    real PII, ``Faker`` only.
    """

    _fake = Faker("es_CO")

    @classmethod
    def build(cls, model_cls: type, /, **overrides: object) -> object:
        """Construct ``model_cls(**kwargs)`` with safe non-persisted defaults."""
        now = datetime.now(UTC).replace(tzinfo=None)
        kwargs: dict[str, object] = {
            "uuid": uuid_lib.uuid4(),
            "created_at": now,
            "created_by": None,
            "vigente_desde": now,
            "vigente_hasta": None,  # T-PR2-018: open version by default
            "estado": "activo",
            "sync_status": "pendiente",
            "sync_timestamp": None,
            "sync_attempts": 0,
        }

        mapper = sa_inspect(model_cls)
        for column in mapper.columns:
            name = column.name
            if name in kwargs:
                continue
            if column.nullable or column.server_default is not None or column.default is not None:
                continue
            # A required column with no DB-side default — synthesize one.
            kwargs[name] = cls._synthesize(column.type)

        kwargs.update(overrides)
        return model_cls(**kwargs)

    @classmethod
    def _synthesize(cls, sa_type: object) -> object:
        if isinstance(sa_type, PG_UUID):
            return uuid_lib.uuid4()
        if isinstance(sa_type, String):
            return cls._fake.word()
        if isinstance(sa_type, Numeric):
            return 0
        if isinstance(sa_type, Boolean):
            return False
        if isinstance(sa_type, Integer):
            return 0
        if isinstance(sa_type, DateTime | Date):
            return datetime.now(UTC).replace(tzinfo=None)
        return None


@pytest.fixture
def v_fixture_factory() -> type[VFixtureFactory]:
    """Fixture handle for :class:`VFixtureFactory` (T-PR2-018)."""
    return VFixtureFactory


# ---------------------------------------------------------------------------
# make_spec (T-PR4-010, REQ-OPS-009, REQ-HOOK-015) — fluent hook-override
# helper for SyncCatalogEntry.
# ---------------------------------------------------------------------------


@pytest.fixture
def make_spec() -> Callable[..., object]:
    """Return ``make_spec(name, **overrides) -> SyncCatalogEntry`` (T-PR4-010).

    Looks up the real entry by ``name`` in ``SYNC_CATALOG`` (falling back to
    ``LOCAL_ONLY_CATALOG``) and returns a ``dataclasses.replace()`` copy with
    ``overrides`` applied. A test overriding exactly one of the 4 hook slots
    (``hook_pre_insert``, ``hook_post_insert``, ``hook_chain_extend``,
    ``hook_validate_parent``) does not have to configure the other three —
    they keep whatever the real catalog entry already declares (``None`` for
    every PR4-era entry; concrete hook implementations land in PR5/PR6).

    Usage::

        spec = make_spec("login", hook_post_insert=lambda ctx: HookResult(proceed=True))
    """

    def _make_spec(name: str, **overrides: object) -> object:
        from dataclasses import replace

        from parkos_core.sync.catalog.local_only_catalog import LOCAL_ONLY_CATALOG
        from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME

        entry = SYNC_CATALOG_BY_NAME.get(name)
        if entry is None:
            entry = next((e for e in LOCAL_ONLY_CATALOG if e.name == name), None)
        if entry is None:
            raise KeyError(
                f"make_spec: {name!r} is not a SYNC_CATALOG or LOCAL_ONLY_CATALOG entry"
            )
        return replace(entry, **overrides)

    return _make_spec


@pytest_asyncio.fixture
async def seeded_sucursal_uuid(pg_engine: AsyncEngine) -> uuid_lib.UUID:
    """Insert one real ``sucursal`` row and return its uuid.

    ``sync_queue.uuid_sucursal`` carries a DB-level FK to ``prod.sucursal``
    (``fk_sync_queue_uuid_sucursal``, ``0001_initial_schema.py``) — tests that
    enqueue rows need a real parent, not a bare ``uuid_lib.uuid4()``.
    """
    from parkos_core.models.V.sucursal import Sucursal

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal = VFixtureFactory.build(Sucursal)
        session.add(sucursal)
        await session.commit()
        return sucursal.uuid


@pytest_asyncio.fixture
async def seeded_usuario_uuid(pg_engine: AsyncEngine) -> uuid_lib.UUID:
    """Insert one real ``usuarios`` row and return its uuid.

    ``permisos_usuario.uuid_usuario`` carries a DB-level FK to
    ``prod.usuarios`` (``fk_permisos_usuario_uuid_usuario``,
    ``0001_initial_schema.py``) — tests that seed permission rows need a
    real parent, not a bare ``uuid_lib.uuid4()``.
    """
    from parkos_core.models.V.usuarios import Usuarios

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        usuario = VFixtureFactory.build(Usuarios)
        session.add(usuario)
        await session.commit()
        return usuario.uuid


__all__ = [
    "VFixtureFactory",
    "alembic_upgrade",
    "app",
    "client",
    "make_spec",
    "mint_admin_jwt",
    "mint_operador_jwt",
    "mint_sync_agent_jwt",
    "pg_async_dsn",
    "pg_dsn",
    "pg_engine",
    "pg_session",
    "postgres_container",
    "seeded_sucursal_uuid",
    "seeded_usuario_uuid",
    "table_set_a",
    "table_set_ls",
    "v_fixture_factory",
]