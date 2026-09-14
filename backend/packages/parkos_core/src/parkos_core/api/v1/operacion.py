"""Operation HTTP routes (PR5 — ingreso lifecycle event).

``ingreso`` is ``[L-E]`` (insert-only event). Writes MUST go through
``repo.event.record_event`` (REQ-30, REQ-33). NO PUT/DELETE — events are
append-only.

Custom ``GET /ingresos/{uuid}/estado`` reads the derived view
``V_INGRESO_ESTADO`` (REQ-32-E-DERIVED-ESTADO, SC-30). State values:
- ``abierto``: ingreso has no ``salidas`` row yet
- ``cerrado``: matching ``salidas`` row exists
- ``anulada``: matching ``anulaciones`` chain exists (PR6 mounts)

**T-PR5-016 (REQ-CAT-017, addendum #2, design.md §2 Issue #11) —
:func:`resolve_active_subscription_for_exit`.** The exit ("salida") HTTP
endpoint itself is not built by any PR up to and including this one (no
``salidas`` CRUD route exists yet in this router or elsewhere in
``api/v1/``) — building it is out of PR5's scope. What PR5 DOES own per
design.md §2 Issue #11 point 3 is the defense-in-depth VALIDATION QUERY the
future CU-03M exit flow will call: a branch that never receives another
branch's ``subscripciones_cliente`` row (``broadcast_policy="subscription"``
scoping, R22) cannot validate against it — that is an *availability*
control, not an *integrity* one, because a stale or manually-inserted row
would still validate. This function explicitly filters
``WHERE uuid_sucursal = :this_branch`` **in addition to** relying on the
scoped sync, so it validates correctly the moment the exit endpoint is
built on top of it, without repeating that mistake.
"""
from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_tenant_ctx, requires_issuer
from ...auth.tenancy import TenantContext
from ...db.engine import get_session
from ...models.L_E.ingreso import Ingreso
from ...models.V.subscripcion_vehiculos import SubscripcionVehiculos
from ...models.V.subscripciones_cliente import SubscripcionesCliente
from ...models.V.vehiculos import Vehiculos
from ...repo.cotizacion import (
    CotizacionError,
    IngresoNoEncontrado,
    IVANoConfigurado,
    TarifaNoVigente,
    cotizar_ingreso,
)
from ...repo.event import record_event
from ...schemas.operacion import (
    CotizarFacturacion,
    CotizarMensualidad,
    CotizarResponse,
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


# ---------------------------------------------------------------------------
# HU-F1.8 (REQ-OPS-022..025) -- GET /operacion/cotizar
# ---------------------------------------------------------------------------


def _cotizar_no_store_headers() -> dict[str, str]:
    """Return the ``Cache-Control: no-store`` headers (R8).

    Every response from ``/operacion/cotizar`` MUST carry this header
    regardless of status code -- a proxy that serves a stale quote
    would silently accept an out-of-date fiscal breakdown. The handler
    attaches the header to both the success path (via ``response.headers``)
    and the error path (via ``HTTPException(headers=...)``).
    """
    return {"Cache-Control": "no-store"}


@router.get(
    "/cotizar",
    response_model=CotizarResponse,
    summary="Server-side quotation for an open ingreso (HU-F1.8, GAP-BE-09)",
    responses={
        404: {"description": "Ingreso no existe o ya cerrado / sin tarifa vigente"},
        500: {"description": "IVA no configurado (KD-IVA deployment blocker)"},
    },
)
async def cotizar_ingreso_handler(
    response: Response,
    uuid_ingreso: uuid_lib.UUID = Query(  # noqa: B008
        ...,
        description="UUIDv4 del ingreso a cotizar",
    ),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_ingreso_issuer_dep),
) -> CotizarResponse:
    """Compute the fiscal breakdown (or short-circuit) for ``uuid_ingreso``.

    Thin adapter over ``repo.cotizacion.cotizar_ingreso`` -- the whole
    pricing formula lives in PL/pgSQL (``prod.calcular_cotizacion``,
    migration ``0022_create_calcular_cotizacion.py``) so the
    ``SELECT ... FOR SHARE`` lock on ``tarifas_sucursal`` (KD-1) holds
    for the whole transaction. Handler-side responsibilities:

      1. Parse ``uuid_ingreso`` (Pydantic UUID4 via ``Query``).
      2. Call the repo; map typed exceptions to ``HTTPException``
         with the right status code and the ``Cache-Control: no-store``
         header attached.
      3. Map the jsonb payload to :class:`CotizarResponse` (discriminated
         by ``cobrar: bool``).

    The function does NOT commit the session -- the AsyncSession
    dependency commits on context-manager exit (and the test suite uses
    nested-rollback). The PL/pgSQL lock is released when the transaction
    ends, which is the same boundary.
    """
    # Attach the no-store header to the SUCCESS path. The error path
    # carries the same header via ``HTTPException(headers=...)`` below.
    response.headers["Cache-Control"] = "no-store"

    try:
        payload = await cotizar_ingreso(session, uuid_ingreso=uuid_ingreso)
    except IngresoNoEncontrado as err:
        raise HTTPException(
            status_code=404,
            detail={"error": "ingreso_no_encontrado"},
            headers=_cotizar_no_store_headers(),
        ) from err
    except TarifaNoVigente as err:
        raise HTTPException(
            status_code=404,
            detail={"error": "tarifa_no_vigente"},
            headers=_cotizar_no_store_headers(),
        ) from err
    except IVANoConfigurado as err:
        raise HTTPException(
            status_code=500,
            detail={"error": "iva_no_configurado"},
            headers=_cotizar_no_store_headers(),
        ) from err
    except CotizacionError as err:
        # Unknown / unexpected error code from the PL/pgSQL function --
        # surface as 500 with the original message; never silently swallow.
        raise HTTPException(
            status_code=500,
            detail={"error": "cotizacion_error"},
            headers=_cotizar_no_store_headers(),
        ) from err

    # Map jsonb -> CotizarResponse. The PL/pgSQL function returns
    # ``cobrar: false, motivo: 'mensualidad_vigente'`` OR
    # ``cobrar: true, ...fiscal fields...`` -- Pydantic's discriminated
    # union picks the variant by ``cobrar``.
    if payload.get("cobrar") is True:
        return CotizarFacturacion.model_validate(payload)
    return CotizarMensualidad.model_validate(payload)


