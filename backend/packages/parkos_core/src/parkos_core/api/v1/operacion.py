"""Operation HTTP routes (PR5 — ingreso lifecycle event).

``ingreso`` is ``[L-E]`` (insert-only event). Writes MUST go through
``repo.event.record_event`` (REQ-30, REQ-33). NO PUT/DELETE — events are
append-only.

Custom ``GET /ingresos/{uuid}/estado`` reads the derived view
``V_INGRESO_ESTADO`` (REQ-32-E-DERIVED-ESTADO, SC-30). State values:
- ``abierto``: ingreso has no ``salidas`` row yet
- ``cerrado``: matching ``salidas`` row exists
- ``anulada``: matching ``anulaciones`` chain exists (PR6 mounts)
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_tenant_ctx, requires_issuer
from ...auth.tenancy import TenantContext
from ...db.engine import get_session
from ...models.L_E.ingreso import Ingreso
from ...repo.event import record_event
from ...schemas.operacion import (
    IngresoCreate,
    IngresoRead,
)

router = APIRouter(prefix="/operacion", tags=["operacion"])

_ingreso_issuer_dep = requires_issuer("operador-", "admin-")


class IngresoEstadoResponse(BaseModel):
    """Response shape for ``GET /ingresos/{uuid}/estado``.

    The state is DERIVED from ``V_INGRESO_ESTADO`` (or computed inline until
    PR6 mounts that view). Possible values: ``abierto``, ``cerrado``,
    ``anulada``.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid_ingreso: uuid_lib.UUID
    estado: str  # 'abierto' | 'cerrado' | 'anulada'
    fecha_ingreso: datetime | None = None
    uuid_sucursal: uuid_lib.UUID | None = None


@router.post(
    "/ingresos",
    response_model=IngresoRead,
    status_code=201,
    summary="Register a vehicle entry (ingreso, [L-E] event)",
)
async def create_ingreso(
    payload: IngresoCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_ingreso_issuer_dep),
) -> IngresoRead:
    """Insert-only write for an ingreso event.

    The Idempotency-Key header is checked by the FastAPI middleware
    (PR2 IdempotencyKeyMiddleware). Body goes through Pydantic validation
    (``IngresoCreate``). Persistence goes through ``repo.event.record_event``
    (REQ-30).
    """
    new_row = await record_event(
        session,
        Ingreso,
        actor_uuid=ctx.actor_uuid,
        new_attrs=payload.model_dump(exclude_none=True),
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return IngresoRead.model_validate(new_row)


@router.get(
    "/ingresos/{uuid}",
    response_model=IngresoRead,
    summary="Read a single ingreso (events are append-only — no history)",
)
async def get_ingreso(
    uuid: uuid_lib.UUID = Path(...),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_ingreso_issuer_dep),
) -> IngresoRead:
    row = (await session.execute(select(Ingreso).where(Ingreso.uuid == uuid))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "uuid": str(uuid)})
    return IngresoRead.model_validate(row)


@router.get(
    "/ingresos/{uuid}/estado",
    response_model=IngresoEstadoResponse,
    summary="Derived state of an ingreso (REQ-32, SC-30)",
)
async def get_ingreso_estado(
    uuid: uuid_lib.UUID = Path(...),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_ingreso_issuer_dep),
) -> IngresoEstadoResponse:
    """Compute the derived state of an ingreso.

    State machine (per SC-30):
    - ``anulada`` if an ``anulaciones`` chain references this ingreso (PR6)
    - ``cerrado`` if a ``salidas`` row references this ingreso (PR6)
    - ``abierto`` otherwise (no exits yet)

    Until PR6 mounts ``salidas`` and ``anulaciones``, we read the
    underlying ingreso + its linkage to ``salidas`` (if any). Returns
    ``abierto`` if no salidas row exists yet, ``cerrado`` otherwise.
    The ``anulada`` branch is a stub (always returns ``abierto`` here
    unless we detect a closed chain via timestamps).
    """
    # 1. Read the ingreso row first (404 if not found).
    ingreso = (await session.execute(select(Ingreso).where(Ingreso.uuid == uuid))).scalar_one_or_none()
    if ingreso is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "uuid": str(uuid)})

    # 2. Query the derived view V_INGRESO_ESTADO. The view is mounted by
    # PR6; for PR5 we query salidas directly (fallback).
    salidas_exists_stmt = text(
        "SELECT EXISTS(SELECT 1 FROM prod.salidas WHERE uuid_ingreso = :ingreso_uuid)"
    )
    salidas_exists = (await session.execute(salidas_exists_stmt, {"ingreso_uuid": str(uuid)})).scalar()

    # TODO: also detect ``anulada`` once PR6 mounts the anulaciones chain.
    estado = "cerrado" if salidas_exists else "abierto"

    return IngresoEstadoResponse(
        uuid_ingreso=ingreso.uuid,
        estado=estado,
        fecha_ingreso=ingreso.fecha_ingreso,
        uuid_sucursal=ingreso.uuid_sucursal,
    )


@router.get(
    "/ingresos",
    response_model=list[IngresoRead],
    summary="List ingresos with simple pagination",
)
async def list_ingresos(
    uuid_sucursal: uuid_lib.UUID | None = None,
    placa: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_ingreso_issuer_dep),
) -> list[IngresoRead]:
    """List recent ingresos (filters: uuid_sucursal, placa). No cursor pagination (yet)."""
    stmt = select(Ingreso)
    if uuid_sucursal is not None:
        stmt = stmt.where(Ingreso.uuid_sucursal == uuid_sucursal)
    if placa is not None:
        stmt = stmt.where(Ingreso.placa == placa)
    stmt = stmt.order_by(Ingreso.created_at.desc()).limit(min(limit, 200))
    result = await session.execute(stmt)
    return [IngresoRead.model_validate(r) for r in result.scalars().all()]


__all__ = ["router"]