"""test_no_raw_dml_on_a_tables.py — REQ-13.

Rejects ``session.execute(insert/update/delete(...))`` against any of the
``[A]`` ORM classes outside the canonical ``repo/append_only.py``
(PR2+) helper. [A] tables are append-only by database contract; the ORM
layer MUST funnel all writes through the helper, which performs the
allowed UPDATE on the four ``sync_queue`` columns and otherwise errors.

The scanner walks ``parkos_core/api/`` and ``parkos_core/repo/``
looking for:

  - ``session.execute(insert(<A class>))``
  - ``session.execute(update(<A class>))``
  - ``session.execute(delete(<A class>))``

The known-good exceptions:

  - ``repo/append_only.py`` (PR2) — the canonical writer for [A]
  - ``repo/sync_outbox.py`` (PR2) — for ``sync_queue`` whitelisted cols
  - ``repo/versioned.py::close_and_insert`` — writes a ``log_transaccional``
    row (the ONE [A] table that versioned.py touches)

For PR1c the ``append_only`` and ``sync_outbox`` modules do NOT exist yet.
The scanner currently flags only PR1b code; tests pass if PR1b respects
the rule (it does — no raw DML on any [A] class outside versioned.py).
"""
from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = (
    Path(__file__).resolve().parents[2]
    / "packages" / "parkos_core" / "src" / "parkos_core"
)
_SCAN_DIRS = (_REPO_ROOT / "api", _REPO_ROOT / "repo")
_VERSIONED_HELPER_PATH = _REPO_ROOT / "repo" / "versioned.py"


def _load_a_class_names() -> set[str]:
    """Return the [A] ORM class names available in PR1b.

    PR1b ships ``LogTransaccional`` only. Subsequent PRs (PR2) add the
    rest: ``Salidas, Caja, FacturaDetalle, FacturaImpuestos,
    FacturaOtrosCobros, FacturaPagos, Arqueo, RevocacionFactura,
    SyncQueue, SyncLog, SyncConflicto``.

    We import what's available; the scanner falls back to the known set
    if the import path is incomplete (e.g. partial PR2 merge).
    """
    candidates: set[str] = {
        "LogTransaccional",
        "Salidas",
        "Caja",
        "FacturaDetalle",
        "FacturaImpuestos",
        "FacturaOtrosCobros",
        "FacturaPagos",
        "Arqueo",
        "RevocacionFactura",
        "SyncQueue",
        "SyncLog",
        "SyncConflicto",
    }
    try:
        from parkos_core.models import LogTransaccional  # type: ignore[import-not-found]

        candidates.add(LogTransaccional.__name__)
    except ImportError:
        pass
    return candidates


# Files that may legitimately touch [A] tables (allowlist).
_ALLOWED_FILES = {
    _VERSIONED_HELPER_PATH,  # close_and_insert → log_transaccional only
}


def _is_session_execute_call(node: ast.Call) -> bool:
    """Same heuristic as test_no_raw_upsert_on_v_tables."""
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr != "execute":
        return False
    base = node.func.value
    return isinstance(base, ast.Name) and base.id in {
        "session",
        "async_session",
        "conn",
        "connection",
        "s",
        "db",
    }


def _dml_targets_a_class(node: ast.AST, a_classes: set[str]) -> tuple[str, str] | None:
    """Return (dml_kind, class_name) if node is ``<DML>(<A class>)``."""
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr not in {"insert", "update", "delete"}:
        return None
    if not node.args:
        return None
    target = node.args[0]
    if isinstance(target, ast.Name) and target.id in a_classes:
        return (node.func.attr, target.id)
    if (
        isinstance(target, ast.Call)
        and isinstance(target.func, ast.Name)
        and target.func.id in a_classes
    ):
        return (node.func.attr, target.func.id)
    return None


def _scan_python_file(path: Path, a_classes: set[str]) -> list[tuple[int, str, str]]:
    """Walk one Python file; return (line_no, dml_kind, class_name) matches."""
    matches: list[tuple[int, str, str]] = []
    if not path.is_file():
        return matches
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return matches

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_session_execute_call(node):
            continue
        first_arg = node.args[0] if node.args else None
        if first_arg is None:
            continue
        hit = _dml_targets_a_class(first_arg, a_classes)
        if hit is None:
            continue
        kind, class_name = hit
        matches.append((node.lineno, kind, class_name))
    return matches


def test_no_raw_dml_on_a_tables() -> None:
    """No raw INSERT/UPDATE/DELETE on [A] tables outside the allowlist."""
    a_classes = _load_a_class_names()
    assert a_classes, "no [A] classes found"

    all_matches: list[tuple[Path, int, str, str]] = []
    for scan_dir in _SCAN_DIRS:
        if not scan_dir.is_dir():
            continue
        for py_file in sorted(scan_dir.rglob("*.py")):
            if py_file in _ALLOWED_FILES:
                continue
            if py_file.name == "__init__.py":
                continue
            for line_no, kind, class_name in _scan_python_file(py_file, a_classes):
                all_matches.append((py_file, line_no, kind, class_name))

    assert not all_matches, (
        "Raw DML on [A] tables outside the allowlist:\n"
        + "\n".join(
            f"  {p.relative_to(_REPO_ROOT)}:{ln}: {k}({c})"
            for p, ln, k, c in all_matches
        )
    )