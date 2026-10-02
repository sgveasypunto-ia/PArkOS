"""HU-F20.2 — dedicated ``POST /clientes/subscripcion-vehiculos``.

THE PROBLEM THIS PINS
----------------------
``schemas/clientes.py``'s ``SubscripcionVehiculosCreate`` docstring
CLAIMED (pre-HU-F20.2) that "the authoritative count check lives in the
endpoint wrapped by T-PR5-06's ``api/v1/clientes.py`` with
``pg_advisory_xact_lock(uuid_subscripcion_cliente)``". That claim was
verified FALSE while building this HU: grepping ``advisory`` /
``cantidad_maxima_vehiculos`` / ``mismo_tipo_vehiculo`` in
``api/v1/clientes.py`` returned nothing, and ``subscripcion-vehiculos``
was mounted 100% generically via ``router_factory.make_router`` with no
pre-insert hook at all -- any caller with ``gestionar_clientes`` could
INSERT an unbounded number of vehiculos onto any subscripcion, mixing
vehicle tipos freely, and double-covering a vehiculo already active on a
different subscripcion. This module builds the validation that docstring
only documented.

WHY A DEDICATED ROUTER AND NOT A HOOK ON ``make_router``
----------------------------------------------------------
Investigated first (per task brief): ``router_factory.make_router``'s
``create_endpoint``/``update_endpoint`` closures call
``repo.versioned.close_and_insert`` directly with no pre-insert hook
parameter of any kind -- adding one would mean changing the SHARED
factory every other mounted resource (``clientes``, ``clientes-b2b``,
``vehiculos``, every ``[V]``/``[L-W]`` table across the whole API)
depends on. Same criterion already applied in HU-F19.5
(``workflows_alerta.py``) and HU-F20.3 (``workflows_anulaciones.py`` /
``workflows_reclamos.py``): ``subscripcion-vehiculos`` is mounted with
``write_enabled=False`` in ``api/v1/clientes.py`` (GET list/detail/history
stay generic -- reads need no validation), and this dedicated router owns
POST only, reusing the EXISTING ``SubscripcionVehiculosCreate`` /
``SubscripcionVehiculosRead`` schemas verbatim (no new wire contract).

PUT is intentionally NOT replaced: nothing in this codebase calls the
generic ``PUT /subscripcion-vehiculos/{uuid}`` (grepped -- the only
"quitar vehiculo" consumer is the dedicated
``PUT /subscripcion-vehiculos/{uuid}/quitar`` in ``clientes_cupos.py``,
which writes via ``repo.versioned.close_and_insert`` directly, never
through the generic factory route), and
``SubscripcionVehiculosUpdate`` cannot carry an ``estado`` transition
anyway (see ``clientes_cupos.py``'s own docstring on that gap). Disabling
it via ``write_enabled=False`` removes dead, unvalidated surface instead
of leaving it half-protected.

VALIDATION ORDER (all BEFORE any INSERT, mirrors ``clientes_venta.py``'s
Layer-5 style 422/404/409 mapping)
--------------------------------------------------------------------------
1. 404 ``subscripcion_no_encontrada`` -- target subscripcion must be
   vigente+activa (reuses ``repo.cupos_subscripcion`` lookup, which
   already joins in the plan + existing vehiculos in one query).
2. 404 ``vehiculo_no_encontrado`` -- ``uuid_vehiculo`` must be vigente.
3. 409 ``vehiculo_ya_inscrito`` -- cheapest check, no cross-subscripcion
   query: is this exact vehiculo already active on THIS subscripcion.
4. 422 ``placa_con_suscripcion_vigente`` (BR3/E1, NEW) -- is this vehiculo
   already active on a DIFFERENT subscripcion (branch-agnostic).
5. 422 ``cantidad_vehiculos_excede_plan`` (V6, reusing
   ``repo.venta_suscripcion.validar_cantidad_maxima_vehiculos`` --
   SAME pure check the venta-at-the-counter flow already uses, just a
   DIFFERENT wire error code per this HU's explicit contract, plan.md
   HU-F20.2 "Errores").
6. 422 ``tipo_vehiculo_mixto_no_permitido`` (V5, reusing
   ``repo.venta_suscripcion.validar_placas_mismo_tipo_vehiculo`` -- same
   reuse/rename rationale as #5).

Concurrency: the actual INSERT goes through
``repo.venta_suscripcion.crear_subscripcion_vehiculos_bulk``, which already
wraps a REAL ``pg_advisory_xact_lock(uuid_subscripcion_cliente)`` (not just
documented) -- serializing two concurrent requests racing the same
subscripcion's vehicle count, same mechanism the venta-at-the-counter flow
and the cupos ``/agregar`` endpoint both already rely on. No new lock
primitive was introduced; this endpoint reuses the existing one.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.permissions import require_permission
from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...db.engine import get_session
from ...models.V.vehiculos import Vehiculos
from ...repo import cupos_subscripcion as repo_cupos
from ...repo import venta_suscripcion as repo_venta
from ...schemas.clientes import SubscripcionVehiculosCreate, SubscripcionVehiculosRead
from ..deps import requires_issuer
from . import _helpers

# NO "/clientes" prefix -- api/v1/clientes.py includes this router into
# ITS OWN router (already carrying prefix="/clientes") via a bare
# ``router.include_router(...)`` with no prefix arg. Same real bug class
# already found + fixed on ``clientes_venta.py`` (see that file's own
# ``router = APIRouter(...)`` comment).
router = APIRouter(prefix="/subscripcion-vehiculos", tags=["clientes"])

# Mirrors the ("operador-,admin-", "gestionar_clientes") policy
# ``_ROUTER_CONFIG["subscripcion-vehiculos"]`` already declares in
# ``api/v1/clientes.py`` -- this endpoint REPLACES only the generic
# factory's POST route, not the issuer/permission contract callers
# already depend on.
_issuer_dep = requires_issuer("operador-", "admin-")
_permission_dep = require_permission("gestionar_clientes")


@router.post(
    "",
    response_model=SubscripcionVehiculosRead,
    status_code=201,
    responses={
        404: {"description": "subscripcion_no_encontrada / vehiculo_no_encontrado"},
        409: {"description": "vehiculo_ya_inscrito"},
        422: {
            "description": (
                "placa_con_suscripcion_vigente / cantidad_vehiculos_excede_plan / "
                "tipo_vehiculo_mixto_no_permitido"
            )
        },
    },
)
async def crear_subscripcion_vehiculo(
    response: Response,
    payload: SubscripcionVehiculosCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_issuer_dep),
    _perm: dict = Depends(_permission_dep),  # noqa: B008
) -> SubscripcionVehiculosRead:
    """``POST /clientes/subscripcion-vehiculos`` -- validated INSERT.

    See module docstring for the full validation order + rationale.
    """
    no_store = _helpers.no_store_headers()

    # --- 1: target subscripcion must exist (vigente+activa), with plan +
    # existing vehiculos loaded in the same query (repo.cupos_subscripcion
    # reuse -- avoids a second round-trip for the same data). ------------
    try:
        detalle = await repo_cupos.buscar_subscripcion_con_vehiculos_por_uuid(
            session, uuid_subscripcion_cliente=payload.uuid_subscripcion_cliente
        )
    except repo_cupos.SubscripcionNoEncontradaError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "subscripcion_no_encontrada"},
            headers=no_store,
        ) from exc

    # --- 2: vehiculo must exist (vigente). -------------------------------
    vehiculo_stmt = select(Vehiculos).where(
        Vehiculos.uuid == payload.uuid_vehiculo,
        Vehiculos.vigente_hasta.is_(None),
    )
    vehiculo = (await session.execute(vehiculo_stmt)).scalar_one_or_none()
    if vehiculo is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "vehiculo_no_encontrado"},
            headers=no_store,
        )

    # --- 3: cheapest check first -- already active on THIS subscripcion. -
    ya_inscrito = any(v.vehiculo.uuid == vehiculo.uuid for v in detalle.vehiculos)
    if ya_inscrito:
        raise HTTPException(
            status_code=409,
            detail={"error": "vehiculo_ya_inscrito", "placa": vehiculo.placa},
            headers=no_store,
        )

    # --- 4: BR3/E1 (NEW) -- not already active on a DIFFERENT subscripcion.
    try:
        await repo_venta.validar_vehiculo_sin_suscripcion_vigente_distinta(
            session,
            uuid_vehiculo=vehiculo.uuid,
            excluir_uuid_subscripcion_cliente=payload.uuid_subscripcion_cliente,
        )
    except repo_venta.PlacaConSuscripcionVigenteError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "placa_con_suscripcion_vigente",
                "placa": vehiculo.placa,
            },
            headers=no_store,
        ) from exc

    # --- 5: V6 cantidad_maxima_vehiculos (reused pure check). ------------
    try:
        repo_venta.validar_cantidad_maxima_vehiculos(
            plan=detalle.plan, n_placas=len(detalle.vehiculos) + 1
        )
    except repo_venta.CantidadMaximaExcedidaError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "cantidad_vehiculos_excede_plan",
                "cantidad_maxima_vehiculos": exc.cantidad_maxima_vehiculos,
                "placas_proporcionadas": exc.placas_proporcionadas,
            },
            headers=no_store,
        ) from exc

    # --- 6: V5 mismo_tipo_vehiculo (reused pure check). ------------------
    try:
        repo_venta.validar_placas_mismo_tipo_vehiculo(
            plan=detalle.plan,
            vehiculos=[v.vehiculo for v in detalle.vehiculos] + [vehiculo],
        )
    except repo_venta.TipoVehiculoIncompatibleError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "tipo_vehiculo_mixto_no_permitido",
                "tipos_encontrados": exc.tipos_encontrados,
            },
            headers=no_store,
        ) from exc

    # --- INSERT -- real pg_advisory_xact_lock (REQ-OP-08 mirror), single
    # commit (KD-VENTA-01-style invariant: exactly one commit per handler).
    nuevas = await repo_venta.crear_subscripcion_vehiculos_bulk(
        session,
        actor_uuid=ctx.actor_uuid,
        uuid_subscripcion_cliente=payload.uuid_subscripcion_cliente,
        uuid_vehiculos=[vehiculo.uuid],
    )
    await session.commit()
    nuevo = nuevas[0]
    await session.refresh(nuevo)

    _helpers.apply_no_store_header(response)
    return SubscripcionVehiculosRead.model_validate(nuevo)


__all__ = ["router"]
