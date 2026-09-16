"""HU-F1.11 / T5.1 + T5.2 + T5.3 — GAP-BE-04 fix verification + router wiring.

Three coordinated assertions live here, all driven by source-level AST
walks (no DB required):

  * **T5.1** — ``api/v1/workflows.py`` line 74 carries
    ``"reimprimir_ticket"`` AND does NOT carry the legacy
    ``"emitir_reimpresion"`` typo. This is the single-line
    GAP-BE-04 reconciliation that unblocks the existing factory-mounted
    GET C+Q surface for operators with the canonical permission.

  * **T5.2** — The legacy ``emitir_reimpresion`` token is not used
    anywhere else in the workflows router config (defense in depth:
    a future operator that inherits the typo would re-introduce the
    blocker).

  * **T5.3** — The new ``workflows_reimpresion`` router is mounted
    in the v1 aggregator with two POST endpoints:

      - POST ``/workflows/reimpresion-ticket`` (201)
      - POST ``/workflows/reimpresion-ticket/{uuid}/anular`` (201)

    Both handlers MUST declare a ``Depends(_reimpresion_issuer_dep)``
    parameter (KD-3 issuer chain) — wired by the handler module and
    exercised by these walks.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


_WORKFLOWS_ROUTER_FILE = (
    _PARKOS_CORE_SRC
    / "parkos_core"
    / "api"
    / "v1"
    / "workflows.py"
)
_REIMPRESION_HANDLER_FILE = (
    _PARKOS_CORE_SRC
    / "parkos_core"
    / "api"
    / "v1"
    / "workflows_reimpresion.py"
)
_V1_AGGREGATOR_FILE = (
    _PARKOS_CORE_SRC
    / "parkos_core"
    / "api"
    / "v1"
    / "__init__.py"
)


# ---------------------------------------------------------------------------
# T5.1 — GAP-BE-04 single-line fix at api/v1/workflows.py:74
# ---------------------------------------------------------------------------


def test_workflows_router_config_uses_reimprimir_ticket_not_emitir_reimpresion() -> None:
    """T5.1: the factory permission for ``reimpresion-ticket`` is the canonical one.

    Walks the source of ``api/v1/workflows.py``, locates the
    ``_ROUTER_CONFIG`` dict, and asserts the value tuple for
    ``"reimpresion-ticket"`` is ``("operador-,admin-", "reimprimir_ticket")``.
    The legacy typo ``"emitir_reimpresion"`` MUST NOT appear anywhere
    in the file.
    """
    source = _WORKFLOWS_ROUTER_FILE.read_text(encoding="utf-8")
    assert "emitir_reimpresion" not in source, (
        "GAP-BE-04 violated: `api/v1/workflows.py` still references the "
        "legacy permission `emitir_reimpresion`; operators with the "
        "canonical `reimprimir_ticket` permission would receive 403 on "
        "the reimpresion-ticket resource (REQ-OPS-076 Scenario 3)."
    )

    tree = ast.parse(source)
    router_config_value: dict[str, tuple[str, str]] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "_ROUTER_CONFIG"
            and isinstance(node.value, ast.Dict)
        ):
            for key, val in zip(node.value.keys, node.value.values):
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(val, ast.Tuple)
                    and len(val.elts) == 2
                ):
                    issuer, perm = val.elts
                    if (
                        isinstance(issuer, ast.Constant)
                        and isinstance(perm, ast.Constant)
                    ):
                        router_config_value[key.value] = (
                            issuer.value,
                            perm.value,
                        )

    assert "reimpresion-ticket" in router_config_value, (
        "GAP-BE-04 violated: `_ROUTER_CONFIG` does not declare a "
        "`reimpresion-ticket` entry"
    )
    issuer, perm = router_config_value["reimpresion-ticket"]
    assert issuer == "operador-,admin-", (
        f"GAP-BE-04 violated: `reimpresion-ticket` issuer is `{issuer}`; "
        f"expected `operador-,admin-`"
    )
    assert perm == "reimprimir_ticket", (
        f"GAP-BE-04 violated: `reimpresion-ticket` permission is `{perm}`; "
        f"expected `reimprimir_ticket` (canonical DEC-TKT-01 permission "
        f"unblocks operators holding it; legacy `emitir_reimpresion` typo "
        f"would 403 them, REQ-OPS-076 Scenario 3)"
    )


# ---------------------------------------------------------------------------
# T5.2 — Legacy typo is not used anywhere else in the v1 router surface
# ---------------------------------------------------------------------------


def test_no_legacy_emitir_reimpresion_in_v1_router_surface() -> None:
    """T5.2: defense in depth — the typo'd permission is not referenced.

    Greps the entire ``api/v1`` package for the legacy
    ``emitir_reimpresion`` string. The only legitimate reference would
    be a comment explaining the GAP-BE-04 reconciliation history; we
    treat any other reference as a regression.
    """
    v1_dir = _PARKOS_CORE_SRC / "parkos_core" / "api" / "v1"
    offenders: list[tuple[Path, int, str]] = []
    for py_file in sorted(v1_dir.rglob("*.py")):
        if py_file.name == "__init__.py" and "GAP-BE-04" in py_file.read_text(
            encoding="utf-8"
        ):
            continue
        try:
            lines = py_file.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for idx, line in enumerate(lines, start=1):
            if "emitir_reimpresion" in line:
                offenders.append((py_file, idx, line.strip()))

    assert not offenders, (
        "GAP-BE-04 violated: legacy permission `emitir_reimpresion` still "
        "appears in api/v1 source:\n"
        + "\n".join(f"  {p.relative_to(_PARKOS_CORE_SRC)}:{ln}: {s}" for p, ln, s in offenders)
    )


# ---------------------------------------------------------------------------
# T5.3 — Router wiring + KD-3 issuer dep on both handlers
# ---------------------------------------------------------------------------


def test_workflows_reimpresion_router_is_mounted_in_v1_aggregator() -> None:
    """T5.3: the reimpresion router is wired into the v1 aggregator.

    Asserts the aggregator imports ``workflows_reimpresion`` AND
    ``include_router``s its ``router`` attribute onto the v1 router.
    """
    source = _V1_AGGREGATOR_FILE.read_text(encoding="utf-8")
    assert "workflows_reimpresion" in source, (
        "T5.3 violated: `workflows_reimpresion` is not imported by "
        "`api/v1/__init__.py`; the POST endpoints would not be registered "
        "on the FastAPI app (REQ-OPS-075 + REQ-OPS-077 unreachable)."
    )
    assert "include_router(workflows_reimpresion.router)" in source, (
        "T5.3 violated: `api/v1/__init__.py` does not call "
        "`include_router(workflows_reimpresion.router)`; the two POST "
        "endpoints would not appear in the OpenAPI schema."
    )


def test_create_reimpresion_endpoint_is_registered_with_201() -> None:
    """T5.3: POST /workflows/reimpresion-ticket is mounted with POST + 201."""
    from parkos_core.api.v1.workflows_reimpresion import router

    match = next(
        (
            r
            for r in router.routes
            if hasattr(r, "path") and r.path == "/workflows/reimpresion-ticket"
        ),
        None,
    )
    assert match is not None, (
        "POST /workflows/reimpresion-ticket route is not registered on the "
        "workflows_reimpresion router"
    )
    assert "POST" in match.methods, (
        f"POST /workflows/reimpresion-ticket is mounted with methods={match.methods}; "
        f"expected POST"
    )
    assert match.status_code == 201, (
        f"POST /workflows/reimpresion-ticket has status_code={match.status_code}; "
        f"expected 201 (resource creation)"
    )


def test_anular_reimpresion_endpoint_is_registered_with_201() -> None:
    """T5.3: POST /workflows/reimpresion-ticket/{uuid}/anular is mounted."""
    from parkos_core.api.v1.workflows_reimpresion import router

    match = next(
        (
            r
            for r in router.routes
            if hasattr(r, "path")
            and r.path == "/workflows/reimpresion-ticket/{uuid_reimpresion}/anular"
        ),
        None,
    )
    assert match is not None, (
        "POST /workflows/reimpresion-ticket/{uuid}/anular route is not registered"
    )
    assert "POST" in match.methods, (
        f"POST /workflows/reimpresion-ticket/{{uuid}}/anular mounted with "
        f"methods={match.methods}"
    )
    assert match.status_code == 201


def _handler_uses_reimpresion_issuer_dep(handler_name: str, dep_name: str) -> bool:
    """Return True iff ``handler_name`` declares ``_claims: None = Depends(dep_name)``."""
    tree = ast.parse(_REIMPRESION_HANDLER_FILE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == handler_name:
            for arg in (
                node.args.args + node.args.kwonlyargs + node.args.posonlyargs
            ):
                if arg.arg != "_claims":
                    continue
                # Walk the defaults to find the Depends(dep_name) call.
                defaults = list(node.args.defaults)
                # Pad defaults with leading ``None`` placeholders so we can
                # index by arg position; align with positional args length.
                positional_args = node.args.args
                padded_defaults = [None] * (
                    len(positional_args) - len(defaults)
                ) + defaults
                default = padded_defaults[-1] if padded_defaults else None
                if (
                    isinstance(default, ast.Call)
                    and isinstance(default.func, ast.Name)
                    and default.func.id == "Depends"
                    and default.args
                    and isinstance(default.args[0], ast.Name)
                    and default.args[0].id == dep_name
                ):
                    return True
    return False


def test_create_handler_uses_reimpresion_issuer_dep() -> None:
    """T5.3 KD-3: ``create_reimpresion_ticket`` depends on _reimpresion_issuer_dep."""
    assert _handler_uses_reimpresion_issuer_dep(
        "create_reimpresion_ticket", "_reimpresion_issuer_dep"
    ), (
        "KD-3 violated: `create_reimpresion_ticket` does NOT depend on "
        "`_reimpresion_issuer_dep`; anon callers could mint a reimpresion row."
    )


def test_anular_handler_uses_anular_reimpresion_issuer_dep() -> None:
    """T5.3 KD-3: ``anular_reimpresion_ticket`` depends on _anular_reimpresion_issuer_dep."""
    assert _handler_uses_reimpresion_issuer_dep(
        "anular_reimpresion_ticket", "_anular_reimpresion_issuer_dep"
    ), (
        "KD-3 violated: `anular_reimpresion_ticket` does NOT depend on "
        "`_anular_reimpresion_issuer_dep`; anon callers could close a chain "
        "(DEC-TKT-06 separate permission gate)."
    )


def test_reimpresion_issuer_deps_use_operador_admin_scope() -> None:
    """T5.3 KD-3: both issuer deps share the same ``operador-,admin-`` prefix.

    Asserts the two ``requires_issuer("operador-", "admin-")`` declarations
    are intact at the top of the handler module — a future edit that
    accidentally narrows the scope would silently lock out branch
    operators.
    """
    source = _REIMPRESION_HANDLER_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    found_deps: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id not in {
            "_reimpresion_issuer_dep",
            "_anular_reimpresion_issuer_dep",
        }:
            continue
        if not (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "requires_issuer"
            and all(isinstance(a, ast.Constant) for a in node.value.args)
        ):
            continue
        found_deps[target.id] = {a.value for a in node.value.args}
    assert set(found_deps.keys()) == {
        "_reimpresion_issuer_dep",
        "_anular_reimpresion_issuer_dep",
    }, (
        f"KD-3 violated: missing issuer dep declaration(s); found {found_deps}"
    )
    for dep_name, prefixes in found_deps.items():
        assert prefixes == {"operador-", "admin-"}, (
            f"KD-3 violated: `{dep_name}` uses prefixes {prefixes}; expected "
            f"exactly {{'operador-', 'admin-'}}"
        )
