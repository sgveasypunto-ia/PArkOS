"""parkos_core API v1 routers — auth, catalogos, facturacion, workflows, etc.

Layer 2 of the DIAN-only boundary (design §10):
- Cloud images: ``PARKOS_DEPLOY=cloud`` → lazy-import ``dian.cloud_router``.
- Branch images: ``PARKOS_DEPLOY != "cloud"`` → no cloud router is mounted.
- Branch images physically lack the module on disk (Layer 1: Dockerfile
  .dockerignore excludes ``**/dian/cloud/**``). The branch image never
  reaches the lazy import.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter

from .auth import router as auth_router
from .catalogos import router as catalogos_router

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(catalogos_router)

# Lazy + conditional DIAN router import (Layer 2 of the boundary).
if os.environ.get("PARKOS_DEPLOY") == "cloud":
    try:
        from parkos_core.dian.cloud_router import router as dian_router

        router.include_router(dian_router)
    except ImportError as e:
        # Cloud image MUST have the module; ImportError here is a build defect.
        raise RuntimeError(
            f"cloud_router_unavailable_in_cloud_image: {e}"
        ) from e

__all__ = ["router", "auth_router", "catalogos_router"]