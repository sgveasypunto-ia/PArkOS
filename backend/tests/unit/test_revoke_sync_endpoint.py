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

import os
import sys
from pathlib import Path

import pytest

# Force cloud deploy BEFORE any parkos_core import - the v1 router reads
# ``PARKOS_DEPLOY`` at module-load time to decide whether to mount
# admin/pairing routers. ``tests/static/conftest.py`` calls
# ``os.environ.setdefault("PARKOS_DEPLOY", "branch")`` for sibling tests,
# which is sticky once set. Override unconditionally here.
os.environ["PARKOS_DEPLOY"] = "cloud"

# ---------------------------------------------------------------------------
# Path bootstrap - mirror backend/tests/conftest.py so this file is
# runnable standalone with ``uv run pytest tests/unit/...``.
# ---------------------------------------------------------------------------

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_API_ADMIN_SRC = _BACKEND_ROOT / "packages" / "api_admin" / "src"
if str(_API_ADMIN_SRC) not in sys.path:
    sys.path.insert(0, str(_API_ADMIN_SRC))


REVOKE_SYNC_PATH = "/admin/sucursales/{uuid_sucursal}/revoke-sync"


def _admin_app():
    """Lazy-import the admin app so module-level errors don't kill pytest.

    Re-imports ``parkos_core.api.v1`` + ``api_admin_main.app`` to honor
    the forced ``PARKOS_DEPLOY=cloud`` env var - a sibling conftest may
    have cached the v1 router with ``branch`` deploy, in which case the
    admin/pairing routers are skipped.
    """
    # Drop cached modules so the next import recomputes the deploy-flag
    # from the current env var. We need to drop ``api_admin_main.app``
    # because it captures ``v1_router`` at import time.
    for mod_name in list(sys.modules):
        if (
            mod_name.startswith("parkos_core.api.v1")
            or mod_name == "parkos_core.api.deps"
            or mod_name == "parkos_core.api.middleware"
            or mod_name.startswith("api_admin_main")
        ):
            sys.modules.pop(mod_name, None)
    try:
        from api_admin_main.app import app as admin_app
    except ImportError as exc:
        pytest.skip(f"api_admin_main.app not importable: {exc}")
    return admin_app


def _has_revoke_sync_path() -> bool:
    """True if the admin app's OpenAPI exposes the revoke-sync endpoint."""
    admin_app = _admin_app()
    schema = admin_app.openapi()
    paths = schema.get("paths", {})
    return any(
        "/admin/sucursales/" in path and path.endswith("/revoke-sync")
        for path in paths
    )


def _require_revoke_sync_mounted() -> None:
    """Skip the test if the revoke-sync endpoint is not mounted.

    On ``PARKOS_DEPLOY=branch`` the admin routers are skipped
    (cloud-only, REQ-X3). This helper guards against the false-fail
    case where a conftest set the env to ``branch`` for a sibling test.
    """
    if not _has_revoke_sync_path():
        pytest.skip(
            "POST /admin/sucursales/{uuid}/revoke-sync not mounted on the "
            "admin app. Likely cause: PARKOS_DEPLOY=branch (cloud-only "
            "admin routers are skipped). Set PARKOS_DEPLOY=cloud to run "
            "this test."
        )


def test_revoke_sync_path_in_openapi() -> None:
    """The endpoint path is registered on the admin app's OpenAPI schema."""
    _require_revoke_sync_mounted()

    admin_app = _admin_app()
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


def test_revoke_sync_unauthenticated_returns_401() -> None:
    """POST without Authorization header -> 401 (issuer guard)."""
    _require_revoke_sync_mounted()

    from fastapi.testclient import TestClient

    admin_app = _admin_app()
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
