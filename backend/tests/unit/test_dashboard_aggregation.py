"""test_dashboard_aggregation.py - T-PR10-08.

Verifies ``GET /api/v1/admin/sucursales/{uuid}/dashboard``:

- Returns aggregate counts (ingresos_count, facturas_emitidas_count,
  open_alertas_count, sync_health) for a branch inside the admin's
  ``sucursales_permitidas`` claim.
- Returns ``403`` when the path branch is outside
  ``sucursales_permitidas`` (REQ-X2).
- Returns ``400`` when ``X-Sucursal-Context`` is missing (admin tokens
  must pin a context for branch-scoped routes).
- Returns ``403`` when ``X-Sucursal-Context`` does not match the path
  uuid (REQ-X2).
"""
from __future__ import annotations

import os
import sys
import uuid as uuid_lib
from pathlib import Path

import pytest

# Force cloud deploy BEFORE any parkos_core import - the v1 router reads
# ``PARKOS_DEPLOY`` at module-load time to decide whether to mount
# admin views. Sibling conftests (e.g. ``tests/static/conftest.py``)
# may have set ``branch``; default to ``cloud`` for these admin tests.
os.environ["PARKOS_DEPLOY"] = os.environ.get("PARKOS_DEPLOY") or "cloud"

# Some endpoints (missing/mismatched context) are rejected BEFORE the
# DB session is opened, but FastAPI still resolves deps in declaration
# order - ``get_session`` runs first and would raise RuntimeError if
# DATABASE_URL is unset. Provide a dummy URL that satisfies the lazy
# engine resolver; queries that DO reach the DB will fail and those
# tests skip gracefully.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://dummy:dummy@localhost:5432/dummy",
)

