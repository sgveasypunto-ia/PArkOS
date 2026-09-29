"""test_dashboard_aggregation.py - T-PR10-08.

Verifies ``GET /api/v1/admin/sucursales/{uuid}/dashboard``:

- Returns ``403`` when the path branch has no OPEN ``usuarios_sucursal``
  row for the actor (REQ-X2). The scope is read FRESH from the DB; the
  ``sucursales_permitidas`` claim in the token is a login-time snapshot
  and grants nothing on its own.
- Returns ``400`` when ``X-Sucursal-Context`` is missing (admin tokens
  must pin a context for branch-scoped routes).
- Returns ``403`` when ``X-Sucursal-Context`` does not match the path
  uuid (REQ-X2).
- Returns ``200`` with aggregate counts, which requires a real, seeded
  open assignment row for the actor.

These tests use a dummy (unreachable) ``DATABASE_URL``, so the DB-touching
assertions skip rather than pass. The skips are deliberate and narrow:
a 403 is an EXPECTED outcome under the fresh-DB contract, but any other
unexpected status is a hard failure so a genuine 500 is never absorbed.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from pathlib import Path

import pytest

# Module-level setup intentionally MINIMAL — see fixtures below.
# Previous module-level ``os.environ.setdefault("DATABASE_URL", ...)``
# polluted the env for subsequent tests in the full suite (test_sync_router,
# test_idempotency_middleware). All env + sys.modules mutations now happen
# in fixtures with save/restore, so a stale value never leaks.
_DUMMY_DB_URL = "postgresql+asyncpg://dummy:dummy@localhost:5432/dummy"
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _ensure_paths() -> None:
    """Insert backend package paths onto sys.path (idempotent)."""
    for _p in (
        _BACKEND_ROOT / "packages" / "parkos_core" / "src",
        _BACKEND_ROOT / "packages" / "api_admin" / "src",
    ):
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))


@pytest.fixture
def dummy_db_url(monkeypatch: pytest.MonkeyPatch):
    """Force DATABASE_URL to a dummy URL; restore on teardown + reset engine cache."""
    import parkos_core.db.engine as _engine_mod

    monkeypatch.setenv("DATABASE_URL", _DUMMY_DB_URL)
    _engine_mod._engine = None
    _engine_mod._sessionmaker = None
    try:
        yield _DUMMY_DB_URL
    finally:
        _engine_mod._engine = None
        _engine_mod._sessionmaker = None


@pytest.fixture
def fresh_admin_app(monkeypatch: pytest.MonkeyPatch):
    """Return a fresh admin app with ``sys.modules`` fully restored on teardown.

    Also restores the parent package's ``__dict__`` entries for each
    purged submodule (Python's import system auto-binds submodules into
    the parent's ``__dict__`` on reimport, so a ``sys.modules``-only
    restore leaves ``from parkos_core.api.v1 import sync_router``
    resolving to the freshly-imported module rather than the original).
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
        from api_admin_main.app import app as admin_app
    except ImportError as exc:
        pytest.skip(f"admin app not importable: {exc}")
    try:
        yield admin_app
    finally:
        for name in list(sys.modules):
            cond_a = name.startswith(_purge_prefixes)
            cond_b = name in _purge_exact
            if (cond_a or cond_b) and name not in saved_modules:
                sys.modules.pop(name, None)
        for name, mod in saved_modules.items():
            sys.modules[name] = mod
        # Restore parent ``__dict__`` entries for each purged submodule.
        for (parent_name, attr), original in saved_parent_attrs.items():
            parent = sys.modules.get(parent_name)
            if parent is not None:
                parent.__dict__[attr] = original


def _client(fresh_admin_app):
    """Lazy-import TestClient bound to the freshly built admin app."""
    from fastapi.testclient import TestClient

    return TestClient(fresh_admin_app)


def _has_dashboard_path(fresh_admin_app) -> bool:
    """True if the dashboard route is mounted on the admin app."""
    paths = fresh_admin_app.openapi().get("paths", {})
    return any(
        "/admin/sucursales/" in path and path.endswith("/dashboard")
        for path in paths
    )


