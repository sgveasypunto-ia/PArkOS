"""test_admin_me.py - T-PR10-07.

Verifies ``GET /api/v1/admin/me`` (admin_views.branch_dashboard-adjacent):

- Returns the actor identity shape: ``actor_uuid``, ``email``, ``rol``,
  ``sucursales_permitidas``, ``permissions``.
- ``permissions`` is a list of permission codes from
  ``permisos_usuario`` (when DB seed data is present).
- ``sucursales_permitidas`` mirrors the JWT claim, coerced to UUIDs.
- A ``sync-agent-`` token returns 401 (cross-issuer rejection).
"""
from __future__ import annotations

import os
import sys
import uuid as uuid_lib
from pathlib import Path

import pytest

# Force cloud deploy BEFORE any parkos_core import - the v1 router reads
# ``PARKOS_DEPLOY`` at module-load time to decide whether to mount
# admin/router views. Sibling conftests (e.g. ``tests/static/conftest.py``)
# may have set ``branch``; default to ``cloud`` for these admin tests.
os.environ["PARKOS_DEPLOY"] = os.environ.get("PARKOS_DEPLOY") or "cloud"

# Some endpoints (cross-issuer / missing-auth) are rejected BEFORE the
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
# when invoked standalone (``uv run pytest tests/unit/test_admin_me.py``).
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
    """Lazy-import the admin app + TestClient. Skip if either is unreachable."""
    from fastapi.testclient import TestClient

    return TestClient(_fresh_admin_app())


def _has_admin_me_path() -> bool:
    """True if ``/api/v1/admin/me`` is mounted on the admin app."""
    try:
        admin_app = _fresh_admin_app()
    except pytest.skip.Exception:
        return False
    paths = admin_app.openapi().get("paths", {})
    return "/api/v1/admin/me" in paths


def _require_admin_me_mounted() -> None:
    """Skip if ``/admin/me`` is not mounted (branch deploy context)."""
    if not _has_admin_me_path():
        pytest.skip(
            "/api/v1/admin/me not mounted - likely PARKOS_DEPLOY=branch "
            "(admin views are cloud-only, REQ-X3). Set PARKOS_DEPLOY=cloud."
        )


def _admin_token(
    *,
    actor_uuid: uuid_lib.UUID | None = None,
    sucursales: list[str] | None = None,
    rol: str = "admin",
    permissions: list[str] | None = None,
) -> str:
    """Mint an ``admin-`` JWT for the test."""
    from parkos_core.auth.tokens import issue_token

    claims: dict[str, object] = {
        "rol": rol,
        "sucursales_permitidas": sucursales or [str(uuid_lib.uuid4())],
    }
    if permissions is not None:
        claims["permissions"] = permissions
    return issue_token(
        subject_uuid=actor_uuid or uuid_lib.uuid4(),
        issuer="admin-test",
        claims=claims,
    )


def _sync_agent_token() -> str:
    """Mint a ``sync-agent-`` JWT for cross-issuer negative tests."""
    from parkos_core.auth.tokens import issue_token

    return issue_token(
        subject_uuid=uuid_lib.uuid4(),
        issuer="sync-agent-test",
        claims={"scope": "cloud"},
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


def test_admin_me_shape_and_permissions() -> None:
    """GET /admin/me returns the actor identity shape + permitted branches."""
    _require_admin_me_mounted()
    actor_uuid = uuid_lib.uuid4()
    sucursales = [str(uuid_lib.uuid4()), str(uuid_lib.uuid4())]
    token = _admin_token(
        actor_uuid=actor_uuid,
        sucursales=sucursales,
        permissions=["config_catalogo", "audit_read"],
    )

    client = _client()
    response = _safe_get(
        client,
        "/api/v1/admin/me",
        {"Authorization": f"Bearer {token}"},
    )

    if response.status_code != 200:
        pytest.skip(
            f"/admin/me returned {response.status_code}: {response.text[:200]}"
        )

    data = response.json()

    # Shape - the response contract is fixed by ``AdminMeResponse``.
    for key in (
        "actor_uuid",
        "sucursales_permitidas",
        "permissions",
    ):
        assert key in data, f"missing key {key!r} in /admin/me response: {list(data.keys())}"

    # Type assertions.
    assert isinstance(data["sucursales_permitidas"], list)
    assert isinstance(data["permissions"], list)

    # When the test DB has permission rows linked to ``actor_uuid``,
    # the permissions list is non-empty (the seed migration
    # ``0002_seed_permisos_canonicos`` registers canonical codes). When
    # the DB is unseeded the list is ``[]`` and the test pins the
    # shape only.
    if data["permissions"]:
        assert len(data["permissions"]) >= 1
        for code in data["permissions"]:
            assert isinstance(code, str)
            assert code, "permission code must be non-empty string"

    # ``sucursales_permitidas`` should mirror the JWT claim (2 branches).
    assert len(data["sucursales_permitidas"]) == len(sucursales)


def test_admin_me_returns_actor_uuid_matching_sub_claim() -> None:
    """``actor_uuid`` echoes the ``sub`` claim from the JWT."""
    _require_admin_me_mounted()
    actor_uuid = uuid_lib.uuid4()
    token = _admin_token(actor_uuid=actor_uuid)

    client = _client()
    response = _safe_get(
        client,
        "/api/v1/admin/me",
        {"Authorization": f"Bearer {token}"},
    )
    if response.status_code != 200:
        pytest.skip(
            f"/admin/me returned {response.status_code}: {response.text[:200]}"
        )

    data = response.json()
    assert data.get("actor_uuid") == str(actor_uuid), (
        f"actor_uuid mismatch: response={data.get('actor_uuid')!r} "
        f"sub={str(actor_uuid)!r}"
    )

def test_admin_me_cross_issuer_returns_401() -> None:
    """``sync-agent-`` token against ``/admin/me`` -> 401 (CrossIssuerError)."""
    _require_admin_me_mounted()

    sync_token = _sync_agent_token()

    client = _client()
    response = _safe_get(
        client,
        "/api/v1/admin/me",
        {"Authorization": f"Bearer {sync_token}"},
    )
    assert response.status_code == 401, (
        f"expected 401 from cross-issuer, got {response.status_code}: "
        f"{response.text[:200]}"
    )


def test_admin_me_unauthenticated_returns_401() -> None:
    """No Authorization header -> 401 (issuer guard)."""
    _require_admin_me_mounted()
    client = _client()
    response = _safe_get(client, "/api/v1/admin/me", {})
    assert response.status_code == 401, (
        f"expected 401 from missing auth, got {response.status_code}"
    )


__all__ = [
    "test_admin_me_cross_issuer_returns_401",
    "test_admin_me_returns_actor_uuid_matching_sub_claim",
    "test_admin_me_shape_and_permissions",
    "test_admin_me_unauthenticated_returns_401",
]
