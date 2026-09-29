"""Regression test for ROUTE-CLASS-01 — FastAPI 0.141.1 body misclassification.

History
-------
``parkos_core.auth.tenancy.requires_sucursal`` was historically a sync
function with a non-defaulted parameter ``ctx: TenantContext`` (a frozen
``@dataclass``). FastAPI 0.141.1's route-introspection cannot resolve
``TenantContext`` from any non-body source — it is neither a Request,
Header, nor annotated ``Annotated[..., Depends(...)]``. The introspection
falls back to treating the parameter as a body field, and (critically)
**propagates that classification to the caller's parameter**:

    _ctx: TenantContext = Depends(requires_sucursal)
    ─────────────────────┬───────────────────────
                         │
                         └── becomes ``body_field`` on the route

Symptom in production: every GET endpoint depending on ``requires_sucursal``
returns ``422 "Field required"`` with ``loc=["body"]`` because the GET
has no body. The browser dashboard hit
``GET /api/v1/empresa/tarifas-sucursal?limit=200`` and saw the 422,
matching this regression on 2026-09-29.

The fix (see ``tenancy.py`` docstring): make ``requires_sucursal``
``async`` AND give ``ctx`` a ``= Depends(get_tenant_ctx)`` default. The
explicit Depends annotation tells FastAPI how to resolve the parameter,
which removes the body-field fallback.

This test guards that invariant so a future refactor that re-introduces
the bug (e.g. dropping the default) fails CI immediately.
"""
from __future__ import annotations

import pytest


# Affected route inventory at the time of the fix. Each entry is
# ``(method, sub_path)``. The aggregated ``empresa.router`` mounts both
# the dedicated HU-F1.4 / PR-C sub-routers AND the factory sub-routers,
# so the inventory is a flat list of all (path, method) pairs where
# the route handler uses ``Depends(requires_sucursal)`` (directly or
# via a Depends that depends on it).
AFFECTED_ROUTES: list[tuple[str, str]] = [
    # tarifas-sucursal dedicated HU-F1.4 GETs
    ("GET", "/tarifas-sucursal"),
    ("GET", "/tarifas-sucursal/{uuid}"),
    # tarifas-sucursal dedicated PR-C by-key GET + POST/PUT
    ("GET", "/tarifas-sucursal/by-key"),
    ("POST", "/tarifas-sucursal"),
    ("PUT", "/tarifas-sucursal/{uuid}"),
    # cantidad-vehiculos-sucursal dedicated PR-C by-key GET + POST/PUT
    ("GET", "/cantidad-vehiculos-sucursal/by-key"),
    ("POST", "/cantidad-vehiculos-sucursal"),
    ("PUT", "/cantidad-vehiculos-sucursal/{uuid}"),
]


def _iter_empresa_routes() -> list[tuple[str, frozenset[str], object]]:
    """Walk the ``empresa`` sub-router inside ``v1.router`` and yield
    ``(relative_path, methods_frozenset, route)`` for every leaf route.

    FastAPI 0.141.1 wraps each ``include_router`` call as an
    ``_IncludedRouter`` instance whose ``original_router`` carries the
    actual routes. We unwind that wrapper so we can introspect the
    leaf ``APIRoute`` objects and check their ``body_field``.
    """
    import parkos_core.api.v1 as v1

    # Find the top-level ``empresa`` wrapper inside v1.router.
    empresa_wrapper = next(
        (
            r
            for r in v1.router.routes
            if getattr(r, "original_router", None) is not None
            and getattr(r.original_router, "prefix", "") == "/empresa"
        ),
        None,
    )
    assert empresa_wrapper is not None, (
        "v1.router has no /empresa wrapper — T-PR4-11 mount drifted?"
    )

    leaves: list[tuple[str, frozenset[str], object]] = []
    for sub in empresa_wrapper.original_router.routes:
        # Recurse one more level — the dedicated sub-routers are
        # included into ``empresa.router`` via ``include_router``.
        inner = getattr(sub, "original_router", None)
        candidates = inner.routes if inner is not None else [sub]
        for route in candidates:
            methods = getattr(route, "methods", None)
            path = getattr(route, "path", None)
            if methods is None or path is None:
                continue
            leaves.append((path, frozenset(methods), route))
    return leaves


