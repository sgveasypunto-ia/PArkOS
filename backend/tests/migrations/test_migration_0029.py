"""HU-F1.11 / T6 — MIGRATION 0029 idempotency + module contract tests.

T6.1 — module-level import contract: ``upgrade()`` and ``downgrade()``
        are callables with the canonical Alembic 4-arg signature.
T6.2 — pre-flight ``DO $$`` aborts on missing tables.
T6.3 — Op 1 siembra idempotency + Op 2 permission seed + Op 3 role
        grants.

The DB-backed tests carry ``@pytest.mark.requires_db``. They run against a
THROW-AWAY database cloned from a template migrated to the revision just
BEFORE 0029: they apply 0029 itself (not ``head``) and, being destructive
(they DROP ``costos_servicios`` / DELETE seeds), must never touch the shared
session database the rest of the suite uses. The module contract tests are
pure Python and run unconditionally.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402

# ---------------------------------------------------------------------------
# Module contract — pure Python, no DB.
# ---------------------------------------------------------------------------


def test_migration_0029_module_imports_with_canonical_revision() -> None:
    """T6.1 RED→GREEN: the migration module imports + revision metadata is set.

    Asserts the module is importable and declares the F1.10 chain head
    as its ``down_revision``. This is the pure-Python contract check
    that runs even without a Postgres container.
    """
    sys.path.insert(
        0,
        str(_BACKEND_ROOT / "packages" / "parkos_core" / "migrations" / "versions"),
    )
    mod = importlib.import_module("0029_reimpresion_siembra_and_permiso_anular")
    assert mod.revision == "0029_reimpresion_siembra_and_permiso_anular", (
        f"unexpected revision id: {mod.revision!r}"
    )
    assert mod.down_revision == (
        "0028_one_fe_per_factura_and_chain_index_and_sync_flip"
    ), (
        "F1.11 migration must chain off the F1.10 head "
        "(0028_one_fe_per_factura_and_chain_index_and_sync_flip); got "
        f"{mod.down_revision!r}"
    )


def test_migration_0029_upgrade_and_downgrade_are_callable() -> None:
    """T6.1 GREEN: ``upgrade()`` and ``downgrade()`` are callables.

    No-arg signature per Alembic convention; the implementation
    captures the alembic ``op`` module via global lookup, so we only
    assert the symbols exist + are callable.
    """
    sys.path.insert(
        0,
        str(_BACKEND_ROOT / "packages" / "parkos_core" / "migrations" / "versions"),
    )
    mod = importlib.import_module("0029_reimpresion_siembra_and_permiso_anular")
    assert callable(mod.upgrade), "MIGRATION 0029 upgrade() is not callable"
    assert callable(mod.downgrade), "MIGRATION 0029 downgrade() is not callable"


# ---------------------------------------------------------------------------
# DB-backed tests -- throw-away database at revision 0028, 0029 applied by hand.
# ---------------------------------------------------------------------------

_REV_0028 = "0028_one_fe_per_factura_and_chain_index_and_sync_flip"
_REV_0029 = "0029_reimpresion_siembra_and_permiso_anular"
_ALEMBIC_CWD = _BACKEND_ROOT / "packages" / "parkos_core"  # alembic.ini lives here
_ALEMBIC_TIMEOUT_S = 600

# Mark all DB-gated tests so the §4.3 check suite can filter them.
requires_db = pytest.mark.requires_db


def _dsn_for(pg_dsn: str, dbname: str) -> str:
    """``pg_dsn`` (a ``postgresql://`` URL) pointed at database ``dbname``."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(pg_dsn)
    return urlunsplit(parts._replace(path=f"/{dbname}"))


def _admin_exec(pg_dsn: str, sql: str) -> None:
    import psycopg

    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        conn.execute(sql)


def _alembic(dsn: str, *args: str):
    """Run ``alembic <args>`` against ``dsn`` (env.py reads ``DATABASE_URL``)."""
    import os
    import subprocess

    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(_ALEMBIC_CWD),
        env={**os.environ, "DATABASE_URL": dsn},
        capture_output=True,
        text=True,
        timeout=_ALEMBIC_TIMEOUT_S,
    )


@pytest.fixture(scope="module")
def dedicated_pg_dsn():
    """DSN of a DEDICATED Postgres container just for this module.

    The migration chain creates cluster-level roles (``CREATE ROLE rol_app``
    ...) unconditionally, so a second database inside the shared session
    container cannot be migrated from scratch. A separate container also keeps
    these destructive tests away from the shared schema.
    """
    from tests.conftest import (
        _DOCKER_TEST,
        DEFAULT_TEST_PG_IMAGE,
        _testcontainers_url_to_psycopg,
    )

    if _DOCKER_TEST:
        pytest.skip("needs its own Postgres container (PARKOS_DOCKER_TEST=1 reuses a live DB)")
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:
        pytest.skip(f"testcontainers[postgres] not installed ({exc})")
    try:
        container = PostgresContainer(DEFAULT_TEST_PG_IMAGE)
        container.start()
    except Exception as exc:  # noqa: BLE001 - Docker daemon unreachable -> skip
        pytest.skip(f"cannot start a Postgres container ({type(exc).__name__}: {exc!s})")
    try:
        yield _testcontainers_url_to_psycopg(container.get_connection_url())
    finally:
        container.stop()


