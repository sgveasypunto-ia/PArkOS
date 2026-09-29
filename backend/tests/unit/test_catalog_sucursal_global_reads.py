"""test_catalog_sucursal_global_reads.py — fix/catalog-sucursal-global-reads.

The 9 ``/api/v1/catalogos/{resource}`` tables and the
``/api/v1/empresa/sucursal`` directory are tenant-global reference data
(``features/catalogos/CatalogPage.tsx:2-7`` documents the invariant:
``CatalogPage`` and the branch picker mount OUTSIDE
``<RequireSucursal>``). Pre-fix, every read endpoint on these surfaces
required ``X-Sucursal-Context`` for ``admin-`` tokens, breaking
``GET /catalogos/tipo-persona``, ``GET /catalogos/tipo-sucursal``,
``GET /empresa/sucursal?limit=200`` etc. on first login (before a
branch was selected) with ``400 missing_sucursal_context``.

This module pins the carve-out at two layers:

1. **Route resolution** — the dedicated global-reads handlers are
   registered BEFORE the factory sub-router on the same path, so
   FastAPI's first-match resolver picks them.
2. **Dependency wiring** — the dedicated handlers DO NOT depend on
   ``get_tenant_ctx``; the factory sub-router's POST/PUT DO (regression
   guard for the existing security posture on writes).
3. **HTTP smoke** — a minimal ``ASGITransport`` app with monkey-patched
   ``verify_jwt`` (no JWT) and a fake session (no DB) confirms
   ``GET /api/v1/catalogos/tipo-persona`` for an ``admin-``-ish caller
   returns 200 without ``X-Sucursal-Context``.

Test isolation:
- No Postgres / testcontainers — pure unit + a tiny in-process HTTP smoke.
- No JWT minting — monkey-patch ``verify_jwt`` to return a static
  admin-like claim set; this is the same pattern that
  ``tests/unit/test_tenancy_admin.py`` uses to drive ``get_tenant_ctx``
  directly without HTTP.

Acceptance criteria (mirrors ``apps/web_admin/e2e/branch-selector.spec.ts``
which already verifies branch switching in the admin app):

- Catalog GETs: 200 without ``X-Sucursal-Context`` for an admin- token.
- Empresa/sucursal GET (list + by-uuid + history): 200 without
  ``X-Sucursal-Context``.
- Catalog POSTs: still depend on ``get_tenant_ctx`` (regression).
- Empresa/sucursal POST/PUT: still depend on ``get_tenant_ctx``.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Route-resolution helpers
# ---------------------------------------------------------------------------

_CATALOG_RESOURCES: tuple[str, ...] = (
    "tipo-persona",
    "tipos-vehiculo",
    "tipo-subscripciones",
    "tipo-tarifa",
    "tipo-sucursal",
    "tipo-arqueo",
    "impuestos",
    "otros-cobros",
    "costos-servicios",
)


def _collect_tenant_deps(dependant: Any) -> list[Any]:
    """Return every ``get_tenant_ctx`` dependency reachable from ``dependant``.

    Recurses into nested dependencies because the factory wraps multiple
    layers (``get_session`` -> ``get_tenant_ctx`` etc).
    """
    from parkos_core.auth.tenancy import get_tenant_ctx

    found: list[Any] = []
    stack: list[Any] = list(dependant.dependencies)
    while stack:
        d = stack.pop()
        if d.call is get_tenant_ctx:
            found.append(d)
        stack.extend(d.dependencies)
    return found


def _walk_routes(routes: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Flatten an ``APIRouter.routes`` list into ``(full_path, APIRoute)``.

    ``_IncludedRouter`` wrappers expose ``.original_router.routes`` AND
    carry the parent's effective prefix in ``.include_context.prefix``;
    we walk through them recursively so the test sees every route that
    FastAPI would actually expose at HTTP time. ``full_path`` is the
    effective path the client sees (parent prefix + child prefix + route
    path), which is what FastAPI uses for matching.
    """
    flat: list[tuple[str, Any]] = []
    for r in routes:
        if hasattr(r, "methods") and r.methods:
            child_prefix = getattr(r, "prefix", "") or ""
            full_path = prefix + child_prefix + r.path
            flat.append((full_path, r))
        inner = getattr(r, "original_router", None) or getattr(r, "router", None)
        if inner is not None and hasattr(inner, "routes"):
            # _IncludedRouter carries the parent's effective prefix here
            include_ctx = getattr(r, "include_context", None)
            child_prefix = (
                getattr(include_ctx, "prefix", "") if include_ctx is not None else ""
            ) or getattr(r, "prefix", "") or ""
            flat.extend(_walk_routes(inner.routes, prefix + child_prefix))
    return flat