@pytest.mark.parametrize("method,path", AFFECTED_ROUTES)
def test_affected_routes_body_field_is_not_ctx(method: str, path: str) -> None:
    """The body_field (when present) MUST NOT be named ``ctx`` or
    ``_ctx``.

    FastAPI 0.141.1 misclassifies a ``TenantContext`` parameter
    (resolved via ``requires_sucursal``) as a body field. The body
    field then carries the FastAPI-mangled parameter name ``ctx``
    (FastAPI strips the leading underscore) instead of the actual
    Pydantic payload schema. For GET routes there is no payload, so
    ``body_field`` is ``None`` entirely. For POST/PUT routes a
    Pydantic body schema IS expected — ``body_field`` should carry
    the schema's name (``payload`` or ``body``), never ``ctx``.

    Symptom when violated:
    - GET: ``422 "Field required"`` with ``loc=["body"]`` because the
      browser sends no body. Dashboard / Tarifas page breaks.
    - POST/PUT: payload is silently routed to the wrong field —
      schema validation against the real ``payload`` schema becomes
      inconsistent. Corruption is silent.
    """
    leaves = _iter_empresa_routes()
    target_methods = frozenset({method})

    matching = [
        route
        for leaf_path, leaf_methods, route in leaves
        if leaf_path == path and leaf_methods == target_methods
    ]
    assert matching, (
        f"{method} {path} not found under /empresa. Did the route "
        f"inventory in AFFECTED_ROUTES drift from source?"
    )
    route = matching[0]
    bf = getattr(route, "body_field", None)
    if bf is not None:
        # POST/PUT: body_field must carry the payload schema's name,
        # NOT the TenantContext Depends parameter.
        assert bf.name not in {"ctx", "_ctx"}, (
            f"{method} {path} ({route.name}) has body_field named "
            f"{bf.name!r} — FastAPI 0.141.1 misclassified the "
            f"requires_sucursal Depends parameter as a body field. "
            f"Expected a Pydantic payload schema (payload/body), not "
            f"the ctx TenantContext parameter. See tenancy.py "
            f"docstring for the signature invariant."
        )


@pytest.mark.parametrize(
    "path",
    [
        "/tarifas-sucursal",
        "/tarifas-sucursal/{uuid}",
        "/tarifas-sucursal/by-key",
        "/cantidad-vehiculos-sucursal/by-key",
    ],
)
def test_affected_get_routes_have_no_body_field(path: str) -> None:
    """GET routes depending on ``requires_sucursal`` MUST have
    ``body_field is None``.

    The original symptom: dashboard / Tarifas page hit GET and got
    ``422 "Field required"`` because FastAPI classified ctx as body.
    Lock down this invariant at the GET level so a regression here
    fails the test immediately.
    """
    leaves = _iter_empresa_routes()
    target_methods = frozenset({"GET"})
    matching = [
        route
        for leaf_path, leaf_methods, route in leaves
        if leaf_path == path and leaf_methods == target_methods
    ]
    assert matching, f"GET {path} not found under /empresa"
    route = matching[0]
    bf = getattr(route, "body_field", None)
    assert bf is None, (
        f"GET {path} ({route.name}) unexpectedly has body_field={bf!r}. "
        f"GET must not require a body — see tenancy.py docstring for the "
        f"signature invariant that prevents FastAPI 0.141.1 from "
        f"misclassifying the TenantContext parameter."
    )


def test_requires_sucursal_signature_is_async_with_depends_default() -> None:
    """Guard the signature invariant directly so a regression here
    fails BEFORE the route-level checks above fire.

    If someone drops the ``= Depends(get_tenant_ctx)`` default OR
    removes the ``async`` keyword, the FastAPI route-classification
    bug returns and every GET depending on it 422s. Asserting on the
    signature keeps the regression one step away from a body_field
    check.
    """
    import inspect

    from parkos_core.auth.tenancy import requires_sucursal

    assert inspect.iscoroutinefunction(requires_sucursal), (
        "requires_sucursal MUST be async — a sync function with a "
        "non-defaulted TenantContext parameter causes FastAPI 0.141.1 "
        "to misclassify the row's ctx parameter as a body field."
    )
    sig = inspect.signature(requires_sucursal)
    ctx_param = sig.parameters["ctx"]
    assert ctx_param.default is not inspect.Parameter.empty, (
        "ctx MUST have a default — FastAPI 0.141.1 requires an "
        "explicit Depends annotation to resolve a dataclass type."
    )
    # The default should be a Depends wrapping get_tenant_ctx. Note
    # ``fastapi.Depends`` is a FUNCTION (not a class); the actual class
    # returned by ``Depends(...)`` is ``fastapi.params.Depends``.
    from fastapi.params import Depends as _DependsClass

    from parkos_core.auth.tenancy import get_tenant_ctx

    assert isinstance(ctx_param.default, _DependsClass), (
        f"ctx default must be a Depends(...) instance (fastapi.params.Depends), "
        f"got {type(ctx_param.default).__name__}"
    )
    assert ctx_param.default.dependency is get_tenant_ctx, (
        "ctx default's dependency must be get_tenant_ctx so FastAPI "
        "knows how to resolve the TenantContext type."
    )