"""test_migration_0034_mv.py -- REQ-OPS-133 (Bug 3 of qa-2026-09-17).

QA-2026-09-17 bug-remediation: bug 3 surfaced the case where
``prod.mv_ocupacion_diaria`` is missing from branch containers that
successfully applied migration 0024 but lost the view to a partial-
commit / restore-from-backup failure. Migration 0034 (CREATE OR
REPLACE) heals the situation idempotently.

TDD RED-then-GREEN coverage for MIGRATION 0034:

  T1 -- module metadata: revision id + down_revision chain off 0024
       (canonical F1.5 head). Pre-implementation this raises
       ``ModuleNotFoundError`` -- that is the RED state.

  T2 -- upgrade() emits ``CREATE OR REPLACE MATERIALIZED VIEW`` against
       ``prod.mv_ocupacion_diaria`` plus a ``to_regclass`` post-upgrade
       assertion + UNIQUE INDEX ``IF NOT EXISTS`` + GRANT. Body is
       asserted via mock to keep the test Docker-free.

  T3 -- downgrade() emits ``DROP MATERIALIZED VIEW IF EXISTS`` against
       the canonical view name.

  T4 -- ``to_regclass('prod.mv_ocupacion_diaria')`` check in
       ``check_schema_match.py`` exits non-zero when the view is
       missing (the CI gate that prompted the fix).

Test pattern precedent: F1.15 ``test_migration_0033_index.py`` (mock-
based, no Docker required) + ``test_migration_0024_mv.py`` (Docker-
gated, separate file).

Skipped cleanly without ``PARKOS_DOCKER_TEST=1`` for any DB-layer
assertion; the source-level tests run on every pytest invocation.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

# Parkos-core versions directory on PYTHONPATH so the module can be imported.
sys.path.insert(
    0,
    str(_BACKEND_ROOT / "packages" / "parkos_core" / "migrations" / "versions"),
)


# ---------------------------------------------------------------------------
# T1 -- module metadata (REQ-OPS-133, Bug 3 of qa-2026-09-17)
# ---------------------------------------------------------------------------


def test_migration_0034_module_imports_with_canonical_revision() -> None:
    """T1 RED/GREEN: module imports + revision metadata chains off 0024.

    MIGRATION 0034 chains off the F1.5 head
    (``0024_mv_ocupacion_diaria``) and uses revision id
    ``0034_recreate_mv_ocupacion_diaria_idempotent``. Pre-implementation
    this raises ``ModuleNotFoundError`` -- that is the RED state.
    """
    mod = importlib.import_module("0034_recreate_mv_ocupacion_diaria_idempotent")
    assert mod.revision == "0034_recreate_mv_ocupacion_diaria_idempotent", (
        f"unexpected revision id: {mod.revision!r}"
    )
    assert mod.down_revision == "0024_mv_ocupacion_diaria", (
        "REQ-OPS-133 violated: MIGRATION 0034 must chain off 0024 head; "
        f"got {mod.down_revision!r}"
    )


def test_migration_0034_upgrade_and_downgrade_are_callable() -> None:
    """T1 GREEN: ``upgrade()`` + ``downgrade()`` are callables.

    Both functions exist and are sync callables (no asyncio machinery
    needed; ``op.execute`` is sync).
    """
    mod = importlib.import_module("0034_recreate_mv_ocupacion_diaria_idempotent")
    assert callable(mod.upgrade), "MIGRATION 0034 upgrade() is not callable"
    assert callable(mod.downgrade), "MIGRATION 0034 downgrade() is not callable"


# ---------------------------------------------------------------------------
# T2 -- upgrade() body: CREATE OR REPLACE + to_regclass + UNIQUE INDEX + GRANT
# ---------------------------------------------------------------------------


def test_migration_0034_uses_create_or_replace_materialized_view() -> None:
    """T2 GREEN: ``upgrade()`` emits ``CREATE OR REPLACE MATERIALIZED VIEW``.

    REQ-OPS-133 invariant: the DDL must be ``CREATE OR REPLACE`` so the
    same migration heals both the missing-MV state and the present-MV
    state (which would otherwise be a hard error with plain CREATE).
    """
    from unittest.mock import MagicMock, patch

    mod = importlib.import_module("0034_recreate_mv_ocupacion_diaria_idempotent")
    captured_sqls: list[str] = []
    mock_op = MagicMock()
    mock_op.execute = MagicMock(side_effect=lambda sql: captured_sqls.append(sql))

    with patch.object(mod, "op", mock_op):
        mod.upgrade()

    create_replace_sqls = [
        s for s in captured_sqls if "CREATE OR REPLACE MATERIALIZED VIEW" in s
    ]
    assert len(create_replace_sqls) == 1, (
        "REQ-OPS-133 violated: upgrade() must emit exactly one "
        "CREATE OR REPLACE MATERIALIZED VIEW; got "
        f"{len(create_replace_sqls)}"
    )
    sql = create_replace_sqls[0]
    assert "prod.mv_ocupacion_diaria" in sql, (
        f"upgrade() must target prod.mv_ocupacion_diaria; got {sql!r}"
    )
    # The SELECT body must be identical to 0024 (same contract):
    # uuid_sucursal, uuid_tipo_vehiculo, count(*) AS activos, GROUP BY
    # the two columns, with the active-ingreso predicate.
    assert "i.uuid_sucursal" in sql, f"upgrade() missing uuid_sucursal; got {sql!r}"
    assert "i.uuid_tipo_vehiculo" in sql, (
        f"upgrade() missing uuid_tipo_vehiculo; got {sql!r}"
    )
    assert "count(*) AS activos" in sql, (
        f"upgrade() missing count(*) AS activos; got {sql!r}"
    )
    assert "GROUP BY i.uuid_sucursal, i.uuid_tipo_vehiculo" in sql, (
        f"upgrade() missing canonical GROUP BY; got {sql!r}"
    )
    # Active-ingreso predicate parts.
    assert "NOT EXISTS" in sql, (
        f"upgrade() missing NOT EXISTS predicate (active-ingreso canon); got {sql!r}"
    )
    assert "prod.salidas" in sql, (
        f"upgrade() missing prod.salidas NOT EXISTS subquery; got {sql!r}"
    )
    assert "prod.anulaciones" in sql, (
        f"upgrade() missing prod.anulaciones NOT EXISTS subquery; got {sql!r}"
    )


def test_migration_0034_emits_to_regclass_post_check() -> None:
    """T2 GREEN: ``upgrade()`` emits a ``to_regclass`` post-upgrade check.

    REQ-OPS-133 + design D3: defensive layer against a future Postgres
    version dropping the ``CREATE OR REPLACE`` form for materialized
    views. The check fails the migration with a typed error if the
    view is somehow still missing.
    """
    from unittest.mock import MagicMock, patch

    mod = importlib.import_module("0034_recreate_mv_ocupacion_diaria_idempotent")
    captured_sqls: list[str] = []
    mock_op = MagicMock()
    mock_op.execute = MagicMock(side_effect=lambda sql: captured_sqls.append(sql))

    with patch.object(mod, "op", mock_op):
        mod.upgrade()

    to_regclass_sqls = [s for s in captured_sqls if "to_regclass" in s]
    assert len(to_regclass_sqls) >= 1, (
        "REQ-OPS-133 violated: upgrade() must emit a to_regclass post-upgrade "
        f"check; got {len(to_regclass_sqls)}"
    )
    sql = to_regclass_sqls[0]
    assert "prod.mv_ocupacion_diaria" in sql, (
        f"upgrade() to_regclass must reference prod.mv_ocupacion_diaria; got {sql!r}"
    )
    # The error message MUST be the canonical typed discriminator so CI
    # log scrapers can grep it.
    assert "mv_ocupacion_diaria_missing_post_create" in sql, (
        f"upgrade() to_regclass block must RAISE the typed discriminator "
        f"'mv_ocupacion_diaria_missing_post_create'; got {sql!r}"
    )


def test_migration_0034_reasserts_unique_index_and_grant() -> None:
    """T2 GREEN: ``upgrade()`` re-asserts UNIQUE INDEX ``IF NOT EXISTS`` + GRANT.

    Idempotent re-assertion: the UNIQUE INDEX is required for
    ``REFRESH MATERIALIZED VIEW CONCURRENTLY``; the GRANT is required
    for ``parkos_app`` to read the view. ``IF NOT EXISTS`` keeps both
    no-ops when present (the common case).
    """
    from unittest.mock import MagicMock, patch

    mod = importlib.import_module("0034_recreate_mv_ocupacion_diaria_idempotent")
    captured_sqls: list[str] = []
    mock_op = MagicMock()
    mock_op.execute = MagicMock(side_effect=lambda sql: captured_sqls.append(sql))

    with patch.object(mod, "op", mock_op):
        mod.upgrade()

    # UNIQUE INDEX + IF NOT EXISTS
    create_unique_idx_sqls = [
        s for s in captured_sqls
        if "CREATE UNIQUE INDEX" in s and "mv_ocupacion_diaria" in s
    ]
    assert len(create_unique_idx_sqls) == 1, (
        "REQ-OPS-133 violated: upgrade() must re-assert the UNIQUE INDEX; "
        f"got {len(create_unique_idx_sqls)}"
    )
    sql = create_unique_idx_sqls[0]
    assert "IF NOT EXISTS" in sql, (
        f"upgrade() UNIQUE INDEX must be idempotent (IF NOT EXISTS); got {sql!r}"
    )
    assert "uq_mv_ocupacion_diaria_sucursal_tipo" in sql, (
        f"upgrade() UNIQUE INDEX must use canonical name "
        f"uq_mv_ocupacion_diaria_sucursal_tipo; got {sql!r}"
    )
    assert "(uuid_sucursal, uuid_tipo_vehiculo)" in sql, (
        f"upgrade() UNIQUE INDEX must declare the natural composite; got {sql!r}"
    )

    # GRANT SELECT
    grant_sqls = [
        s for s in captured_sqls if "GRANT SELECT" in s
        and "mv_ocupacion_diaria" in s
    ]
    assert len(grant_sqls) == 1, (
        f"REQ-OPS-133 violated: upgrade() must re-issue the GRANT; got "
        f"{len(grant_sqls)}"
    )


# ---------------------------------------------------------------------------
# T3 -- downgrade() body
# ---------------------------------------------------------------------------


def test_migration_0034_downgrade_drops_materialized_view() -> None:
    """T3 GREEN: ``downgrade()`` emits ``DROP MATERIALIZED VIEW IF EXISTS``.

    Mirrors the 0024 downgrade contract; the same DROP form drops the
    view AND its indexes (no explicit DROP INDEX required).
    """
    from unittest.mock import MagicMock, patch

    mod = importlib.import_module("0034_recreate_mv_ocupacion_diaria_idempotent")
    captured_sqls: list[str] = []
    mock_op = MagicMock()
    mock_op.execute = MagicMock(side_effect=lambda sql: captured_sqls.append(sql))

    with patch.object(mod, "op", mock_op):
        mod.downgrade()

    drop_sqls = [
        s for s in captured_sqls if "DROP MATERIALIZED VIEW" in s
    ]
    assert len(drop_sqls) == 1, (
        f"downgrade() must emit exactly one DROP MATERIALIZED VIEW; got "
        f"{len(drop_sqls)}"
    )
    sql = drop_sqls[0]
    assert "IF EXISTS" in sql, (
        f"downgrade() must be idempotent (IF EXISTS); got {sql!r}"
    )
    assert "prod.mv_ocupacion_diaria" in sql, (
        f"downgrade() must target prod.mv_ocupacion_diaria; got {sql!r}"
    )


# ---------------------------------------------------------------------------
# T4 -- CI gate (REQ-OPS-133): check_schema_match.py exits non-zero on missing MV
# ---------------------------------------------------------------------------


def test_check_schema_match_exits_nonzero_on_missing_mv() -> None:
    """T4 GREEN: ``check_schema_match.py`` exposes the MV check.

    REQ-OPS-133 Scenario 'CI gate fails when MV missing': the script
    must assert ``to_regclass('prod.mv_ocupacion_diaria') IS NOT NULL``
    and integrate the result into the main exit-code aggregator. This
    test pins the source-level invariant -- it does NOT require Docker;
    the DB-layer assertion is exercised via the script's CLI in CI.
    """
    # _BACKEND_ROOT = backend/ ; repo root is _BACKEND_ROOT.parent
    repo_root = _BACKEND_ROOT.parent
    p = repo_root / "openspec" / "scripts" / "check_schema_match.py"
    assert p.is_file(), f"check_schema_match.py missing: {p}"
    src = p.read_text(encoding="utf-8")
    assert "to_regclass" in src, (
        "REQ-OPS-133 violated: check_schema_match.py must call to_regclass() "
        "to assert prod.mv_ocupacion_diaria presence"
    )
    assert "mv_ocupacion_diaria_missing" in src, (
        "REQ-OPS-133 violated: check_schema_match.py must emit the "
        "'mv_ocupacion_diaria_missing' discriminator when the view is absent"
    )
    assert "uq_mv_ocupacion_diaria_sucursal_tipo" in src, (
        "REQ-OPS-133 violated: check_schema_match.py must also assert the "
        "UNIQUE INDEX required by REFRESH CONCURRENTLY"
    )


__all__ = [
    "test_check_schema_match_exits_nonzero_on_missing_mv",
    "test_migration_0034_downgrade_drops_materialized_view",
    "test_migration_0034_emits_to_regclass_post_check",
    "test_migration_0034_module_imports_with_canonical_revision",
    "test_migration_0034_reasserts_unique_index_and_grant",
    "test_migration_0034_upgrade_and_downgrade_are_callable",
    "test_migration_0034_uses_create_or_replace_materialized_view",
]