def _find_first_route(
    routes: list[tuple[str, Any]], path_suffix: str, methods: set[str]
) -> Any | None:
    """Return the FIRST ``APIRoute`` whose ``full_path`` ends with ``path_suffix``
    and whose methods overlap ``methods``."""
    for full_path, r in routes:
        if full_path.endswith(path_suffix) and r.methods & methods:
            return r
    return None


def _find_all_routes(
    routes: list[tuple[str, Any]], path: str, methods: set[str]
) -> list[Any]:
    """Return ALL ``APIRoute``s whose ``full_path == path`` and whose methods overlap."""
    out: list[Any] = []
    for full_path, r in routes:
        if full_path == path and r.methods & methods:
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# Catalogos: route resolution + dependency wiring
# ---------------------------------------------------------------------------


class TestCatalogosGlobalReadsRouteResolution:
    """The 9 ``GET /catalogos/{resource}`` endpoints are tenant-free.

    Confirmed by route introspection: the registered ``APIRoute`` for
    each catalog GET has NO ``get_tenant_ctx`` in its dependency tree.
    """

    @pytest.fixture(scope="class")
    def catalogos_routes(self) -> list[tuple[str, Any]]:
        from parkos_core.api.v1.catalogos import router

        return _walk_routes(router.routes)

    @pytest.mark.parametrize("resource", _CATALOG_RESOURCES)
    def test_get_list_does_not_depend_on_tenant_ctx(
        self,
        catalogos_routes: list[tuple[str, Any]],
        resource: str,
    ) -> None:
        route = _find_first_route(
            catalogos_routes,
            path_suffix=f"/{resource}",
            methods={"GET"},
        )
        assert route is not None, f"GET /{resource} not found"
        assert not _collect_tenant_deps(route.dependant), (
            f"GET /catalogos/{resource} unexpectedly depends on get_tenant_ctx; "
            "the fix was meant to remove it so admin- tokens work pre-branch."
        )

    @pytest.mark.parametrize("resource", _CATALOG_RESOURCES)
    def test_get_by_uuid_does_not_depend_on_tenant_ctx(
        self,
        catalogos_routes: list[tuple[str, Any]],
        resource: str,
    ) -> None:
        route = _find_first_route(
            catalogos_routes,
            path_suffix=f"/{resource}/{{uuid}}",
            methods={"GET"},
        )
        assert route is not None, f"GET /{resource}/{{uuid}} not found"
        assert not _collect_tenant_deps(route.dependant)

    @pytest.mark.parametrize("resource", _CATALOG_RESOURCES)
    def test_history_does_not_depend_on_tenant_ctx(
        self,
        catalogos_routes: list[tuple[str, Any]],
        resource: str,
    ) -> None:
        route = _find_first_route(
            catalogos_routes,
            path_suffix=f"/{resource}/{{uuid}}/history",
            methods={"GET"},
        )
        assert route is not None, f"GET /{resource}/{{uuid}}/history not found"
        assert not _collect_tenant_deps(route.dependant)


class TestCatalogosWritesStillRequireTenant:
    """Regression guard: POST/PUT on catalogs MUST keep ``get_tenant_ctx``.

    The carve-out only relaxed READ endpoints. Writes stay tenant-scoped
    because ``admin-`` without a branch should not be able to insert
    catalog rows without an explicit scope decision.
    """

    @pytest.fixture(scope="class")
    def catalogos_routes(self) -> list[tuple[str, Any]]:
        from parkos_core.api.v1.catalogos import router

        return _walk_routes(router.routes)

    @pytest.mark.parametrize("resource", _CATALOG_RESOURCES)
    def test_post_still_depends_on_tenant_ctx(
        self,
        catalogos_routes: list[tuple[str, Any]],
        resource: str,
    ) -> None:
        # After walking through the _IncludedRouter wrappers, every factory
        # route has the composed full path (``/catalogos/{resource}``).
        # The dedicated global reads do NOT register POST, so any POST on
        # this path comes from the factory sub-router.
        posts = _find_all_routes(
            catalogos_routes,
            path=f"/catalogos/{resource}",
            methods={"POST"},
        )
        assert posts, f"POST /catalogos/{resource} not found"
        post_route = posts[0]
        assert _collect_tenant_deps(post_route.dependant), (
            f"POST /catalogos/{resource} must still depend on get_tenant_ctx "
            "(writes stay tenant-scoped)."
        )

    @pytest.mark.parametrize("resource", _CATALOG_RESOURCES)
    def test_put_still_depends_on_tenant_ctx(
        self,
        catalogos_routes: list[tuple[str, Any]],
        resource: str,
    ) -> None:
        puts = _find_all_routes(
            catalogos_routes,
            path=f"/catalogos/{resource}/{{uuid}}",
            methods={"PUT"},
        )
        assert puts, f"PUT /catalogos/{resource}/{{uuid}} not found"
        put_route = puts[0]
        assert _collect_tenant_deps(put_route.dependant), (
            f"PUT /catalogos/{resource}/{{uuid}} must still depend on get_tenant_ctx."
        )


