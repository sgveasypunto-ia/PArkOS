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


def _collect_session_commit_lines(
    source: str, function_name: str | None = None
) -> list[int]:
    """Return the 1-indexed line numbers of every ``await session.commit()``.

    When ``function_name`` is given, only commits inside that top-level
    function are counted (``facturacion.py`` hosts several handlers, each
    owning its own single commit).
    """
    tree = ast.parse(source)
    scope: ast.AST = tree
    if function_name is not None:
        scope = next(
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == function_name
        )
    hits: list[int] = []
    for node in ast.walk(scope):
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

    Walks the AST of ``create_factura_electronica`` in
    ``api/v1/facturacion.py`` and counts ``await session.commit()``
    invocations. There must be exactly one.
    """
    source = _HANDLER_FILE.read_text(encoding="utf-8")
    hits = _collect_session_commit_lines(source, "create_factura_electronica")
    assert len(hits) == 1, (
        f"KD-FE-01 violated: found {len(hits)} `await session.commit()` "
        f"calls in create_factura_electronica of {_HANDLER_FILE.name} "
        f"(lines {hits}); the FE row + initial envio_dian row MUST commit "
        f"atomically in a single transaction."
    )


def test_create_factura_electronica_commit_is_inside_create_handler() -> None:
    """KD-FE-01: the read handler of the FE resource never commits.

    ``get_factura_electronica`` is a pure GET (view JOIN); a commit there
    would mean a write slipped into the read path. (Other handlers in the
    module -- pago, servicio, reintentar -- own their own single commit and
    are pinned by their own tests.)
    """
    source = _HANDLER_FILE.read_text(encoding="utf-8")
    assert _collect_session_commit_lines(source, "get_factura_electronica") == []
    assert len(_collect_session_commit_lines(source, "retry_envio_dian")) == 1
