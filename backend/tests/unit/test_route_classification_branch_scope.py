"""Route-classification + signature guard for ``require_branch_scope`` (PR-A).

The sibling test ``test_route_classification_requires_sucursal.py`` documents a
production incident: FastAPI 0.141.1 cannot resolve a non-``Annotated``
dataclass parameter, silently falls back to classifying it as a **body field**,
and every GET endpoint depending on it returns ``422 "Field required"`` with
``loc=["body"]``. ``require_branch_scope`` returns ``BranchScope`` — another
frozen dataclass — on the six ``GET /operacion`` read routes, so it carries the
exact same hazard.

That failure mode would be maximally confusing here: it is indistinguishable
from a 403 scope rejection at a glance, the branch-scoped dashboard would just
be empty, and nothing would point at a FastAPI introspection quirk. Six tests
cost less than one debugging session.

Two invariants, checked at different levels on purpose:

1. the ``require_branch_scope`` SIGNATURE (async + ``ctx`` defaulting to
   ``Depends(get_tenant_ctx)``) — fails first, naming the real cause;
2. the resolved ROUTE ``body_field`` on all six reads — catches the symptom even
   if someone wires the dependency in a different, still-broken way later.

``session`` is intentionally exempt from the default rule. It uses
``Annotated[AsyncSession, Depends(get_session)]``, which FastAPI resolves
without a default — and it CANNOT have one, because it precedes the defaulted
``ctx``. ``get_tenant_ctx`` has the same shape.
"""
from __future__ import annotations

import inspect

import pytest


# Every read route guarded by ``require_branch_scope`` in api/v1/operacion.py.
# If a seventh read path is added there, it belongs in this list.
SCOPED_READ_ROUTES: list[str] = [
    "/operacion/ingresos",
    "/operacion/ingresos/{uuid}",
    "/operacion/ingresos/{uuid}/estado",
    "/operacion/salidas",
    "/operacion/salidas/{uuid}",
    "/operacion/ocupacion",
]


def _iter_operacion_routes() -> list[object]:
    import parkos_core.api.v1 as v1

    wrapper = next(
        (
            r
            for r in v1.router.routes
            if getattr(r, "original_router", None) is not None
            and getattr(r.original_router, "prefix", "") == "/operacion"
        ),
        None,
    )
    assert wrapper is not None, (
        "v1.router has no /operacion wrapper — mount drifted?"
    )
    leaves: list[object] = []
    for sub in wrapper.original_router.routes:
        inner = getattr(sub, "original_router", None)
        candidates = inner.routes if inner is not None else [sub]
        for route in candidates:
            if getattr(route, "methods", None) and getattr(route, "path", None):
                leaves.append(route)
    return leaves


def test_require_branch_scope_signature_is_async_with_depends_default() -> None:
    """Fail on the real cause before any route-level symptom shows up."""
    from fastapi.params import Depends as DependsClass

    from parkos_core.auth.tenancy import get_tenant_ctx, require_branch_scope

    assert inspect.iscoroutinefunction(require_branch_scope), (
        "require_branch_scope MUST be async — a sync function whose return "
        "type FastAPI cannot resolve is misclassified as a body field and "
        "every GET depending on it 422s."
    )
    params = inspect.signature(require_branch_scope).parameters
    assert "ctx" in params, "require_branch_scope lost its ctx parameter"
    assert params["ctx"].default is not inspect.Parameter.empty, (
        "ctx MUST have a default — a bare ``ctx: TenantContext`` makes "
        "FastAPI 0.141.1 fall back to body-field classification."
    )
    assert isinstance(params["ctx"].default, DependsClass), (
        f"ctx default must be Depends(...), got "
        f"{type(params['ctx'].default).__name__}"
    )
    assert params["ctx"].default.dependency is get_tenant_ctx, (
        "ctx default's dependency must be get_tenant_ctx."
    )


def test_scope_parameter_precedes_no_defaulted_session() -> None:
    """Pin the ordering that makes the file even importable.

    ``session: _DbSession`` must come before the defaulted ``ctx``; the reverse
    raises ``SyntaxError: parameter without a default follows parameter with a
    default``. Cheap to assert, and it localizes the failure to this file rather
    than to whatever imports it.
    """
    from parkos_core.auth.tenancy import require_branch_scope

    names = [
        name
        for name in inspect.signature(require_branch_scope).parameters
    ]
    assert names.index("session") < names.index("ctx"), (
        f"session must precede the defaulted ctx, got {names}"
    )


@pytest.mark.parametrize("path", SCOPED_READ_ROUTES)
def test_scoped_read_routes_have_no_body_field(path: str) -> None:
    """All six reads are GETs, so a body field can only be a misclassification."""
    routes = _iter_operacion_routes()
    matching = [
        route
        for route in routes
        if getattr(route, "path", None) == path
        and getattr(route, "methods", None) == frozenset({"GET"})
    ]
    assert matching, (
        f"GET {path} not found under /operacion — has the SCOPED_READ_ROUTES "
        f"inventory drifted from source?"
    )
    route = matching[0]
    assert getattr(route, "body_field", None) is None, (
        f"GET {path} ({route.name}) has body_field="
        f"{getattr(route, 'body_field', None)!r}. A GET must never require a "
        f"body; this means FastAPI classified the BranchScope dependency as a "
        f"payload. Symptom: 422 'Field required' loc=['body'] on every call, "
        f"which reads like an empty branch instead of a server bug."
    )


def test_every_scoped_read_route_actually_depends_on_the_scope() -> None:
    """The inventory above must be real, not aspirational.

    A route listed here but not actually depending on ``require_branch_scope``
    would be silently unscoped while CI reports the scope suite as covered. This
    is the check that keeps the integration tests in
    ``test_operacion_scope_lista.py`` honest.
    """
    from parkos_core.auth.tenancy import require_branch_scope

    routes = _iter_operacion_routes()
    for path in SCOPED_READ_ROUTES:
        matching = [
            route
            for route in routes
            if getattr(route, "path", None) == path
            and getattr(route, "methods", None) == frozenset({"GET"})
        ]
        assert matching, f"GET {path} not found"
        dependant = getattr(matching[0], "dependant", None)
        # ``dependant.dependencies`` is the reliable surface: it holds the
        # resolved sub-dependencies regardless of how the default was written,
        # and walking it transitively also catches an indirect wiring.
        found = False
        stack = list(getattr(dependant, "dependencies", []) or [])
        while stack:
            dep = stack.pop()
            stack.extend(getattr(dep, "dependencies", []) or [])
            if getattr(dep, "call", None) is require_branch_scope:
                found = True
        assert found, (
            f"GET {path} does not depend on require_branch_scope — either it "
            f"was not wired up, or it was wired through a wrapper that no "
            f"longer enforces branch scope."
        )
