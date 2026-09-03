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
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Select, event, text
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


def extract_sucursales_permitidas(claims: Any) -> list[uuid_lib.UUID]:
    """Read ``sucursales_permitidas`` off a claims dict or a context object.

    Accepts either the decoded JWT claims (``dict``) returned by
    ``requires_issuer('admin-')`` or any object exposing the attribute
    (e.g. a future ``TenantContext`` extension). Malformed entries are
    dropped so a bad claim can only ever NARROW the scope (REQ-X2).
    """
    if isinstance(claims, dict):
        raw_list = claims.get("sucursales_permitidas") or []
    else:
        raw_list = getattr(claims, "sucursales_permitidas", None) or []

    out: list[uuid_lib.UUID] = []
    for raw in raw_list:
        try:
            out.append(raw if isinstance(raw, uuid_lib.UUID) else uuid_lib.UUID(str(raw)))
        except (ValueError, TypeError, AttributeError):
            continue
    return out


def apply_admin_scope(
    session: Any,  # AsyncSession | None — unused today, kept for a future hook
    statement: Select[Any],
    claims: Any,
) -> Select[Any]:
    """Append ``WHERE uuid = ANY(:permitidas)`` to an ``admin-`` query (T-PR10-04).

    Defense in depth (REQ-X2): route handlers call this helper so the scope
    filter lives in ONE place. Even when a handler forgets its own
    ``WHERE``, the returned statement is already restricted to the branches
    carried by the admin token.

    ``session`` is accepted (and ignored) so the signature stays stable when
    the filter moves into the ``do_orm_execute`` listener above.

    Behaviour:

    - Empty / missing ``sucursales_permitidas`` → ``WHERE FALSE`` (fail
      closed: an admin with no branches sees nothing, never everything).
    - Statement targeting an entity with ``uuid_sucursal`` → filter on that
      column. Otherwise filter on the entity's own ``uuid`` (the
      ``sucursal`` table case).
    """
    permitidas = extract_sucursales_permitidas(claims)
    if not permitidas:
        # Fail closed — a false predicate guarantees no rows leak through.
        return statement.where(text("FALSE"))

    entity = None
    for desc in getattr(statement, "column_descriptions", []) or []:
        candidate = desc.get("entity") if isinstance(desc, dict) else None
        if candidate is not None:
            entity = candidate
            break

    if entity is None:
        # Nothing to anchor the filter to; fail closed rather than widen.
        return statement.where(text("FALSE"))

    column = getattr(entity, "uuid_sucursal", None)
    if column is None:
        column = getattr(entity, "uuid", None)
    if column is None:
        return statement.where(text("FALSE"))

    return statement.where(column.in_(permitidas))


__all__ = [
    "TenantScopeViolationError",
    "_ctx_sucursal",
    "apply_admin_scope",
    "extract_sucursales_permitidas",
    "get_current_sucursal_uuid",
    "install_tenant_event_listener",
    "set_tenant_context",
]