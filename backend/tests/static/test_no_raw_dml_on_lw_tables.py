"""test_no_raw_dml_on_lw_tables.py — REQ-21 (workflow state-machine invariant).

Rejects ``session.execute(update/delete(...))`` against any ``[L-W]`` ORM
class outside the canonical ``repo/workflow.py::append_transition`` helper.

``[L-W]`` (workflow) tables carry state machines (REQ-21). The ONLY allowed
write path is :func:`repo.workflow.append_transition`, which:

1. Looks up the parent row's current ``estado``.
2. Validates the transition is legal per ``STATE_MACHINES[table]``.
3. Inserts a new row linked via ``uuid_xxx_padre`` + co-transactional
   ``log_transaccional``.

Any direct UPDATE or DELETE bypasses the state-machine validator — defense
in depth.

``[L-W]`` ORM classes (PR6 ships these):

- ReimpresionTicket, Anulaciones, Reclamos, Alerta, EnvioDian, ValidacionEvento

The known-good exception is ``repo/workflow.py`` — that module is the
single writer for ``[L-W]`` tables.
"""
from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = (
    Path(__file__).resolve().parents[2]
    / "packages" / "parkos_core" / "src" / "parkos_core"
)
_SCAN_DIRS = (_REPO_ROOT / "api", _REPO_ROOT / "repo")
_WORKFLOW_HELPER_PATH = _REPO_ROOT / "repo" / "workflow.py"


def _load_lw_class_names() -> set[str]:
    """Return the set of ``[L-W]`` ORM class names (PR6 ships 6)."""
    try:
        from parkos_core.models.L_W.alerta import Alerta  # type: ignore[import-not-found]
        from parkos_core.models.L_W.anulaciones import Anulaciones
        from parkos_core.models.L_W.envio_dian import EnvioDian
        from parkos_core.models.L_W.reclamos import Reclamos
        from parkos_core.models.L_W.reimpresion_ticket import ReimpresionTicket
        from parkos_core.models.L_W.validacion_evento import ValidacionEvento
    except ImportError:
        return {
            "ReimpresionTicket", "Anulaciones", "Reclamos",
            "Alerta", "EnvioDian", "ValidacionEvento",
        }
    classes = (ReimpresionTicket, Anulaciones, Reclamos, Alerta, EnvioDian, ValidacionEvento)
    return {c.__name__ for c in classes}


def _is_session_execute_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr != "execute":
        return False
    base = node.func.value
    return isinstance(base, ast.Name) and base.id in {
        "session", "async_session", "conn", "connection", "s", "db",
    }


def _leftmost_call(node: ast.Call) -> ast.Call:
    """Walk ``Call.func.value`` down to the leftmost nested Call.

    Handles chained SQLAlchemy 2.0 calls like ``update(X).where(...).values(...)``.
    """
    cur = node
    while (
        isinstance(cur, ast.Call)
        and isinstance(cur.func, ast.Attribute)
        and isinstance(cur.func.value, ast.Call)
    ):
        cur = cur.func.value
    return cur


def _is_root_update_or_delete(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Attribute) and node.func.attr in {"update", "delete"}
    ) or (
        isinstance(node.func, ast.Name) and node.func.id in {"update", "delete"}
    )


def _mutation_targets_lw_class(node: ast.Call, lw_classes: set[str]) -> bool:
    if not node.args:
        return False
    target = node.args[0]
    if isinstance(target, ast.Name) and target.id in lw_classes:
        return True
    return (
        isinstance(target, ast.Call)
        and isinstance(target.func, ast.Name)
        and target.func.id in lw_classes
    )


def _scan_python_file(path: Path, lw_classes: set[str]) -> list[tuple[int, str]]:
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
        if not isinstance(first_arg, ast.Call):
            continue
        root = _leftmost_call(first_arg)
        if not _is_root_update_or_delete(root):
            continue
        if not _mutation_targets_lw_class(root, lw_classes):
            continue
        snippet = ast.unparse(node)[:160]
        matches.append((node.lineno, snippet))
    return matches


def test_no_raw_dml_on_lw_tables() -> None:
    """No raw UPDATE/DELETE on ``[L-W]`` tables outside ``repo/workflow.py``."""
    lw_classes = _load_lw_class_names()
    assert lw_classes, "no [L-W] classes found — parkos_core.models.L_W import path broken?"

    all_matches: list[tuple[Path, int, str]] = []
    for scan_dir in _SCAN_DIRS:
        if not scan_dir.is_dir():
            continue
        for py_file in sorted(scan_dir.rglob("*.py")):
            if py_file == _WORKFLOW_HELPER_PATH:
                continue
            if py_file.name == "__init__.py":
                continue
            for line_no, snippet in _scan_python_file(py_file, lw_classes):
                all_matches.append((py_file, line_no, snippet))

    assert not all_matches, (
        "Raw UPDATE/DELETE on [L-W] tables outside repo/workflow.py:\n"
        + "\n".join(
            f"  {p.relative_to(_REPO_ROOT)}:{ln}: {s}"
            for p, ln, s in all_matches
        )
    )