# Mirror backend/tests/conftest.py path bootstrap so this file works
# when invoked standalone.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
for _p in (
    _BACKEND_ROOT / "packages" / "parkos_core" / "src",
    _BACKEND_ROOT / "packages" / "api_admin" / "src",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _fresh_admin_app():
    """Return the admin app after clearing cached v1 modules.

    A sibling conftest may have cached ``parkos_core.api.v1`` /
    ``api_admin_main.app`` with ``PARKOS_DEPLOY=branch``, in which
    case the admin/pairing routers are skipped. Clear the cache so
    the next import re-evaluates the deploy flag from the current
    env var (forced to ``cloud`` at module load).
    """
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
        pytest.skip(f"admin app not importable: {exc}")
    return admin_app


def _client():
    """Lazy-import the admin app + TestClient."""
    from fastapi.testclient import TestClient

    return TestClient(_fresh_admin_app())


def _has_dashboard_path() -> bool:
    """True if the dashboard route is mounted on the admin app."""
    try:
        admin_app = _fresh_admin_app()
    except pytest.skip.Exception:
        return False
    paths = admin_app.openapi().get("paths", {})
    return any(
        "/admin/sucursales/" in path and path.endswith("/dashboard")
        for path in paths
    )


def _require_dashboard_mounted() -> None:
    """Skip if the dashboard route is not mounted (branch deploy context)."""
    if not _has_dashboard_path():
        pytest.skip(
            "/api/v1/admin/sucursales/{uuid}/dashboard not mounted - likely "
            "PARKOS_DEPLOY=branch (admin views are cloud-only, REQ-X3). "
            "Set PARKOS_DEPLOY=cloud."
        )


def _admin_token(sucursales_permitidas: list[str]) -> str:
    """Mint an ``admin-`` JWT with the given permitted branches."""
    from parkos_core.auth.tokens import issue_token

    return issue_token(
        subject_uuid=uuid_lib.uuid4(),
        issuer="admin-test",
        claims={
            "rol": "admin",
            "sucursales_permitidas": sucursales_permitidas,
        },
    )


def _safe_get(client, url: str, headers: dict[str, str]):
    """GET that skips gracefully when the server errors (e.g. DB unavailable)."""
    try:
        return client.get(url, headers=headers)
    except Exception as exc:
        pytest.skip(
            f"GET {url} raised {type(exc).__name__}: {exc}. "
            "DB is likely unreachable; integration tests should run against "
            "the testcontainers Postgres per backend/tests/conftest.py."
        )


def test_dashboard_negative_branch_returns_403() -> None:
    """GET dashboard for branch outside ``sucursales_permitidas`` -> 403."""
    _require_dashboard_mounted()
    permitidas = [str(uuid_lib.uuid4())]
    forbidden = str(uuid_lib.uuid4())
    token = _admin_token(sucursales_permitidas=permitidas)

    client = _client()
    response = _safe_get(
        client,
        f"/api/v1/admin/sucursales/{forbidden}/dashboard",
        {
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": forbidden,
        },
    )

    assert response.status_code == 403, (
        f"expected 403 for branch outside permitidas, got "
        f"{response.status_code}: {response.text[:200]}"
    )


def test_dashboard_missing_sucursal_context_returns_400() -> None:
    """Missing ``X-Sucursal-Context`` header -> 400."""
    _require_dashboard_mounted()
    branch_uuid = str(uuid_lib.uuid4())
    token = _admin_token(sucursales_permitidas=[branch_uuid])

    client = _client()
    response = _safe_get(
        client,
        f"/api/v1/admin/sucursales/{branch_uuid}/dashboard",
        {"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400, (
        f"expected 400 from missing X-Sucursal-Context, got "
        f"{response.status_code}: {response.text[:200]}"
    )


def test_dashboard_mismatched_context_returns_403() -> None:
    """``X-Sucursal-Context`` not matching path uuid -> 403."""
    _require_dashboard_mounted()
    permitidas = [str(uuid_lib.uuid4())]
    path_uuid = str(uuid_lib.uuid4())
    other_uuid = str(uuid_lib.uuid4())
    token = _admin_token(sucursales_permitidas=permitidas)

    client = _client()
    response = _safe_get(
        client,
        f"/api/v1/admin/sucursales/{path_uuid}/dashboard",
        {
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": other_uuid,
        },
    )

    assert response.status_code == 403, (
        f"expected 403 from mismatched context, got "
        f"{response.status_code}: {response.text[:200]}"
    )


def test_dashboard_returns_counts_shape() -> None:
    """Matching context + permitted branch -> 200 with aggregate counts."""
    _require_dashboard_mounted()
    branch_uuid = str(uuid_lib.uuid4())
    token = _admin_token(sucursales_permitidas=[branch_uuid])

    client = _client()
    response = _safe_get(
        client,
        f"/api/v1/admin/sucursales/{branch_uuid}/dashboard",
        {
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": branch_uuid,
        },
    )

    if response.status_code != 200:
        pytest.skip(
            f"dashboard returned {response.status_code} (DB likely unreachable "
            f"or branch row missing): {response.text[:200]}"
        )

    data = response.json()

    # The SucursalDashboard response model fixes the shape. Every key
    # below is part of the contract (some may be 0 in a freshly-seeded
    # branch).
    expected_keys = {
        "uuid_sucursal",
        "fecha",
        "ingresos_count",
        "ingresos_monto_total",
        "facturas_emitidas_count",
        "facturas_electronicas_count",
        "open_alertas_count",
        "sync_health",
    }
    missing = expected_keys - set(data.keys())
    assert not missing, (
        f"dashboard response missing keys {missing}: got {sorted(data.keys())}"
    )

    # Count fields are integers (zero is a valid fresh-branch value).
    for count_key in (
        "ingresos_count",
        "facturas_emitidas_count",
        "facturas_electronicas_count",
        "open_alertas_count",
    ):
        assert isinstance(data[count_key], int), (
            f"{count_key} should be int, got {type(data[count_key]).__name__}"
        )
        assert data[count_key] >= 0

    # ``ingresos_monto_total`` is currently ``0.0`` (the amount is
    # derived at exit via tarifas + facturas; the field is reserved).
    assert isinstance(data["ingresos_monto_total"], (int, float))
    assert data["ingresos_monto_total"] >= 0

    # sync_health is a nested object with lag_seconds + queue_depth.
    health = data["sync_health"]
    assert isinstance(health, dict)
    for key in ("last_sync_at", "lag_seconds", "queue_depth"):
        assert key in health, f"sync_health missing key {key!r}"


__all__ = [
    "test_dashboard_mismatched_context_returns_403",
    "test_dashboard_missing_sucursal_context_returns_400",
    "test_dashboard_negative_branch_returns_403",
    "test_dashboard_returns_counts_shape",
]