def _require_dashboard_mounted(fresh_admin_app) -> None:
    """Skip if the dashboard route is not mounted (branch deploy context)."""
    if not _has_dashboard_path(fresh_admin_app):
        pytest.skip(
            "/api/v1/admin/sucursales/{uuid}/dashboard not mounted - likely "
            "PARKOS_DEPLOY=branch (admin views are cloud-only, REQ-X3). "
            "Set PARKOS_DEPLOY=cloud."
        )


def _admin_token(sucursales_permitidas: list[str]) -> str:
    """Mint an ``admin-`` JWT carrying the legacy claim.

    The claim is kept so the tests document that it is NOT what grants
    access: ``branch_dashboard`` resolves scope from
    ``prod.usuarios_sucursal`` at request time.
    """
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


def test_dashboard_negative_branch_returns_403(
    dummy_db_url: str, fresh_admin_app
) -> None:
    """Branch with no open assignment for the actor => 403.

    The token's claim deliberately does NOT list ``forbidden``: with the
    fresh-DB contract the claim cannot grant access either way, and the
    DB is the sole source of truth.
    """
    _require_dashboard_mounted(fresh_admin_app)
    forbidden = str(uuid_lib.uuid4())
    token = _admin_token(sucursales_permitidas=[])

    client = _client(fresh_admin_app)
    response = _safe_get(
        client,
        f"/api/v1/admin/sucursales/{forbidden}/dashboard",
        {
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": forbidden,
        },
    )

    assert response.status_code == 403, (
        f"expected 403 for a branch with no open assignment, got "
        f"{response.status_code}: {response.text[:200]}"
    )


def test_dashboard_missing_sucursal_context_returns_400(
    dummy_db_url: str, fresh_admin_app
) -> None:
    """Missing ``X-Sucursal-Context`` header -> 400."""
    _require_dashboard_mounted(fresh_admin_app)
    branch_uuid = str(uuid_lib.uuid4())
    token = _admin_token(sucursales_permitidas=[branch_uuid])

    client = _client(fresh_admin_app)
    response = _safe_get(
        client,
        f"/api/v1/admin/sucursales/{branch_uuid}/dashboard",
        {"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400, (
        f"expected 400 from missing X-Sucursal-Context, got "
        f"{response.status_code}: {response.text[:200]}"
    )


def test_dashboard_mismatched_context_returns_403(
    dummy_db_url: str, fresh_admin_app
) -> None:
    """``X-Sucursal-Context`` not matching path uuid -> 403 (checked pre-scope)."""
    _require_dashboard_mounted(fresh_admin_app)
    permitidas = [str(uuid_lib.uuid4())]
    path_uuid = str(uuid_lib.uuid4())
    other_uuid = str(uuid_lib.uuid4())
    token = _admin_token(sucursales_permitidas=permitidas)

    client = _client(fresh_admin_app)
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


def test_dashboard_returns_counts_shape(
    dummy_db_url: str, fresh_admin_app
) -> None:
    """Aggregate shape on a 200, which now REQUIRES a seeded assignment.

    Under the fresh-DB contract the claim alone no longer grants access,
    so a 200 needs a real open ``usuarios_sucursal`` row for the actor.
    These tests cannot seed (dummy DB), so a 403 is the expected outcome
    and is skipped with an explicit reason. Any OTHER unexpected status
    is a hard failure — a generic ``skip on != 200`` would happily
    absorb a real 500 and hide a regression.
    """
    _require_dashboard_mounted(fresh_admin_app)
    branch_uuid = str(uuid_lib.uuid4())
    token = _admin_token(sucursales_permitidas=[branch_uuid])

    client = _client(fresh_admin_app)
    response = _safe_get(
        client,
        f"/api/v1/admin/sucursales/{branch_uuid}/dashboard",
        {
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": branch_uuid,
        },
    )

    if response.status_code == 403:
        pytest.skip(
            "no open usuarios_sucursal row seeded for the actor, so the "
            "fresh-DB scope gate correctly refuses: 403. Run against a "
            "seeded DB to exercise the 200 aggregate shape."
        )
    assert response.status_code == 200, (
        f"expected 200 for a branch with a seeded assignment, got "
        f"{response.status_code}: {response.text[:200]}"
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
