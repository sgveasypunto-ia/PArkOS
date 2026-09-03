"""parkos_core auth helpers — JWT, permissions, tenancy (design §7-9).

PR1b ships:
- :mod:`.jwt_issuer_guard` — three-issuer verification (``admin-``, ``operador-``, ``sync-agent-``)
- :mod:`.permissions` — ``require_permission(codigo)`` dependency
- :mod:`.tenancy` — ``TenantContext`` + ``X-Sucursal-Context`` enforcement
- :mod:`.tokens` — ``issue_token``/``verify_token`` with grace rotation

The ``passwords`` helper (bcrypt 12+) is bootstrap-owned and lives at
``dian/common/`` in the bootstrap layout; deferred here.
"""
from __future__ import annotations

from .jwt_issuer_guard import (
    CrossIssuerError,
    InvalidTokenError,
    requires_issuer,
    verify_jwt,
)
from .permissions import require_permission
from .tenancy import (
    MissingSucursalContextError,
    TenantContext,
    TenantScopeViolationError,
    UnauthorizedSucursalContextError,
    get_tenant_ctx,
)
from .tokens import (
    issue_token,
    verify_token,
)

__all__ = [
    "CrossIssuerError",
    "InvalidTokenError",
    "requires_issuer",
    "verify_jwt",
    "require_permission",
    "TenantContext",
    "TenantScopeViolationError",
    "MissingSucursalContextError",
    "UnauthorizedSucursalContextError",
    "get_tenant_ctx",
    "issue_token",
    "verify_token",
]