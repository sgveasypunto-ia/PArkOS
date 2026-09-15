"""HU-F1.6 / R-A3 -- AST walk: ``repo/ingreso.py::crear_ingreso_evento``.

Defense in depth (R-A3 mitigation, design §13). The ONLY allowed write
path on ``prod.ingreso`` is :func:`repo.ingreso.crear_ingreso_evento`;
this test rejects any ``UPDATE | DELETE | TRUNCATE | MERGE | FOR UPDATE |
FOR SHARE`` literal in that function's body (case-insensitive, outside
strings/docstrings).

Pattern: F1.3/F1.5/F1.8 precedent (see ``tests/static/test_no_write_in_ocupacion.py``).
"""
from __future__ import annotations

import ast
from itertools import pairwise
from pathlib import Path

import pytest

_REPO_FILE = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "parkos_core"
    / "src"
    / "parkos_core"
    / "repo"
    / "ingreso.py"
)

_FORBIDDEN = ("UPDATE", "DELETE", "TRUNCATE", "MERGE")


def _iter_identifiers(fn: ast.FunctionDef) -> list[tuple[str, int]]:
    """Yield (name, lineno) for every identifier + constant string token.

    Uses ``ast.walk`` over the function body so the depth-first traversal
    mirrors what the handler does at runtime -- the exact same code
    patterns (UPDATE / DELETE / ... literals) get flagged uniformly.

    The function's docstring (and constant-string children ONLY when they
    are inside an :class:`ast.Expr` that begins the body, i.e. the
    docstring position) are excluded -- the helper explicitly documents
    which verbs the test rejects.
    """
    tokens: list[tuple[str, int]] = []
    docstring_value: str | None = None
    if (
        fn.body
        and isinstance(fn.body[0], ast.Expr)
        and isinstance(fn.body[0].value, ast.Constant)
        and isinstance(fn.body[0].value.value, str)
    ):
        docstring_value = fn.body[0].value.value
    for node in ast.walk(fn):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value == docstring_value:
                continue
            tokens.append((node.value, node.lineno))
        elif isinstance(node, ast.Name):
            tokens.append((node.id, node.lineno))
        elif isinstance(node, ast.Attribute):
            tokens.append((node.attr, node.lineno))
    return tokens


def _find_crear_ingreso_evento(tree: ast.Module) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "crear_ingreso_evento":
            return node  # type: ignore[return-value]
        if isinstance(node, ast.FunctionDef) and node.name == "crear_ingreso_evento":
            return node
    raise AssertionError(
        "crear_ingreso_evento not found in repo/ingreso.py -- handler cannot "
        "delegate the [L-E] INSERT path"
    )


def test_crear_ingreso_evento_rechaza_update_delete_truncate() -> None:
    """R-A3 CI gate: the body of ``crear_ingreso_evento`` cannot reference any
    write verb (UPDATE / DELETE / TRUNCATE / MERGE) or pessimistic lock
    modifier (FOR UPDATE / FOR SHARE). The function delegates to
    ``repo.event.record_event`` which carries its own R-A3 contract.
    """
    src = _REPO_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = _find_crear_ingreso_evento(tree)
    tokens = _iter_identifiers(fn)
    offenders: list[tuple[str, int]] = []
    for name, lineno in tokens:
        upper = name.upper()
        if any(kw in upper for kw in _FORBIDDEN):
            offenders.append((name, lineno))
    if offenders:
        formatted = ", ".join(f"{name!r}@L{ln}" for name, ln in offenders)
        pytest.fail(
            f"crear_ingreso_evento contains forbidden write literals: {formatted}"
        )
    # Also explicitly forbid ``FOR`` immediately followed by ``UPDATE|SHARE``
    # (pessimistic locks on the [L-E] event table -- R-A3 forbids them).
    for (n1, _ln1), (n2, _ln2) in pairwise(tokens):
        if n1.upper() == "FOR" and n2.upper() in {"UPDATE", "SHARE"}:
            pytest.fail(
                f"crear_ingreso_evento contains FOR {n2.upper()} "
                "(pessimistic lock on [L-E]) -- R-A3 forbids it"
            )


__all__ = [
    "test_crear_ingreso_evento_rechaza_update_delete_truncate",
]