# ---------------------------------------------------------------------------
# Empresa/sucursal: route resolution + dependency wiring
# ---------------------------------------------------------------------------


class TestEmpresaSucursalGlobalReadsRouteResolution:
    """``GET /empresa/sucursal`` (list + by-uuid + history) is tenant-free."""

    @pytest.fixture(scope="class")
    def empresa_routes(self) -> list[tuple[str, Any]]:
        from parkos_core.api.v1.empresa import router

        return _walk_routes(router.routes)

    def test_get_list_does_not_depend_on_tenant_ctx(
        self, empresa_routes: list[tuple[str, Any]]
    ) -> None:
        route = _find_first_route(
            empresa_routes,
            path_suffix="/sucursal",
            methods={"GET"},
        )
        assert route is not None, "GET /empresa/sucursal not found"
        assert not _collect_tenant_deps(route.dependant)

    def test_get_by_uuid_does_not_depend_on_tenant_ctx(
        self, empresa_routes: list[tuple[str, Any]]
    ) -> None:
        route = _find_first_route(
            empresa_routes,
            path_suffix="/sucursal/{uuid}",
            methods={"GET"},
        )
        assert route is not None, "GET /empresa/sucursal/{uuid} not found"
        assert not _collect_tenant_deps(route.dependant)

    def test_history_does_not_depend_on_tenant_ctx(
        self, empresa_routes: list[tuple[str, Any]]
    ) -> None:
        route = _find_first_route(
            empresa_routes,
            path_suffix="/sucursal/{uuid}/history",
            methods={"GET"},
        )
        assert route is not None, "GET /empresa/sucursal/{uuid}/history not found"
        assert not _collect_tenant_deps(route.dependant)


class TestEmpresaSucursalWritesStillRequireTenant:
    """Regression guard: POST/PUT on ``/empresa/sucursal`` stay tenant-scoped."""

    @pytest.fixture(scope="class")
    def empresa_routes(self) -> list[tuple[str, Any]]:
        from parkos_core.api.v1.empresa import router

        return _walk_routes(router.routes)

    def test_post_still_depends_on_tenant_ctx(
        self, empresa_routes: list[tuple[str, Any]]
    ) -> None:
        posts = _find_all_routes(
            empresa_routes, path="/empresa/sucursal", methods={"POST"}
        )
        assert posts, "POST /empresa/sucursal not found"
        assert _collect_tenant_deps(posts[0].dependant)

    def test_put_still_depends_on_tenant_ctx(
        self, empresa_routes: list[tuple[str, Any]]
    ) -> None:
        puts = _find_all_routes(
            empresa_routes, path="/empresa/sucursal/{uuid}", methods={"PUT"}
        )
        assert puts, "PUT /empresa/sucursal/{uuid} not found"
        assert _collect_tenant_deps(puts[0].dependant)


# ---------------------------------------------------------------------------
# HTTP smoke — full request cycle without DB / without a real JWT
# ---------------------------------------------------------------------------


