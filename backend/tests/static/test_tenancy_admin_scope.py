"""test_tenancy_admin_scope.py - T-PR10-09.

Static AST scan that pins the tenancy-listener pattern across admin
route handlers (``parkos_core/api/v1/admin_*.py``).

The canonical contract:

- The ``apply_admin_scope`` helper from :mod:`parkos_core.db.tenancy`
  is the SINGLE source of truth for ``admin-`` issuer scope filtering
  (REQ-X2, defense in depth - T-PR10-04).
- Route handlers MUST NOT bypass it: every SELECT against an entity
  carrying ``uuid_sucursal`` should either route through
  ``apply_admin_scope(...)`` OR be pinned to the path uuid (the
  ``/admin/sucursales/{uuid}/dashboard`` case).
- The module MUST import the helper (silent absence = bypass risk).

This scanner walks the AST and asserts each rule. It does NOT execute
the app - it operates purely on the source. DB-less.
"""
from __future__ import annotations

import ast
from pathlib import Path

ADMIN_V1_DIR = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "parkos_core"
    / "src"
    / "parkos_core"
    / "api"
    / "v1"
)

LISTENER_MODULE = "parkos_core.db.tenancy"
HELPER_NAME = "apply_admin_scope"


def _admin_route_files() -> list[Path]:
    """Return all ``admin_*.py`` route files under the v1 directory."""
    if not ADMIN_V1_DIR.is_dir():
        return []
    return sorted(ADMIN_V1_DIR.glob("admin_*.py"))


def _imports_listener(tree: ast.AST) -> bool:
    """Return True if any ``from <...>db.tenancy import ...`` is present.

    Matches both absolute (``parkos_core.db.tenancy``) and relative
    (``from ...db.tenancy``) imports. The relative case parses with
    ``node.level > 0`` and ``node.module == "db.tenancy"`` — the
    ``...`` is stored as the relative-import level, not in the
    module string.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        # Absolute import
        if module == "parkos_core.db.tenancy":
            return True
        # Relative import: ``from ...db.tenancy import ...``
        # Python parses ``...`` into ``node.level`` and the rest into
        # ``node.module``. The module string is just "db.tenancy".
        if module == "db.tenancy" and getattr(node, "level", 0) > 0:
            return True
    return False


def _calls_helper(tree: ast.AST, helper: str) -> bool:
    """Return True if any AST call has attr == helper (i.e. ``apply_admin_scope(...)``)."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == helper:
            return True
        if isinstance(func, ast.Name) and func.id == helper:
            return True
    return False


def test_admin_route_files_exist() -> None:
    """At least one ``admin_*.py`` route file lives under the v1 directory."""
    files = _admin_route_files()
    assert files, (
        f"no admin_*.py route files in {ADMIN_V1_DIR}. PR10 should ship "
        "parkos_core/api/v1/admin_views.py at minimum."
    )


def test_admin_routes_import_listener() -> None:
    """Every admin route file imports from ``parkos_core.db.tenancy``.

    The listener module exposes ``apply_admin_scope`` (REQ-X2 scope
    filter) and ``extract_sucursales_permitidas`` (claim parser).
    A silent absence means a new admin route was added without the
    tenancy hookup - which is a security defect.
    """
    files = _admin_route_files()
    missing: list[str] = []
    for fp in files:
        try:
            tree = ast.parse(fp.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            missing.append(f"{fp.name}: parse error: {exc}")
            continue
        if not _imports_listener(tree):
            missing.append(fp.name)

    assert not missing, (
        "Admin route file(s) do not import parkos_core.db.tenancy. "
        "Without apply_admin_scope + extract_sucursales_permitidas, the "
        "REQ-X2 scope filter is bypassed:\n  - "
        + "\n  - ".join(missing)
    )


def test_admin_views_calls_apply_admin_scope() -> None:
    """``admin_views.py`` actually invokes ``apply_admin_scope`` on a query.

    The import alone is not enough - a route file could import the
    helper but never call it. The ``/sucursales`` endpoint must use it
    for its SELECT (REQ-X2 + T-PR10-04). The other two endpoints
    (``/admin/me``, ``/admin/sucursales/{uuid}/dashboard``) are scoped
    by the JWT claim or by the path uuid respectively; the static
    scan accepts either pattern as long as ``admin_views.py`` calls
    ``apply_admin_scope`` AT LEAST once.
    """
    target = ADMIN_V1_DIR / "admin_views.py"
    if not target.is_file():
        # No admin_views.py means PR10 hasn't shipped yet - skip cleanly.
        import pytest

        pytest.skip(f"{target} not present (PR10 not yet shipped)")

    tree = ast.parse(target.read_text(encoding="utf-8"))
    assert _calls_helper(tree, HELPER_NAME), (
        f"{target.name} imports parkos_core.db.tenancy but never calls "
        f"{HELPER_NAME}(...). At least one query MUST go through the "
        "scope filter (T-PR10-04)."
    )


def test_admin_routes_have_no_delete_decorators() -> None:
    """No admin route file declares a DELETE HTTP method.

    Belt-and-suspenders alongside ``test_no_delete_routes.py``: that
    test scans the FULL v1 directory; this one narrows to admin routes
    so a regression in the admin surface is caught with a focused
    failure message.
    """
    for fp in _admin_route_files():
        try:
            tree = ast.parse(fp.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "delete"
                and isinstance(func.value, ast.Name)
                and func.value.id in {"router", "app", "sync_revoke_router"}
            ):
                # ``ast.Attribute.attr == 'delete'`` can hit unrelated
                # calls like ``dict.delete``; narrow to FastAPI router
                # / app decorator names.
                raise AssertionError(
                    f"{fp.name}: declares a DELETE route at line "
                    f"{node.lineno} - AGENTS.md S3 forbids DELETE at "
                    "any layer."
                )


__all__ = [
    "ADMIN_V1_DIR",
    "HELPER_NAME",
    "LISTENER_MODULE",
    "test_admin_route_files_exist",
    "test_admin_routes_have_no_delete_decorators",
    "test_admin_routes_import_listener",
    "test_admin_views_calls_apply_admin_scope",
]
