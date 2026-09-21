"""HU-F12.1 -- per-turn KPI aggregation repo helper.

``calcular_resumen_mi_turno(session, uuid_sesion)`` reads the open
``prod.sesion`` row, runs the open-window temporal JOIN against
``prod.ingreso`` and ``prod.salidas``, and adds the two
``factura_pagos`` ``SUM`` aggregates (efectivo / datafono).

This helper is **read-only** — no INSERT, UPDATE, or DELETE. The
endpoint that exposes it (``GET /operacion/mi-turno``) returns
``MiTurnoRead`` over the wire.

Reuse of the canonical ``SUM`` helper
(:func:`parkos_core.repo.arqueo._sum_factura_pagos_by_medio_pago`) is
mandatory per AD-3 / R-F12.1-2 — no new SUM helper introduced.

Tuple arguments (verbatim F1.13 ``calcular_esperado_sesion``):
    * ``("efectivo",)``                          -> efectivo bucket
    * ``("tarjeta", "datafono")``                -> datafono bucket
      (both tarjeta and datafono classify as POS PIN-pad payments
      distinct from efectivo, per ``repo/arqueo.py:345``).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..app.sql.mi_turno_query import build_mi_turno_counts_sql
from ..models.L_S.sesion import Sesion
from ..schemas.operacion import MiTurnoRead


class SesionNotFoundError(Exception):
    """Raised when ``prod.sesion.uuid`` does not resolve.

    Translated to HTTP 404 ``sesion_not_found`` by the handler
    (:func:`parkos_core.api.v1.operacion.get_mi_turno`).
    """

    def __init__(self, *, uuid_sesion: uuid_lib.UUID) -> None:
        super().__init__(f"sesion not found: uuid={uuid_sesion}")
        self.uuid_sesion = uuid_sesion


async def _sum_factura_pagos_by_medio_pago(
    session: AsyncSession,
    *,
    uuid_sesion: uuid_lib.UUID,
    medios_pago: tuple[str, ...],
) -> Decimal:
    """Re-export of the canonical SUM helper for the mi-turno flow.

    Wraps :func:`parkos_core.repo.arqueo._sum_factura_pagos_by_medio_pago`
    so the handler can patch a single import path in unit tests. The
    canonical helper signature is preserved verbatim (R-F12.1-2).

    Importing at module-level would create a circular dependency
    (``repo.mi_turno`` -> ``repo.arqueo``); the import is local on
    purpose and the lookup is cheap.
    """
    from . import arqueo as _arqueo

    raw = await _arqueo._sum_factura_pagos_by_medio_pago(
        session,
        uuid_sesion=uuid_sesion,
        uuid_sucursal=None,
        fecha=None,
        medios_pago=medios_pago,
    )
    return Decimal(str(raw)) if not isinstance(raw, Decimal) else raw


async def calcular_resumen_mi_turno(
    session: AsyncSession,
    *,
    uuid_sesion: uuid_lib.UUID,
    timestamp_calculo: datetime,
) -> MiTurnoRead:
    """Compute the per-turn KPI aggregate (REQ-OPS-184..186).

    Pipeline:
      1. SELECT prod.sesion (404 if not found)
      2. Build the open-window JOIN SQL with the resolved branch scope
      3. SUM ``prod.factura_pagos.valor`` twice (efectivo, datafono)
         via the canonical :func:`arqueo._sum_factura_pagos_by_medio_pago`
      4. Return :class:`MiTurnoRead` with ``timestamp_calculo`` echoed
         from the caller (the handler injects the naive UTC value at
         request time so test mocks can pin a deterministic timestamp).

    Raises:
        SesionNotFoundError: when ``prod.sesion.uuid`` does not resolve.
    """
    # 1. Resolve the sesion anchor.
    sesion = (
        await session.execute(select(Sesion).where(Sesion.uuid == uuid_sesion))
    ).scalar_one_or_none()
    if sesion is None:
        raise SesionNotFoundError(uuid_sesion=uuid_sesion)

    # The sesion's branch scope is the tenant-pin anchor (REQ-OPS-185).
    # The handler has already validated ``Sesion.uuid_sucursal ==
    # ctx.sucursal_uuid`` BEFORE this helper is called; we propagate
    # the resolved value into the FILTER so the COUNT can never
    # accidentally include events from a different branch.
    s_sucursal = sesion.uuid_sucursal
    if s_sucursal is None:
        # Defensive: a sesion without a branch is a data-integrity bug.
        # We still return a zero-state response rather than 500 so the
        # FE keeps the panel functional.
        return MiTurnoRead(
            uuid_sesion=sesion.uuid,
            uuid_sucursal=uuid_lib.UUID(int=0),  # sentinel
            timestamp_calculo=timestamp_calculo,
        )

    t_open = sesion.timestamp_apertura
    t_close = sesion.timestamp_cierre

    sql = build_mi_turno_counts_sql(
        uuid_sesion=uuid_sesion,
        s_sucursal=s_sucursal,
        t_open=t_open.isoformat() if t_open is not None else None,
        t_close=t_close.isoformat() if t_close is not None else None,
    )

    bind_params: dict[str, object] = {
        "uuid_sesion": str(uuid_sesion),
        "S_s": str(s_sucursal),
        "t_open": t_open,
        "t_close": t_close,
    }

    row = (await session.execute(text(sql), bind_params)).first()
    if row is None:
        # Defensive: the sesion was deleted between the SELECT and the
        # COUNT. Treat as zero-state so the panel degrades gracefully.
        ingresos_count = 0
        salidas_count = 0
    else:
        ingresos_count = int(row[0] or 0)
        salidas_count = int(row[1] or 0)

    # 3. SUM factura_pagos (efectivo + datafono) via canonical helper.
    total_efectivo = await _sum_factura_pagos_by_medio_pago(
        session,
        uuid_sesion=uuid_sesion,
        medios_pago=("efectivo",),
    )
    total_datafono = await _sum_factura_pagos_by_medio_pago(
        session,
        uuid_sesion=uuid_sesion,
        medios_pago=("tarjeta", "datafono"),
    )

    return MiTurnoRead(
        uuid_sesion=sesion.uuid,
        uuid_sucursal=s_sucursal,
        timestamp_calculo=timestamp_calculo,
        ingresos_count=ingresos_count,
        salidas_count=salidas_count,
        total_cobrado_efectivo_cop=total_efectivo,
        total_cobrado_datafono_cop=total_datafono,
    )


__all__ = ["SesionNotFoundError", "calcular_resumen_mi_turno"]