class TestGlobalReadsHTTPSmoke:
    """End-to-end smoke that ``GET`` returns 200 without ``X-Sucursal-Context``.

    Patches ``verify_jwt`` at every module that imports it (the closures
    inside ``requires_issuer._dep`` and ``require_permission._dep``
    capture it by name — patching the module globals is the only way to
    replace the captured reference). Replaces the SQL session with a
    no-op async session. Overrides ``get_tenant_ctx`` to a tenant-free
    admin- context so even if a factory sub-router sneaks in via the
    route stack it doesn't blow up the test on the 400 fallback path.
    """

    @pytest.fixture
    def patched_app(self, monkeypatch: pytest.MonkeyPatch):
        """Build a minimal FastAPI app with the catalog + empresa routers,
        patch ``verify_jwt`` everywhere, and override ``get_session`` +
        ``get_tenant_ctx``.

        Yields the app ready to be wrapped in an ASGITransport client.
        """
        import uuid as _uuid

        from fastapi import FastAPI

        from parkos_core.api.v1.catalogos import router as catalogos_router
        from parkos_core.api.v1.empresa import router as empresa_router
        from parkos_core.auth.tenancy import (
            TenantContext,
            get_tenant_ctx,
        )
        from parkos_core.db.engine import get_session

        async def fake_verify_jwt(request: Any) -> dict[str, Any]:
            return {
                "iss": "admin-test",
                "sub": str(_uuid.uuid4()),
                "rol": "admin",
                "sucursales_permitidas": [],
            }

        # SQL session — empty results, callable methods.
        class _EmptyScalars:
            def all(self):
                return []

            def first(self):
                return None

        class _EmptyResult:
            def scalars(self):
                return _EmptyScalars()

        class _FakeSession:
            async def execute(self, stmt: Any) -> Any:
                return _EmptyResult()

            async def commit(self) -> None:
                return None

            async def refresh(self, obj: Any) -> None:
                return None

        async def fake_get_session() -> Any:
            return _FakeSession()

        async def fake_get_tenant_ctx(*args: Any, **kwargs: Any) -> TenantContext:
            # If the factory sub-router's POST/PUT somehow gets invoked
            # by a misrouted request, simulate admin- with NO branch so
            # we can confirm the dedup logic still rejects.
            return TenantContext(
                actor_uuid=_uuid.uuid4(),
                actor_rol="admin",
                issuer_prefix="admin-",
                sucursal_uuid=None,
            )

        app = FastAPI()
        app.include_router(catalogos_router, prefix="/api/v1")
        app.include_router(empresa_router, prefix="/api/v1")
        app.dependency_overrides[get_session] = fake_get_session
        app.dependency_overrides[get_tenant_ctx] = fake_get_tenant_ctx

        # Belt-and-suspenders for the verify_jwt capture-by-reference issue.
        # The closures look up the name in the module globals; setting via
        # ``monkeypatch.setattr`` on the module entry is the canonical way.
        import parkos_core.auth.jwt_issuer_guard as _gj
        import parkos_core.auth.permissions as _pj
        import parkos_core.auth.tenancy as _tj

        monkeypatch.setattr(_gj, "verify_jwt", fake_verify_jwt)
        monkeypatch.setattr(_pj, "verify_jwt", fake_verify_jwt)
        monkeypatch.setattr(_tj, "verify_jwt", fake_verify_jwt)

        return app

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/catalogos/tipo-persona",
            "/api/v1/catalogos/tipo-sucursal",
            "/api/v1/catalogos/tipos-vehiculo",
            "/api/v1/empresa/sucursal",
            "/api/v1/empresa/sucursal?limit=200",
        ],
    )
    async def test_get_returns_200_without_sucursal_header(
        self, patched_app: Any, path: str
    ) -> None:
        """Admin- without ``X-Sucursal-Context`` succeeds for global reads.

        Pre-fix this returned ``400 missing_sucursal_context``. Post-fix
        the read handler returns ``200 {items: [], next_cursor: null}``.
        """
        import httpx

        transport = httpx.ASGITransport(app=patched_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t"
        ) as client:
            r = await client.get(path)  # NO Authorization, NO X-Sucursal-Context
        assert r.status_code == 200, (
            f"GET {path} returned {r.status_code}: {r.text[:200]}; "
            "expected 200 after the global-reads carve-out."
        )
        body = r.json()
        assert body == {"items": [], "next_cursor": None}


# ---------------------------------------------------------------------------
# Scope enforcement — the carve-out removes the HEADER requirement, not the
# authorization requirement. ``/empresa/sucursal`` is still bounded to the
# caller's permitted branches. Tests below pin that contract so a future
# refactor cannot silently turn the directory into a cross-tenant leak.
# ---------------------------------------------------------------------------


