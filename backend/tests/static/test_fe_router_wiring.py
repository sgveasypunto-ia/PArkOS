"""HU-F1.10 / T7.1 + T7.2 — router wiring verification + KD-3 issuer chain.

T7.1: the 3 FE routes are mounted on the ``facturacion`` router with
the correct paths, HTTP methods, and status codes.

  - POST   /factura-electronica                       (201)
  - GET    /factura-electronica/{uuid}                (200)
  - POST   /factura-electronica/{uuid}/reintentar     (201)

T7.2: every FE handler depends on ``_fe_issuer_dep`` (KD-3 layer 1
of defense in depth — ``operador-,admin-`` issuer scope).

Both walks inspect the FastAPI router's route table. KD-3 wiring is
asserted by checking that the handler's signature includes a
``Depends(_fe_issuer_dep)`` parameter.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


_HANDLER_FILE = (
    _PARKOS_CORE_SRC
    / "parkos_core"
    / "api"
    / "v1"
    / "facturacion.py"
)


# ---------------------------------------------------------------------------
# T7.1 — Routes are registered
# ---------------------------------------------------------------------------


def test_post_factura_electronica_route_is_registered() -> None:
    """T7.1: POST /factura-electronica is mounted with status_code=201."""
    from parkos_core.api.v1.facturacion import router

    match = next(
        (
            r
            for r in router.routes
            if hasattr(r, "path") and r.path == "/factura-electronica"
        ),
        None,
    )
    assert match is not None, (
        "POST /factura-electronica route is not registered on the "
        "facturacion router"
    )
    assert "POST" in match.methods, (
        f"POST /factura-electronica is mounted with methods={match.methods}; "
        f"expected to include POST"
    )
    assert match.status_code == 201, (
        f"POST /factura-electronica has status_code={match.status_code}; "
        f"expected 201 (resource creation)"
    )


def test_get_factura_electronica_uuid_route_is_registered() -> None:
    """T7.1: GET /factura-electronica/{uuid} is mounted with status_code=200."""
    from parkos_core.api.v1.facturacion import router

    match = next(
        (
            r
            for r in router.routes
            if hasattr(r, "path")
            and r.path == "/factura-electronica/{uuid}"
        ),
        None,
    )
    assert match is not None, (
        "GET /factura-electronica/{uuid} route is not registered"
    )
    assert "GET" in match.methods, (
        f"GET /factura-electronica/{{uuid}} mounted with methods={match.methods}"
    )
    assert match.status_code == 200


def test_post_reintentar_route_is_registered() -> None:
    """T7.1: POST /factura-electronica/{uuid}/reintentar is mounted with 201."""
    from parkos_core.api.v1.facturacion import router

    match = next(
        (
            r
            for r in router.routes
            if hasattr(r, "path")
            and r.path == "/factura-electronica/{uuid}/reintentar"
        ),
        None,
    )
    assert match is not None, (
        "POST /factura-electronica/{uuid}/reintentar route is not registered"
    )
    assert "POST" in match.methods
    assert match.status_code == 201


# ---------------------------------------------------------------------------
# T7.2 — KD-3 issuer chain wired on every handler
# ---------------------------------------------------------------------------


def _handler_uses_fe_issuer_dep(handler_name: str) -> bool:
    """Return True iff ``handler_name`` declares a ``Depends(_fe_issuer_dep)``."""
    tree = ast.parse(_HANDLER_FILE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == handler_name:
            for arg in (
                node.args.args + node.args.kwonlyargs + node.args.posonlyargs
            ):
                if arg.arg == "_claims":
                    default = node.args.defaults[0] if node.args.defaults else None
                    # ``_claims: None = Depends(_fe_issuer_dep)`` — the default
                    # is a ``Call`` whose func is ``Name(id='Depends')`` and
                    # whose first arg is ``Name(id='_fe_issuer_dep')``.
                    if (
                        isinstance(default, ast.Call)
                        and isinstance(default.func, ast.Name)
                        and default.func.id == "Depends"
                        and default.args
                        and isinstance(default.args[0], ast.Name)
                        and default.args[0].id == "_fe_issuer_dep"
                    ):
                        return True
    return False


def test_create_handler_uses_fe_issuer_dep() -> None:
    """T7.2: ``create_factura_electronica`` depends on ``_fe_issuer_dep``."""
    assert _handler_uses_fe_issuer_dep("create_factura_electronica"), (
        "KD-3 violated: `create_factura_electronica` does NOT depend on "
        "`_fe_issuer_dep`; any caller (including anon) could mint an FE."
    )


def test_get_handler_uses_fe_issuer_dep() -> None:
    """T7.2: ``get_factura_electronica`` depends on ``_fe_issuer_dep``."""
    assert _handler_uses_fe_issuer_dep("get_factura_electronica"), (
        "KD-3 violated: `get_factura_electronica` does NOT depend on "
        "`_fe_issuer_dep`; cross-tenant read access would be unguarded."
    )


def test_retry_handler_uses_fe_issuer_dep() -> None:
    """T7.2: ``retry_envio_dian`` depends on ``_fe_issuer_dep``."""
    assert _handler_uses_fe_issuer_dep("retry_envio_dian"), (
        "KD-3 violated: `retry_envio_dian` does NOT depend on "
        "`_fe_issuer_dep`; cross-tenant retry submission would be unguarded."
    )


def test_fe_issuer_dep_uses_operador_admin_scope() -> None:
    """T7.2: ``_fe_issuer_dep`` is ``requires_issuer("operador-", "admin-")``.

    The two issuer prefixes are the only ones permitted to create / read /
    retry an FE — KD-3 layer 1 of defense in depth.
    """
    tree = ast.parse(_HANDLER_FILE.read_text(encoding="utf-8"))
    target_name: str | None = None
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_fe_issuer_dep"
        ):
            target_name = "_fe_issuer_dep"
            value = node.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "requires_issuer"
                and len(value.args) == 2
                and all(isinstance(a, ast.Constant) for a in value.args)
            ):
                prefixes = {a.value for a in value.args}
                assert prefixes == {"operador-", "admin-"}, (
                    f"KD-3 violated: `_fe_issuer_dep` uses prefixes "
                    f"{prefixes}; expected exactly "
                    f"{{'operador-', 'admin-'}}"
                )
                return
    assert target_name is not None, (
        "KD-3 violated: `_fe_issuer_dep` not declared in facturacion.py"
    )
