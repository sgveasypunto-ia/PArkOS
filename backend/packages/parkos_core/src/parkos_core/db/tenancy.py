"""Tenant-scoping ContextVar + SQLAlchemy event listener (design §9).

Every request runs with a ``uuid_sucursal`` set by ``auth/tenancy.py``. The
listener here injects ``WHERE uuid_sucursal = :ctx_sucursal`` into every
SELECT/UPDATE/DELETE that touches a table which carries ``uuid_sucursal``.

Catalog tables (``permisos``, ``tipo_persona``, etc.) do not have
``uuid_sucursal`` and are unaffected. The listener's column scan makes this
decision per-entity; no manual ``WHERE uuid_sucursal = ...`` is needed in
router code.

Note on the target: ``do_orm_execute`` fires on the underlying sync
``Session`` that ``AsyncSession`` wraps. Listening on ``Session`` covers
both sync and async paths.
"""
from __future__ import annotations

import uuid as uuid_lib
from contextvars import ContextVar

from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.orm import Session

_ctx_sucursal: ContextVar[uuid_lib.UUID | None] = ContextVar(
    "ctx_sucursal_uuid",
    default=None,
)


class TenantScopeViolationError(HTTPException):
    """Raised when a query would touch rows outside the tenant context."""

    def __init__(self, detail: str = "tenant_scope_violation") -> None:
        super().__init__(status_code=403, detail={"error": detail})


def set_tenant_context(sucursal_uuid: uuid_lib.UUID) -> None:
    """Bind ``sucursal_uuid`` to the current async task for downstream queries."""
    _ctx_sucursal.set(sucursal_uuid)


def get_current_sucursal_uuid() -> uuid_lib.UUID | None:
    """Return the bound ``sucursal_uuid`` (or ``None`` for cloud-scope sync)."""
    return _ctx_sucursal.get()


def install_tenant_event_listener() -> None:
    """Attach the listener that auto-filters SELECT/UPDATE/DELETE by tenant.

    Idempotent: SQLAlchemy raises on duplicate registration; we guard with
    a flag so the function is safe at import time.
    """
    if getattr(install_tenant_event_listener, "_installed", False):
        return

    @event.listens_for(Session, "do_orm_execute")
    def _filter_by_sucursal(state: object) -> None:
        is_select = getattr(state, "is_select", False)
        is_update = getattr(state, "is_update", False)
        is_delete = getattr(state, "is_delete", False)
        if not (is_select or is_update or is_delete):
            return
        ctx_uuid = _ctx_sucursal.get()
        if ctx_uuid is None:
            return
        for tbl in getattr(state, "column_descriptions", []) or []:
            entity = tbl.get("entity") if isinstance(tbl, dict) else None
            if entity is None:
                continue
            if hasattr(entity, "uuid_sucursal"):
                state.statement = state.statement.where(  # type: ignore[attr-defined]
                    entity.uuid_sucursal == ctx_uuid,
                )

    install_tenant_event_listener._installed = True  # type: ignore[attr-defined]


__all__ = [
    "_ctx_sucursal",
    "set_tenant_context",
    "get_current_sucursal_uuid",
    "install_tenant_event_listener",
    "TenantScopeViolationError",
]