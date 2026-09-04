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

import os
import sys
import time
import uuid as uuid_lib
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

if sys.platform == "win32":
    # ``psycopg`` (v3) cannot use the Windows ``ProactorEventLoop`` for async
    # operations. Switch to the selector-loop policy BEFORE any asyncio
    # import happens in third-party libs. Available on Windows since
    # Python 3.8 via selectors.SelectSelector — guarded by hasattr for
    # forward compat.
    import asyncio
    import selectors

    try:
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()  # type: ignore[attr-defined]
        )
    except (AttributeError, OSError):
        pass

import psycopg
import pytest
import pytest_asyncio
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


__all__ = [
    "alembic_upgrade",
    "app",
    "client",
    "mint_admin_jwt",
    "mint_operador_jwt",
    "mint_sync_agent_jwt",
    "pg_async_dsn",
    "pg_dsn",
    "pg_engine",
    "pg_session",
    "postgres_container",
    "table_set_a",
    "table_set_ls",
]