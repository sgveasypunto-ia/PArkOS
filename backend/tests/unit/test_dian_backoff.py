"""test_dian_backoff.py — T-PR9-004 acceptance for ``dian.backoff``.

``DIAN_BACKOFF_SCHEDULE`` is declared exactly once, in
``parkos_core.dian.backoff``, and IMPORTED (never re-declared as a second
literal tuple) by both:

  - the sync catalog entries (``factura_electronica`` / ``revocacion_factura``)
  - the cloud-side DIAN dispatcher module

Also asserts the curve's exact values (1m -> 5m -> 15m -> 1h -> 6h -> 24h)
and that it is distinct from ``repo.sync_queue.BACKOFF_SCHEDULE`` (the
general curve).
"""
from __future__ import annotations

import ast
import os
from datetime import timedelta
from pathlib import Path

from parkos_core.dian.backoff import DIAN_BACKOFF_SCHEDULE, DIAN_MAX_RETRIES
from parkos_core.repo.sync_queue import BACKOFF_SCHEDULE as GENERAL_BACKOFF_SCHEDULE

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _REPO_ROOT / "packages" / "parkos_core" / "src" / "parkos_core"


def test_curve_values_exact() -> None:
    """1m -> 5m -> 15m -> 1h -> 6h -> 24h, terminal after 6 attempts."""
    expected = (
        timedelta(minutes=1),
        timedelta(minutes=5),
        timedelta(minutes=15),
        timedelta(hours=1),
        timedelta(hours=6),
        timedelta(hours=24),
    )
    assert expected == DIAN_BACKOFF_SCHEDULE
    assert DIAN_MAX_RETRIES == 6
    assert len(DIAN_BACKOFF_SCHEDULE) == DIAN_MAX_RETRIES


def test_curve_is_distinct_from_the_general_sync_queue_curve() -> None:
    """The DIAN curve must not collapse onto the general replication curve."""
    assert DIAN_BACKOFF_SCHEDULE != GENERAL_BACKOFF_SCHEDULE
    assert len(GENERAL_BACKOFF_SCHEDULE) == 6
    # Both cap at 24h, but the front of the curve differs (15m vs 30m).
    assert DIAN_BACKOFF_SCHEDULE[2] == timedelta(minutes=15)
    assert GENERAL_BACKOFF_SCHEDULE[2] == timedelta(minutes=30)


def _names_imported_from_dian_backoff(path: Path) -> set[str]:
    """Return the names a module imports from ``parkos_core.dian.backoff``.

    Handles BOTH relative-import shapes actually used in this codebase:
    ``from ....dian.backoff import X`` (module="dian.backoff", deep
    relative — the catalog entries, several packages away) and
    ``from ..backoff import X`` (module="backoff", level=2 — the
    dispatcher, which already lives INSIDE the ``dian`` package so its
    relative import never spells out "dian").
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        is_deep_relative = node.module.endswith("dian.backoff")
        is_sibling_relative = node.module == "backoff" and node.level >= 1
        if is_deep_relative or is_sibling_relative:
            imported.update(alias.name for alias in node.names)
    return imported


def _module_source_declares_dian_backoff_schedule_literal(path: Path) -> bool:
    """True if the module assigns its OWN ``DIAN_BACKOFF_SCHEDULE`` literal.

    Distinguishes "imports the shared constant" from "redeclares a second,
    independently-drifting tuple with the same name" (T-PR9-004's explicit
    anti-duplication acceptance criterion).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "DIAN_BACKOFF_SCHEDULE" in targets:
                return True
    return False


def test_catalog_entries_import_not_redeclare_the_curve() -> None:
    """``sync_entries_le.py`` / ``sync_entries_a.py`` import the shared constant."""
    le_path = _PARKOS_CORE_SRC / "sync" / "catalog" / "entries" / "sync_entries_le.py"
    a_path = _PARKOS_CORE_SRC / "sync" / "catalog" / "entries" / "sync_entries_a.py"

    assert "DIAN_BACKOFF_SCHEDULE" in _names_imported_from_dian_backoff(le_path)
    assert "DIAN_BACKOFF_SCHEDULE" in _names_imported_from_dian_backoff(a_path)
    assert not _module_source_declares_dian_backoff_schedule_literal(le_path)
    assert not _module_source_declares_dian_backoff_schedule_literal(a_path)


def test_dispatcher_imports_not_redeclares_the_curve() -> None:
    """``dian/cloud/dispatcher.py`` imports the shared constant too."""
    dispatcher_path = _PARKOS_CORE_SRC / "dian" / "cloud" / "dispatcher.py"

    assert "DIAN_BACKOFF_SCHEDULE" in _names_imported_from_dian_backoff(dispatcher_path)
    assert not _module_source_declares_dian_backoff_schedule_literal(dispatcher_path)


def test_backoff_module_has_no_branch_deploy_guard() -> None:
    """``dian/backoff.py`` must import cleanly on BOTH deploys (plain data)."""
    prev = os.environ.get("PARKOS_DEPLOY")
    os.environ["PARKOS_DEPLOY"] = "branch"
    try:
        import importlib
        import sys

        sys.modules.pop("parkos_core.dian.backoff", None)
        module = importlib.import_module("parkos_core.dian.backoff")
        assert module.DIAN_BACKOFF_SCHEDULE == DIAN_BACKOFF_SCHEDULE
    finally:
        if prev is None:
            os.environ.pop("PARKOS_DEPLOY", None)
        else:
            os.environ["PARKOS_DEPLOY"] = prev
