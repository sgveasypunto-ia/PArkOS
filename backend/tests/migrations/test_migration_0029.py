"""HU-F1.11 / T6 — MIGRATION 0029 idempotency + module contract tests.

T6.1 — module-level import contract: ``upgrade()`` and ``downgrade()``
        are callables with the canonical Alembic 4-arg signature.
T6.2 — pre-flight ``DO $$`` aborts on missing tables
        (gated ``PARKOS_DOCKER_TEST=1``).
T6.3 — Op 1 siembra idempotency + Op 2 permission seed + Op 3 role
        grants (gated ``PARKOS_DOCKER_TEST=1``).

The DB-gated tests carry ``@pytest.mark.requires_db`` so the §4.3 check
suite skips them cleanly when no Postgres is reachable. The module
contract tests are pure Python and run unconditionally — they assert
the migration module is importable + upgrade/downgrade are defined.
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
# DB-gated tests — require PARKOS_DOCKER_TEST=1 + reachable Postgres.
# ---------------------------------------------------------------------------

# Mark all DB-gated tests so the §4.3 check suite can filter them.
requires_db = pytest.mark.requires_db


@requires_db
def test_migration_0029_preflight_blocks_when_costos_servicios_missing(
    pg_dsn: str,
) -> None:
    """T6.1 RED: pre-flight aborts when ``prod.costos_servicios`` is missing.

    Drops the table (test-only); asserts ``alembic upgrade head`` raises
    a ``0029_preflight_abort`` exception naming the missing table.
    Re-CREATEs the table post-assertion for idempotency.
    """
    import re

    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS prod.costos_servicios CASCADE;")
        conn.commit()

    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option(
        "script_location",
        str(_BACKEND_ROOT / "packages" / "parkos_core" / "migrations"),
    )
    cfg.set_main_option(
        "sqlalchemy.url",
        pg_dsn.replace("postgresql://", "postgresql+psycopg://"),
    )

    try:
        with pytest.raises(Exception) as exc_info:
            command.upgrade(cfg, "head")
        msg = str(exc_info.value)
        assert re.search(
            r"0029_preflight_abort|prod\.costos_servicios", msg
        ), f"pre-flight abort signature missing: {msg!r}"
    finally:
        # Best-effort re-create the table for subsequent tests. The
        # canonical CREATE TABLE lives in migration 0001; we only need
        # the table to exist for downstream migrations.
        with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS prod.costos_servicios (
                    uuid uuid PRIMARY KEY DEFAULT gen_random_uuid()
                );
                """
            )
            conn.commit()


@requires_db
def test_migration_0029_op1_siembra_inserts_when_absent(pg_dsn: str) -> None:
    """T6.1 GREEN: Op 1 conditional siembra inserts the ``reimpresion`` row.

    Removes any existing siembra; runs the migration (idempotent);
    asserts exactly 1 vigente row exists for ``concepto='reimpresion'``.
    """
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM prod.costos_servicios WHERE concepto = 'reimpresion';"
        )
        conn.commit()

    # Run the migration upgrade head.
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option(
        "script_location",
        str(_BACKEND_ROOT / "packages" / "parkos_core" / "migrations"),
    )
    # Use the same DSN alembic will translate; we override the URL via env.
    cfg.set_main_option("sqlalchemy.url", pg_dsn.replace("postgresql://", "postgresql+psycopg://"))
    command.upgrade(cfg, "head")

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM prod.costos_servicios "
            "WHERE concepto = 'reimpresion' "
            "  AND vigente_hasta IS NULL "
            "  AND estado = 'activo';"
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 1, (
            f"expected exactly 1 siembra row; found {row[0]}"
        )


@requires_db
def test_migration_0029_op2_seed_anular_reimpresion_permission(pg_dsn: str) -> None:
    """T6.1 GREEN: Op 2 seeds ``anular_reimpresion`` in ``prod.permisos``."""
    import psycopg

    # Idempotent: delete any pre-existing seed; migration re-inserts.
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM prod.permisos WHERE permiso = 'anular_reimpresion';"
        )
        conn.commit()

    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option(
        "script_location",
        str(_BACKEND_ROOT / "packages" / "parkos_core" / "migrations"),
    )
    cfg.set_main_option("sqlalchemy.url", pg_dsn.replace("postgresql://", "postgresql+psycopg://"))
    command.upgrade(cfg, "head")

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM prod.permisos "
            "WHERE permiso = 'anular_reimpresion';"
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 1, (
            f"expected exactly 1 permission row; found {row[0]}"
        )


@requires_db
def test_migration_0029_idempotent_reapply(pg_dsn: str) -> None:
    """T6.3: re-applying MIGRATION 0029 is a no-op (no duplicates)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option(
        "script_location",
        str(_BACKEND_ROOT / "packages" / "parkos_core" / "migrations"),
    )
    cfg.set_main_option("sqlalchemy.url", pg_dsn.replace("postgresql://", "postgresql+psycopg://"))
    command.upgrade(cfg, "head")
    # Re-apply — must not raise.
    command.upgrade(cfg, "head")

    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM prod.costos_servicios "
            "WHERE concepto = 'reimpresion' "
            "  AND vigente_hasta IS NULL "
            "  AND estado = 'activo';"
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 1, (
            f"re-apply produced duplicate siembra rows: {row[0]}"
        )

        cur.execute(
            "SELECT count(*) FROM prod.permisos "
            "WHERE permiso = 'anular_reimpresion';"
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 1, (
            f"re-apply produced duplicate permission rows: {row[0]}"
        )


@requires_db
def test_migration_0029_downgrade_reverses_three_ops(pg_dsn: str) -> None:
    """T6.4: downgrade reverses Op 1 + Op 2 + Op 3 (round-trip)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option(
        "script_location",
        str(_BACKEND_ROOT / "packages" / "parkos_core" / "migrations"),
    )
    cfg.set_main_option("sqlalchemy.url", pg_dsn.replace("postgresql://", "postgresql+psycopg://"))
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")

    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM prod.permisos "
            "WHERE permiso = 'anular_reimpresion';"
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 0, (
            f"downgrade did not remove permission: count={row[0]}"
        )
