"""test_no_raw_upsert_on_v_tables.py — C-2 (bi-temporal invariant).

Rejects ``session.execute(update(...))`` against any of the [V] ORM classes
outside the canonical ``repo/versioned.py::close_and_insert`` helper. The
[V] (versioned) tables accept close+insert as the SOLE mutation pattern;
any direct UPDATE violates the bi-temporal invariant — the old version
must stay readable for history reconstruction.

The AST scanner is conservative: it walks every file under
``parkos_core/api/`` and ``parkos_core/repo/`` looking for
``ast.Call(func=ast.Attribute(attr="update"))`` inside a
``session.execute(...)`` or ``conn.execute(...)`` argument, where the
update target is a [V] class.

The known-good exception is ``repo/versioned.py::close_and_insert`` —
that function is the single writer for [V] tables.

[V] ORM classes (PR1b ships these; subsequent PRs add more):

  - Usuarios, Permisos, PermisosUsuario, UsuariosSucursal, TipoPersona

The scanner imports ``parkos_core.models`` to get the canonical class
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
_VERSIONED_HELPER_PATH = _REPO_ROOT / "repo" / "versioned.py"


def _load_v_class_names() -> set[str]:
    """Return the set of [V] ORM class names imported from
    ``parkos_core.models``. Imported lazily so missing deps surface at
    AST-scan time rather than at collection time.
    """
    try:
        from parkos_core.models import (  # type: ignore[import-not-found]
            Permisos,
            PermisosUsuario,
            TipoPersona,
            Usuarios,
            UsuariosSucursal,
        )
    except ImportError:
        # In PR1c the models package exists; if import fails we surface
        # the names from a known list so the scanner still works for code
        # that hasn't been imported yet.
        return {
            "Permisos",
            "PermisosUsuario",
            "TipoPersona",
            "Usuarios",
            "UsuariosSucursal",
        }
    classes = (Permisos, PermisosUsuario, TipoPersona, Usuarios, UsuariosSucursal)
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


def _is_update_call(node: ast.AST) -> bool:
    """True iff node is ``session.execute(update(...))`` (i.e. an
    ``ast.Call`` whose function is ``ast.Attribute(attr="update")``).
    """
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "update"
    )


def _update_targets_v_class(node: ast.Call, v_classes: set[str]) -> bool:
    """True iff ``update(X)`` references a [V] class name."""
    if not node.args:
        return False
    target = node.args[0]
    if isinstance(target, ast.Name) and target.id in v_classes:
        return True
    return (
        isinstance(target, ast.Call)
        and isinstance(target.func, ast.Name)
        and target.func.id in v_classes
    )


def _scan_python_file(path: Path, v_classes: set[str]) -> list[tuple[int, str]]:
    """Walk one Python file; return matches of ``session.execute(update(<V>))``."""
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
        if first_arg is None or not _is_update_call(first_arg):
            continue
        if not _update_targets_v_class(first_arg, v_classes):
            continue
        snippet = ast.unparse(node)[:160]
        matches.append((node.lineno, snippet))

    return matches


def test_no_raw_upsert_on_v_tables() -> None:
    """No raw UPDATE on [V] tables outside ``repo/versioned.py``."""
    v_classes = _load_v_class_names()
    assert v_classes, "no [V] classes found — parkos_core.models import path broken?"

    all_matches: list[tuple[Path, int, str]] = []
    for scan_dir in _SCAN_DIRS:
        if not scan_dir.is_dir():
            continue
        for py_file in sorted(scan_dir.rglob("*.py")):
            if py_file == _VERSIONED_HELPER_PATH:
                continue
            if py_file.name == "__init__.py":
                continue
            for line_no, snippet in _scan_python_file(py_file, v_classes):
                all_matches.append((py_file, line_no, snippet))

    assert not all_matches, (
        "Raw UPDATE on [V] tables outside repo/versioned.py:\n"
        + "\n".join(
            f"  {p.relative_to(_REPO_ROOT)}:{ln}: {s}"
            for p, ln, s in all_matches
        )
    )