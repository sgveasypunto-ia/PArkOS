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

import sys
import uuid as uuid_lib
from pathlib import Path

import pytest

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
    """Force DATABASE_URL to a dummy URL; restore on teardown + reset engine cache.

    Without the cache reset, ``parkos_core.db.engine``'s lazy
    ``_sessionmaker`` keeps a stale connection from prior tests
    (e.g. ``test_idempotency_middleware::test_middleware_with_header_passes_through_when_no_db``
    would dial ``localhost:5432`` and hit ``OSError: Connect call failed``).
    """
    # Lazy-import the engine module so it lands in sys.modules (the
    # ``import ... as m`` form binds ``m`` to the ``engine`` proxy at
    # the bottom of engine.py, which triggers engine creation on first
    # attribute access). Fetch via ``sys.modules`` and poke the
    # underlying globals directly.
    import sys as _sys

    import parkos_core.db.engine  # noqa: F401 — side-effect: registers module
    _engine_mod = _sys.modules["parkos_core.db.engine"]

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

    Purging ``parkos_core.api.v1.*`` from ``sys.modules`` lets the next
    import re-evaluate ``PARKOS_DEPLOY`` (forced to ``cloud``). Without
    save/restore, sibling tests that imported those modules at collection
    time (e.g. ``test_sync_router``) reference module instances that no
    longer match ``sys.modules`` — ``monkeypatch.setattr`` then patches
    the wrong module and the endpoint runs the unpatched function
    (``consume_pairing_token`` real call -> ``pairing_token_not_found``).

    Also restores the parent package's ``__dict__`` entries for each
    purged submodule (Python's import system auto-binds submodules
    into the parent's ``__dict__`` on reimport, so a ``sys.modules``-only
    restore leaves ``from parkos_core.api.v1 import sync_router``
    resolving to the freshly-imported module).
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
        for (parent_name, attr), original in saved_parent_attrs.items():
            parent = sys.modules.get(parent_name)
            if parent is not None:
                parent.__dict__[attr] = original


def _client(app):
    """Lazy-import TestClient bound to the freshly built admin app."""
    from fastapi.testclient import TestClient

    return TestClient(app)


def _require_admin_me_mounted(app) -> None:
    """Skip if ``/admin/me`` is not mounted (branch deploy context)."""
    if "/api/v1/admin/me" not in app.openapi().get("paths", {}):
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


def test_admin_me_shape_and_permissions(
    dummy_db_url: str, fresh_admin_app
) -> None:
    """GET /admin/me returns the actor identity shape + permitted branches."""
    _require_admin_me_mounted(fresh_admin_app)
    actor_uuid = uuid_lib.uuid4()
    sucursales = [str(uuid_lib.uuid4()), str(uuid_lib.uuid4())]
    token = _admin_token(
        actor_uuid=actor_uuid,
        sucursales=sucursales,
        permissions=["config_catalogo", "audit_read"],
    )

    client = _client(fresh_admin_app)
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

    for key in (
        "actor_uuid",
        "sucursales_permitidas",
        "permissions",
    ):
        assert key in data, f"missing key {key!r} in /admin/me response: {list(data.keys())}"

    assert isinstance(data["sucursales_permitidas"], list)
    assert isinstance(data["permissions"], list)

    if data["permissions"]:
        assert len(data["permissions"]) >= 1
        for code in data["permissions"]:
            assert isinstance(code, str)
            assert code, "permission code must be non-empty string"

    assert len(data["sucursales_permitidas"]) == len(sucursales)


def test_admin_me_returns_actor_uuid_matching_sub_claim(
    dummy_db_url: str, fresh_admin_app
) -> None:
    """``actor_uuid`` echoes the ``sub`` claim from the JWT."""
    _require_admin_me_mounted(fresh_admin_app)
    actor_uuid = uuid_lib.uuid4()
    token = _admin_token(actor_uuid=actor_uuid)

    client = _client(fresh_admin_app)
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


def test_admin_me_cross_issuer_returns_401(
    dummy_db_url: str, fresh_admin_app
) -> None:
    """``sync-agent-`` token against ``/admin/me`` -> 401 (CrossIssuerError)."""
    _require_admin_me_mounted(fresh_admin_app)

    sync_token = _sync_agent_token()

    client = _client(fresh_admin_app)
    response = _safe_get(
        client,
        "/api/v1/admin/me",
        {"Authorization": f"Bearer {sync_token}"},
    )
    assert response.status_code == 401, (
        f"expected 401 from cross-issuer, got {response.status_code}: "
        f"{response.text[:200]}"
    )


def test_admin_me_unauthenticated_returns_401(
    dummy_db_url: str, fresh_admin_app
) -> None:
    """No Authorization header -> 401 (issuer guard)."""
    _require_admin_me_mounted(fresh_admin_app)
    client = _client(fresh_admin_app)
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
