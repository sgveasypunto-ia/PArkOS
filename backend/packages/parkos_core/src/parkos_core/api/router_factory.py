"""parkos_core FastAPI router factory (design §5).

Generates the uniform C+Q+U surface per table:
- ``GET    /<resource>`` — list with cursor pagination (REQ-OP-01)
- ``GET    /<resource>/{uuid}`` — current version (filters by ``vigente_hasta IS NULL``)
- ``GET    /<resource>/{uuid}/history`` — all versions (history endpoint, REQ-05)
- ``POST   /<resource>`` — insert (REQ-03 / REQ-10)
- ``PUT    /<resource>/{uuid}`` — close+insert for [V] (REQ-04)
- NO DELETE — defense in depth (SC-04), enforced at static test layer.

PR1b supports ``repo_kind="versioned"`` and ``"session_cycle"``. Other kinds
(``"append_only"``, ``"event"``, ``"workflow"``) are stubbed in PR1b and
filled in by their respective PRs.
"""
from __future__ import annotations

import logging
import uuid as uuid_lib
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.tenancy import TenantContext
from ..db.engine import get_session
from ..repo.pagination import Cursor, InvalidCursorError, decode as cursor_decode
from ..repo.pagination import encode as cursor_encode
from ..repo.versioned import close_and_insert, current_version
from .deps import get_tenant_ctx, requires_issuer

if TYPE_CHECKING:
    from pydantic import BaseModel

logger = logging.getLogger(__name__)


