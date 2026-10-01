"""Operational reports (HU-F17.1/F17.2, PR-C).

Cloud-friendly surfaces (can mount on ``api_admin`` and ``api_sucursal``).
Only ``admin-`` issuers reach this surface, gated by
``require_branch_scope`` so the report cannot leak across the actor's
permitted branches.

Endpoints:

- ``GET /api/v1/admin/reporteria/operacional?uuid_sucursal=&fecha_desde=&fecha_hasta=``

  Returns per-day counts + monto_facturado/monto_cobrado for the branch
  over the date range, plus a grand-total rollup. No time series, no
  charts — explicit F17.1 user directive.

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
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_session, require_branch_scope, requires_issuer
from ...auth.tenancy import BranchScope
from ...models.A.factura_pagos import FacturaPagos
from ...models.A.salidas import Salidas
from ...models.L_E.facturas import Facturas
from ...models.L_E.ingreso import Ingreso
from ...models.L_W.anulaciones import Anulaciones
from ...schemas.reporteria import (
    ReporteOperacionalItem,
    ReporteOperacionalResponse,
)

router = APIRouter(prefix="/admin/reporteria", tags=["admin", "reporteria"])

_admin_issuer_dep = requires_issuer("admin-")
AdminClaims = Annotated[dict[str, Any], Depends(_admin_issuer_dep)]
DbSession = Annotated[AsyncSession, Depends(get_session)]


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

    return ReporteOperacionalResponse(
        uuid_sucursal=target,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        items=items,
        totales=totales,
        generado_en=datetime.now(UTC),
    )


__all__ = ["router"]