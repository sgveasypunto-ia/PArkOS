"""test_no_raw_dml_on_le_tables.py — REQ-33 (insert-only invariant for [L-E]).

Rejects ``session.execute(update(...))`` or ``session.execute(delete(...))``
against any ``[L-E]`` ORM class outside the canonical
``repo/event.py::record_event`` helper.

``[L-E]`` (lifecycle event) tables are append-only by definition. Any direct
UPDATE or DELETE on them is a violation of the audit-first canon
(AGENTS.md §3): a lifecycle event is a point-in-time fact and cannot be
rewritten or erased. The only legal write is INSERT, routed through
``record_event``.

The AST scanner walks every file under ``parkos_core/api/`` and
``parkos_core/repo/`` looking for
``session.execute(update(<LE_class>))`` or
``session.execute(delete(<LE_class>))`` where the target is a ``[L-E]`` ORM
class.

``[L-E]`` ORM classes (PR5 ships ``Ingreso``; PR6 adds ``Facturas`` and
``FacturaElectronica``):

- ``Ingreso`` — vehicle entry event

The known-good exception is ``repo/event.py`` — that module contains
``record_event``, the single writer for ``[L-E]`` tables.

The scanner imports ``parkos_core.models.L_E`` to get the canonical class
list at test-load time, then walks AST with that list as the rejection
target.
"""
from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = (
    Path(__file__).resolve().parents[2]
    / "packages" / "parkos_core" / "src" / "parkos_core"
)
_SCAN_DIRS = (_REPO_ROOT / "api", _REPO_ROOT / "repo")
_EVENT_HELPER_PATH = _REPO_ROOT / "repo" / "event.py"


def _load_le_class_names() -> set[str]:
    """Return the set of ``[L-E]`` ORM class names.

    Imported lazily so missing deps surface at AST-scan time rather than
    at collection time.
    """
    try:
        from parkos_core.models.L_E.ingreso import (  # type: ignore[import-not-found]
            Ingreso,
        )
    except ImportError:
        # In PR5 the models package exists; if import fails we surface
        # the names from a known list so the scanner still works for code
        # that hasn't been imported yet.
        return {"Ingreso"}
    classes = (Ingreso,)
    return {c.__name__ for c in classes}


def _is_session_execute_call(node: ast.Call) -> bool:
    """True iff the call's function is ``<obj>.execute`` where <obj> is
    plausibly a session/connection (``session``, ``conn``, ``db``, ``s``,
    ``async_session``, ``connection``).
    """
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


def _leftmost_call(node: ast.Call) -> ast.Call:
    """Walk ``node.func.value`` chain to find the leftmost ``ast.Call``.

    Handles the SQLAlchemy 2.0 chained idiom::

        update(Model).where(...).values(...)

    The outermost ``ast.Call`` here is ``.values(...)``, but the chain
    bottoms out in ``update(Model)``. We walk ``.func.value`` until the
    chain terminates in a non-``Call`` and return the leftmost call.
    """
    current: ast.AST = node
    while isinstance(current, ast.Call):
        func = current.func
        if not isinstance(func, ast.Attribute):
            return current
        inner = func.value
        if not isinstance(inner, ast.Call):
            return current
        current = inner
    return current


def _is_root_update_or_delete(root: ast.Call) -> str | None:
    """Return ``'update'`` / ``'delete'`` if ``root`` is a top-level
    ``update(...)`` / ``delete(...)`` call, else ``None``.

    Handles both spellings:
      - ``update(X)`` / ``delete(X)`` where the function is an imported
        name (``ast.Name``).
      - ``sa.update(X)`` / ``sql.delete(X)`` where the function is an
        attribute access (``ast.Attribute``).
    """
    func = root.func
    if isinstance(func, ast.Name) and func.id in {"update", "delete"}:
        return func.id
    if isinstance(func, ast.Attribute) and func.attr in {"update", "delete"}:
        return func.attr
    return None


def _mutation_targets_le_class(node: ast.Call, le_classes: set[str]) -> bool:
    """True iff ``update(X)`` or ``delete(X)`` references a ``[L-E]`` class
    name (either as a bare name ``X`` or as a call ``X(...)``).
    """
    if not node.args:
        return False
    target = node.args[0]
    if isinstance(target, ast.Name) and target.id in le_classes:
        return True
    return (
        isinstance(target, ast.Call)
        and isinstance(target.func, ast.Name)
        and target.func.id in le_classes
    )


def _scan_python_file(path: Path, le_classes: set[str]) -> list[tuple[int, str]]:
    """Walk one Python file; return matches of
    ``session.execute(update(<LE>))`` or
    ``session.execute(delete(<LE>))``, including chained variants like
    ``session.execute(update(<LE>).where(...).values(...))``.
    """
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
        root_call = _leftmost_call(first_arg)
        if _is_root_update_or_delete(root_call) is None:
            continue
        if not _mutation_targets_le_class(root_call, le_classes):
            continue
        snippet = ast.unparse(node)[:160]
        matches.append((node.lineno, snippet))

    return matches


def test_no_raw_dml_on_le_tables() -> None:
    """No raw UPDATE/DELETE on ``[L-E]`` tables outside ``repo/event.py``."""
    le_classes = _load_le_class_names()
    assert le_classes, "no [L-E] classes found — parkos_core.models.L_E.ingreso import path broken?"

    all_matches: list[tuple[Path, int, str]] = []
    for scan_dir in _SCAN_DIRS:
        if not scan_dir.is_dir():
            continue
        for py_file in sorted(scan_dir.rglob("*.py")):
            if py_file == _EVENT_HELPER_PATH:
                continue
            if py_file.name == "__init__.py":
                continue
            for line_no, snippet in _scan_python_file(py_file, le_classes):
                all_matches.append((py_file, line_no, snippet))

    assert not all_matches, (
        "Raw UPDATE/DELETE on [L-E] tables outside repo/event.py:\n"
        + "\n".join(
            f"  {p.relative_to(_REPO_ROOT)}:{ln}: {s}"
            for p, ln, s in all_matches
        )
    )