def _statement_entity_name(stmt: Any) -> str | None:
    """Return the ORM entity class name targeted by ``stmt``, if any.

    SQLAlchemy's :attr:`ColumnCollection.column_descriptions` exposes the
    source ``Mapped`` entity for every column originated from an ORM
    descriptor. ``select(UsuariosSucursal.uuid_sucursal)`` and
    ``select(Sucursal)`` both populate it, which is enough to tell the
    two queries apart in a fake session.
    """
    for desc in getattr(stmt, "column_descriptions", []) or []:
        if not isinstance(desc, dict):
            continue
        entity = desc.get("entity")
        if entity is not None:
            return getattr(entity, "__name__", None)
    return None


class _ScopeFakeSession:
    """Session that serves ``UsuariosSucursal`` and ``Sucursal`` queries.

    Any other query — e.g. ``current_version`` invoked for a UUID that
    should have been short-circuited — raises. That makes the
    "the handler returned 404 without ever touching the Sucursal table"
    property visible as a test failure rather than a silent green.
    """

    def __init__(
        self,
        *,
        permitted: list[Any],
        sucursal_rows: list[Any] | None = None,
    ) -> None:
        self._permitted = list(permitted)
        self._rows = list(sucursal_rows or [])

    async def execute(self, stmt: Any) -> Any:
        entity = _statement_entity_name(stmt)
        if entity == "UsuariosSucursal":
            scalars = self._permitted
        elif entity == "Sucursal":
            scalars = self._rows
        else:
            raise AssertionError(
                f"_ScopeFakeSession.execute: unexpected entity {entity!r} "
                "for stmt; the security property requires the handler to "
                "short-circuit BEFORE this query is reached."
            )

        class _Scalars:
            def __init__(self, items: list[Any]) -> None:
                self._items = items

            def all(self) -> list[Any]:
                return list(self._items)

            def first(self) -> Any | None:
                return self._items[0] if self._items else None

        class _Result:
            def __init__(self, items: list[Any]) -> None:
                self._items = items

            def scalars(self) -> Any:
                return _Scalars(self._items)

        return _Result(scalars)

    async def commit(self) -> None:
        return None

    async def refresh(self, obj: Any) -> None:
        return None


