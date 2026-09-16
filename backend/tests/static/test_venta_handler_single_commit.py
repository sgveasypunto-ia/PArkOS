"""HU-F1.12 / T6.1 — KD-VENTA-01 single-commit AST walks.

KD-VENTA-01 single-commit invariant (mirror of F1.10 KD-FE-01 + F1.11
KD-TKT-01): the ``venta_suscripcion`` handler MUST contain exactly ONE
``await session.commit()`` call.

The handler MUST also AVOID:
  - ``session.begin_nested()`` (no SAVEPOINT, KD-VENTA-01)
  - String literals starting with ``SAVEPOINT`` or ``RELEASE SAVEPOINT``
    (defense in depth; catches accidental nested-transaction usage).

Pattern: parse the source file with ``ast.parse``, walk every AST node
inside the handler body, count ``await session.commit()``
invocations, count nested-transaction calls, collect any SAVEPOINT
strings. Pure Python, no DB.
"""
from __future__ import annotations

import ast
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"

_HANDLER_FILE = (
    _PARKOS_CORE_SRC / "parkos_core" / "api" / "v1" / "clientes_venta.py"
)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _handler_node(tree: ast.Module, name: str) -> ast.AsyncFunctionDef:
    """Locate ``name`` coroutine in the parsed module."""
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(
        f"`{name}` coroutine not found in {_HANDLER_FILE.name}"
    )


def _collect_commit_lines(handler: ast.AsyncFunctionDef) -> list[int]:
    """Return 1-indexed line numbers of every ``await session.commit()``."""
    hits: list[int] = []
    for node in ast.walk(handler):
        if not isinstance(node, ast.Await):
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        func = value.func
        if not isinstance(func, ast.Attribute):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "session"):
            continue
        if func.attr != "commit":
            continue
        hits.append(node.lineno)
    return hits


def _collect_begin_nested_calls(handler: ast.AsyncFunctionDef) -> list[int]:
    """Return line numbers of any ``session.begin_nested()`` call.

    KD-VENTA-01 forbids SAVEPOINT nesting -- the single-commit invariant
    is violated by any nested-transaction usage.
    """
    hits: list[int] = []
    for node in ast.walk(handler):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr != "begin_nested":
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "session"):
            continue
        hits.append(node.lineno)
    return hits


def _collect_savepoint_strings(handler: ast.AsyncFunctionDef) -> list[tuple[int, str]]:
    """Return string literals that look like ``SAVEPOINT`` / ``RELEASE SAVEPOINT``."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(handler):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            upper = node.value.upper().lstrip()
            if upper.startswith("SAVEPOINT") or "RELEASE SAVEPOINT" in upper:
                hits.append((node.lineno, node.value[:80]))
    return hits


# ---------------------------------------------------------------------------
# T6.1 -- KD-VENTA-01 single-commit + no nested-transaction
# ---------------------------------------------------------------------------


def test_venta_suscripcion_handler_invokes_session_commit_exactly_once() -> None:
    """T6.1 / KD-VENTA-01: ``venta_suscripcion`` commits exactly ONCE.

    Walks the AST of ``venta_suscripcion`` and counts
    ``await session.commit()`` invocations. There must be exactly one.
    The 9-table atomic sale (cliente + vehiculo + subscripcion + junction
    + optional cobro/FE) MUST commit in a single transaction.
    """
    tree = _parse(_HANDLER_FILE)
    handler = _handler_node(tree, "venta_suscripcion")
    hits = _collect_commit_lines(handler)
    assert len(hits) == 1, (
        f"KD-VENTA-01 violated: `venta_suscripcion` has "
        f"{len(hits)} `await session.commit()` calls (lines {hits}); "
        f"the 9-table atomic sale MUST commit atomically in "
        f"exactly one transaction."
    )


def test_venta_suscripcion_handler_has_no_begin_nested() -> None:
    """T6.1: ``venta_suscripcion`` MUST NOT call ``session.begin_nested()``.

    KD-VENTA-01 forbids SAVEPOINT nesting; the handler commits in a
    single transaction.
    """
    tree = _parse(_HANDLER_FILE)
    handler = _handler_node(tree, "venta_suscripcion")
    hits = _collect_begin_nested_calls(handler)
    assert not hits, (
        f"KD-VENTA-01 violated: `venta_suscripcion` calls "
        f"session.begin_nested() at lines {hits}; nested transactions "
        f"break the single-commit invariant."
    )


def test_venta_suscripcion_handler_has_no_savepoint_strings() -> None:
    """T6.1: ``venta_suscripcion`` MUST NOT contain SAVEPOINT strings.

    Defense in depth: catches accidental raw ``SAVEPOINT`` SQL literals
    that would bypass the ``begin_nested`` AST check above.
    """
    tree = _parse(_HANDLER_FILE)
    handler = _handler_node(tree, "venta_suscripcion")
    hits = _collect_savepoint_strings(handler)
    assert not hits, (
        f"KD-VENTA-01 violated: `venta_suscripcion` contains "
        f"SAVEPOINT literals at lines {[line for line, _ in hits]}; "
        f"the single-commit invariant forbids nested transactions."
    )
