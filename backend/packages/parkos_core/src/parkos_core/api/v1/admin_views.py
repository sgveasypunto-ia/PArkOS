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
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_session, requires_issuer
from ...db.tenancy import extract_sucursales_permitidas_fresh
from ...models.A.alert_types import AlertTypes
from ...models.A.factura_pagos import FacturaPagos
from ...models.A.salidas import Salidas
from ...models.A.sync_log import SyncLog
from ...models.L_E.factura_electronica import FacturaElectronica
from ...models.L_E.facturas import Facturas
from ...models.L_E.ingreso import Ingreso
from ...models.L_W.alerta import Alerta
from ...models.L_W.anulaciones import Anulaciones
from ...models.L_W.envio_dian import EnvioDian
from ...models.V.cantidad_vehiculos_sucursal import CantidadVehiculosSucursal
from ...models.V.permisos import Permisos
from ...models.V.permisos_usuario import PermisosUsuario
from ...models.V.subscripciones_cliente import SubscripcionesCliente
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


class DashboardOcupacionAgregada(BaseModel):
    """Aggregate occupancy across the resolved branch set (HU-F17.1)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    ocupados: int
    capacidad: int
    porcentaje: float | None  # None when capacidad == 0 (undefined, not zero)


class DashboardSuscripcionesActivas(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    count: int


class DashboardMedioPagoItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    medio_pago: str
    monto_total: float


class DashboardTopSucursalItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid_sucursal: uuid_lib.UUID
    nombre: str | None
    monto_total: float


class DashboardSyncAgregado(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    sucursales_ok: int
    sucursales_degradadas: int
    queue_depth_total: int
    max_lag_seconds: int | None


class DashboardAlertaSeveridadItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    severity: str
    count: int


class DashboardEstadoFEItem(BaseModel):
    """One bucket of the FE-send-status breakdown (ChartPie ``estado FE 24h``).

    ``prod.factura_electronica`` carries no clean DIAN acceptance-state
    column (no ``estado``/``estado_dian`` field exists on the real schema —
    verified against the model, not assumed from plan.md). The real signal
    available is whether an ``envio_dian`` row recorded a provider response
    for that invoice. ``estado`` is therefore one of ``'enviada'``
    (at least one ``envio_dian.respuesta_proveedor IS NOT NULL``) or
    ``'pendiente'`` (no such response yet) — a deliberate 2-state proxy,
    not the DIAN-level accepted/rejected distinction plan.md assumed.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    estado: str
    count: int


class DashboardOcupacionHorariaItem(BaseModel):
    """One (sucursal, hour-of-day) cell for ``HeatmapOcupacion`` (last 24h).

    ``ingresos_count`` is the number of vehicle entries created in that UTC
    hour bucket — a real, directly-queryable proxy for activity intensity.
    It is NOT true concurrent occupancy (that needs interval-overlap math
    across ``ingreso``/``salidas`` per hour, out of scope here); documented
    as an approximation.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid_sucursal: uuid_lib.UUID
    hora: int
    ingresos_count: int


class DashboardResumenError(BaseModel):
    """One sucursal that could not be resolved/scoped into the summary."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid_sucursal: uuid_lib.UUID
    motivo: str