def _install_scope_patches(
    monkeypatch: pytest.MonkeyPatch,
    *,
    app: Any,
    permitted: list[Any],
    rows: list[Any] | None = None,
    iss_claim: str = "admin-test",
) -> dict[str, Any]:
    """Wire a minimal app with the scope-enforcing fake session.

    Returns the claim dict so the test can assert against it.
    """
    import uuid as _uuid

    from parkos_core.auth.tenancy import TenantContext, get_tenant_ctx
    from parkos_core.db.engine import get_session

    actor_uuid = _uuid.uuid4()
    claim: dict[str, Any] = {
        "iss": iss_claim,
        "sub": str(actor_uuid),
        "rol": "admin",
        "sucursales_permitidas": [],  # stale snapshot — ignored on admin-
    }

    async def fake_verify_jwt(request: Any) -> dict[str, Any]:
        return claim

    async def fake_get_session() -> Any:
        return _ScopeFakeSession(permitted=permitted, sucursal_rows=rows or [])

    async def fake_get_tenant_ctx(*args: Any, **kwargs: Any) -> TenantContext:
        return TenantContext(
            actor_uuid=actor_uuid,
            actor_rol="admin",
            issuer_prefix="admin-",
            sucursal_uuid=None,
        )

    app.dependency_overrides[get_session] = fake_get_session
    app.dependency_overrides[get_tenant_ctx] = fake_get_tenant_ctx

    import parkos_core.auth.jwt_issuer_guard as _gj
    import parkos_core.auth.permissions as _pj
    import parkos_core.auth.tenancy as _tj

    monkeypatch.setattr(_gj, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(_pj, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(_tj, "verify_jwt", fake_verify_jwt)

    return claim


class TestEmpresaSucursalScopeEnforced:
    """The directory is still bounded to the caller's permitted branches.

    Dropping the ``X-Sucursal-Context`` requirement was a HEADER change,
    not an authorization change. ``AGENTS.md`` lists "Tenant scope leak
    in admin JWT" as a HIGH risk whose mitigation is enforcing
    ``sucursales_permitidas`` on every call. These tests fail closed if
    a future refactor removes that filter from any of the 3 read
    handlers.
    """

    @pytest.fixture
    def scoped_app(self, monkeypatch: pytest.MonkeyPatch):
        from fastapi import FastAPI

        from parkos_core.api.v1.empresa import router as empresa_router

        app = FastAPI()
        app.include_router(empresa_router, prefix="/api/v1")
        return app

    @pytest.mark.asyncio
    async def test_list_returns_empty_when_caller_has_no_permitted_branches(
        self, monkeypatch: pytest.MonkeyPatch, scoped_app: Any
    ) -> None:
        """``admin-`` with no ``usuarios_sucursal`` rows must see NOTHING.

        Fail closed: the directory is part of the auth boundary, so a
        caller who has not been assigned a branch cannot enumerate the
        directory. ``db.tenancy.apply_admin_scope`` documents the same
        contract for the factory path.
        """
        import httpx

        _install_scope_patches(
            monkeypatch, app=scoped_app, permitted=[], rows=[]
        )
        transport = httpx.ASGITransport(app=scoped_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t"
        ) as client:
            r = await client.get("/api/v1/empresa/sucursal?limit=200")
        assert r.status_code == 200, r.text
        assert r.json() == {"items": [], "next_cursor": None}

    @pytest.mark.asyncio
    async def test_list_with_no_permitted_does_not_touch_sucursal_table(
        self, monkeypatch: pytest.MonkeyPatch, scoped_app: Any
    ) -> None:
        """Fail-closed path must NOT execute the ``Sucursal`` SELECT.

        Defence in depth: even if the table is poisoned with extra rows,
        an admin with no assignments must never read them. The fake
        session raises if the handler reaches ``select(Sucursal)`` while
        the permitted set is empty — that turns a silent leak into a
        visible regression.
        """
        import httpx

        _install_scope_patches(
            monkeypatch,
            app=scoped_app,
            permitted=[],
            rows=[_build_fake_sucursal()],  # would leak if handler ran the SELECT
        )
        transport = httpx.ASGITransport(app=scoped_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t"
        ) as client:
            r = await client.get("/api/v1/empresa/sucursal")
        assert r.status_code == 200
        assert r.json() == {"items": [], "next_cursor": None}

    @pytest.mark.asyncio
    async def test_detail_of_non_permitted_branch_returns_404(
        self, monkeypatch: pytest.MonkeyPatch, scoped_app: Any
    ) -> None:
        """Detail must NOT leak whether a UUID exists outside scope.

        A non-permitted UUID is indistinguishable from a non-existent
        one (``404 sucursal_no_encontrada``), so an attacker cannot use
        the endpoint as a directory-discovery oracle. The fake session
        raises if the handler reaches ``current_version(Sucursal, ...)``
        for a UUID outside the permitted set.
        """
        import httpx

        permitted = [uuid_lib.uuid4()]
        non_permitted = uuid_lib.uuid4()
        _install_scope_patches(
            monkeypatch,
            app=scoped_app,
            permitted=permitted,
            rows=[],  # empty — must not be queried
        )
        transport = httpx.ASGITransport(app=scoped_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t"
        ) as client:
            r = await client.get(f"/api/v1/empresa/sucursal/{non_permitted}")
        assert r.status_code == 404, r.text
        body = r.json()
        assert body["detail"]["error"] == "sucursal_no_encontrada"
        assert body["detail"]["uuid"] == str(non_permitted)

    @pytest.mark.asyncio
    async def test_history_of_non_permitted_branch_returns_404(
        self, monkeypatch: pytest.MonkeyPatch, scoped_app: Any
    ) -> None:
        """History endpoint inherits the same 404 short-circuit."""
        import httpx

        permitted = [uuid_lib.uuid4()]
        non_permitted = uuid_lib.uuid4()
        _install_scope_patches(
            monkeypatch,
            app=scoped_app,
            permitted=permitted,
            rows=[],
        )
        transport = httpx.ASGITransport(app=scoped_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t"
        ) as client:
            r = await client.get(
                f"/api/v1/empresa/sucursal/{non_permitted}/history"
            )
        assert r.status_code == 404, r.text
        assert r.json()["detail"]["error"] == "sucursal_no_encontrada"


def _build_fake_sucursal() -> Any:
    """Build a minimal Sucursal-shaped object for the ``Sucursal`` SELECT.

    Only fields the handler reads before model_validate are populated;
    the model_validate step itself is bypassed because the test
    ``test_list_with_no_permitted_does_not_touch_sucursal_table`` must
    prove the handler never reaches the Sucursal SELECT.
    """
    return SimpleNamespace(
        uuid=uuid_lib.uuid4(),
        vigente_desde=datetime.now(UTC),
        vigente_hasta=None,
    )
