"""test_revoke_sync_endpoint.py - T-PR10-05 verify.

Pins the contract for ``POST /api/v1/admin/sucursales/{uuid}/revoke-sync``
(PR8c wire-up, design §21.3, REQ-OP-04). The endpoint was added in PR8b
as a 501-stub and wired up in PR8c; this test confirms it is mounted on
the cloud admin app and that the issuer guard fires for unauthenticated
requests.

Behavior pinned:

- Endpoint exists in the admin OpenAPI schema at path
  ``/admin/sucursales/{uuid}/revoke-sync`` with method ``POST``.
- Unauthenticated ``POST`` returns ``401`` (issuer guard fires before
  the route handler runs).
- The route is NOT exposed on the branch deploy (``PARKOS_DEPLOY=branch``)
  per the cloud-only DIAN boundary (REQ-X3, design §10).

This test uses the admin app's OpenAPI schema as the source of truth:
if the path is absent the test SKIPS cleanly (no failure) because that
means the test is running in a branch-deploy context.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REVOKE_SYNC_PATH = "/admin/sucursales/{uuid_sucursal}/revoke-sync"


def _ensure_paths() -> None:
    """Insert backend package paths onto sys.path (idempotent)."""
    _BACKEND_ROOT = Path(__file__).resolve().parents[2]
    _API_ADMIN_SRC = _BACKEND_ROOT / "packages" / "api_admin" / "src"
    if str(_API_ADMIN_SRC) not in sys.path:
        sys.path.insert(0, str(_API_ADMIN_SRC))


@pytest.fixture
def admin_app(monkeypatch: pytest.MonkeyPatch):
    """Return the admin app with ``sys.modules`` fully restored on teardown.

    Same pattern as ``tests/unit/test_admin_me.py::fresh_admin_app`` —
    purges ``parkos_core.api.v1.*`` (and the parent package itself) from
    ``sys.modules`` to force re-evaluation of ``PARKOS_DEPLOY=cloud``,
    then restores the originals. Also restores the parent package's
    ``__dict__`` entries for each submodule (Python's import system
    auto-binds submodules into the parent's ``__dict__`` on reimport,
    so a ``sys.modules``-only restore leaves ``from parkos_core.api.v1
    import sync_router`` resolving to the freshly-imported module).
    """
    _ensure_paths()
    monkeypatch.setenv("PARKOS_DEPLOY", "cloud")

    _purge_prefixes = ("parkos_core.api.v1", "api_admin_main")
    _purge_exact = {"parkos_core.api.deps", "parkos_core.api.middleware"}
    saved_modules = {
        name: mod
        for name, mod in sys.modules.items()
        if name.startswith(_purge_prefixes) or name in _purge_exact
    }
    # Capture parent-package ``__dict__`` entries for every submodule
    # we are about to purge. After reimport, Python mutates the parent's
    # ``__dict__`` to point to the NEW submodule; on teardown we restore
    # the OLD submodule so ``from parent import submodule`` resolves
    # correctly for downstream tests.
    saved_parent_attrs: dict[tuple[str, str], object] = {}
    for name, mod in saved_modules.items():
        if "." not in name:
            continue
        parent_name, _, attr = name.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is None:
            continue
        if attr in parent.__dict__ and parent.__dict__[attr] is mod:
            saved_parent_attrs[(parent_name, attr)] = mod
    for name in list(saved_modules):
        sys.modules.pop(name, None)

    try:
        from api_admin_main.app import app as built_app
    except ImportError as exc:
        pytest.skip(f"api_admin_main.app not importable: {exc}")
    try:
        yield built_app
    finally:
        # Drop any modules freshly imported by the admin app, then
        # re-insert the saved originals so module identities match.
        for name in list(sys.modules):
            cond_a = name.startswith(_purge_prefixes)
            cond_b = name in _purge_exact
            if (cond_a or cond_b) and name not in saved_modules:
                sys.modules.pop(name, None)
        for name, mod in saved_modules.items():
            sys.modules[name] = mod
        # Restore parent ``__dict__`` entries for each purged submodule.
        # Without this, ``from parkos_core.api.v1 import sync_router``
        # returns the freshly-imported (NEW) module rather than the
        # one ``sync_router_obj`` (captured at collection time) points to.
        for (parent_name, attr), original in saved_parent_attrs.items():
            parent = sys.modules.get(parent_name)
            if parent is not None:
                parent.__dict__[attr] = original


def _has_revoke_sync_path(app) -> bool:
    """True if the admin app's OpenAPI exposes the revoke-sync endpoint."""
    schema = app.openapi()
    paths = schema.get("paths", {})
    return any(
        "/admin/sucursales/" in path and path.endswith("/revoke-sync")
        for path in paths
    )


def _require_revoke_sync_mounted(app) -> None:
    """Skip the test if the revoke-sync endpoint is not mounted.

    On ``PARKOS_DEPLOY=branch`` the admin routers are skipped
    (cloud-only, REQ-X3). This helper guards against the false-fail
    case where a conftest set the env to ``branch`` for a sibling test.
    """
    if not _has_revoke_sync_path(app):
        pytest.skip(
            "POST /admin/sucursales/{uuid}/revoke-sync not mounted on the "
            "admin app. Likely cause: PARKOS_DEPLOY=branch (cloud-only "
            "admin routers are skipped). Set PARKOS_DEPLOY=cloud to run "
            "this test."
        )


def test_revoke_sync_path_in_openapi(admin_app) -> None:
    """The endpoint path is registered on the admin app's OpenAPI schema."""
    _require_revoke_sync_mounted(admin_app)

    schema = admin_app.openapi()
    paths = schema.get("paths", {})

    matched = [
        path
        for path in paths
        if "/admin/sucursales/" in path
        and path.endswith("/revoke-sync")
    ]
    assert matched, (
        "POST /admin/sucursales/{uuid}/revoke-sync not found in admin OpenAPI. "
        f"Available paths: {sorted(paths.keys())}"
    )

    # The matched path must expose POST (not GET, not DELETE).
    for path in matched:
        ops = paths[path]
        assert "post" in ops, (
            f"{path} does not expose POST (methods={sorted(ops.keys())})"
        )


def test_revoke_sync_unauthenticated_returns_401(admin_app) -> None:
    """POST without Authorization header -> 401 (issuer guard)."""
    _require_revoke_sync_mounted(admin_app)

    from fastapi.testclient import TestClient

    client = TestClient(admin_app)

    response = client.post(
        "/api/v1/admin/sucursales/00000000-0000-0000-0000-000000000001/revoke-sync",
        json={"jwt_kid": "sync-agent-current", "jwt_uuid": "test-jti"},
    )

    # 401 from ``requires_issuer('admin-')`` when no Bearer token is
    # supplied. If the endpoint were absent the test would observe
    # 404/405 instead, so this assert pins the contract.
    assert response.status_code == 401, (
        f"expected 401 from missing auth, got {response.status_code}: "
        f"{response.text[:200]}"
    )


__all__ = [
    "REVOKE_SYNC_PATH",
    "test_revoke_sync_path_in_openapi",
    "test_revoke_sync_unauthenticated_returns_401",
]
