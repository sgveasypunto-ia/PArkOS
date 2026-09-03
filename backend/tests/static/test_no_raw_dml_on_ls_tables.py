"""test_no_raw_dml_on_ls_tables.py — REQ-46.

Rejects raw UPDATE/DELETE on [L-S] (session lifecycle) tables outside the
``repo/session_cycle.py`` helper. [L-S] tables have a DB-layer
``BEFORE UPDATE`` session-guard trigger that requires a co-transactional
``log_transaccional`` row — only the helper knows how to write that row
in the right order, so any other writer is rejected.

[L-S] ORM classes (PR1b ships ``Login``; PR7 adds ``Sesion``):

  - Login
  - Sesion

The scanner is identical in shape to the [A] / [V] scanners — same AST
walk, same allowlist pattern. The allowlist is just
``repo/session_cycle.py``.
"""
from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = (
    Path(__file__).resolve().parents[2]
    / "packages" / "parkos_core" / "src" / "parkos_core"
)
_SCAN_DIRS = (_REPO_ROOT / "api", _REPO_ROOT / "repo")
_SESSION_CYCLE_PATH = _REPO_ROOT / "repo" / "session_cycle.py"


def _load_ls_class_names() -> set[str]:
    """Return the [L-S] ORM class names available in PR1b.

    PR1b ships ``Login``. PR7 adds ``Sesion``. We import what's
    importable and fall back to the known set otherwise.
    """
    candidates: set[str] = {"Login", "Sesion"}
    try:
        from parkos_core.models import Login  # type: ignore[import-not-found]

        candidates.add(Login.__name__)
    except ImportError:
        pass
    return candidates


def _is_session_execute_call(node: ast.Call) -> bool:
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


def _dml_targets_ls_class(node: ast.AST, ls_classes: set[str]) -> str | None:
    """Return the class name if node is ``<DML>(<LS class>)``.

    We reject UPDATE and DELETE — INSERT is allowed (that's the
    ``record_login`` path).
    """
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr not in {"update", "delete"}:
        return None
    if not node.args:
        return None
    target = node.args[0]
    if isinstance(target, ast.Name) and target.id in ls_classes:
        return target.id
    if (
        isinstance(target, ast.Call)
        and isinstance(target.func, ast.Name)
        and target.func.id in ls_classes
    ):
        return target.func.id
    return None


def _scan_python_file(path: Path, ls_classes: set[str]) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
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
        hit = _dml_targets_ls_class(first_arg, ls_classes)
        if hit is None:
            continue
        matches.append((node.lineno, hit))

    return matches


def test_no_raw_dml_on_ls_tables() -> None:
    """No raw UPDATE/DELETE on [L-S] tables outside ``repo/session_cycle.py``."""
    ls_classes = _load_ls_class_names()
    assert ls_classes, "no [L-S] classes found"

    all_matches: list[tuple[Path, int, str]] = []
    for scan_dir in _SCAN_DIRS:
        if not scan_dir.is_dir():
            continue
        for py_file in sorted(scan_dir.rglob("*.py")):
            if py_file == _SESSION_CYCLE_PATH:
                continue
            if py_file.name == "__init__.py":
                continue
            for line_no, class_name in _scan_python_file(py_file, ls_classes):
                all_matches.append((py_file, line_no, class_name))

    assert not all_matches, (
        "Raw UPDATE/DELETE on [L-S] tables outside repo/session_cycle.py:\n"
        + "\n".join(
            f"  {p.relative_to(_REPO_ROOT)}:{ln}: {c}"
            for p, ln, c in all_matches
        )
    )