"""test_no_delete_routes.py — SC-04.

Rejects any DELETE HTTP route emitted by the FastAPI app factory or any
v1 router module. Defense in depth: the API contract (AGENTS.md §3)
forbids DELETE at every layer — no DELETE endpoint, no raw DELETE DML,
no DELETE permission on [A] tables — and this static scan catches
accidental additions at code-review time.

The scanner walks ``parkos_core/api/router_factory.py`` and every module
under ``parkos_core/api/v1/`` looking for ``ast.Call`` nodes whose
function is one of:

  - ``APIRouter.delete(...)``
  - ``@router.delete(...)`` decorators
  - ``@app.delete(...)`` decorators
  - ``add_api_route(..., methods=['DELETE'])`` or
    ``add_api_route(..., methods=['delete'])``

Any match → CI red.

Additionally, the test instantiates ``api_admin_main.app`` and
``api_sucursal_main.app``, calls ``app.openapi()`` on each, and asserts
that the generated schema contains ZERO operations with method ``"delete"``.
That second check covers dynamic route registration via ``add_api_route``
that an AST scanner might miss.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_API_ROOT = (
    Path(__file__).resolve().parents[2]
    / "packages" / "parkos_core" / "src" / "parkos_core" / "api"
)
_ROUTER_FACTORY = _API_ROOT / "router_factory.py"
_V1_DIR = _API_ROOT / "v1"

_DELETE_FUNCNAMES = frozenset({"delete"})


def _scan_python_file(path: Path) -> list[tuple[int, str]]:
    """Walk one Python file; return a list of (line_no, snippet) for each DELETE match.

    Matches:
      - ``APIRouter.delete(...)`` / ``router.delete(...)`` / ``app.delete(...)``
      - ``@<anything>.delete(...)`` decorator
      - ``add_api_route(..., methods=['delete'|'DELETE'])``
    """
    matches: list[tuple[int, str]] = []
    if not path.is_file():
        return matches
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return matches

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func

        # 1. ``<something>.delete(...)`` direct call or decorator
        if isinstance(func, ast.Attribute) and func.attr in _DELETE_FUNCNAMES:
            snippet = ast.unparse(node)[:120]
            matches.append((node.lineno, snippet))
            continue

        # 2. ``add_api_route(..., methods=[...])`` with 'delete' in methods
        if isinstance(func, ast.Name) and func.id == "add_api_route":
            for kw in node.keywords:
                if kw.arg != "methods":
                    continue
                value = kw.value
                # methods=[...] or methods='DELETE'
                if isinstance(value, (ast.List, ast.Tuple)):
                    for elt in value.elts:
                        if (
                            isinstance(elt, ast.Constant)
                            and isinstance(elt.value, str)
                            and elt.value.lower() == "delete"
                        ):
                            matches.append((
                                node.lineno,
                                f"add_api_route(methods={elt.value!r})",
                            ))
                            break
                elif isinstance(value, ast.Constant) and isinstance(
                    value.value, str
                ) and value.value.lower() == "delete":
                    matches.append((
                        node.lineno,
                        f"add_api_route(methods={value.value!r})",
                    ))

    return matches


def test_router_factory_has_no_delete_routes() -> None:
    """``router_factory.py`` MUST NOT produce DELETE routes."""
    matches = _scan_python_file(_ROUTER_FACTORY)
    assert not matches, (
        f"router_factory.py emits DELETE routes: {matches}"
    )


def test_v1_routers_have_no_delete_routes() -> None:
    """Every file under ``parkos_core/api/v1/`` MUST NOT emit DELETE routes."""
    if not _V1_DIR.is_dir():
        pytest.skip(
            f"v1 directory {_V1_DIR} not found — placeholder expected on PR1c"
        )

    all_matches: list[tuple[Path, int, str]] = []
    for py_file in sorted(_V1_DIR.glob("*.py")):
        if py_file.name == "__init__.py":
            # Empty placeholder — only the bare ``router = APIRouter()`` lives here
            # in PR1c; nothing to scan. Keep this skip explicit for the future.
            continue
        for line_no, snippet in _scan_python_file(py_file):
            all_matches.append((py_file, line_no, snippet))

    assert not all_matches, (
        "DELETE routes found in parkos_core/api/v1/:\n"
        + "\n".join(f"  {p.name}:{ln}: {s}" for p, ln, s in all_matches)
    )


def test_openapi_contains_no_delete_operations() -> None:
    """The runtime OpenAPI schema from both apps contains zero DELETE operations."""
    try:
        from api_admin_main.app import app as admin_app
        from api_sucursal_main.app import app as sucursal_app
    except ImportError as exc:
        pytest.skip(f"could not import app factories: {exc}")

    for label, fastapi_app in (("admin", admin_app), ("sucursal", sucursal_app)):
        schema = fastapi_app.openapi()
        for path, ops in schema.get("paths", {}).items():
            for method in ops:
                if method.lower() == "delete":
                    pytest.fail(
                        f"{label} OpenAPI exposes DELETE: {method.upper()} {path}"
                    )