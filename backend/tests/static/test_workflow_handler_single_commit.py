"""HU-F1.11 / T7.3 — KD-TKT-01 single-commit AST walks.

T7.3: ``create_reimpresion_ticket`` and ``anular_reimpresion_ticket``
       MUST contain exactly ONE ``await session.commit()`` call.
       KD-TKT-01 single-commit invariant (mirror of F1.10 KD-FE-01).

Both handlers MUST also AVOID:
  - ``session.begin_nested()`` (no SAVEPOINT, KD-TKT-01)
  - String literals starting with ``SAVEPOINT`` or ``RELEASE SAVEPOINT``
    (defense in depth; catches accidental nested-transaction usage).

Pattern: parse the source file with ``ast.parse``, walk every AST node
inside the two handler bodies, count ``await session.commit()``
invocations, count nested-transaction calls, collect any SAVEPOINT
strings. Pure Python, no DB.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


_HANDLER_FILE = (
    _PARKOS_CORE_SRC
    / "parkos_core"
    / "api"
    / "v1"
    / "workflows_reimpresion.py"
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

    KD-TKT-01 forbids SAVEPOINT nesting — the single-commit invariant
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
# T7.3 — KD-TKT-01 single-commit + no nested-transaction on both handlers
# ---------------------------------------------------------------------------


def test_create_reimpresion_ticket_handler_invokes_session_commit_exactly_once() -> None:
    """T7.3 / KD-TKT-01: ``create_reimpresion_ticket`` commits exactly ONCE.

    Walks the AST of ``create_reimpresion_ticket`` and counts
    ``await session.commit()`` invocations. There must be exactly one.
    """
    tree = _parse(_HANDLER_FILE)
    handler = _handler_node(tree, "create_reimpresion_ticket")
    hits = _collect_commit_lines(handler)
    assert len(hits) == 1, (
        f"KD-TKT-01 violated: `create_reimpresion_ticket` has "
        f"{len(hits)} `await session.commit()` calls (lines {hits}); "
        f"the INSERT chain root + audit log MUST commit atomically in "
        f"exactly one transaction."
    )


def test_create_reimpresion_ticket_handler_has_no_begin_nested() -> None:
    """T7.3: ``create_reimpresion_ticket`` MUST NOT call ``session.begin_nested()``.

    KD-TKT-01 forbids SAVEPOINT nesting; the handler commits in a
    single transaction.
    """
    tree = _parse(_HANDLER_FILE)
    handler = _handler_node(tree, "create_reimpresion_ticket")
    hits = _collect_begin_nested_calls(handler)
    assert not hits, (
        f"KD-TKT-01 violated: `create_reimpresion_ticket` calls "
        f"session.begin_nested() at lines {hits}; nested transactions "
        f"break the single-commit invariant."
    )


def test_create_reimpresion_ticket_handler_has_no_savepoint_strings() -> None:
    """T7.3: ``create_reimpresion_ticket`` MUST NOT contain SAVEPOINT strings.

    Defense in depth: catches accidental raw ``SAVEPOINT`` SQL literals
    that would bypass the ``begin_nested`` AST check above.
    """
    tree = _parse(_HANDLER_FILE)
    handler = _handler_node(tree, "create_reimpresion_ticket")
    hits = _collect_savepoint_strings(handler)
    assert not hits, (
        f"KD-TKT-01 violated: `create_reimpresion_ticket` contains "
        f"SAVEPOINT literals at lines {[line for line, _ in hits]}; "
        f"the single-commit invariant forbids nested transactions."
    )


def test_anular_reimpresion_ticket_handler_invokes_session_commit_exactly_once() -> None:
    """T7.3 / KD-TKT-01: ``anular_reimpresion_ticket`` commits exactly ONCE.

    Walks the AST of ``anular_reimpresion_ticket`` and counts
    ``await session.commit()`` invocations. There must be exactly one.
    """
    tree = _parse(_HANDLER_FILE)
    handler = _handler_node(tree, "anular_reimpresion_ticket")
    hits = _collect_commit_lines(handler)
    assert len(hits) == 1, (
        f"KD-TKT-01 violated: `anular_reimpresion_ticket` has "
        f"{len(hits)} `await session.commit()` calls (lines {hits}); "
        f"the INSERT new-rechazada row MUST commit atomically in "
        f"exactly one transaction."
    )


def test_anular_reimpresion_ticket_handler_has_no_begin_nested() -> None:
    """T7.3: ``anular_reimpresion_ticket`` MUST NOT call ``session.begin_nested()``."""
    tree = _parse(_HANDLER_FILE)
    handler = _handler_node(tree, "anular_reimpresion_ticket")
    hits = _collect_begin_nested_calls(handler)
    assert not hits, (
        f"KD-TKT-01 violated: `anular_reimpresion_ticket` calls "
        f"session.begin_nested() at lines {hits}; nested transactions "
        f"break the single-commit invariant."
    )


def test_anular_reimpresion_ticket_handler_has_no_savepoint_strings() -> None:
    """T7.3: ``anular_reimpresion_ticket`` MUST NOT contain SAVEPOINT strings."""
    tree = _parse(_HANDLER_FILE)
    handler = _handler_node(tree, "anular_reimpresion_ticket")
    hits = _collect_savepoint_strings(handler)
    assert not hits, (
        f"KD-TKT-01 violated: `anular_reimpresion_ticket` contains "
        f"SAVEPOINT literals at lines {[line for line, _ in hits]}; "
        f"the single-commit invariant forbids nested transactions."
    )
