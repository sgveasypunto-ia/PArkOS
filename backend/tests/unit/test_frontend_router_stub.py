"""HU-F1.9 / T7.3 -- Frontend-facing router stub at ``apps/facturacion/router.py``.

The ``apps/facturacion/router.py`` is the contract surface for the F1.11
React app. It registers the same 2 endpoints as the canonical
``parkos_core.api.v1.facturacion.router`` so the frontend can rely on a
single mount point regardless of where the backend runs.

This module gates:

- The router stub file exists.
- It exposes ``router`` (FastAPI ``APIRouter`` instance).
- Both ``POST /factura`` and ``POST /factura-pagos`` are registered on
  the router.

DB-free: pure import + AST inspection.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROUTER_STUB_PATH = Path("apps/facturacion/router.py")


def _load_stub_module():
    """Load ``apps/facturacion/router.py`` via importlib (mirrors F1.9
    static-analysis test pattern: bypass pytest session-skip cascade)."""
    spec = importlib.util.spec_from_file_location(
        "facturacion_router_stub", str(ROUTER_STUB_PATH)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_router_stub_file_existe() -> None:
    """RED: router stub file MUST exist at apps/facturacion/router.py."""
    assert ROUTER_STUB_PATH.is_file(), (
        f"Router stub missing at {ROUTER_STUB_PATH}. "
        "Author it as a thin FastAPI router re-exporting the F1.9 endpoints."
    )


def test_router_stub_expone_router_apirouter() -> None:
    """RED: the stub MUST expose a FastAPI ``APIRouter`` named ``router``."""
    from fastapi import APIRouter

    mod = _load_stub_module()
    assert hasattr(mod, "router"), (
        "apps/facturacion/router.py MUST expose a `router` attribute."
    )
    assert isinstance(mod.router, APIRouter), (
        f"apps.facturacion.router.router MUST be an APIRouter instance, "
        f"got {type(mod.router).__name__}."
    )


def test_router_stub_registra_dos_endpoints() -> None:
    """RED: both POST /factura and POST /factura-pagos MUST be registered.

    Mirrors ``tests/unit/test_facturacion_handler_structure.py`` but
    against the frontend-facing stub.
    """
    from fastapi.routing import APIRoute

    mod = _load_stub_module()
    routes = [r for r in mod.router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert any("/factura" in p for p in paths), (
        "POST /factura not registered in apps/facturacion/router.py. "
        f"Found paths: {sorted(paths)}"
    )
    assert any("factura-pagos" in p for p in paths), (
        "POST /factura-pagos not registered in apps/facturacion/router.py. "
        f"Found paths: {sorted(paths)}"
    )
