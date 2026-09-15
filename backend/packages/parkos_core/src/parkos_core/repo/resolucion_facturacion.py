"""Branch-local ``consecutivo`` assignment for ``factura_electronica`` (T-PR9-002).

D1-rev (design.md §1 Executive Summary, §2 Issue #9): the branch assigns its
own DIAN ``consecutivo`` locally, inside its own (already-synced,
``cloud_to_branch``) ``resolucion_facturacion`` range, **without waiting on
the cloud** — this is what makes offline invoicing possible. The cloud only
validates the received ``consecutivo`` falls inside the resolution's
authorized range (``dian/cloud/dispatcher.py``, T-PR9-003) and forwards the
document to the DIAN provider; it never assigns the number itself.

This mirrors the row-locking mechanism of the withdrawn cloud-side
``dian/cloud/atomic_next_consecutivo.py`` allocator (``SELECT ... FOR
UPDATE`` on the resolution row + ``COALESCE(MAX(consecutivo), rango_desde -
1) + 1``, scoped to the resolution) but runs against the BRANCH's local
database and adds the property that module never needed: idempotent,
transactional assignment keyed on the emitting business event, so a retry
of the SAME event never mints a second number (design.md §2 Issue #9:
"never generate a consecutivo, discard it, and generate a new one on
retry"). See this PR's apply report for the disposition of
``atomic_next_consecutivo.py`` itself (left in place; it now serves a
DIFFERENT, still-live cloud-only endpoint outside this PR's scope).
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.L_E.factura_electronica import FacturaElectronica
from ..models.V.resolucion_facturacion import ResolucionFacturacion


class ResolucionFacturacionNotFoundError(RuntimeError):
    """Raised when ``resolucion_uuid`` matches no local ``resolucion_facturacion`` row."""


class ConsecutivoRangeExhaustedError(RuntimeError):
    """Raised when the resolution's authorized range has no room left.

    Callers map this to ``alerta tipo_alerta='fe_numbering_exhausted'``
    (``repo/alert_types.py``, T-PR8-002) — the branch needs a new DIAN
    resolution before it can number another document.
    """


async def assign_consecutivo(
    session: AsyncSession,
    resolucion_uuid: uuid_lib.UUID,
    source_event_uuid: uuid_lib.UUID,
) -> int:
    """Assign the next ``consecutivo`` inside ``resolucion_uuid``'s range.

    **Idempotent per ``source_event_uuid``** (T-PR9-001, design.md §2 Issue
    #9): looks up FIRST whether a ``factura_electronica`` row already
    exists for this exact ``(resolucion_uuid, source_event_uuid)`` pair. If
    one does, its already-assigned ``consecutivo`` is returned — a retry of
    the SAME emitting event (e.g. the caller crashed after this function
    returned but before the row's INSERT committed, and re-invokes the
    whole create flow) reuses the same number instead of leaking a gap or
    handing out a second one for the same invoice.

    **No side effect outside the caller's transaction.** This helper only
    reads plus takes a row lock (``SELECT ... FOR UPDATE`` on the
    resolution row) — it never inserts or commits anything itself. The
    caller is expected to INSERT the new ``factura_electronica`` row (via
    ``repo.event.record_event``) using the returned number and commit
    together, in the SAME transaction/session. If that transaction rolls
    back, nothing was consumed: no ``factura_electronica`` row landed, so
    the next call recomputes ``MAX(consecutivo)`` from the SAME committed
    state and hands out the SAME number again.

    Args:
        session: Active ``AsyncSession`` — caller commits together with
            the ``factura_electronica`` INSERT that consumes the returned
            number.
        resolucion_uuid: The specific ``resolucion_facturacion`` version
            row (the branch's own, already-synced ``cloud_to_branch``
            copy) to assign inside. Matches
            ``factura_electronica.uuid_resolucion_facturacion`` exactly.
        source_event_uuid: Identifies the business event requesting a
            number — the associated ``facturas`` row's ``uuid``
            (``factura_electronica.uuid_factura``, 1:1 with the DIAN
            invoice). Used ONLY for the idempotency lookup; never
            persisted by this function.

    Returns:
        The next ``consecutivo`` (``int``), guaranteed inside
        ``[rango_desde, rango_hasta]`` when both bounds are set.

    Raises:
        ResolucionFacturacionNotFoundError: no local row for
            ``resolucion_uuid``.
        ConsecutivoRangeExhaustedError: the resolution's range has no
            room left for another number.
    """
    # 1. Idempotency check FIRST — a retry of the same source event must
    # return the already-assigned number, never touch MAX() again.
    existing = (
        await session.execute(
            select(FacturaElectronica.consecutivo).where(
                FacturaElectronica.uuid_resolucion_facturacion == resolucion_uuid,
                FacturaElectronica.uuid_factura == source_event_uuid,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return int(existing)

    # 2. Lock the resolution row for the duration of this transaction —
    # concurrent assignment attempts on the SAME resolution (e.g. two
    # cashiers at the same branch) serialize cleanly instead of racing on
    # the MAX() read below.
    resolucion = (
        await session.execute(
            select(ResolucionFacturacion)
            .where(ResolucionFacturacion.uuid == resolucion_uuid)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if resolucion is None:
        raise ResolucionFacturacionNotFoundError(
            f"resolucion_facturacion {resolucion_uuid} not found (branch-local copy)"
        )

    rango_desde = resolucion.rango_desde
    rango_hasta = resolucion.rango_hasta
    start = (rango_desde - 1) if rango_desde is not None else 0

    # scalar_one: COALESCE always returns exactly one value.
    max_consecutivo = (
        await session.execute(
            text(
                "SELECT COALESCE(MAX(consecutivo), :start) "
                "FROM prod.factura_electronica "
                "WHERE uuid_resolucion_facturacion = :uuid"
            ),
            {"start": start, "uuid": str(resolucion_uuid)},
        )
    ).scalar_one()
    next_value = int(max_consecutivo) + 1

    if rango_hasta is not None and next_value > rango_hasta:
        raise ConsecutivoRangeExhaustedError(
            f"resolucion_facturacion {resolucion_uuid} range exhausted: "
            f"next consecutivo {next_value} exceeds rango_hasta={rango_hasta}"
        )

    return next_value


async def buscar_resolucion_vigente_por_sucursal(
    session: AsyncSession, *, uuid_sucursal: uuid_lib.UUID
) -> ResolucionFacturacion | None:
    """REQ-OPS-073 / R2 mitigation — locate the vigente resolution.

    A given ``uuid_sucursal`` may have multiple version rows over time
    (bi-temporal close+insert). The vigente row is the one whose
    ``vigente_hasta IS NULL`` (open interval) AND ``estado='activo'``.
    In the (defensive) case that more than one row satisfies both,
    ``ORDER BY vigente_desde DESC LIMIT 1`` returns the latest.

    Returns the ORM row, or ``None`` if no vigente row exists.
    """
    stmt = (
        select(ResolucionFacturacion)
        .where(
            ResolucionFacturacion.uuid_sucursal == uuid_sucursal,
            ResolucionFacturacion.vigente_hasta.is_(None),
            ResolucionFacturacion.estado == "activo",
        )
        .order_by(ResolucionFacturacion.vigente_desde.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


__all__ = [
    "ConsecutivoRangeExhaustedError",
    "ResolucionFacturacionNotFoundError",
    "assign_consecutivo",
    "buscar_resolucion_vigente_por_sucursal",
]
