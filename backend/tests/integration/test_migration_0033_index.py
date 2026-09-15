"""HU-F1.15 / T1.1..T1.3 -- MIGRATION 0033 pre-flight + module-contract tests.

Pre-flight on 2026-09-15 confirmed:

  * ``prod.login`` exists with composite PK + FK ``fk_login_uuid_usuario``
    (migration 0001:511-523, [L-S] SessionBase, 5 business columns).
  * ``prod.usuarios`` exists ([V] VersionedBase, bi-temporal).
  * ``prod.login`` has the implicit FK index ``login_uuid_usuario_idx``
    on ``uuid_usuario`` (migration 0001:1247-1255) -- NO composite
    index on ``(uuid_usuario, timestamp_evento DESC)`` exists today.
  * ``audit_read`` permission pre-seeded at
    ``0002_seed_permisos_canonicos.py:48`` (DEC-LOGIN-09.B reused from
    F1.14 DEC-SYNC-03.B).

This module verifies the migration file metadata + pre-flight state
(source-level + structure). The DB-layer assertions are exercised in
gated integration tests (Docker + testcontainers[postgres]), not here.

T1.1 RED: ``test_migration_0033_module_imports_with_canonical_revision``
asserts that the new migration module is importable + has the right
``revision`` + ``down_revision`` chain (F1.14 head = ``0032_...``).
Pre-implementation this raises ``ModuleNotFoundError`` -- that is the
RED state.
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
# T1.1.1 -- migration file metadata
# ---------------------------------------------------------------------------


def test_migration_0033_module_imports_with_canonical_revision() -> None:
    """T1.1 RED/GREEN: module imports + revision metadata matches F1.14 head.

    MIGRATION 0033 chains off F1.14 head
    (``0032_seed_alert_types_operativos``) and uses revision id
    ``0033_login_historic_index``. Pre-implementation this raises
    ``ModuleNotFoundError`` -- that is the RED state.
    """
    mod = importlib.import_module("0033_login_historic_index")
    assert mod.revision == "0033_login_historic_index", (
        f"unexpected revision id: {mod.revision!r}"
    )
    assert mod.down_revision == "0032_seed_alert_types_operativos", (
        "F1.15 migration must chain off the F1.14 head "
        "(0032_seed_alert_types_operativos); got "
        f"{mod.down_revision!r}"
    )


def test_migration_0033_upgrade_and_downgrade_are_callable() -> None:
    """T1.1 GREEN: ``upgrade()`` + ``downgrade()`` are callables.

    MIGRATION 0033 is a REAL DDL composite index (DEC-LOGIN-06):
    Op 0 pre-flight DO $$ asserting 2 tables (login, usuarios) +
    Op 1 ``CREATE INDEX CONCURRENTLY prod.idx_login_uuid_usuario_evento
    ON prod.login (uuid_usuario, timestamp_evento DESC)`` wrapped in
    ``op.get_context().autocommit_block()``. ``downgrade()`` reverses
    via ``DROP INDEX CONCURRENTLY`` (also wrapped in autocommit_block).
    """
    mod = importlib.import_module("0033_login_historic_index")
    assert callable(mod.upgrade), "MIGRATION 0033 upgrade() is not callable"
    assert callable(mod.downgrade), "MIGRATION 0033 downgrade() is not callable"


# ---------------------------------------------------------------------------
# T1.1.2 -- DEC-LOGIN-06: composite index DDL body verbatim
# ---------------------------------------------------------------------------


def test_migration_0033_creates_composite_index_on_login() -> None:
    """T1.1 GREEN: ``upgrade()`` emits the canonical composite index DDL.

    DEC-LOGIN-06 + design.md Appendix A verbatim:
    ``CREATE INDEX CONCURRENTLY IF NOT EXISTS
    prod.idx_login_uuid_usuario_evento
    ON prod.login (uuid_usuario, timestamp_evento DESC)``
    wrapped in ``op.get_context().autocommit_block()`` (CONCURRENTLY
    cannot run inside a transaction).
    """
    from unittest.mock import MagicMock, patch

    mod = importlib.import_module("0033_login_historic_index")
    captured_sqls: list[str] = []

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=None)
    mock_ctx.__exit__ = MagicMock(return_value=None)
    mock_op = MagicMock()
    mock_op.get_context.return_value.autocommit_block.return_value = mock_ctx
    mock_op.execute = MagicMock(side_effect=lambda sql: captured_sqls.append(sql))

    with patch.object(mod, "op", mock_op):
        mod.upgrade()

    create_idx_sqls = [
        s for s in captured_sqls if "CREATE INDEX CONCURRENTLY" in s
    ]
    assert len(create_idx_sqls) == 1, (
        f"upgrade() must emit exactly one CREATE INDEX CONCURRENTLY; got {len(create_idx_sqls)}"
    )
    sql = create_idx_sqls[0]
    assert "prod.idx_login_uuid_usuario_evento" in sql, (
        f"upgrade() missing canonical index name prod.idx_login_uuid_usuario_evento; got {sql!r}"
    )
    assert "ON prod.login" in sql, f"upgrade() must target prod.login table; got {sql!r}"
    assert "(uuid_usuario, timestamp_evento DESC)" in sql, (
        f"upgrade() must declare composite on (uuid_usuario, timestamp_evento DESC); got {sql!r}"
    )
    assert "IF NOT EXISTS" in sql, (
        f"upgrade() CREATE INDEX must be idempotent (IF NOT EXISTS) per DEC-LOGIN-06; got {sql!r}"
    )
    # Verify autocommit_block() wrapping (CONCURRENTLY cannot run in transaction).
    mock_op.get_context.return_value.autocommit_block.assert_called()


def test_migration_0033_downgrade_drops_composite_index() -> None:
    """T1.1 GREEN: ``downgrade()`` emits the canonical DROP INDEX DDL.

    DEC-LOGIN-06 invariant: downgrade reverses Op 1 cleanly via
    ``DROP INDEX CONCURRENTLY IF EXISTS prod.idx_login_uuid_usuario_evento``
    wrapped in ``op.get_context().autocommit_block()``.
    """
    from unittest.mock import MagicMock, patch

    mod = importlib.import_module("0033_login_historic_index")
    captured_sqls: list[str] = []

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=None)
    mock_ctx.__exit__ = MagicMock(return_value=None)
    mock_op = MagicMock()
    mock_op.get_context.return_value.autocommit_block.return_value = mock_ctx
    mock_op.execute = MagicMock(side_effect=lambda sql: captured_sqls.append(sql))

    with patch.object(mod, "op", mock_op):
        mod.downgrade()

    drop_idx_sqls = [
        s for s in captured_sqls if "DROP INDEX CONCURRENTLY" in s
    ]
    assert len(drop_idx_sqls) == 1, (
        f"downgrade() must emit exactly one DROP INDEX CONCURRENTLY; got {len(drop_idx_sqls)}"
    )
    sql = drop_idx_sqls[0]
    assert "prod.idx_login_uuid_usuario_evento" in sql, (
        f"downgrade() must drop the canonical index name; got {sql!r}"
    )
    assert "IF EXISTS" in sql, (
        f"downgrade() DROP INDEX must be idempotent (IF EXISTS); got {sql!r}"
    )


# ---------------------------------------------------------------------------
# T1.1.3 -- DEC-LOGIN-09.B: audit_read permission pre-seeded at 0002:48
# ---------------------------------------------------------------------------


def test_audit_read_pre_seeded_in_0002_migration() -> None:
    """T1.1: ``audit_read`` permission is pre-seeded in ``0002_seed_permisos_canonicos.py``.

    DEC-LOGIN-09.B resolved: no new permission seeded in MIGRATION 0033;
    the F1.15 endpoint reuses ``audit_read`` from the canonical
    permission list (F1.14 DEC-SYNC-03.B precedent). This test asserts
    the source-level invariant.
    """
    p = (
        _BACKEND_ROOT
        / "packages"
        / "parkos_core"
        / "migrations"
        / "versions"
        / "0002_seed_permisos_canonicos.py"
    )
    assert p.is_file(), f"canonical migration missing: {p}"
    source = p.read_text(encoding="utf-8")
    assert '"audit_read"' in source or "'audit_read'" in source, (
        "0002_seed_permisos_canonicos.py must pre-seed the audit_read permission "
        "(DEC-LOGIN-09.B)"
    )
