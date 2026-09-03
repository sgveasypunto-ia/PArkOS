"""FastAPI dependency re-exports (design §5).

Centralizes the imports so routers depend on a single module rather than
walking the package hierarchy. New dependencies added in future PRs land here.
"""
from __future__ import annotations

from ..auth.jwt_issuer_guard import requires_issuer
from ..auth.tenancy import TenantContext, get_tenant_ctx
from ..db.engine import get_session
from ..db.tenancy import install_tenant_event_listener

# Install the per-AsyncSession tenant filter on first import.
install_tenant_event_listener()

__all__ = [
    "get_session",
    "get_tenant_ctx",
    "TenantContext",
    "requires_issuer",
    "install_tenant_event_listener",
]