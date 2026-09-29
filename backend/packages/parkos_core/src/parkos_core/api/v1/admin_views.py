"""Multi-sucursal admin views (PR10).

Cloud-only endpoints (T-PR10-01..03):

- ``GET /api/v1/sucursales`` — list permitted branches (scoped by the
  actor's currently-open ``usuarios_sucursal`` rows, read fresh).
- ``GET /api/v1/admin/sucursales/{uuid}/dashboard`` — aggregates for a
  single branch (ingresos_count, montos, sync_health, alerts).
- ``GET /api/v1/admin/me`` — actor identity + permissions + permitted
  branches (used by BranchSelector).

Cloud-only mount: imported on ``api_admin`` only (per ``api/v1/__init__.py``
DIAN boundary + this PR's wire step). ``api_sucursal`` does NOT mount
admin_views (REQ-X2: branch operators have no cross-branch visibility).

Issuer: ``admin-`` for all 3 endpoints. The issuer dependency
(:func:`~parkos_core.auth.jwt_issuer_guard.requires_issuer`) returns the
decoded claims, which is where ``sucursales_permitidas`` lives. These
routes deliberately do NOT depend on ``get_tenant_ctx``: that dependency
requires an ``X-Sucursal-Context`` header for ``admin-`` tokens, which
``/sucursales`` and ``/admin/me`` must answer BEFORE a branch is selected
(the BranchSelector calls them to learn which branches exist).

Read-only module: no INSERT/UPDATE/DELETE, no DELETE route (project
architectural principle #3 — the API exposes Consulta/Inserción/
Actualización only).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_session, requires_issuer
from ...db.tenancy import extract_sucursales_permitidas_fresh
from ...models.A.sync_log import SyncLog
from ...models.L_E.factura_electronica import FacturaElectronica
from ...models.L_E.ingreso import Ingreso
from ...models.L_W.alerta import Alerta
from ...models.V.permisos import Permisos
from ...models.V.permisos_usuario import PermisosUsuario
from ...models.V.sucursal import Sucursal
from ...models.V.usuarios import Usuarios

router = APIRouter(prefix="", tags=["admin"])

_admin_issuer_dep = requires_issuer("admin-")

AdminClaims = Annotated[dict[str, Any], Depends(_admin_issuer_dep)]
DbSession = Annotated[AsyncSession, Depends(get_session)]


# ============================================================================
# Response shapes
# ============================================================================


class SucursalListItem(BaseModel):
    """One row in the ``/sucursales`` list (T-PR10-01)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid: uuid_lib.UUID
    nombre: str | None
    ciudad: str | None
    uuid_tipo_sucursal: uuid_lib.UUID | None


class SucursalSyncStatus(BaseModel):
    """Nested ``sync_status`` block (T-PR10-01)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    last_sync_at: datetime | None
    last_error: str | None
    last_heartbeat_at: datetime | None


class SucursalItem(BaseModel):
    """Full ``/sucursales`` item (T-PR10-01)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid: uuid_lib.UUID
    nombre: str | None
    ciudad: str | None
    uuid_tipo_sucursal: uuid_lib.UUID | None
    sync_status: SucursalSyncStatus
    open_alerts_count: int
    last_pairing_at: datetime | None


class SucursalListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    items: list[SucursalItem]
    next_cursor: str | None