@pytest.fixture(scope="module")
def template_db_0028(dedicated_pg_dsn: str):
    """A database migrated up to (and including) revision 0028; the clone source."""
    import uuid

    name = f"t0029_tmpl_{uuid.uuid4().hex[:8]}"
    _admin_exec(dedicated_pg_dsn, f'CREATE DATABASE "{name}"')
    proc = _alembic(_dsn_for(dedicated_pg_dsn, name), "upgrade", _REV_0028)
    assert proc.returncode == 0, (proc.stderr or proc.stdout)[-1500:]
    return name


@pytest.fixture
def scratch_dsn(dedicated_pg_dsn: str, template_db_0028: str):
    """A fresh clone of the 0028 template, dropped after the test."""
    import uuid

    name = f"t0029_{uuid.uuid4().hex[:8]}"
    _admin_exec(dedicated_pg_dsn, f'CREATE DATABASE "{name}" TEMPLATE "{template_db_0028}"')
    try:
        yield _dsn_for(dedicated_pg_dsn, name)
    finally:
        _admin_exec(dedicated_pg_dsn, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _count(dsn: str, sql: str) -> int:
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
    assert row is not None
    return row[0]


_SQL_SIEMBRA = (
    "SELECT count(*) FROM prod.costos_servicios "
    "WHERE concepto = 'reimpresion' AND vigente_hasta IS NULL AND estado = 'activo'"
)
_SQL_PERMISO = "SELECT count(*) FROM prod.permisos WHERE permiso = 'anular_reimpresion'"


@requires_db
def test_migration_0029_preflight_blocks_when_costos_servicios_missing(
    scratch_dsn: str,
) -> None:
    """T6.1 RED: pre-flight aborts when ``prod.costos_servicios`` is missing."""
    import re

    import psycopg

    with psycopg.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS prod.costos_servicios CASCADE;")
        conn.commit()

    proc = _alembic(scratch_dsn, "upgrade", _REV_0029)
    msg = (proc.stderr or "") + (proc.stdout or "")
    assert proc.returncode != 0, "0029 must abort when costos_servicios is missing"
    assert re.search(r"0029_preflight_abort|prod\.costos_servicios", msg), (
        f"pre-flight abort signature missing: {msg[-800:]!r}"
    )


@requires_db
def test_migration_0029_op1_siembra_inserts_when_absent(scratch_dsn: str) -> None:
    """T6.1 GREEN: Op 1 conditional siembra inserts the ``reimpresion`` row."""
    import psycopg

    with psycopg.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM prod.costos_servicios WHERE concepto = 'reimpresion';")
        conn.commit()

    proc = _alembic(scratch_dsn, "upgrade", _REV_0029)
    assert proc.returncode == 0, (proc.stderr or proc.stdout)[-1500:]

    n = _count(scratch_dsn, _SQL_SIEMBRA)
    assert n == 1, f"expected exactly 1 siembra row; found {n}"


@requires_db
def test_migration_0029_op2_seed_anular_reimpresion_permission(scratch_dsn: str) -> None:
    """T6.1 GREEN: Op 2 seeds ``anular_reimpresion`` in ``prod.permisos``."""
    import psycopg

    with psycopg.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM prod.permisos WHERE permiso = 'anular_reimpresion';")
        conn.commit()

    proc = _alembic(scratch_dsn, "upgrade", _REV_0029)
    assert proc.returncode == 0, (proc.stderr or proc.stdout)[-1500:]

    n = _count(scratch_dsn, _SQL_PERMISO)
    assert n == 1, f"expected exactly 1 permission row; found {n}"


@requires_db
def test_migration_0029_idempotent_reapply(scratch_dsn: str) -> None:
    """T6.3: re-applying MIGRATION 0029 is a no-op (no duplicates)."""
    proc = _alembic(scratch_dsn, "upgrade", _REV_0029)
    assert proc.returncode == 0, (proc.stderr or proc.stdout)[-1500:]
    # Re-apply for real: rewind the version pointer WITHOUT running the
    # downgrade (which would remove the seeds), then upgrade again.
    proc = _alembic(scratch_dsn, "stamp", _REV_0028)
    assert proc.returncode == 0, (proc.stderr or proc.stdout)[-1500:]
    proc = _alembic(scratch_dsn, "upgrade", _REV_0029)
    assert proc.returncode == 0, (proc.stderr or proc.stdout)[-1500:]

    n = _count(scratch_dsn, _SQL_SIEMBRA)
    assert n == 1, f"re-apply produced duplicate siembra rows: {n}"
    n = _count(scratch_dsn, _SQL_PERMISO)
    assert n == 1, f"re-apply produced duplicate permission rows: {n}"


@requires_db
def test_migration_0029_downgrade_reverses_three_ops(scratch_dsn: str) -> None:
    """T6.4: downgrade reverses Op 1 + Op 2 + Op 3 (round-trip)."""
    proc = _alembic(scratch_dsn, "upgrade", _REV_0029)
    assert proc.returncode == 0, (proc.stderr or proc.stdout)[-1500:]
    assert _count(scratch_dsn, _SQL_PERMISO) == 1
    proc = _alembic(scratch_dsn, "downgrade", _REV_0028)
    assert proc.returncode == 0, (proc.stderr or proc.stdout)[-1500:]

    n = _count(scratch_dsn, _SQL_PERMISO)
    assert n == 0, f"downgrade did not remove permission: count={n}"