# ---------------------------------------------------------------------------
# T-PR5-016 (REQ-CAT-017, addendum #2) — CU-03M subscription lookup, R22
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubscriptionLookupResult:
    """Outcome of :func:`resolve_active_subscription_for_exit` (T-PR5-016).

    ``message`` distinguishes the two operator-facing states design.md §2
    Issue #11 point 4 requires kept distinct: "no subscription at this
    branch" (R22 — a normal, silent, correct outcome; the vehicle may
    legitimately be subscribed at a DIFFERENT branch, which this branch
    cannot see by ``broadcast_policy="subscription"`` scoping) vs.
    "subscription expired" (a subscription row DOES exist locally for this
    branch, but ``fecha_vencimiento`` has passed).
    """

    found: bool
    subscripcion: SubscripcionesCliente | None = None
    message: str | None = None


async def resolve_active_subscription_for_exit(
    session: AsyncSession,
    *,
    placa: str,
    uuid_sucursal: uuid_lib.UUID,
    as_of: date | None = None,
) -> SubscriptionLookupResult:
    """CU-03M exit-with-subscription validation query (R22, design.md §2 Issue #11).

    Looks up an OPEN ``subscripciones_cliente`` row covering ``placa``
    (via the ``subscripcion_vehiculos`` junction, both currently-open
    versions) that ALSO belongs to THIS branch.

    **Defense in depth (belt and suspenders, not a contradiction of the
    scoping decision).** ``broadcast_policy="subscription"`` sync already
    means a non-selling branch's local ``subscripciones_cliente`` table
    simply does not contain another branch's rows — that is an
    *availability* control. This function ALSO filters explicitly on
    ``uuid_sucursal == :this_branch`` so a stale or manually-inserted row
    for another branch is rejected even if it were somehow present locally
    — an *integrity* control, independent of the sync scoping.

    Returns:
        ``SubscriptionLookupResult(found=False, message="no subscription at
        this branch")`` when no row matches — R22's normal, silent, correct
        outcome (charge the standard tariff; no ``sync_conflict``, no
        ``alerta``, no buffer row, no error metric).
        ``SubscriptionLookupResult(found=False, message="subscription
        expired")`` when a matching row exists but ``fecha_vencimiento`` is
        in the past.
        ``SubscriptionLookupResult(found=True, subscripcion=...)`` otherwise.
    """
    stmt = (
        select(SubscripcionesCliente)
        .join(
            SubscripcionVehiculos,
            SubscripcionVehiculos.uuid_subscripcion_cliente == SubscripcionesCliente.uuid,
        )
        .join(Vehiculos, Vehiculos.uuid == SubscripcionVehiculos.uuid_vehiculo)
        .where(
            SubscripcionesCliente.uuid_sucursal == uuid_sucursal,  # R22 defense in depth
            SubscripcionesCliente.vigente_hasta.is_(None),
            SubscripcionVehiculos.vigente_hasta.is_(None),
            Vehiculos.vigente_hasta.is_(None),
            Vehiculos.placa == placa,
        )
        .order_by(SubscripcionesCliente.vigente_desde.desc())
    )
    subscripcion = (await session.execute(stmt)).scalars().first()

    if subscripcion is None:
        return SubscriptionLookupResult(found=False, message="no subscription at this branch")

    reference_date = as_of or datetime.now(UTC).date()
    if (
        subscripcion.fecha_vencimiento is not None
        and subscripcion.fecha_vencimiento < reference_date
    ):
        return SubscriptionLookupResult(
            found=False, subscripcion=subscripcion, message="subscription expired"
        )

    return SubscriptionLookupResult(found=True, subscripcion=subscripcion)


__all__ = ["SubscriptionLookupResult", "cotizar_ingreso_handler", "resolve_active_subscription_for_exit", "router"]