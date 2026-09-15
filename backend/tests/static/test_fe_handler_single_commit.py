"""HU-F1.10 / T4.5 — AST walk enforcing KD-FE-01 single-commit invariant.

The handler MUST contain exactly ONE ``await session.commit()`` call.
Adding a second commit (whether inside the create chain or accidentally
introduced by a future edit) breaks KD-FE-01: the FE row + initial envio
row are no longer atomic, and a network hiccup between commits can leave
a half-written FE.

Pattern: parse the source file with ``ast.parse``, walk every
``ast.Await`` node, count ``session.commit()`` invocations. Assert
``count == 1`` with a diagnostic message naming the line numbers.

The walk is intentionally permissive about *what calls commit* — it only
locks the count. Tests pinning the actual line number would be brittle;
the diagnostic message names the offending lines for the developer.
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
    / "facturacion.py"
)


def _collect_session_commit_lines(source: str) -> list[int]:
    """Return the 1-indexed line numbers of every ``await session.commit()``."""
    tree = ast.parse(source)
    hits: list[int] = []
    for node in ast.walk(tree):
        # Look for ``Await(value=Call(func=Attribute(value=Name('session'),
        # attr='commit')))``
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


def test_create_factura_electronica_has_exactly_one_session_commit() -> None:
    """KD-FE-01: the handler commits exactly ONCE.

    Walks the AST of ``api/v1/facturacion.py`` and counts
    ``await session.commit()`` invocations. There must be exactly one.
    """
    source = _HANDLER_FILE.read_text(encoding="utf-8")
    hits = _collect_session_commit_lines(source)
    assert len(hits) == 1, (
        f"KD-FE-01 violated: found {len(hits)} `await session.commit()` "
        f"calls in {_HANDLER_FILE.name} (lines {hits}); the FE row + initial "
        f"envio_dian row MUST commit atomically in a single transaction."
    )


def test_create_factura_electronica_commit_is_inside_create_handler() -> None:
    """KD-FE-01: the single commit must live inside ``create_factura_electronica``.

    Specifically, no other top-level coroutine in the module may
    accidentally invoke ``await session.commit()`` outside the create
    handler (those would belong to the GET or /reintentar handlers).
    """
    source = _HANDLER_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Build a map of function name → first commit line inside it.
    func_first_commit: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            inner_hits: list[int] = []
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Await)
                    and isinstance(child.value, ast.Call)
                    and isinstance(child.value.func, ast.Attribute)
                    and isinstance(child.value.func.value, ast.Name)
                    and child.value.func.value.id == "session"
                    and child.value.func.attr == "commit"
                ):
                    inner_hits.append(child.lineno)
            if inner_hits:
                func_first_commit[node.name] = min(inner_hits)

    create_hits = func_first_commit.get("create_factura_electronica", [])
    assert len(create_hits) >= 1, (
        "KD-FE-01 violated: `create_factura_electronica` has no "
        "`await session.commit()`; the FE row + envio row would never "
        "materialize."
    )
    # No other top-level coroutine in this module may have a commit yet.
    other_commit_funcs = {
        name: line
        for name, line in func_first_commit.items()
        if name != "create_factura_electronica"
    }
    assert not other_commit_funcs, (
        f"KD-FE-01 violated: only `create_factura_electronica` may own a "
        f"`await session.commit()`. Found commits inside: "
        f"{other_commit_funcs}"
    )
