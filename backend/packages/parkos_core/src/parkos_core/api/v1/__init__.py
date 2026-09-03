"""parkos_core FastAPI v1 router package (PR1c placeholder).

PR1b ships a small set of v1 routers — this ``__init__`` aggregates them
so the apps (``api_admin_main`` and ``api_sucursal_main``) can mount
``/api/v1/*`` with a single ``include_router(v1_router)`` call.

Layout:

  - ``auth``        — REQ-42 / REQ-43 / REQ-45 (login + refresh + logout)
  - ``catalogos``   — REQ-OP-13 / REQ-02-V-CONSULTA (smoke mount: tipo-persona)

The DIAN-only boundary (design §10) is enforced by ``api_admin`` /
``api_sucursal`` apps at the FastAPI mount level: the apps choose which
routers to include, not this package. Future PRs add ``facturacion``,
``sync``, ``clientes``, ``envio_dian`` (cloud-only), etc.
"""
from __future__ import annotations

from fastapi import APIRouter

from . import auth, catalogos

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(catalogos.router)

__all__ = ["router"]