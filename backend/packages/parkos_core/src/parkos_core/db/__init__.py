"""parkos_core database layer — async engine, session factory, and tenancy
SQLAlchemy event listener (design §9).

The migration ``env.py`` translates ``DATABASE_URL`` (``postgresql+asyncpg``)
to ``postgresql+psycopg2`` for Alembic's sync runtime. Application code uses
``get_session()`` which returns an :class:`AsyncSession`.
"""
from __future__ import annotations

from .base import Base
from .engine import get_session, sessionmaker, engine
from .tenancy import (
    TenantScopeViolationError,
    get_current_sucursal_uuid,
    set_tenant_context,
    install_tenant_event_listener,
)

__all__ = [
    "Base",
    "engine",
    "sessionmaker",
    "get_session",
    "get_current_sucursal_uuid",
    "set_tenant_context",
    "install_tenant_event_listener",
    "TenantScopeViolationError",
]