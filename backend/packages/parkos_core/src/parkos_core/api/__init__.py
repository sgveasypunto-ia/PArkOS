"""parkos_core FastAPI building blocks (design §5).

- :mod:`.router_factory` — :func:`make_router` (uniform C+Q+U surface per table)
- :mod:`.deps` — dependency re-exports (get_session, get_tenant_ctx, etc.)
- :mod:`.middleware` — :class:`IdempotencyKeyMiddleware` (REQ-OP-04)

The DIAN-only boundary (design §10) is enforced inside :mod:`api.v1` via a
lazy import of ``parkos_core.dian.cloud_router`` that fires only when
``PARKOS_DEPLOY=cloud``. Branch images never see the cloud router module on
disk (image-level exclusion, design §10 Layer 1).
"""
from __future__ import annotations

from .deps import (
    get_session,
    get_tenant_ctx,
    requires_issuer,
)
from .middleware import IdempotencyKeyMiddleware
from .router_factory import make_router

__all__ = [
    "get_session",
    "get_tenant_ctx",
    "requires_issuer",
    "IdempotencyKeyMiddleware",
    "make_router",
]