class DashboardSyncHealth(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    last_sync_at: datetime | None
    lag_seconds: int | None
    queue_depth: int


class SucursalDashboard(BaseModel):
    """``GET /admin/sucursales/{uuid}/dashboard`` (T-PR10-02)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid_sucursal: uuid_lib.UUID
    fecha: datetime
    ingresos_count: int
    ingresos_monto_total: float
    facturas_emitidas_count: int
    facturas_electronicas_count: int
    open_alertas_count: int
    sync_health: DashboardSyncHealth


class AdminMeResponse(BaseModel):
    """``GET /admin/me`` (T-PR10-03)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    actor_uuid: uuid_lib.UUID
    email: str | None
    rol: str | None
    sucursales_permitidas: list[uuid_lib.UUID]
    permissions: list[str]


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/sucursales",
    response_model=SucursalListResponse,
    summary="List branches the admin can manage (T-PR10-01, REQ-X2)",
)
async def list_sucursales(
    session: DbSession,
    claims: AdminClaims,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SucursalListResponse:
    """Return branches + sync status + alerts count + last pairing.

    Scope filter: queries ``prod.usuarios_sucursal`` fresh on every
    request (rather than reading the JWT claim ``sucursales_permitidas``
    which is captured at login time and would miss branches created in
    the same session). See
    :func:`~parkos_core.db.tenancy.extract_sucursales_permitidas_fresh`
    for the rationale and the security upside (revocations take effect
    immediately, not on next login).
    """
    actor_uuid = uuid_lib.UUID(claims["sub"])
    permitidas = await extract_sucursales_permitidas_fresh(
        session, actor_uuid=actor_uuid
    )

    if not permitidas:
        # Fail closed: admin with no open assignments sees nothing.
        return SucursalListResponse(items=[], next_cursor=None)

    stmt = (
        select(Sucursal)
        .where(
            Sucursal.vigente_hasta.is_(None),
            Sucursal.uuid.in_(permitidas),
        )
        .order_by(Sucursal.nombre)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()

    items: list[SucursalItem] = []
    for row in rows:
        # Belt-and-suspenders: ``Sucursal.uuid.in_(permitidas)`` already
        # restricts the SELECT, but a defensive belt-and-suspenders check
        # here keeps the contract documented at the item-construction
        # site. Cheap (set membership).
        if row.uuid not in permitidas:
            continue

        last_sync_stmt = (
            select(SyncLog)
            .where(SyncLog.uuid_sucursal == row.uuid)
            .order_by(SyncLog.timestamp_evento.desc())
            .limit(1)
        )
        last_sync = (await session.execute(last_sync_stmt)).scalars().first()

        open_alerts_stmt = (
            select(func.count())
            .select_from(Alerta)
            .where(
                Alerta.uuid_sucursal == row.uuid,
                Alerta.vigente_hasta.is_(None),
            )
        )
        open_alerts = (await session.execute(open_alerts_stmt)).scalar() or 0

        items.append(
            SucursalItem(
                uuid=row.uuid,
                nombre=row.nombre,
                ciudad=row.ciudad,
                uuid_tipo_sucursal=row.uuid_tipo_sucursal,
                sync_status=SucursalSyncStatus(
                    last_sync_at=last_sync.timestamp_evento if last_sync else None,
                    last_error=_last_error(last_sync),
                    last_heartbeat_at=last_sync.timestamp_evento if last_sync else None,
                ),
                open_alerts_count=int(open_alerts),
                last_pairing_at=None,  # pairing_tokens (PR8) — wired when shipped
            )
        )

    # Cursor pagination (REQ-OP-01) lands with the pairing_tokens join; this
    # PR returns the first page only and reports no continuation.
    return SucursalListResponse(items=items, next_cursor=None)


def _last_error(last_sync: SyncLog | None) -> str | None:
    """Render ``sync_log.operaciones_fallidas`` as a human-readable error.

    ``sync_log`` carries counters, not messages — the closest signal to a
    "last error" is a non-zero failure count on the most recent cycle.
    """
    if last_sync is None:
        return None
    fallidas = last_sync.operaciones_fallidas or 0
    if fallidas <= 0:
        return None
    return f"{int(fallidas)} operaciones fallidas en el ultimo ciclo"


def _queue_depth(last_sync: SyncLog | None) -> int:
    """Pending operations for the last cycle (sent minus succeeded)."""
    if last_sync is None:
        return 0
    enviadas = last_sync.operaciones_enviadas or 0
    exitosas = last_sync.operaciones_exitosas or 0
    return max(int(enviadas) - int(exitosas), 0)


@router.get(
    "/admin/sucursales/{uuid}/dashboard",
    response_model=SucursalDashboard,
    summary="Branch dashboard aggregates (T-PR10-02, REQ-X2)",
)
async def branch_dashboard(
    uuid: uuid_lib.UUID,
    session: DbSession,
    claims: AdminClaims,
    x_sucursal_context: Annotated[
        uuid_lib.UUID | None, Header(alias="X-Sucursal-Context")
    ] = None,
) -> SucursalDashboard:
    """Aggregate metrics for one branch.

    Requires ``X-Sucursal-Context`` matching the path UUID (400 if missing,
    403 if mismatched or outside the actor's open ``usuarios_sucursal``
    rows — REQ-X2). The scope check reads the DB fresh for the same reason
    as :func:`admin_me`: the JWT claim is a login-time snapshot. Every
    metric is one aggregate query (no N+1).
    """
    if x_sucursal_context is None:
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_sucursal_context"},
        )
    if x_sucursal_context != uuid:
        raise HTTPException(
            status_code=403,
            detail={"error": "x_sucursal_context_mismatch", "path_uuid": str(uuid)},
        )
    actor_uuid = uuid_lib.UUID(claims["sub"])
    if uuid not in await extract_sucursales_permitidas_fresh(
        session, actor_uuid=actor_uuid
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "unauthorized_sucursal_context"},
        )

    ingresos_count = (
        await session.execute(
            select(func.count()).select_from(Ingreso).where(Ingreso.uuid_sucursal == uuid)
        )
    ).scalar() or 0

    # ``ingreso`` carries no monetary column (the amount is derived at exit
    # via tarifas + facturas). The field is reported as 0.0 until the
    # salidas/facturas join lands; the shape stays stable for the UI.
    ingresos_monto_total = 0.0

    facturas_electronicas_count = (
        await session.execute(
            select(func.count())
            .select_from(FacturaElectronica)
            .where(FacturaElectronica.uuid_sucursal == uuid)
        )
    ).scalar() or 0

    open_alertas_count = (
        await session.execute(
            select(func.count())
            .select_from(Alerta)
            .where(Alerta.uuid_sucursal == uuid, Alerta.vigente_hasta.is_(None))
        )
    ).scalar() or 0

    last_sync = (
        await session.execute(
            select(SyncLog)
            .where(SyncLog.uuid_sucursal == uuid)
            .order_by(SyncLog.timestamp_evento.desc())
            .limit(1)
        )
    ).scalars().first()

    now = datetime.now(UTC).replace(tzinfo=None)
    lag_seconds: int | None = None
    if last_sync is not None and last_sync.timestamp_evento is not None:
        lag_seconds = max(int((now - last_sync.timestamp_evento).total_seconds()), 0)

    return SucursalDashboard(
        uuid_sucursal=uuid,
        fecha=now,
        ingresos_count=int(ingresos_count),
        ingresos_monto_total=ingresos_monto_total,
        facturas_emitidas_count=int(facturas_electronicas_count),
        facturas_electronicas_count=int(facturas_electronicas_count),
        open_alertas_count=int(open_alertas_count),
        sync_health=DashboardSyncHealth(
            last_sync_at=last_sync.timestamp_evento if last_sync else None,
            lag_seconds=lag_seconds,
            queue_depth=_queue_depth(last_sync),
        ),
    )


