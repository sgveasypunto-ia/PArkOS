"""HU-F1.9 / T4 RED -- static-analysis tests for the facturacion handler module.

The 12-step ``create_factura`` + 5-step ``create_factura_pago`` handler chains
(design §7) are LOCKED IN ORDER by ``tests/static/test_factura_handler_step_order.py``
(T6). This module gates the structural invariants that the AST walks
depend on:

- Module exposes ``router`` (FastAPI ``APIRouter`` mount point) with the
  documented ``prefix='/facturacion'`` and ``tags=['facturacion']``.
- ``POST /factura`` is registered with ``response_model=FacturaRead`` and
  ``status_code=201``.
- ``POST /factura-pagos`` is registered with
  ``response_model=FacturaPagoRead`` and ``status_code=201``.
- Both handlers use the ``_helpers.no_store_headers`` helper (R-A6
  reuse from F1.6/F1.7).
- Both handlers use the ``_facturacion_issuer_dep`` dependency wired
  via ``requires_issuer(...)``.
- The single-commit invariant (KD-FACT-01) is checked via source
  inspection: exactly one ``await session.commit()`` in each handler
  body. (The AST walk in T6 enforces the same on the deeper
  token-by-token level.)

DB-coupled happy paths and error discriminators live in
``tests/integration/test_factura_create_db.py`` (T5.1..T5.11).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HANDLER_MODULE_PATH = Path(
    "packages/parkos_core/src/parkos_core/api/v1/facturacion.py"
)


def _load_handler_module():
    """Load ``api/v1/facturacion.py`` from disk and execute it.

    Mirrors F1.7's T4 RED pattern: bypass pytest's session-skip cascade
    by loading the module directly via ``importlib``.
    """
    sys.modules.pop("parkos_core.api.v1.facturacion", None)
    spec = importlib.util.spec_from_file_location(
        "parkos_core.api.v1.facturacion", str(HANDLER_MODULE_PATH)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_handler_module_imports_clean() -> None:
    """RED: handler module MUST be importable (syntax + import-graph OK)."""
    mod = _load_handler_module()
    assert mod is not None
    # Existing CRUD mount (PR6) MUST still be present after append.
    assert hasattr(mod, "router")
    assert hasattr(mod, "_mount_factura")


def test_router_prefix_and_tags() -> None:
    """RED: router carries the documented prefix + tags."""
    mod = _load_handler_module()
    assert mod.router.prefix == "/facturacion"
    assert "facturacion" in mod.router.tags


def test_post_factura_registered_with_correct_response_model() -> None:
    """RED: ``POST /factura`` route is registered with status_code=201 and
    the expected ``FacturaRead`` response model."""
    from fastapi.routing import APIRoute
    from parkos_core.schemas.facturacion import FacturaRead

    mod = _load_handler_module()
    routes = [r for r in mod.router.routes if isinstance(r, APIRoute)]
    # FastAPI exposes the FULL path including the router prefix.
    factura_routes = [r for r in routes if r.path == "/facturacion/factura"]
    assert factura_routes, "POST /facturacion/factura route not registered"
    assert factura_routes[0].status_code == 201
    assert factura_routes[0].response_model is FacturaRead


def test_post_factura_pagos_registered_with_correct_response_model() -> None:
    """RED: ``POST /factura-pagos`` route is registered with status_code=201."""
    from fastapi.routing import APIRoute
    from parkos_core.schemas.facturacion import FacturaPagoRead

    mod = _load_handler_module()
    routes = [r for r in mod.router.routes if isinstance(r, APIRoute)]
    pagos_routes = [r for r in routes if r.path == "/facturacion/factura-pagos"]
    assert pagos_routes, "POST /facturacion/factura-pagos route not registered"
    assert pagos_routes[0].status_code == 201
    assert pagos_routes[0].response_model is FacturaPagoRead


def test_create_factura_includes_all_12_step_markers() -> None:
    """RED: source contains markers for the 12-step chain (D-HU-F1.9-11).

    The markers are source comments inside ``create_factura`` body. The
    AST walk (T6.1) enforces the EXACT order; here we only check that
    all 12 markers exist so a future-dev that deletes a step fails this
    gate before the AST walk runs.
    """
    src = HANDLER_MODULE_PATH.read_text(encoding="utf-8")
    required_markers = [
        "# --- Step 1:",
        "# --- Step 2:",
        "# --- Step 3:",
        "# --- Step 4:",
        "# --- Step 5:",
        "# --- Step 6:",
        "# --- Step 7:",
        "# --- Step 8:",
        "# --- Step 9:",
        "# --- Step 10:",
        "# --- Step 11:",
        "# --- Step 12:",
    ]
    for marker in required_markers:
        assert marker in src, (
            f"step marker missing from create_factura source: {marker!r}"
        )


def test_create_factura_pago_includes_all_5_step_markers() -> None:
    """RED: source contains markers for the 5-step chain."""
    src = HANDLER_MODULE_PATH.read_text(encoding="utf-8")
    for marker in (
        "# --- Step 1:",
        "# --- Step 2:",
        "# --- Step 3:",
        "# --- Step 4:",
        "# --- Step 5:",
    ):
        assert marker in src, (
            f"step marker missing from create_factura_pago source: {marker!r}"
        )


def test_handler_uses_no_store_helper() -> None:
    """RED: source imports ``no_store_headers`` + ``apply_no_store_header``.

    R-A6 reuse from F1.6/F1.7 -- the helpers in ``api/v1/_helpers.py``
    enforce ``Cache-Control: no-store`` on every response. The facturacion
    handler MUST go through them (no inline ``headers={'Cache-Control': ...}``).
    """
    src = HANDLER_MODULE_PATH.read_text(encoding="utf-8")
    assert "no_store_headers" in src, (
        "facturacion handler MUST call no_store_headers() from _helpers."
    )
    assert "apply_no_store_header" in src, (
        "facturacion handler MUST call apply_no_store_header(response) on success."
    )


def test_handler_uses_requires_issuer_dependency() -> None:
    """RED: handler wires the issuer-prefix guard for both endpoints."""
    src = HANDLER_MODULE_PATH.read_text(encoding="utf-8")
    assert "requires_issuer" in src, (
        "facturacion handler MUST call requires_issuer(...) for KD-3 chain."
    )
    assert "_facturacion_issuer_dep" in src, (
        "facturacion handler MUST define _facturacion_issuer_dep dep."
    )


def test_handler_single_commit_invariant() -> None:
    """RED: each handler body has exactly ONE ``await session.commit()`` call.

    KD-FACT-01 invariant -- the AST walk in T6 enforces this on the full
    module; this test gives an early failure with a clearer message.
    The file ALSO contains docstring mentions of ``await session.commit()``
    (in summary + step descriptions) so we use a regex that matches the
    call form ONLY (preceded by indentation, NOT a triple-quote line).

    Count bumped 4 -> 5 (2026-09-25, HU-F8.3 ajuste 2026-09-25-c):
    ``create_factura_servicio`` (factura de servicio suelto sin
    ``uuid_salida``, para reimpresión de tiquete) is a 5th handler in
    this same module, with its own single commit -- it does NOT modify
    ``create_factura``/``create_factura_pago``/``create_factura_electronica``/
    ``retry_envio_dian``.
    """
    import re

    src = HANDLER_MODULE_PATH.read_text(encoding="utf-8")
    # Match indented ``await session.commit()`` — excludes docstring occurrences.
    pattern = re.compile(r"^\s+await session\.commit\(\)", re.MULTILINE)
    commit_count = len(pattern.findall(src))
    assert commit_count == 5, (
        f"Expected exactly 5 commits (one per F1.9+F1.10+HU-F8.3 handler), "
        f"found {commit_count}. KD-FACT-01 invariant violated: each handler "
        "MUST commit exactly once."
    )
