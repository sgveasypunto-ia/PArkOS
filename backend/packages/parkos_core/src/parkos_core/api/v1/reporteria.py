"""Operational + financial reports (HU-F17.1/F17.2/F17.3, PR-C).

Module docstring says "can mount on ``api_admin`` and ``api_sucursal``"
(aspirational/stale -- confirmed against ``api/v1/__init__.py::
_build_router``: this router is actually mounted ONLY on cloud deploys,
same ``if _IS_BRANCH: skip`` gate as ``admin_views.router``, found while
building HU-F17.3). Only ``admin-`` issuers reach this surface; the
single-branch endpoints are additionally gated by ``require_branch_scope``
so the report cannot leak across the actor's permitted branches.

Endpoints:

- ``GET /api/v1/admin/reporteria/operacional?uuid_sucursal=&fecha_desde=&fecha_hasta=``

  Returns per-day counts + monto_facturado/monto_cobrado for the branch
  over the date range, plus a grand-total rollup. No time series, no
  charts — explicit F17.1 user directive.

- ``GET /api/v1/admin/reporteria/facturas?uuid_sucursal=&desde=&hasta=&cursor=&limit=``
  (HU-F17.3) -- paginated ``facturas`` rows resolved against their REAL
  columns (``numero_completo``/``iva``/``estado`` are NOT physical
  ``facturas`` columns; see :func:`reporte_facturas`'s docstring).

- ``GET /api/v1/admin/reporteria/fe?estado=&cursor=&limit=`` (HU-F17.3,
  BR1) -- paginated ``factura_electronica`` + its latest DIAN ack from
  ``prod.v_factura_electronica_acuse``. Cross-branch (every branch the
  admin can see), same reasoning as ``reporte_ocupacion``.

- ``GET /api/v1/admin/reporteria/pagos?uuid_sucursal=&desde=&hasta=``
  (HU-F17.3, BR2) -- pagos netos (pago - reverso) agrupados por
  ``medio_pago``/día.

Notes on the SQL
----------------

- ``Facturas.total`` (prod.facturas) is the local invoice total. Summed
  directly per branch per day; no join to ``FacturaElectronica``
  required for facturado. Electronic-vs-physical split is reported via
  ``factura_electronica`` separately when needed (out of scope here).
- ``monto_cobrado_total`` = ``SUM(FacturaPagos.valor WHERE tipo_movimiento='pago')
  - SUM(... WHERE tipo_movimiento='reverso')``. Computed in SQL via a
  single ``CASE`` aggregate, no join to ``anulaciones`` needed.
- Ingresos ``activos`` = ingresos without a non-anulada salida. The same
  ``V_INGRESO_ESTADO`` derivation lives in ``operacion.py::list_ingresos``;
  we keep this slice read-only and recompute inline.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, column, func, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_session, require_branch_scope, requires_issuer
from ...auth.tenancy import BranchScope, TenantScopeViolationError
from ...db.tenancy import extract_sucursales_permitidas_fresh
from ...models.A.factura_impuestos import FacturaImpuestos
from ...models.A.factura_pagos import FacturaPagos
from ...models.A.salidas import Salidas
from ...models.L_E.factura_electronica import FacturaElectronica
from ...models.L_E.facturas import Facturas
from ...models.L_E.ingreso import Ingreso
from ...models.L_W.anulaciones import Anulaciones
from ...models.V.cantidad_vehiculos_sucursal import CantidadVehiculosSucursal
from ...models.V.subscripciones_cliente import SubscripcionesCliente
from ...models.V.sucursal import Sucursal
from ...repo.pagination import Cursor, InvalidCursorError
from ...repo.pagination import decode as cursor_decode
from ...repo.pagination import encode as cursor_encode
from ...repo.workflow import STATE_MACHINES
from ...schemas.reporteria import (
    CohorteRetencionCell,
    CohorteSuscripcionItem,
    ReporteEstanciaItem,
    ReporteFacturaItem,
    ReporteFacturasResponse,
    ReporteFeItem,
    ReporteFeResponse,
    ReporteOcupacionAgregada,
    ReporteOcupacionHeatmapCell,
    ReporteOcupacionResponse,
    ReporteOcupacionSucursalItem,
    ReporteOperacionalIngresoItem,
    ReporteOperacionalItem,
    ReporteOperacionalResponse,
    ReportePagoMedioItem,
    ReportePagosResponse,
    ReporteSuscripcionesCohorteResponse,
    SuscripcionPorVencerItem,
)

router = APIRouter(prefix="/admin/reporteria", tags=["admin", "reporteria"])

_admin_issuer_dep = requires_issuer("admin-")
AdminClaims = Annotated[dict[str, Any], Depends(_admin_issuer_dep)]
DbSession = Annotated[AsyncSession, Depends(get_session)]

# ``prod.v_factura_electronica_acuse`` (migration 0009_add_derived_read_
# views.py) has no ORM model -- it is a derived read view (one row per
# ``uuid_factura_electronica``, the latest ``envio_dian`` row by
# ``timestamp_evento``) and HU-F17.3 is its first application-code
# reader (confirmed: no prior ``repo/``/``api/`` module queries it). A
# lightweight Core ``table()`` binding -- not a mapped class, the view
# has no PK and is never written to -- is the idiomatic SQLAlchemy 2.0
# way to SELECT/JOIN it alongside ORM entities in the same statement.
v_factura_electronica_acuse = table(
    "v_factura_electronica_acuse",
    column("uuid_factura_electronica"),
    column("cufe"),
    column("estado"),
    column("timestamp_evento"),
    schema="prod",
)

# Real domain of ``envio_dian.estado`` / ``v_factura_electronica_acuse.
# estado`` (HU-F17.3 BR1 -- "o el dominio real que encuentres"), confirmed
# against EVERY writer of the column:
#
# - ``repo.workflow.STATE_MACHINES["envio_dian"]`` -- the ``POST
#   /envio-dian`` transition endpoint's state machine: ``pendiente|
#   enviado|ack|error``.
# - ``dian.cloud.dispatcher``'s own ``ESTADO_*`` constants, which mutate
#   ``envio.estado`` DIRECTLY, bypassing that state machine:
#   ``aceptado|rechazado|timeout|en_proceso`` (``error`` overlaps the
#   state-machine's own terminal value).
#
# The real domain is the UNION of both -- see ``dian/cloud_router.py``'s
# ``_ENVIO_DIAN_ESTADOS`` module comment, which already documents this
# EXACT same drift for HU-F13.4 (plan.md's assumed 4-value
# ``pendiente|enviado|aceptado|rechazado`` is actually
# ``schemas.facturacion.FacturaDisplayFE.estado_dian``'s simplified
# display projection, not this column's raw domain).
#
# Duplicated here as plain string literals rather than importing
# ``dian.cloud_router``/``dian.cloud.dispatcher``: both modules raise
# ``ImportError`` under ``PARKOS_DEPLOY=branch`` (REQ-X3 belt-and-
# suspenders) -- importing either here would coral this router's
# importability to the dian boundary even though it is otherwise
# unrelated to the DIAN cloud-dispatch write path.
_ESTADO_DIAN_VALUES: frozenset[str] = frozenset(STATE_MACHINES["envio_dian"]) | {
    "aceptado",
    "rechazado",
    "timeout",
    "en_proceso",
}


@router.get(
    "/operacional",
    response_model=ReporteOperacionalResponse,
    summary="Operational totals for one branch over a date range (HU-F17.1)",
)
async def reporte_operacional(
    session: Annotated[AsyncSession, Depends(get_session)],
    _claims: Annotated[None, Depends(_admin_issuer_dep)],
    scope: Annotated[BranchScope, Depends(require_branch_scope)],
    uuid_sucursal: uuid_lib.UUID = Query(  # noqa: B008
        ...,
        description="Branch to report on. Must be in the actor's permitted set.",
    ),
    fecha_desde: date | None = Query(  # noqa: B008
        None,
        description="Inclusive UTC start date. If absent, defaults to 30 days back.",
    ),
    fecha_hasta: date | None = Query(  # noqa: B008
        None,
        description="Inclusive UTC end date. If absent, defaults to today (UTC).",
    ),
    uuid_tipo_vehiculo: uuid_lib.UUID | None = Query(  # noqa: B008
        None,
        description=(
            "HU-F17.2: optional vehicle-type filter, applied to both the "
            "``ingresos`` list and ``tiempos_estancia`` (BR1)."
        ),
    ),
    cursor: str | None = Query(
        None,
        description="HU-F17.2: opaque cursor for the ``ingresos`` list only.",
    ),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ReporteOperacionalResponse:
    """Per-day + grand-total operational aggregates.

    Two-step authorization so a caller with NO permitted branches does
    not get 403 (which would imply "you named a branch you don't own");
    instead they get 400 ``missing_sucursal_context``, the same shape
    ``/operacion/ocupacion`` already returns (PR-A).

    The SQL aggregates per UTC date (cast on ``created_at``), reusing
    the same bi-temporal ``vigente_*`` philosophy by counting the rows
    that are CURRENT at the moment of the read.
    """
    # 1. Resolve the date window.
    today = datetime.now(UTC).date()
    if fecha_hasta is None:
        fecha_hasta = today
    if fecha_desde is None:
        fecha_desde = fecha_hasta.replace(day=1) if fecha_hasta.day == 1 else today.replace(
            day=max(1, today.day - 29)
        )
        # Force at least 1 day of range; if both None we still want one row
        # in `items` so the UI can render the empty-state consistently.
    if fecha_desde > fecha_hasta:
        raise HTTPException(
            status_code=400,
            detail={"error": "fecha_desde_after_hasta"},
        )

    # 2. Authorization (same two-step as PR-A's get_ocupacion).
    if not scope.permitidas:
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_sucursal_context"},
        )
    permitidas = scope.narrow(uuid_sucursal)
    target = next(iter(permitidas))

    # 3. SQL — three independent per-day rollups, then a UNION ALL
    # pattern joined on (fecha). This keeps every count and sum
    # correct against its own table without the cartesian-product
    # trap of joining ingreso + salidas + facturas + pagos in one
    # SELECT. The outer join in the final SELECT is on the date key
    # only, which is unique per row in each subquery.
    #
    # monto_cobrado_neto = SUM(pago) - SUM(reverso), per (factura, day)
    # — net of void on the SAME pago, never cross-factura.
    monto_cobrado_neto_expr = func.coalesce(
        func.sum(
            case(
                (FacturaPagos.tipo_movimiento == "pago", FacturaPagos.valor),
                (FacturaPagos.tipo_movimiento == "reverso", -FacturaPagos.valor),
                else_=0,
            )
        ),
        0.0,
    )

    # Activos: ingresos without a non-anulada salida.
    ingresos_activos_subq = (
        select(Ingreso.uuid.label("uuid"))
        .outerjoin(Salidas, Salidas.uuid_ingreso == Ingreso.uuid)
        .outerjoin(
            Anulaciones,
            (Anulaciones.uuid_salida == Salidas.uuid)
            & (Anulaciones.tipo_anulable == "salida")
            & (Anulaciones.estado == "ejecutada"),
        )
        .where(Ingreso.uuid_sucursal == target)
        .where(Salidas.uuid.is_(None) | (Anulaciones.uuid.is_not(None)))
        .subquery()
    )

    # Per-day rollup of ingreso-side counts (no factura join — keeps the
    # count clean).
    per_day_ingresos = (
        select(
            func.date(Ingreso.created_at).label("fecha"),
            func.count(func.distinct(Ingreso.uuid)).label("ingresos_count"),
            func.count(func.distinct(ingresos_activos_subq.c.uuid)).label(
                "ingresos_activos_count"
            ),
            func.count(func.distinct(Salidas.uuid)).label("salidas_count"),
        )
        .select_from(Ingreso)
        .outerjoin(
            ingresos_activos_subq,
            ingresos_activos_subq.c.uuid == Ingreso.uuid,
        )
        .outerjoin(Salidas, Salidas.uuid_ingreso == Ingreso.uuid)
        .where(Ingreso.uuid_sucursal == target)
        .where(func.date(Ingreso.created_at) >= fecha_desde)
        .where(func.date(Ingreso.created_at) <= fecha_hasta)
        .group_by(func.date(Ingreso.created_at))
        .subquery()
    )

    # Per-day rollup of factura-side counts/montos. Group by day
    # (cast on ``created_at``) so each row is one date.
    per_day_facturas = (
        select(
            func.date(Facturas.created_at).label("fecha"),
            func.count(func.distinct(Facturas.uuid)).label("facturas_emitidas_count"),
            func.coalesce(func.sum(Facturas.total), 0.0).label("monto_facturado_total"),
        )
        .select_from(Facturas)
        .where(Facturas.uuid_sucursal == target)
        .where(Facturas.uuid_ingreso.is_not(None))
        .where(func.date(Facturas.created_at) >= fecha_desde)
        .where(func.date(Facturas.created_at) <= fecha_hasta)
        .group_by(func.date(Facturas.created_at))
        .subquery()
    )

    # Per-day rollup of pago-side net amount. Same date axis.
    per_day_pagos = (
        select(
            func.date(FacturaPagos.created_at).label("fecha"),
            monto_cobrado_neto_expr.label("monto_cobrado_total"),
        )
        .select_from(FacturaPagos)
        .join(Facturas, Facturas.uuid == FacturaPagos.uuid_factura)
        .where(Facturas.uuid_sucursal == target)
        .where(Facturas.uuid_ingreso.is_not(None))
        .where(func.date(FacturaPagos.created_at) >= fecha_desde)
        .where(func.date(FacturaPagos.created_at) <= fecha_hasta)
        .group_by(func.date(FacturaPagos.created_at))
        .subquery()
    )

    per_day_rows = (
        await session.execute(
            select(
                per_day_ingresos.c.fecha.label("fecha"),
                per_day_ingresos.c.ingresos_count,
                per_day_ingresos.c.ingresos_activos_count,
                per_day_ingresos.c.salidas_count,
                func.coalesce(per_day_facturas.c.facturas_emitidas_count, 0).label(
                    "facturas_emitidas_count"
                ),
                func.coalesce(per_day_facturas.c.monto_facturado_total, 0.0).label(
                    "monto_facturado_total"
                ),
                func.coalesce(per_day_pagos.c.monto_cobrado_total, 0.0).label(
                    "monto_cobrado_total"
                ),
            )
            .select_from(per_day_ingresos)
            .outerjoin(
                per_day_facturas,
                per_day_facturas.c.fecha == per_day_ingresos.c.fecha,
            )
            .outerjoin(
                per_day_pagos,
                per_day_pagos.c.fecha == per_day_ingresos.c.fecha,
            )
            .order_by(per_day_ingresos.c.fecha)
        )
    ).all()

    items = [
        ReporteOperacionalItem(
            fecha=row.fecha,
            ingresos_count=int(row.ingresos_count or 0),
            ingresos_activos_count=int(row.ingresos_activos_count or 0),
            salidas_count=int(row.salidas_count or 0),
            facturas_emitidas_count=int(row.facturas_emitidas_count or 0),
            monto_facturado_total=float(row.monto_facturado_total or 0.0),
            monto_cobrado_total=float(row.monto_cobrado_total or 0.0),
        )
        for row in per_day_rows
    ]

    # Grand totals (re-aggregate from the per-day rows so the SQL stays
    # single-pass and the totals field is the sum of items, never a
    # second source of truth).
    totales = ReporteOperacionalItem(
        fecha=None,
        ingresos_count=sum(item.ingresos_count for item in items),
        ingresos_activos_count=sum(item.ingresos_activos_count for item in items),
        salidas_count=sum(item.salidas_count for item in items),
        facturas_emitidas_count=sum(item.facturas_emitidas_count for item in items),
        monto_facturado_total=sum(item.monto_facturado_total for item in items),
        monto_cobrado_total=sum(item.monto_cobrado_total for item in items),
    )

    # 4. HU-F17.2 -- ingresos filtrados (sucursal/fecha/tipo) con
    # paginacion cursor estandar, y tiempos de estancia (BR1).
    #
    # ``salida_no_anulada_subq`` is the mirror image of
    # ``ingresos_activos_subq`` above: instead of "no salida (or only an
    # anulada one)", this picks the salida that IS valid (not anulada)
    # for an ingreso -- i.e. a COMPLETED stay, the only case a stay time
    # can be computed for. Filtering here is on ``fecha_ingreso`` (the
    # business timestamp BR1 names), deliberately NOT ``created_at`` --
    # that keeps this slice's date semantics distinct from the per-day
    # KPI rollup above (which filters on ``created_at`` and predates
    # this HU).
    salida_no_anulada_subq = (
        select(
            Salidas.uuid_ingreso.label("uuid_ingreso"),
            Salidas.fecha_salida.label("fecha_salida"),
        )
        .outerjoin(
            Anulaciones,
            (Anulaciones.uuid_salida == Salidas.uuid)
            & (Anulaciones.tipo_anulable == "salida")
            & (Anulaciones.estado == "ejecutada"),
        )
        .where(Anulaciones.uuid.is_(None))
        .subquery()
    )

    try:
        decoded_cursor = cursor_decode(cursor) if cursor else None
    except InvalidCursorError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_cursor", "detail": str(exc)},
        ) from exc

    ingresos_stmt = (
        select(
            Ingreso.uuid,
            Ingreso.uuid_sucursal,
            Ingreso.uuid_tipo_vehiculo,
            Ingreso.placa,
            Ingreso.consecutivo,
            Ingreso.fecha_ingreso,
            Ingreso.created_at,
            salida_no_anulada_subq.c.fecha_salida,
        )
        .select_from(Ingreso)
        .outerjoin(
            salida_no_anulada_subq,
            salida_no_anulada_subq.c.uuid_ingreso == Ingreso.uuid,
        )
        .where(Ingreso.uuid_sucursal == target)
        .where(Ingreso.fecha_ingreso.is_not(None))
        .where(func.date(Ingreso.fecha_ingreso) >= fecha_desde)
        .where(func.date(Ingreso.fecha_ingreso) <= fecha_hasta)
    )
    if uuid_tipo_vehiculo is not None:
        ingresos_stmt = ingresos_stmt.where(
            Ingreso.uuid_tipo_vehiculo == uuid_tipo_vehiculo
        )
    ingresos_stmt = ingresos_stmt.order_by(Ingreso.created_at.desc(), Ingreso.uuid.asc())
    if decoded_cursor is not None:
        if decoded_cursor.created_at is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_cursor",
                    "detail": "cursor missing created_at (required for ingreso listings)",
                },
            )
        cursor_ts = datetime.fromisoformat(
            decoded_cursor.created_at.replace("Z", "+00:00")  # noqa: FURB162
        ).replace(tzinfo=None)
        cursor_uuid = uuid_lib.UUID(decoded_cursor.uuid)
        ingresos_stmt = ingresos_stmt.where(
            (Ingreso.created_at < cursor_ts)
            | ((Ingreso.created_at == cursor_ts) & (Ingreso.uuid > cursor_uuid))
        )
    ingresos_stmt = ingresos_stmt.limit(limit + 1)

    ingreso_rows = (await session.execute(ingresos_stmt)).all()
    ingresos_next_cursor: str | None = None
    if len(ingreso_rows) > limit:
        ingreso_rows = ingreso_rows[:limit]
        last = ingreso_rows[-1]
        ingresos_next_cursor = cursor_encode(
            Cursor(created_at=last.created_at.isoformat(), uuid=str(last.uuid))
        )

    ingresos_items = [
        ReporteOperacionalIngresoItem(
            uuid=row.uuid,
            uuid_sucursal=row.uuid_sucursal,
            uuid_tipo_vehiculo=row.uuid_tipo_vehiculo,
            placa=row.placa,
            consecutivo=row.consecutivo,
            fecha_ingreso=row.fecha_ingreso,
            fecha_salida=row.fecha_salida,
            tiempo_estancia_segundos=(
                (row.fecha_salida - row.fecha_ingreso).total_seconds()
                if row.fecha_salida is not None and row.fecha_ingreso is not None
                else None
            ),
        )
        for row in ingreso_rows
    ]

    # Tiempos de estancia (BR1): promedio/maximo/minimo agrupado por dia,
    # sobre TODO el rango filtrado (no paginado -- ya esta acotado por
    # fecha_desde/fecha_hasta, misma logica que ``totales`` arriba). Solo
    # cuentan las estancias completas (INNER JOIN con una salida valida).
    duracion_expr = func.extract(
        "epoch", salida_no_anulada_subq.c.fecha_salida - Ingreso.fecha_ingreso
    )
    estancia_stmt = (
        select(
            func.date(Ingreso.fecha_ingreso).label("fecha"),
            func.count().label("muestras"),
            func.avg(duracion_expr).label("promedio_segundos"),
            func.max(duracion_expr).label("maximo_segundos"),
            func.min(duracion_expr).label("minimo_segundos"),
        )
        .select_from(Ingreso)
        .join(
            salida_no_anulada_subq,
            salida_no_anulada_subq.c.uuid_ingreso == Ingreso.uuid,
        )
        .where(Ingreso.uuid_sucursal == target)
        .where(Ingreso.fecha_ingreso.is_not(None))
        .where(func.date(Ingreso.fecha_ingreso) >= fecha_desde)
        .where(func.date(Ingreso.fecha_ingreso) <= fecha_hasta)
    )
    if uuid_tipo_vehiculo is not None:
        estancia_stmt = estancia_stmt.where(
            Ingreso.uuid_tipo_vehiculo == uuid_tipo_vehiculo
        )
    estancia_stmt = estancia_stmt.group_by(func.date(Ingreso.fecha_ingreso)).order_by(
        func.date(Ingreso.fecha_ingreso)
    )
    estancia_rows = (await session.execute(estancia_stmt)).all()
    tiempos_estancia = [
        ReporteEstanciaItem(
            fecha=row.fecha,
            muestras=int(row.muestras or 0),
            promedio_segundos=float(row.promedio_segundos or 0.0),
            maximo_segundos=float(row.maximo_segundos or 0.0),
            minimo_segundos=float(row.minimo_segundos or 0.0),
        )
        for row in estancia_rows
    ]

    return ReporteOperacionalResponse(
        uuid_sucursal=target,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        items=items,
        totales=totales,
        generado_en=datetime.now(UTC),
        ingresos=ingresos_items,
        ingresos_next_cursor=ingresos_next_cursor,
        tiempos_estancia=tiempos_estancia,
    )


@router.get(
    "/ocupacion",
    response_model=ReporteOcupacionResponse,
    summary="Cross-branch occupancy heatmap, multi-day (HU-F17.2)",
)
async def reporte_ocupacion(
    session: DbSession,
    claims: AdminClaims,
    desde: Annotated[
        date | None,
        Query(description="Inclusive UTC start date. Defaults to 6 days back."),
    ] = None,
    hasta: Annotated[
        date | None,
        Query(description="Inclusive UTC end date. Defaults to today (UTC)."),
    ] = None,
) -> ReporteOcupacionResponse:
    """24h x N-sucursales heatmap over ``[desde, hasta]`` (HU-F17.2).

    Cross-branch by nature (every branch the actor can see, same as
    ``admin_views.dashboard_resumen``) -- deliberately does NOT depend on
    ``get_tenant_ctx``/``require_branch_scope`` for the same reason that
    module documents: those dependencies bind a SINGLE
    ``X-Sucursal-Context`` branch to the SQLAlchemy ``do_orm_execute``
    listener, which would silently narrow this endpoint to one branch.
    Scope is resolved fresh from ``usuarios_sucursal``
    (:func:`extract_sucursales_permitidas_fresh`) instead.

    Two numbers ship together:

    - ``data``/``sucursales`` -- the heatmap itself. Same shape and same
      activity-intensity-proxy semantics as
      ``admin_views.DashboardOcupacionHorariaItem`` (HU-F17.1); the only
      difference is the window (``[desde, hasta]``, multi-day) instead
      of a fixed last-24h/today-only lookback -- see
      ``ReporteOcupacionHeatmapCell`` docstring.
    - ``ocupacion_agregada`` -- BR2's ratio (ingresos activos / capacidad
      vigente), reusing the exact "sin salida no-anulada" criterion
      ``admin_views.dashboard_resumen`` already proved out. This is
      necessarily a CURRENT snapshot (active-right-now), not historical,
      so it ignores ``desde``/``hasta`` -- there is no stored history of
      past occupancy to recompute it against.
    """
    actor_uuid = uuid_lib.UUID(claims["sub"])
    permitidas = await extract_sucursales_permitidas_fresh(session, actor_uuid=actor_uuid)
    if not permitidas:
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_sucursal_context"},
        )

    today = datetime.now(UTC).date()
    if hasta is None:
        hasta = today
    if desde is None:
        desde = hasta - timedelta(days=6)
    if desde > hasta:
        raise HTTPException(
            status_code=422,
            detail={"error": "rango_fecha_invalido"},
        )

    sucursal_rows = (
        await session.execute(
            select(Sucursal.uuid, Sucursal.nombre).where(
                Sucursal.uuid.in_(permitidas),
                Sucursal.vigente_hasta.is_(None),
            )
        )
    ).all()
    sucursales = [
        ReporteOcupacionSucursalItem(uuid=row.uuid, nombre=row.nombre)
        for row in sucursal_rows
    ]
    target = {row.uuid for row in sucursal_rows}

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
                func.date(Ingreso.created_at) >= desde,
                func.date(Ingreso.created_at) <= hasta,
            )
            .group_by(Ingreso.uuid_sucursal, hora_expr)
        )
    ).all()
    data = [
        ReporteOcupacionHeatmapCell(
            uuid_sucursal=row.uuid_sucursal,
            hora=int(row.hora),
            ingresos_count=int(row.ingresos_count),
        )
        for row in heatmap_rows
        if row.uuid_sucursal is not None
    ]

    # BR2: ingresos activos (sin salida no-anulada) / capacidad vigente.
    # Exact same subquery shape as ``admin_views.dashboard_resumen`` (BR2:
    # "reusalo tal cual").
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
    ocupacion_agregada = ReporteOcupacionAgregada(
        ocupados=int(ocupados),
        capacidad=int(capacidad),
        porcentaje=(float(ocupados) / float(capacidad) * 100.0) if capacidad else None,
    )

    return ReporteOcupacionResponse(
        sucursales=sucursales,
        data=data,
        ocupacion_agregada=ocupacion_agregada,
        desde=desde,
        hasta=hasta,
        generado_en=datetime.now(UTC),
    )


@router.get(
    "/facturas",
    response_model=ReporteFacturasResponse,
    summary=(
        "Paginated facturas resolved against real columns (HU-F17.3); "
        "optionally cross-branch by cliente (HU-F20.1)"
    ),
)
async def reporte_facturas(
    session: DbSession,
    claims: AdminClaims,
    uuid_sucursal: uuid_lib.UUID | None = Query(  # noqa: B008
        None,
        description=(
            "Branch to report on. Must be in the actor's permitted set. "
            "Required unless uuid_cliente is given."
        ),
    ),
    uuid_cliente: uuid_lib.UUID | None = Query(  # noqa: B008
        None,
        description=(
            "HU-F20.1: filter to one cliente's facturas, across every "
            "branch the actor can see. Required unless uuid_sucursal is "
            "given."
        ),
    ),
    desde: date | None = Query(  # noqa: B008
        None,
        description="Inclusive UTC start date. Defaults to 6 days back.",
    ),
    hasta: date | None = Query(  # noqa: B008
        None,
        description="Inclusive UTC end date. Defaults to today (UTC).",
    ),
    cursor: str | None = Query(None, description="Opaque cursor, created_at-keyed."),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ReporteFacturasResponse:
    """One branch's (or, since HU-F20.1, one cliente's cross-branch) ``facturas`` rows,
    newest first, cursor-paginated.

    Every displayed column is resolved against the REAL schema (see
    ``ReporteFacturaItem``'s docstring for the full rationale):
    ``numero_completo`` via an outer join to ``factura_electronica``
    (``NULL`` when absent -- not every factura has an FE), ``iva`` via a
    correlated ``SUM(factura_impuestos.valor)`` scalar subquery (so the
    row cardinality stays 1:1 with ``facturas``, no join fan-out), and
    ``estado`` via the same ad-hoc "EXISTS a non-voided anulaciones row"
    pattern already used by ``reporte_operacional``'s
    ``ingresos_activos_subq`` -- ``anulaciones.tipo_anulable`` is only
    ever ``ingreso``/``salida`` (never ``factura`` directly), so the
    derivation follows the factura's own ``uuid_ingreso``/``uuid_salida``
    pointers.

    HU-F20.1 adds an optional ``uuid_cliente`` filter (``FacturaElectronica.
    uuid_cliente`` -- ``Facturas`` itself has no cliente column, confirmed
    against ``models/L_E/facturas.py``) so a client's detail page can list
    their facturas across every branch, not just one. At least one of
    ``uuid_sucursal``/``uuid_cliente`` is required (422 ``missing_filter``).

    Deliberately does NOT depend on ``require_branch_scope``/
    ``get_tenant_ctx`` -- same reasoning ``reporte_fe``/``reporte_ocupacion``
    already document, and confirmed live here: ``parkosFetch`` (web_admin's
    shared fetch wrapper) ALWAYS injects ``X-Sucursal-Context`` from the
    topbar's globally-selected branch (``lib/sucursal-context.tsx``), so
    binding this endpoint to that dependency would silently collapse the
    HU-F20.1 cross-branch cliente read down to whichever branch happens to
    be selected in the UI -- not a leak (the listener only ever narrows via
    AND), but silently wrong data. Scope is instead resolved fresh from
    ``usuarios_sucursal`` (:func:`extract_sucursales_permitidas_fresh`),
    exactly like those two endpoints, and intersected explicitly with
    whichever filter the caller asked for -- so every row is still
    guaranteed to belong to a branch this actor is currently permitted to
    see, in both modes.
    """
    if uuid_sucursal is None and uuid_cliente is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_filter",
                "detail": "Debe especificar uuid_sucursal o uuid_cliente",
            },
        )

    today = datetime.now(UTC).date()
    if hasta is None:
        hasta = today
    if desde is None:
        desde = hasta - timedelta(days=6)
    if desde > hasta:
        raise HTTPException(
            status_code=422,
            detail={"error": "rango_fecha_invalido"},
        )

    actor_uuid = uuid_lib.UUID(claims["sub"])
    permitidas = await extract_sucursales_permitidas_fresh(session, actor_uuid=actor_uuid)
    if not permitidas:
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_sucursal_context"},
        )
    permitidas_set = frozenset(permitidas)

    if uuid_sucursal is not None:
        if uuid_sucursal not in permitidas_set:
            raise TenantScopeViolationError()
        target_sucursales = frozenset({uuid_sucursal})
    else:
        target_sucursales = permitidas_set

    try:
        decoded_cursor = cursor_decode(cursor) if cursor else None
    except InvalidCursorError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_cursor", "detail": str(exc)},
        ) from exc

    # BR: estado derivado -- EXISTS anulaciones ejecutada sobre el
    # uuid_ingreso/uuid_salida de la factura -> 'anulada', si no -> 'vigente'.
    anulada_exists = (
        select(Anulaciones.uuid)
        .where(Anulaciones.estado == "ejecutada")
        .where(
            (
                Facturas.uuid_salida.is_not(None)
                & (Anulaciones.tipo_anulable == "salida")
                & (Anulaciones.uuid_salida == Facturas.uuid_salida)
            )
            | (
                Facturas.uuid_ingreso.is_not(None)
                & (Anulaciones.tipo_anulable == "ingreso")
                & (Anulaciones.uuid_ingreso == Facturas.uuid_ingreso)
            )
        )
        .exists()
    )
    estado_expr = case((anulada_exists, "anulada"), else_="vigente").label("estado")

    iva_subq = (
        select(func.coalesce(func.sum(FacturaImpuestos.valor), 0.0))
        .where(FacturaImpuestos.uuid_factura == Facturas.uuid)
        .correlate(Facturas)
        .scalar_subquery()
    )

    stmt = (
        select(
            Facturas.uuid,
            Facturas.uuid_sucursal,
            Facturas.created_at,
            FacturaElectronica.prefijo,
            FacturaElectronica.consecutivo,
            Facturas.subtotal,
            Facturas.descuento,
            iva_subq.label("iva"),
            Facturas.total,
            estado_expr,
        )
        .select_from(Facturas)
        .outerjoin(FacturaElectronica, FacturaElectronica.uuid_factura == Facturas.uuid)
        .where(Facturas.uuid_sucursal.in_(target_sucursales))
        .where(func.date(Facturas.created_at) >= desde)
        .where(func.date(Facturas.created_at) <= hasta)
    )
    if uuid_cliente is not None:
        # The outerjoin above stays an outerjoin (shared with the
        # numero_completo resolution above) -- adding this predicate on
        # the joined side still only ever matches rows that DO have a
        # FacturaElectronica for this cliente; a NULL-FE row can never
        # satisfy ``== uuid_cliente``, so no restructuring is needed for
        # this filter to apply (works identically whether uuid_sucursal
        # is present or not).
        stmt = stmt.where(FacturaElectronica.uuid_cliente == uuid_cliente)
    stmt = stmt.order_by(Facturas.created_at.desc(), Facturas.uuid.asc())
    if decoded_cursor is not None:
        if decoded_cursor.created_at is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_cursor",
                    "detail": "cursor missing created_at (required for facturas listing)",
                },
            )
        cursor_ts = datetime.fromisoformat(
            decoded_cursor.created_at.replace("Z", "+00:00")  # noqa: FURB162
        ).replace(tzinfo=None)
        cursor_uuid = uuid_lib.UUID(decoded_cursor.uuid)
        stmt = stmt.where(
            (Facturas.created_at < cursor_ts)
            | ((Facturas.created_at == cursor_ts) & (Facturas.uuid > cursor_uuid))
        )
    stmt = stmt.limit(limit + 1)

    rows = (await session.execute(stmt)).all()
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = cursor_encode(
            Cursor(created_at=last.created_at.isoformat(), uuid=str(last.uuid))
        )

    items = [
        ReporteFacturaItem(
            uuid=row.uuid,
            uuid_sucursal=row.uuid_sucursal,
            created_at=row.created_at,
            numero_completo=(
                f"{row.prefijo}{row.consecutivo}"
                if row.prefijo is not None and row.consecutivo is not None
                else None
            ),
            subtotal=float(row.subtotal) if row.subtotal is not None else None,
            descuento=float(row.descuento) if row.descuento is not None else None,
            iva=float(row.iva or 0.0),
            total=float(row.total) if row.total is not None else None,
            estado=row.estado,
        )
        for row in rows
    ]

    return ReporteFacturasResponse(
        # None only in the HU-F20.1 cross-branch-by-cliente mode -- rows
        # may legitimately span multiple branches, so there is no single
        # branch to report here (see ReporteFacturasResponse docstring).
        uuid_sucursal=uuid_sucursal,
        desde=desde,
        hasta=hasta,
        items=items,
        next_cursor=next_cursor,
        generado_en=datetime.now(UTC),
    )


@router.get(
    "/fe",
    response_model=ReporteFeResponse,
    summary="Paginated factura_electronica + DIAN ack state (HU-F17.3, BR1)",
)
async def reporte_fe(
    session: DbSession,
    claims: AdminClaims,
    estado: str | None = Query(
        None,
        description=(
            "Raw v_factura_electronica_acuse.estado filter. 422 "
            "invalid_estado if not a real value."
        ),
    ),
    cursor: str | None = Query(None, description="Opaque cursor, created_at-keyed."),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ReporteFeResponse:
    """Cross-branch ``factura_electronica`` listing + latest DIAN ack (BR1).

    Cross-branch by nature -- same reasoning as ``reporte_ocupacion``:
    deliberately does NOT depend on ``get_tenant_ctx``/
    ``require_branch_scope`` (those bind a SINGLE
    ``X-Sucursal-Context`` branch to the ``do_orm_execute`` listener,
    which would silently narrow this endpoint to one branch). Scope is
    resolved fresh from ``usuarios_sucursal``
    (:func:`extract_sucursales_permitidas_fresh`) instead.

    ``estado`` is the RAW ``v_factura_electronica_acuse.estado`` value
    (BR1) -- see ``_ESTADO_DIAN_VALUES`` module comment for the real
    (8-value) domain this filter validates against, confirmed drift vs.
    plan.md's assumed 4 values.
    """
    if estado is not None and estado not in _ESTADO_DIAN_VALUES:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_estado",
                "estado": estado,
                "allowed": sorted(_ESTADO_DIAN_VALUES),
            },
        )

    actor_uuid = uuid_lib.UUID(claims["sub"])
    permitidas = await extract_sucursales_permitidas_fresh(session, actor_uuid=actor_uuid)
    if not permitidas:
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_sucursal_context"},
        )

    try:
        decoded_cursor = cursor_decode(cursor) if cursor else None
    except InvalidCursorError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_cursor", "detail": str(exc)},
        ) from exc

    stmt = (
        select(
            FacturaElectronica.uuid,
            FacturaElectronica.uuid_sucursal,
            FacturaElectronica.uuid_factura,
            FacturaElectronica.prefijo,
            FacturaElectronica.consecutivo,
            FacturaElectronica.created_at,
            v_factura_electronica_acuse.c.cufe,
            v_factura_electronica_acuse.c.estado,
            v_factura_electronica_acuse.c.timestamp_evento,
        )
        .select_from(FacturaElectronica)
        .outerjoin(
            v_factura_electronica_acuse,
            v_factura_electronica_acuse.c.uuid_factura_electronica == FacturaElectronica.uuid,
        )
        .where(FacturaElectronica.uuid_sucursal.in_(permitidas))
    )
    if estado is not None:
        stmt = stmt.where(v_factura_electronica_acuse.c.estado == estado)
    stmt = stmt.order_by(FacturaElectronica.created_at.desc(), FacturaElectronica.uuid.asc())
    if decoded_cursor is not None:
        if decoded_cursor.created_at is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_cursor",
                    "detail": "cursor missing created_at (required for fe listing)",
                },
            )
        cursor_ts = datetime.fromisoformat(
            decoded_cursor.created_at.replace("Z", "+00:00")  # noqa: FURB162
        ).replace(tzinfo=None)
        cursor_uuid = uuid_lib.UUID(decoded_cursor.uuid)
        stmt = stmt.where(
            (FacturaElectronica.created_at < cursor_ts)
            | ((FacturaElectronica.created_at == cursor_ts) & (FacturaElectronica.uuid > cursor_uuid))
        )
    stmt = stmt.limit(limit + 1)

    rows = (await session.execute(stmt)).all()
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = cursor_encode(
            Cursor(created_at=last.created_at.isoformat(), uuid=str(last.uuid))
        )

    items = [
        ReporteFeItem(
            uuid=row.uuid,
            uuid_sucursal=row.uuid_sucursal,
            uuid_factura=row.uuid_factura,
            numero_completo=(
                f"{row.prefijo}{row.consecutivo}"
                if row.prefijo is not None and row.consecutivo is not None
                else None
            ),
            cufe=row.cufe,
            estado_dian=row.estado,
            timestamp_evento=row.timestamp_evento,
        )
        for row in rows
    ]

    return ReporteFeResponse(
        items=items,
        next_cursor=next_cursor,
        generado_en=datetime.now(UTC),
    )


@router.get(
    "/pagos",
    response_model=ReportePagosResponse,
    summary="Pagos netos agrupados por medio_pago y dia (HU-F17.3, BR2)",
)
async def reporte_pagos(
    session: DbSession,
    _claims: Annotated[None, Depends(_admin_issuer_dep)],
    scope: Annotated[BranchScope, Depends(require_branch_scope)],
    uuid_sucursal: uuid_lib.UUID = Query(  # noqa: B008
        ...,
        description="Branch to report on. Must be in the actor's permitted set.",
    ),
    desde: date | None = Query(  # noqa: B008
        None,
        description="Inclusive UTC start date. Defaults to 6 days back.",
    ),
    hasta: date | None = Query(  # noqa: B008
        None,
        description="Inclusive UTC end date. Defaults to today (UTC).",
    ),
) -> ReportePagosResponse:
    """One branch's pagos, netted (pago - reverso) and grouped by
    ``(fecha, medio_pago)`` (BR2).

    ``tipo_movimiento='reverso'`` rows are NEVER filtered out -- they
    subtract from the same day/medio bucket, same ``CASE`` aggregate
    shape as ``reporte_operacional``'s ``monto_cobrado_neto_expr``. Joins
    through ``facturas`` (not ``factura_pagos.uuid_sucursal`` directly)
    to scope by branch -- same join path ``reporte_operacional``'s
    ``per_day_pagos`` subquery already uses, trusting ``facturas.
    uuid_sucursal`` as the source of truth for which branch a payment
    belongs to.
    """
    today = datetime.now(UTC).date()
    if hasta is None:
        hasta = today
    if desde is None:
        desde = hasta - timedelta(days=6)
    if desde > hasta:
        raise HTTPException(
            status_code=422,
            detail={"error": "rango_fecha_invalido"},
        )

    if not scope.permitidas:
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_sucursal_context"},
        )
    permitidas = scope.narrow(uuid_sucursal)
    target = next(iter(permitidas))

    medio_pago_expr = func.coalesce(FacturaPagos.medio_pago, "sin_especificar")
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
    stmt = (
        select(
            func.date(FacturaPagos.created_at).label("fecha"),
            medio_pago_expr.label("medio_pago"),
            monto_neto_expr.label("monto_neto"),
        )
        .select_from(FacturaPagos)
        .join(Facturas, Facturas.uuid == FacturaPagos.uuid_factura)
        .where(Facturas.uuid_sucursal == target)
        .where(func.date(FacturaPagos.created_at) >= desde)
        .where(func.date(FacturaPagos.created_at) <= hasta)
        .group_by(func.date(FacturaPagos.created_at), medio_pago_expr)
        .order_by(func.date(FacturaPagos.created_at), medio_pago_expr)
    )
    rows = (await session.execute(stmt)).all()
    items = [
        ReportePagoMedioItem(
            fecha=row.fecha,
            medio_pago=row.medio_pago,
            monto_neto=float(row.monto_neto or 0.0),
        )
        for row in rows
    ]

    return ReportePagosResponse(
        uuid_sucursal=target,
        desde=desde,
        hasta=hasta,
        items=items,
        generado_en=datetime.now(UTC),
    )


# HU-F17.4 -- subscription cohort retention heatmap + próximas a vencer.
#
# ``subscripciones_cliente``'s real columns (confirmed against
# ``models/V/subscripciones_cliente.py`` -- NO drift vs. plan.md's BR1,
# despite BR1's "CONFIRMÁ el nombre real" caution): ``fecha_inicio_cobertura``
# and ``fecha_vencimiento`` are exactly the names plan.md assumed.
_MAX_OFFSET_MESES = 12
_PROXIMAS_A_VENCER_LIMIT = 20


def _month_floor(d: date) -> date:
    """First day of ``d``'s UTC calendar month."""
    return d.replace(day=1)


def _add_months(d: date, months: int) -> date:
    """``d`` (month-floored semantics) shifted by ``months`` calendar months."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    return date(year, month, 1)


def _months_between(start: date, end: date) -> int:
    """Whole calendar months from ``start`` to ``end`` (both month-floored)."""
    return (end.year - start.year) * 12 + (end.month - start.month)


@router.get(
    "/suscripciones/cohorte",
    response_model=ReporteSuscripcionesCohorteResponse,
    summary="Subscription cohort retention heatmap + próximas a vencer (HU-F17.4)",
)
async def reporte_suscripciones_cohorte(
    session: DbSession,
    claims: AdminClaims,
    desde: Annotated[
        date | None,
        Query(
            description=(
                "Inclusive UTC lower bound on the cohort month "
                "(fecha_inicio_cobertura). Defaults to 11 months back "
                "from `hasta`'s month (a 12-cohort-month window)."
            )
        ),
    ] = None,
    hasta: Annotated[
        date | None,
        Query(description="Inclusive UTC upper bound on the cohort month. Defaults to today (UTC)."),
    ] = None,
) -> ReporteSuscripcionesCohorteResponse:
    """Cohort retention heatmap (BR1) + próximas-a-vencer alert list (HU-F17.4).

    Cross-branch by nature (every branch the admin can see, no
    ``uuid_sucursal`` query param) -- same reasoning ``reporte_ocupacion``/
    ``reporte_fe`` already document for this router: those dependencies
    bind a SINGLE ``X-Sucursal-Context`` branch, which would silently
    narrow an endpoint meant to span every branch the actor can see.
    Scope is resolved fresh from ``usuarios_sucursal``
    (:func:`extract_sucursales_permitidas_fresh`) instead.

    BR1 cohort math (see :class:`CohorteRetencionCell` for the full
    rationale) is computed APPLICATION-SIDE, not in SQL: the matrix's
    column count (``mes_offset``) is dynamic per cohort (how many whole
    months have elapsed since that cohort's start, capped at
    ``_MAX_OFFSET_MESES``), which is awkward to express as a single SQL
    aggregate without either a recursive CTE or a fixed-width CROSS JOIN
    that would compute (and discard) not-yet-measurable future cells.
    Fetching the raw (``fecha_inicio_cobertura``, ``fecha_vencimiento``)
    rows once and reducing them in Python keeps the logic simple,
    testable, and correct for the dataset sizes a subscription cohort
    report deals with (one row per customer per subscription period).

    Both queries filter ``vigente_hasta IS NULL`` -- each logical
    subscription's CURRENT version (a renewal or an early cancellation
    both go through ``close_and_insert``, REQ-04/05 -- see
    :class:`CohorteSuscripcionItem`'s docstring).
    """
    actor_uuid = uuid_lib.UUID(claims["sub"])
    permitidas = await extract_sucursales_permitidas_fresh(session, actor_uuid=actor_uuid)
    if not permitidas:
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_sucursal_context"},
        )

    today = datetime.now(UTC).date()
    if hasta is None:
        hasta = today
    if desde is None:
        desde = _add_months(_month_floor(hasta), -(_MAX_OFFSET_MESES - 1))
    if desde > hasta:
        raise HTTPException(
            status_code=422,
            detail={"error": "rango_fecha_invalido"},
        )

    cohort_rows = (
        await session.execute(
            select(
                SubscripcionesCliente.fecha_inicio_cobertura,
                SubscripcionesCliente.fecha_vencimiento,
            )
            .where(SubscripcionesCliente.uuid_sucursal.in_(permitidas))
            .where(SubscripcionesCliente.vigente_hasta.is_(None))
            .where(SubscripcionesCliente.fecha_inicio_cobertura.is_not(None))
            .where(SubscripcionesCliente.fecha_inicio_cobertura >= desde)
            .where(SubscripcionesCliente.fecha_inicio_cobertura <= hasta)
        )
    ).all()

    members_by_month: dict[date, list[date | None]] = {}
    for row in cohort_rows:
        mes = _month_floor(row.fecha_inicio_cobertura)
        members_by_month.setdefault(mes, []).append(row.fecha_vencimiento)

    cohortes: list[CohorteSuscripcionItem] = []
    data: list[CohorteRetencionCell] = []
    for mes in sorted(members_by_month):
        vencimientos = members_by_month[mes]
        size = len(vencimientos)
        cohortes.append(CohorteSuscripcionItem(mes_cohorte=mes, cohorte_size=size))
        max_offset = min(_MAX_OFFSET_MESES, _months_between(mes, today))
        for offset in range(max_offset + 1):
            threshold = _add_months(mes, offset)
            retenidos = sum(1 for v in vencimientos if v is None or v >= threshold)
            data.append(
                CohorteRetencionCell(
                    mes_cohorte=mes,
                    mes_offset=offset,
                    cohorte_size=size,
                    retenidos=retenidos,
                    porcentaje_retencion=(retenidos / size * 100.0) if size else 0.0,
                )
            )

    # Próximas a vencer -- reuses the exact REQ-OPS-181 criterion (see
    # SuscripcionPorVencerItem's docstring): dias_para_vencer >= 0
    # (vencidas excluded), ascending by fecha_vencimiento, top 20. Also
    # excludes administratively deactivated subscriptions
    # (``estado == 'inactivo'``, VersionedMixin's generic flag) -- those
    # are no longer a live expiry concern for the admin's alert list,
    # unlike the cohort math above which deliberately does NOT apply
    # this filter (a cohort's retention denominator must include every
    # historical member regardless of its current administrative state).
    por_vencer_rows = (
        await session.execute(
            select(
                SubscripcionesCliente.uuid,
                SubscripcionesCliente.uuid_cliente,
                SubscripcionesCliente.uuid_sucursal,
                SubscripcionesCliente.fecha_vencimiento,
            )
            .where(SubscripcionesCliente.uuid_sucursal.in_(permitidas))
            .where(SubscripcionesCliente.vigente_hasta.is_(None))
            .where(SubscripcionesCliente.estado == "activo")
            .where(SubscripcionesCliente.fecha_vencimiento.is_not(None))
            .where(SubscripcionesCliente.fecha_vencimiento >= today)
            .order_by(SubscripcionesCliente.fecha_vencimiento.asc())
            .limit(_PROXIMAS_A_VENCER_LIMIT)
        )
    ).all()
    proximas_a_vencer = [
        SuscripcionPorVencerItem(
            uuid=row.uuid,
            uuid_cliente=row.uuid_cliente,
            uuid_sucursal=row.uuid_sucursal,
            fecha_vencimiento=row.fecha_vencimiento,
            dias_para_vencer=(row.fecha_vencimiento - today).days,
        )
        for row in por_vencer_rows
    ]

    return ReporteSuscripcionesCohorteResponse(
        desde=desde,
        hasta=hasta,
        cohortes=cohortes,
        data=data,
        max_offset_meses=_MAX_OFFSET_MESES,
        proximas_a_vencer=proximas_a_vencer,
        generado_en=datetime.now(UTC),
    )


__all__ = ["router"]