@router.get(
    "/admin/me",
    response_model=AdminMeResponse,
    summary="Actor identity + permissions + permitted branches (T-PR10-03)",
)
async def admin_me(
    session: DbSession,
    claims: AdminClaims,
) -> AdminMeResponse:
    """Return the actor's identity + RBAC permissions for the BranchSelector.

    ``sucursales_permitidas`` is read fresh from ``prod.usuarios_sucursal``
    rather than from the JWT claim, for the same reason as
    :func:`list_sucursales`: the claim is a login-time snapshot, so a branch
    created (and auto-assigned) in the current session would stay invisible
    until the token expires. This endpoint feeds the BranchSelector's own
    filter, so a stale claim here re-introduced the same symptom on the
    client even with ``/sucursales`` already reading fresh.
    """
    try:
        actor_uuid = uuid_lib.UUID(str(claims["sub"]))
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_token", "detail": "malformed_sub_claim"},
        ) from e

    usuario = (
        await session.execute(
            select(Usuarios).where(
                Usuarios.uuid == actor_uuid,
                Usuarios.vigente_hasta.is_(None),
            )
        )
    ).scalars().first()

    permisos_stmt = (
        select(Permisos.permiso)
        .join(PermisosUsuario, PermisosUsuario.uuid_permiso == Permisos.uuid)
        .where(
            PermisosUsuario.uuid_usuario == actor_uuid,
            PermisosUsuario.vigente_hasta.is_(None),
            Permisos.vigente_hasta.is_(None),
        )
    )
    permissions = [
        p for p in (await session.execute(permisos_stmt)).scalars().all() if p is not None
    ]

    permitidas = await extract_sucursales_permitidas_fresh(
        session, actor_uuid=actor_uuid
    )

    return AdminMeResponse(
        actor_uuid=actor_uuid,
        email=usuario.email if usuario else None,
        rol=usuario.rol if usuario else claims.get("rol"),
        sucursales_permitidas=permitidas,
        permissions=sorted(set(permissions)),
    )


__all__ = [
    "AdminMeResponse",
    "DashboardSyncHealth",
    "SucursalDashboard",
    "SucursalItem",
    "SucursalListItem",
    "SucursalListResponse",
    "SucursalSyncStatus",
    "router",
]