class DashboardResumen(BaseModel):
    """``GET /admin/dashboard/resumen`` (HU-F17.1, BR2)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    sucursales: list[uuid_lib.UUID]
    ocupacion: DashboardOcupacionAgregada
    suscripciones_activas: DashboardSuscripcionesActivas
    medios_pago_dia: list[DashboardMedioPagoItem]
    top_sucursales: list[DashboardTopSucursalItem]
    sync_agregado: DashboardSyncAgregado
    alertas_por_severidad: list[DashboardAlertaSeveridadItem]
    estado_envio_fe_24h: list[DashboardEstadoFEItem]
    ocupacion_horaria: list[DashboardOcupacionHorariaItem]
    errores: list[DashboardResumenError]
    generado_en: datetime


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

    # HU-F17.2 / PR-C: real monto total, summed from the local invoice
    # chain. ``prod.facturas.total`` (operational invoice total) is the
    # wire-level number the operator sees on the receipt; we sum it for
    # the branch's ingresos in the current calendar day so the dashboard
    # KPI matches what ``/admin/reporteria/operacional`` reports on the
    # same range.
    ingresos_monto_total = (
        await session.execute(
            select(func.coalesce(func.sum(Facturas.total), 0.0))
            .join(Ingreso, Ingreso.uuid == Facturas.uuid_ingreso)
            .where(Ingreso.uuid_sucursal == uuid)
            .where(func.date(Ingreso.created_at) == datetime.now(UTC).date())
        )
    ).scalar() or 0.0

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


_SYNC_LAG_OK_THRESHOLD_SECONDS = 900  # 15 min -- same order of magnitude as
# ``sync_interval_seconds`` (job_sync_sucursal / job_sync_cloud run every few
# minutes); a branch quiet for longer than this is "degraded" for the
# aggregate card, not a hard SLO -- just the dashboard's at-a-glance cutoff.


@router.get(
    "/admin/dashboard/resumen",
    response_model=DashboardResumen,
    summary="Cross-branch executive dashboard aggregates (HU-F17.1)",
)
async def dashboard_resumen(
    session: DbSession,
    claims: AdminClaims,
    sucursales: Annotated[
        str | None,
        Query(
            description=(
                "Comma-separated uuid_sucursal list to scope the summary to. "
                "Defaults to every branch currently permitted for the actor."
            )
        ),
    ] = None,
) -> DashboardResumen:
    """Aggregate KPIs across the actor's permitted branches (BR1/BR2).

    Deliberately does NOT depend on ``get_tenant_ctx``/``require_branch_scope``:
    ``parkosFetch`` (web_admin) attaches ``X-Sucursal-Context`` to every admin
    request for the currently-selected branch, and ``get_tenant_ctx`` would
    bind that single branch to the SQLAlchemy ``do_orm_execute`` listener via
    ``set_tenant_context`` -- silently narrowing every query in THIS handler
    to one branch regardless of the ``sucursales`` query param. This endpoint
    is cross-branch by nature, so it follows the same manual
    ``requires_issuer`` + fresh-DB-scope pattern as the rest of this module
    instead.

    Per-sucursal resolution failures (not permitted, or no longer vigente)
    are soft failures: they are excluded from the aggregation and reported
    in ``errores``, never a hard 4xx for the whole request (BR2).
    """
    actor_uuid = uuid_lib.UUID(claims["sub"])
    permitidas = await extract_sucursales_permitidas_fresh(
        session, actor_uuid=actor_uuid
    )
    if not permitidas:
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_sucursal_context"},
        )

    errores: list[DashboardResumenError] = []
    if sucursales is None or sucursales.strip() == "":
        requested = set(permitidas)
    else:
        requested = set()
        for raw in sucursales.split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                parsed = uuid_lib.UUID(raw)
            except ValueError:
                continue  # malformed token: nothing to attribute an error to
            if parsed not in permitidas:
                errores.append(
                    DashboardResumenError(
                        uuid_sucursal=parsed, motivo="sucursal_no_autorizada"
                    )
                )
                continue
            requested.add(parsed)

    nombre_by_uuid: dict[uuid_lib.UUID, str | None] = {}
    target: set[uuid_lib.UUID] = set()
    if requested:
        vigentes_rows = (
            await session.execute(
                select(Sucursal.uuid, Sucursal.nombre).where(
                    Sucursal.uuid.in_(requested),
                    Sucursal.vigente_hasta.is_(None),
                )
            )
        ).all()
        for row in vigentes_rows:
            nombre_by_uuid[row.uuid] = row.nombre
            target.add(row.uuid)
        for uuid_sucursal in requested - target:
            errores.append(
                DashboardResumenError(
                    uuid_sucursal=uuid_sucursal, motivo="sucursal_no_encontrada"
                )
            )

    today = datetime.now(UTC).date()
    now_naive = datetime.now(UTC).replace(tzinfo=None)
    hace_24h = now_naive - timedelta(hours=24)
    hace_30d = today - timedelta(days=29)

    if not target:
        # Every requested branch failed resolution (or the actor has none
        # left after filtering) -- return a zeroed partial response instead
        # of failing the whole request closed (BR2).
        return DashboardResumen(
            sucursales=[],
            ocupacion=DashboardOcupacionAgregada(ocupados=0, capacidad=0, porcentaje=None),
            suscripciones_activas=DashboardSuscripcionesActivas(count=0),
            medios_pago_dia=[],
            top_sucursales=[],
            sync_agregado=DashboardSyncAgregado(
                sucursales_ok=0,
                sucursales_degradadas=0,
                queue_depth_total=0,
                max_lag_seconds=None,
            ),
            alertas_por_severidad=[],
            estado_envio_fe_24h=[],
            ocupacion_horaria=[],
            errores=errores,
            generado_en=datetime.now(UTC),
        )

    # 1. Ocupacion agregada: ingresos activos (sin salida no-anulada) / capacidad
    # vigente, sumada por tipo de vehiculo (BR2). Reuses the ``ingresos
    # activos`` subquery shape already proven in reporteria.py.
    ingresos_activos_subq = (
        select(Ingreso.uuid.label("uuid"))
        .outerjoin(Salidas, Salidas.uuid_ingreso == Ingreso.uuid)
        .outerjoin(
            Anulaciones,
            (Anulaciones.uuid_salida == Salidas.uuid)
            & (Anulaciones.tipo_anulable == "salida")
            & (Anulaciones.estado == "ejecutada"),
        )
        .where(Ingreso.uuid_sucursal.in_(target))
        .where(Salidas.uuid.is_(None) | (Anulaciones.uuid.is_not(None)))
        .subquery()
    )
    ocupados = (
        await session.execute(
            select(func.count(func.distinct(ingresos_activos_subq.c.uuid)))
        )
    ).scalar() or 0
    capacidad = (
        await session.execute(
            select(func.coalesce(func.sum(CantidadVehiculosSucursal.cantidad), 0)).where(
                CantidadVehiculosSucursal.uuid_sucursal.in_(target),
                CantidadVehiculosSucursal.vigente_hasta.is_(None),
            )
        )
    ).scalar() or 0
    ocupacion = DashboardOcupacionAgregada(
        ocupados=int(ocupados),
        capacidad=int(capacidad),
        porcentaje=(float(ocupados) / float(capacidad) * 100.0) if capacidad else None,
    )

    # 2. Suscripciones activas: vigentes hoy (bi-temporal vigente_hasta IS
    # NULL + fecha_vencimiento aun no cumplida o sin vencimiento).
    suscripciones_count = (
        await session.execute(
            select(func.count())
            .select_from(SubscripcionesCliente)
            .where(
                SubscripcionesCliente.uuid_sucursal.in_(target),
                SubscripcionesCliente.vigente_hasta.is_(None),
                (SubscripcionesCliente.fecha_vencimiento.is_(None))
                | (SubscripcionesCliente.fecha_vencimiento >= today),
            )
        )
    ).scalar() or 0

    # 3. Medios de pago del dia: neto pago-reverso por medio_pago, hoy.
    monto_neto_expr = func.coalesce(
        func.sum(
            case(
                (FacturaPagos.tipo_movimiento == "pago", FacturaPagos.valor),
                (FacturaPagos.tipo_movimiento == "reverso", -FacturaPagos.valor),
                else_=0,
            )
        ),
        0.0,
    )
    medio_pago_rows = (
        await session.execute(
            select(FacturaPagos.medio_pago, monto_neto_expr.label("monto_total"))
            .where(
                FacturaPagos.uuid_sucursal.in_(target),
                func.date(FacturaPagos.created_at) == today,
            )
            .group_by(FacturaPagos.medio_pago)
            .order_by(monto_neto_expr.desc())
        )
    ).all()
    medios_pago_dia = [
        DashboardMedioPagoItem(
            medio_pago=row.medio_pago or "sin_especificar",
            monto_total=float(row.monto_total or 0.0),
        )
        for row in medio_pago_rows
    ]

    # 4. Top-5 sucursales por ingresos facturados, ultimos 30 dias.
    monto_facturado_expr = func.coalesce(func.sum(Facturas.total), 0.0)
    top_rows = (
        await session.execute(
            select(Facturas.uuid_sucursal, monto_facturado_expr.label("monto_total"))
            .where(
                Facturas.uuid_sucursal.in_(target),
                func.date(Facturas.created_at) >= hace_30d,
                func.date(Facturas.created_at) <= today,
            )
            .group_by(Facturas.uuid_sucursal)
            .order_by(monto_facturado_expr.desc())
            .limit(5)
        )
    ).all()
    top_sucursales = [
        DashboardTopSucursalItem(
            uuid_sucursal=row.uuid_sucursal,
            nombre=nombre_by_uuid.get(row.uuid_sucursal),
            monto_total=float(row.monto_total or 0.0),
        )
        for row in top_rows
        if row.uuid_sucursal is not None
    ]

    # 5. Estado de sync agregado: DISTINCT ON latest sync_log row per branch.
    latest_sync_rows = (
        await session.execute(
            select(SyncLog)
            .where(SyncLog.uuid_sucursal.in_(target))
            .distinct(SyncLog.uuid_sucursal)
            .order_by(SyncLog.uuid_sucursal, SyncLog.timestamp_evento.desc())
        )
    ).scalars().all()
    sucursales_ok = 0
    sucursales_degradadas = 0
    queue_depth_total = 0
    max_lag_seconds: int | None = None
    seen_sync: set[uuid_lib.UUID] = set()
    for sync_row in latest_sync_rows:
        if sync_row.uuid_sucursal is not None:
            seen_sync.add(sync_row.uuid_sucursal)
        lag: int | None = None
        if sync_row.timestamp_evento is not None:
            lag = max(int((now_naive - sync_row.timestamp_evento).total_seconds()), 0)
        queue_depth_total += _queue_depth(sync_row)
        if lag is not None and lag <= _SYNC_LAG_OK_THRESHOLD_SECONDS:
            sucursales_ok += 1
        else:
            sucursales_degradadas += 1
        if lag is not None:
            max_lag_seconds = lag if max_lag_seconds is None else max(max_lag_seconds, lag)
    # Branches with no sync_log row at all have never synced -- degraded.
    sucursales_degradadas += len(target - seen_sync)
    sync_agregado = DashboardSyncAgregado(
        sucursales_ok=sucursales_ok,
        sucursales_degradadas=sucursales_degradadas,
        queue_depth_total=queue_depth_total,
        max_lag_seconds=max_lag_seconds,
    )

    # 6. Alertas abiertas por severidad (catalog join on the business key).
    alert_rows = (
        await session.execute(
            select(AlertTypes.severity, func.count(func.distinct(Alerta.uuid)))
            .select_from(Alerta)
            .join(AlertTypes, AlertTypes.tipo_alerta == Alerta.tipo_alerta)
            .where(
                Alerta.uuid_sucursal.in_(target),
                Alerta.vigente_hasta.is_(None),
            )
            .group_by(AlertTypes.severity)
        )
    ).all()
    alertas_por_severidad = [
        DashboardAlertaSeveridadItem(severity=row[0], count=int(row[1]))
        for row in alert_rows
    ]

    # 7. Estado de envio FE (24h) -- ChartPie data. See DashboardEstadoFEItem
    # docstring for why this is a 2-state proxy rather than a DIAN status enum.
    fe_envio_rows = (
        await session.execute(
            select(
                FacturaElectronica.uuid,
                func.bool_or(EnvioDian.respuesta_proveedor.is_not(None)).label("enviada"),
            )
            .select_from(FacturaElectronica)
            .outerjoin(
                EnvioDian,
                EnvioDian.uuid_factura_electronica == FacturaElectronica.uuid,
            )
            .where(
                FacturaElectronica.uuid_sucursal.in_(target),
                FacturaElectronica.created_at >= hace_24h,
            )
            .group_by(FacturaElectronica.uuid)
        )
    ).all()
    enviadas_count = sum(1 for row in fe_envio_rows if row.enviada)
    pendientes_count = len(fe_envio_rows) - enviadas_count
    estado_envio_fe_24h = [
        DashboardEstadoFEItem(estado="enviada", count=enviadas_count),
        DashboardEstadoFEItem(estado="pendiente", count=pendientes_count),
    ]

    # 8. Ocupacion horaria (HeatmapOcupacion, 24h x N sucursales) -- see
    # DashboardOcupacionHorariaItem docstring for the approximation note.
    hora_expr = func.extract("hour", Ingreso.created_at)
    heatmap_rows = (
        await session.execute(
            select(
                Ingreso.uuid_sucursal,
                hora_expr.label("hora"),
                func.count().label("ingresos_count"),
            )
            .where(
                Ingreso.uuid_sucursal.in_(target),
                Ingreso.created_at >= hace_24h,
            )
            .group_by(Ingreso.uuid_sucursal, hora_expr)
        )
    ).all()
    ocupacion_horaria = [
        DashboardOcupacionHorariaItem(
            uuid_sucursal=row.uuid_sucursal,
            hora=int(row.hora),
            ingresos_count=int(row.ingresos_count),
        )
        for row in heatmap_rows
        if row.uuid_sucursal is not None
    ]

    return DashboardResumen(
        sucursales=sorted(target, key=str),
        ocupacion=ocupacion,
        suscripciones_activas=DashboardSuscripcionesActivas(count=int(suscripciones_count)),
        medios_pago_dia=medios_pago_dia,
        top_sucursales=top_sucursales,
        sync_agregado=sync_agregado,
        alertas_por_severidad=alertas_por_severidad,
        estado_envio_fe_24h=estado_envio_fe_24h,
        ocupacion_horaria=ocupacion_horaria,
        errores=errores,
        generado_en=datetime.now(UTC),
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
    "DashboardAlertaSeveridadItem",
    "DashboardEstadoFEItem",
    "DashboardMedioPagoItem",
    "DashboardOcupacionAgregada",
    "DashboardOcupacionHorariaItem",
    "DashboardResumen",
    "DashboardResumenError",
    "DashboardSuscripcionesActivas",
    "DashboardSyncAgregado",
    "DashboardSyncHealth",
    "DashboardTopSucursalItem",
    "SucursalDashboard",
    "SucursalItem",
    "SucursalListItem",
    "SucursalListResponse",
    "SucursalSyncStatus",
    "router",
]