def make_router(
    *,
    resource: str,
    model_cls: type,
    read_schema: type["BaseModel"],
    read_list_schema: type["BaseModel"],
    create_schema: type["BaseModel"] | None = None,
    update_schema: type["BaseModel"] | None = None,
    repo_kind: str = "versioned",
    derived_view: str | None = None,
    issuer_required: str,
    permission_required: str | None = None,
    write_enabled: bool = True,
    transition_states: list[str] | None = None,
) -> APIRouter:
    """Build the C+Q+U router for ``model_cls``.

    See design §5 for the full contract.

    Args:
        resource: URL slug (``"tipo-persona"``).
        model_cls: ORM class (e.g. ``TipoPersona``).
        read_schema: Pydantic Read schema.
        read_list_schema: Pydantic ReadList schema.
        create_schema: Pydantic Create schema (or ``None`` if writes disabled).
        update_schema: Pydantic Update schema.
        repo_kind: ``"versioned"`` (PR1b), ``"session_cycle"`` (PR1b),
            ``"append_only"``, ``"event"``, ``"workflow"`` (later PRs).
        derived_view: Optional derived view name (reserved for PR3+).
        issuer_required: Comma-separated issuer prefixes (e.g. ``"admin-,operador-"``).
        permission_required: Optional permission code (REQ-OP-13).
        write_enabled: Whether to mount POST + PUT endpoints.
        transition_states: Reserved for [L-W] tables (later PRs).
    """
    router = APIRouter(prefix=f"/{resource}", tags=[resource])

    issuers = [s.strip() for s in issuer_required.split(",")]
    issuer_dep = requires_issuer(*issuers)

    # Lazy import to avoid the dependency cycle with permissions.py at module
    # load time.
    from ..auth.permissions import require_permission

    perm_dependency = (
        require_permission(permission_required) if permission_required else None
    )

    # --- READ: list with cursor pagination ---
    @router.get("", response_model=read_list_schema)
    async def list_endpoint(
        cursor: str | None = Query(None),
        limit: int = Query(50, ge=1, le=200),
        session: AsyncSession = Depends(get_session),
        ctx: TenantContext = Depends(get_tenant_ctx),
        _claims: None = Depends(issuer_dep),
    ):
        try:
            decoded = cursor_decode(cursor) if cursor else None
        except InvalidCursorError as e:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_cursor", "detail": str(e)},
            )

        # Base query — only "current" rows for [V] tables (vigente_hasta IS NULL).
        stmt = select(model_cls)
        if hasattr(model_cls, "vigente_hasta"):
            stmt = stmt.where(model_cls.vigente_hasta.is_(None))
        stmt = stmt.order_by(model_cls.vigente_desde.desc(), model_cls.uuid.asc())
        if decoded is not None:
            stmt = stmt.where(
                (model_cls.vigente_desde < decoded.vigente_desde)
                | (
                    (model_cls.vigente_desde == decoded.vigente_desde)
                    & (model_cls.uuid > uuid_lib.UUID(decoded.uuid))
                )
            )
        stmt = stmt.limit(limit + 1)

        result = await session.execute(stmt)
        rows = list(result.scalars().all())

        next_cursor: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = cursor_encode(
                Cursor(
                    vigente_desde=last.vigente_desde.isoformat(),
                    uuid=str(last.uuid),
                )
            )

        items = [read_schema.model_validate(row) for row in rows]
        return read_list_schema(items=items, next_cursor=next_cursor)

    # --- READ: current single row ---
    @router.get("/{uuid}", response_model=read_schema)
    async def get_endpoint(
        uuid: uuid_lib.UUID = Path(...),
        session: AsyncSession = Depends(get_session),
        _ctx: TenantContext = Depends(get_tenant_ctx),
        _claims: None = Depends(issuer_dep),
    ):
        row = await current_version(session, model_cls, uuid)
        if row is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "uuid": str(uuid)},
            )
        return read_schema.model_validate(row)

    # --- READ: full history (all versions for the same business identity) ---
    if hasattr(model_cls, "vigente_hasta"):
        @router.get("/{uuid}/history", response_model=list[read_schema])
        async def history_endpoint(
            uuid: uuid_lib.UUID = Path(...),
            session: AsyncSession = Depends(get_session),
            _ctx: TenantContext = Depends(get_tenant_ctx),
            _claims: None = Depends(issuer_dep),
        ):
            stmt = (
                select(model_cls)
                .where(model_cls.uuid == uuid)
                .order_by(model_cls.vigente_desde.desc())
            )
            result = await session.execute(stmt)
            rows = list(result.scalars().all())
            return [read_schema.model_validate(r) for r in rows]

    # --- WRITE: POST (insert) + PUT (close+insert) ---
    extra_deps = [Depends(perm_dependency)] if perm_dependency is not None else []

    if write_enabled and repo_kind == "versioned" and create_schema is not None:
        @router.post(
            "",
            response_model=read_schema,
            status_code=201,
            dependencies=extra_deps,
        )
        async def create_endpoint(
            payload,  # FastAPI injects create_schema instance; using `Any` here
            session: AsyncSession = Depends(get_session),
            ctx: TenantContext = Depends(get_tenant_ctx),
            _claims: None = Depends(issuer_dep),
        ):
            payload_dict = payload.model_dump(exclude_none=True)
            new_row = await close_and_insert(
                session,
                model_cls,
                current_uuid=None,
                new_attrs=payload_dict,
                actor_uuid=ctx.actor_uuid,
                log_tx=True,
            )
            await session.commit()
            await session.refresh(new_row)
            return read_schema.model_validate(new_row)

        if update_schema is not None:
            @router.put(
                "/{uuid}",
                response_model=read_schema,
                dependencies=extra_deps,
            )
            async def update_endpoint(
                payload,  # FastAPI injects update_schema instance
                uuid: uuid_lib.UUID = Path(...),
                session: AsyncSession = Depends(get_session),
                ctx: TenantContext = Depends(get_tenant_ctx),
                _claims: None = Depends(issuer_dep),
            ):
                payload_dict = payload.model_dump(exclude_none=True)
                new_row = await close_and_insert(
                    session,
                    model_cls,
                    current_uuid=uuid,
                    new_attrs=payload_dict,
                    actor_uuid=ctx.actor_uuid,
                    log_tx=True,
                )
                await session.commit()
                await session.refresh(new_row)
                return read_schema.model_validate(new_row)

    elif write_enabled and repo_kind == "session_cycle" and create_schema is not None:
        # Session-cycle tables expose only POST (record event) and PUT (close).
        # PR7 fleshes out the full set.
        @router.post("", response_model=read_schema, status_code=201)
        async def create_session_endpoint(
            payload,  # FastAPI injects create_schema instance
            session: AsyncSession = Depends(get_session),
            ctx: TenantContext = Depends(get_tenant_ctx),
            _claims: None = Depends(issuer_dep),
        ):
            from ..repo.session_cycle import record_login

            row = await record_login(
                session,
                usuario_uuid=payload.uuid_usuario,
                sucursal_uuid=payload.uuid_sucursal,
                actor_uuid=ctx.actor_uuid,
            )
            await session.commit()
            await session.refresh(row)
            return read_schema.model_validate(row)

    # The derived_view argument is reserved for PR3+ (e.g. V_FACTURA_ESTADO).
    # It's accepted here so future tables can pass it without changing the
    # factory signature; PR1b emits no route for it.
    _ = derived_view
    _ = transition_states

    return router


__all__ = ["make_router"]