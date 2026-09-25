"""Operation HTTP routes (PR5 — ingreso lifecycle event + F1.5/F1.6/F1.8 deltas).

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

HU-F1.6 (REQ-OPS-034..041) extends ``POST /operacion/ingresos`` with the
11-step server-side validation chain (D-HU-F1.6-11): KD-3 → V5 → V4 →
KD-FORZADO-01 → V1+V2 → V3 → V6 → V8 → INSERT → alerta (same TX) → V9
derivation. The handler delegates to ``repo.ingreso.*`` helpers; see
``tests/static/test_kd_forzado_in_handler.py`` for the AST walk that locks
the invocation order.
"""
from __future__ import annotations

import logging
import uuid as uuid_lib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_tenant_ctx, requires_issuer
from ...auth.permissions import require_permission
from ...auth.tenancy import TenantContext
from ...db.engine import get_session
from ...models.A.salidas import Salidas
from ...models.L_E.ingreso import Ingreso
from ...models.L_S.sesion import Sesion
from ...models.L_W.anulaciones import Anulaciones
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
from ...repo.ingreso import (
    assign_ingreso_consecutivo,
    crear_ingreso_evento,
    existe_ingreso_activo,
    insertar_alerta_forzado,
    validar_cupo_disponible,
    validar_kd_forzado,
    validar_subscripcion_vigente,
    validar_tarifa_vigente,
    validar_tipo_vehiculo_vigente,
)
from ...repo.ocupacion import get_ocupacion_puros_activos
from ...repo.placa import detectar_tipo_vehiculo
from ...repo.salida import (
    SalidaDuplicada,
    SalidaNoEncontrada,
    SalidaYaAnulada,
    anular_salida_no_pagada,
    buscar_ingreso_activo_por_uuid,
    cotizar_para_salida,
    crear_salida_evento,
    insertar_alerta_salida_forzado,
)
from ...schemas.operacion import (
    AnularSalidaNoPagadaPayload,
    CotizarFacturacion,
    CotizarMensualidad,
    CotizarResponse,
    IngresoCreateForzado,
    IngresoRead,
    IngresoReadForzado,
    MiTurnoRead,
    OcupacionItem,
    OcupacionResponse,
    SalidaCreateForzado,
    SalidaRead,
    SalidaReadForzado,
)
from ...schemas.workflows import AnulacionesRead
from ._helpers import apply_no_store_header, no_store_headers

router = APIRouter(prefix="/operacion", tags=["operacion"])

logger = logging.getLogger(__name__)

_ingreso_issuer_dep = requires_issuer("operador-", "admin-")
# F8.1-b (HU-F8.1-anular-salida-no-pagada, 2026-09-23): the auto-annul
# handler reuses the same issuer class as `create_salida` (operadores
# own salidas). The semantically correct permission here would be
# ``anular_salida`` (a permission that DOES exist in
# ``prod.permisos`` per the 2026-09-23 RBAC audit) BUT the operator
# role has NOT been granted that permission — only ``anular_ingreso``
# (a different permission, originally meant for ingreso annulment)
# is in the operator's grant set per the audit. Using
# ``anular_ingreso`` here is a temporary workaround so the
# close-without-pay auto-annul can ship; the proper RBAC fix
# (operator role gains ``anular_salida``) is tracked separately
# and MUST be done before this handler is exposed to operators who
# don't already hold ``anular_ingreso``.
_anular_salida_issuer_dep = requires_issuer("operador-", "admin-")
_anular_salida_perm_dep = require_permission("anular_ingreso")


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
    response_model=IngresoReadForzado,
    status_code=201,
    summary="HU-F1.6: validated register of a vehicle entry (ingreso, [L-E] event)",
    responses={
        400: {"description": "missing_sucursal_context"},
        403: {
            "description": (
                "tenant_scope_violation (operador) | "
                "sucursal_not_permitted (admin)"
            )
        },
        409: {"description": "ingreso_activo_existente (V8)"},
        422: {
            "description": (
                "placa_formato_invalido (V5) | tipo_vehiculo_invalido (V4) | "
                "forzado_contradiccion (KD-FORZADO-01) | "
                "motivo_forzado_requerido (V2) | "
                "motivo_forzado_insuficiente (KD-FORZADO-01) | "
                "cupo_no_configurado (V1) | "
                "tarifa_vigente_no_encontrada (V3) | "
                "subscripcion_inactiva_o_vencida (V6)"
            )
        },
    },
)
async def create_ingreso(
    response: Response,
    payload: IngresoCreateForzado,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_ingreso_issuer_dep),
) -> IngresoReadForzado:
    """HU-F1.6 / REQ-OPS-034..041: validated INSERT for ``prod.ingreso``.

    11-step chain (D-HU-F1.6-11). Every step raises ``HTTPException``
    with the typed discriminator + ``Cache-Control: no-store``. Order is
    locked by ``tests/static/test_kd_forzado_in_handler.py``.
    """
    no_store = no_store_headers()

    # --- Step 1: KD-3 (resolve target sucursal + tenant scope). ---------
    target = payload.uuid_sucursal or ctx.sucursal_uuid
    if target is None:
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_sucursal_context"},
            headers=no_store,
        )
    if (
        ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or target != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "tenant_scope_violation"},
            headers=no_store,
        )

    # --- Step 2: V5 (regex-derived uuid_tipo_vehiculo). -----------------
    # REQ-OPS-134 (qa-2026-09-17 bug 4): honor the explicit
    # ``payload.uuid_tipo_vehiculo`` BEFORE falling back to the regex
    # helper. This is defense in depth -- the F6.1 frontend sends a
    # UUID that may not match the regex (e.g. operator override of a
    # moto plate whose tipo was chosen by a dropdown, not the regex).
    # The explicit UUID short-circuits the regex; ``placa`` is still
    # validated separately by the V8/V1/V2 chain below.
    #
    # REQ-OPS-194 (HU-INGRESO-SIN-PLACA): when ``placa is None``, the
    # operator MUST have picked a tipo via the discriminated-union UI
    # (bici / patineta). ``detectar_tipo_vehiculo`` cannot derive a tipo
    # from an empty placa, so we short-circuit with a typed 422 if both
    # are absent (UI bug -- the operator clicked "Sin placa" without
    # selecting a tipo in the dropdown).
    uuid_tipo_vehiculo = payload.uuid_tipo_vehiculo
    if uuid_tipo_vehiculo is None:
        if payload.placa is None:
            raise HTTPException(
                status_code=422,
                detail={"error": "tipo_vehiculo_requerido_sin_placa"},
                headers=no_store,
            )
        uuid_tipo_vehiculo = await detectar_tipo_vehiculo(session, payload.placa)
        if uuid_tipo_vehiculo is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "placa_formato_invalido",
                    "formatos_aceptados": ["ABC123", "ABC12D"],
                },
                headers=no_store,
            )

    # --- Step 3: V4 (catalog vigente check, KD-V3 no bypass). ----------
    if not await validar_tipo_vehiculo_vigente(
        session, uuid_tipo_vehiculo=uuid_tipo_vehiculo
    ):
        raise HTTPException(
            status_code=422,
            detail={"error": "tipo_vehiculo_invalido"},
            headers=no_store,
        )

    # --- Step 4: KD-FORZADO-01 (prefix contract). ----------------------
    motivo = validar_kd_forzado(payload.observaciones, payload.forzado)
    bypass_reason: str | None = "forzado" if motivo is not None else None

    # --- Step 5: V1+V2 (cupo no config + agotado). ---------------------
    cupo_result = await validar_cupo_disponible(
        session,
        uuid_sucursal=target,
        uuid_tipo_vehiculo=uuid_tipo_vehiculo,
        forzado=bool(bypass_reason),
    )
    if cupo_result.cupo_no_configurado:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "cupo_no_configurado",
                "forzado_permitido": True,
            },
            headers=no_store,
        )
    if cupo_result.cupo_agotado:
        if not bypass_reason:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "motivo_forzado_requerido",
                    "cupo_maximo": cupo_result.cupo_maximo,
                    "activos": cupo_result.activos,
                },
                headers=no_store,
            )
        bypass_reason = "cupo_agotado"

    # --- Step 6: V3 (tarifa vigente, bi-temporal). ---------------------
    tarifa_result = await validar_tarifa_vigente(
        session,
        uuid_sucursal=target,
        uuid_tipo_vehiculo=uuid_tipo_vehiculo,
        at=datetime.now(UTC).replace(tzinfo=None),
        forzado=bool(bypass_reason),
    )
    if not tarifa_result.vigente and not bypass_reason:
        raise HTTPException(
            status_code=422,
            detail={"error": "tarifa_vigente_no_encontrada"},
            headers=no_store,
        )

    # --- Step 7: V6 (subscripcion vigente, bi-temporal). --------------
    subscripcion_vigente = False
    if payload.uuid_subscripcion_cliente is not None:
        sub_result = await validar_subscripcion_vigente(
            session,
            uuid_subscripcion_cliente=payload.uuid_subscripcion_cliente,
            forzado=bool(bypass_reason),
        )
        subscripcion_vigente = sub_result.vigente
        if not sub_result.vigente and not bypass_reason:
            raise HTTPException(
                status_code=422,
                detail={"error": "subscripcion_inactiva_o_vencida"},
                headers=no_store,
            )

    # --- Step 8: V8 (no duplicate active ingreso, NO lock pesimista). --
    # REQ-OPS-040 modified (HU-INGRESO-SIN-PLACA): SKIP V8 for no-placa
    # ingresos. For ``placa is None``, ``existe_ingreso_activo(placa='')``
    # is meaningless (no placa to match on). Duplicate detection for
    # no-placa is delegated to the partial UK ``uq_ingreso_consecutivo_
    # partial`` on ``prod.ingreso.consecutivo`` (REQ-OPS-192, defense in
    # depth) -- if a race ever mints the same consecutivo twice, the DB
    # rejects with 23505.
    if payload.placa is not None:
        uuid_activo = await existe_ingreso_activo(
            session, uuid_sucursal=target, placa=payload.placa
        )
        if uuid_activo is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "ingreso_activo_existente",
                    "uuid_ingreso_existente": str(uuid_activo),
                },
                headers=no_store,
            )

    # --- Step 8.5 (NEW, REQ-OPS-191): assign ``consecutivo`` for no-placa.
    # Pre-generate the ``Ingreso.uuid`` BEFORE calling the helper so the
    # ``<uuid8>`` suffix in the formatted string is deterministic across
    # retries (the helper's idempotency anchor is ``last_event_uuid ==
    # source_event_uuid``). The handler then INSERTs ``ingreso.uuid =
    # new_uuid`` in Step 9 below -- byte-identical persisted PK.
    consecutivo: str | None = None
    new_uuid: uuid_lib.UUID | None = None
    if payload.placa is None:
        new_uuid = uuid_lib.uuid4()
        consecutivo = await assign_ingreso_consecutivo(
            session,
            uuid_sucursal=target,
            uuid_tipo_vehiculo=uuid_tipo_vehiculo,
            source_event_uuid=new_uuid,
        )

    # --- Step 9: INSERT + alerta (same TX, R5). ------------------------
    # REQ-OPS-194: ``placa_presente`` is a client-side Zod discriminator
    # that the server reads (as a side effect of ``placa`` being None) but
    # MUST NOT land in the persisted row -- it's not a business column.
    # ``forzado`` is also excluded (it gates the alerta flow, never
    # persisted per D-HU-F1.6-5).
    new_attrs = payload.model_dump(
        exclude_none=True, exclude={"forzado", "placa_presente"}
    )
    new_attrs["uuid_tipo_vehiculo"] = uuid_tipo_vehiculo
    new_attrs["uuid_sucursal"] = target
    # REGRESSION fix (2026-09-22, directiva del operador): el INSERT
    # path NO estaba poblando ``fecha_ingreso`` en ``prod.ingreso`` — la
    # columna es nullable sin DEFAULT (verificar ``information_schema``
    # confirma ``is_nullable=YES`` / ``column_default=NULL``). El bug
    # cascadea al PL/pgSQL ``prod.calcular_cotizacion`` que retorna
    # NULL en subtotal/iva/total/tiempo_minutos para salidas de
    # rotación → Pydantic ValidationError 500 al operador. Bug abierto
    # #2009 (memoria Engram). Root cause fix: stamp explícito al
    # momento del INSERT. Migration 0046 (``0046_fix_cotizar_fecha_
    # ingreso_coalesce``) agrega defense in depth via COALESCE para
    # registros históricos NULL.
    new_attrs["fecha_ingreso"] = datetime.now(UTC).replace(tzinfo=None)
    if consecutivo is not None and new_uuid is not None:
        # No-placa path: stamp the helper-minted consecutivo and the
        # pre-generated PK so the row's ``uuid.hex[:8]`` matches the
        # ``<uuid8>`` suffix the helper emitted. The ``[L-E]`` AST lock
        # is preserved -- this is still INSERT (consecutivo is in
        # new_attrs, never UPDATEd; the AST walk in
        # tests/static/test_no_write_after_insert.py continues to pass).
        new_attrs["consecutivo"] = consecutivo
        new_attrs["uuid"] = new_uuid
    new_row = await crear_ingreso_evento(
        session,
        actor_uuid=ctx.actor_uuid,
        new_attrs=new_attrs,
    )
    if bypass_reason == "cupo_agotado":
        await insertar_alerta_forzado(
            session,
            uuid_sucursal=target,
            uuid_ingreso=new_row.uuid,
            actor_uuid=ctx.actor_uuid,
            motivo=motivo or "(sin motivo)",
        )
    await session.commit()

    # REGRESSION fix (2026-09-22, directiva del operador): refresh the
    # ``prod.mv_ocupacion_diaria`` MV immediately after the ingreso
    # INSERT so the GET /operacion/ocupacion endpoint returns the
    # new ``activos`` count in the same HTTP response cycle. Without
    # this, the dashboard <OcupacionPanel /> (Inventario card)
    # would keep showing the pre-mutation count for up to 10s (the
    # ``RefreshMvOcupacionWorker`` cadence) and combined with the
    # FE SWR 10–15s polling tick the operator perceived the panels
    # as "hardcoded".
    #
    # The helper is a SECURITY DEFINER function (migration 0045) that
    # runs ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` as the ``parkos``
    # owner. ``parkos_app`` (the role the BE connects as) has EXECUTE
    # but does NOT hold the underlying REFRESH privilege on the MV
    # (least-privilege posture, migration 0021 + 0024). The
    # IF-EXISTS guard inside the function makes it safe to call even
    # before the first worker cycle populated the MV.
    #
    # We do NOT commit the REFRESH — it runs in the same TX as the
    # underlying SELECT against the MV, so the read-modify cycle is
    # atomic. The REFRESH itself opens a brief AccessExclusiveLock;
    # CONCURRENTLY keeps GET /operacion/ocupacion readers unblocked.
    try:
        await session.execute(
            text("SELECT prod.refresh_mv_ocupacion_diaria()")
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        # The MV refresh is observability / FE-liveness — NEVER fail
        # the operator's ingreso because the MV worker would have
        # caught up within 10s anyway. KD-5: log + continue.
        await session.rollback()
        logger.warning(
            "ingreso_post_commit_refresh_failed",
            extra={
                "event": "ingreso_post_commit_refresh_failed",
                "uuid_ingreso": str(new_row.uuid),
                "exception_class": type(exc).__name__,
            },
        )

    # --- Step 10: V9 derivation (DEC-SUC-21). --------------------------
    # BUGFIX (adenda, mismo cambio que el campo impreso en el tiquete):
    # antes solo miraba la PRESENCIA de ``uuid_subscripcion_cliente`` en
    # el payload, no si la suscripcion referenciada seguia vigente. En el
    # camino normal era invisible (Step 7 ya rechaza con 422 si no esta
    # vigente), pero en el camino FORZADO (KD-FORZADO-01) Step 7 NO
    # rechaza aunque ``sub_result.vigente`` sea False -- resultado: un
    # ingreso forzado con una suscripcion vencida quedaba etiquetado
    # "MENSUALIDAD" sin cobertura real. Usa el resultado real de V6
    # (``subscripcion_vigente``, Step 7) en vez de la mera presencia del
    # campo.
    tipo_entrada: str = (
        "MENSUALIDAD"
        if (payload.uuid_subscripcion_cliente is not None and subscripcion_vigente)
        else "ROTACION"
    )

    # --- Step 11: response shape. --------------------------------------
    apply_no_store_header(response)
    await session.refresh(new_row)
    base = IngresoRead.model_validate(new_row).model_dump()
    # REQ-OPS-197: ``consecutivo`` is already in ``base`` (added to
    # ``IngresoRead`` in commit A.2; the new row was just INSERTed with
    # the helper-minted string in Step 9, so ``new_row.consecutivo``
    # holds the value). The model_dump above surfaces it verbatim —
    # DO NOT pass ``consecutivo`` again as an explicit kwarg or
    # Pydantic raises ``multiple values for keyword argument``.
    return IngresoReadForzado(
        **base,
        tipo_entrada=tipo_entrada,  # type: ignore[arg-type]
        forzado_en_creacion=bypass_reason is not None,
        motivo_forzado=motivo if bypass_reason else None,
    )


# ---------------------------------------------------------------------------
# HU-F1.7 -- POST /operacion/salidas (REQ-OPS-042..052, D-HU-F1.7-20)
# ---------------------------------------------------------------------------


@router.post(
    "/salidas",
    response_model=SalidaReadForzado,
    status_code=201,
    summary=(
        "HU-F1.7 / REQ-OPS-042..052: validated register of a vehicle exit "
        "(salida, [A] append-only) with tipo_salida server-side derivation."
    ),
    responses={
        400: {"description": "missing_sucursal_context"},
        403: {"description": "tenant_scope_violation (operador)"},
        404: {"description": "ingreso_no_encontrado (V1)"},
        409: {"description": "salida_duplicada (partial unique index)"},
        422: {
            "description": (
                "placa_no_coincide_con_ingreso (V3) | "
                "motivo_forzado_requerido (KD-FORZADO-01) | "
                "forzado_contradiccion (KD-FORZADO-01) | "
                "motivo_forzado_insuficiente (KD-FORZADO-01) | "
                "subscripcion_inactiva_o_vencida (V2) | "
                "tarifa_vigente_no_encontrada (V5)"
            )
        },
        500: {"description": "iva_no_configurado (KD-IVA, post-0026: never)"},
    },
)
async def create_salida(
    payload: SalidaCreateForzado,
    response: Response,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_ingreso_issuer_dep),
) -> SalidaReadForzado:
    """HU-F1.7 / REQ-OPS-042..052: validated INSERT for ``prod.salidas``.

    12-step chain (D-HU-F1.7-20) locked by
    ``tests/static/test_salida_handler_step_order.py``:

        1. KD-3 issuer claims + no_store headers
        2. V1 ingreso activo exists (404 if None)
        3. tenant scope post-V1 (403 if operador cross-branch)
        4. V2 subscripcion vigente al momento salida (422 if not bypassed)
        5. V3 placa matches ingreso (422 if mismatch)
        6. V4 KD-FORZADO-01 prefix contract (sets bypass_reason)
        7. V5 tarifa vigente via F1.8 PL/pgSQL (derives tipo_salida)
        8. INSERT prod.salidas [A] (409 on partial unique index)
        9. alerta same-TX if V2/V5 bypassed + single commit() (KD-S7)
       10. tipo_salida documented for AST walk literal
       11. response shape + session.refresh
       12. return 201 SalidaReadForzado

    Lock continuity (KD-S7, KD-1 from F1.8): the prod.calcular_cotizacion
    call in Step 7 acquires SELECT ... FOR SHARE on tarifas_sucursal.
    The lock is held through Step 8 (INSERT salida) and Step 9 (alerta
    INSERT). Released at session.commit() in Step 9. NO sub-transactions,
    NO SAVEPOINT (KD-S7 invariant).

    The Idempotency-Key header is checked by the FastAPI middleware
    (PR2 IdempotencyKeyMiddleware).
    """
    no_store = no_store_headers()

    # --- Step 1: KD-3 (issuer claims + no_store). ----------------------
    # Resolved via dependency injection; no client-supplied sucursal
    # (server derives from ingreso.uuid_sucursal in Step 3).

    # --- Step 2: V1 (ingreso activo exists). ----------------------------
    ingreso = await buscar_ingreso_activo_por_uuid(
        session, uuid_ingreso=payload.uuid_ingreso
    )
    if ingreso is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "ingreso_no_encontrado",
                "uuid_ingreso": str(payload.uuid_ingreso),
            },
            headers=no_store,
        )

    # --- Step 3: tenant scope (post-V1, KD-S2). ------------------------
    target_sucursal = ingreso.uuid_sucursal
    if (
        ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or target_sucursal != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tenant_scope_violation",
                "uuid_ingreso": str(payload.uuid_ingreso),
            },
            headers=no_store,
        )

    # --- Step 4: V2 (subscripcion vigente al momento salida). -----------
    bypass_reason: str | None = None
    if ingreso.uuid_subscripcion_cliente is not None:
        sub_result = await validar_subscripcion_vigente(
            session,
            uuid_subscripcion_cliente=ingreso.uuid_subscripcion_cliente,
            forzado=payload.forzado,
        )
        if not sub_result.vigente:
            if not payload.forzado:
                raise HTTPException(
                    status_code=422,
                    detail={"error": "subscripcion_inactiva_o_vencida"},
                    headers=no_store,
                )
            bypass_reason = "subscripcion_vencida"

    # --- Step 5: V3 (placa matches ingreso). ---------------------------
    if payload.placa is not None:
        tipo_req = await detectar_tipo_vehiculo(session, payload.placa)
        tipo_ing = await detectar_tipo_vehiculo(session, ingreso.placa or "")
        if tipo_req != tipo_ing:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "placa_no_coincide_con_ingreso",
                    "placa_request": payload.placa,
                    "placa_ingreso": ingreso.placa,
                },
                headers=no_store,
            )

    # --- Step 6: V4 KD-FORZADO-01 prefix contract (F1.6 verbatim). -----
    motivo = validar_kd_forzado(payload.observaciones, payload.forzado)
    if motivo is not None and bypass_reason is None:
        bypass_reason = "forzado"  # generic bypass reason for V5 only

    # --- Step 7: V5 tarifa vigente via F1.8 PL/pgSQL inline. -----------
    try:
        cotizacion = await cotizar_para_salida(
            session, uuid_ingreso=payload.uuid_ingreso
        )
    except TarifaNoVigente as exc:
        if not bypass_reason:
            raise HTTPException(
                status_code=422,
                detail={"error": "tarifa_vigente_no_encontrada"},
                headers=no_store,
            ) from exc
        bypass_reason = "tarifa_no_vigente"
        cotizacion = {"cobrar": True}  # placeholder for snapshot shape
    except IVANoConfigurado as exc:
        # KD-IVA -- post-0026 deploy: never; pre-0026: blocked.
        raise HTTPException(
            status_code=500,
            detail={"error": "iva_no_configurado"},
            headers=no_store,
        ) from exc

    # Derive tipo_salida from F1.8's cobrar flag (DEC-SUC-21-NEW):
    tipo_salida: Literal["MENSUALIDAD", "ROTACION"] = (
        "MENSUALIDAD" if cotizacion.get("cobrar") is False else "ROTACION"
    )

    # --- Step 8: INSERT salida [A] append-only (DEC-SAL-01). ----------
    # REGRESSION fix (2026-09-22, directiva del operador): the
    # ``dateutil.relativedelta(years=2)`` was replaced with a stdlib
    # ``timedelta(days=730)`` (DIAN 5-year retention requires only the
    # "today + N days" granularity for the 2-year `fecha_retencion_hasta`
    # we stamp on ``prod.salidas``). The ``dateutil`` dep was never in
    # backend/pyproject.toml (see repo/ingreso_consecutivo.py:156 for
    # the team's documented rationale), so the endpoint raised
    # ``ModuleNotFoundError: No module named 'dateutil'`` on every POST
    # — the operator's "salida doesn't update panels" complaint traced
    # to this pre-existing bug. 730 days = 2 years (no leap-day
    # sensitive — fine for retention).
    new_attrs = {
        "uuid_sucursal": target_sucursal,
        "uuid_ingreso": payload.uuid_ingreso,
        "fecha_salida": datetime.now(UTC).replace(tzinfo=None),
        "fecha_retencion_hasta": date.today() + timedelta(days=730),
    }
    try:
        new_row = await crear_salida_evento(
            session,
            actor_uuid=ctx.actor_uuid,
            new_attrs=new_attrs,
        )
    except SalidaDuplicada as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "salida_duplicada",
                "uuid_ingreso": str(payload.uuid_ingreso),
            },
            headers=no_store,
        ) from exc

    # --- Step 9: alertas same-TX (KD-S12, R5) + single commit(). ------
    if bypass_reason == "subscripcion_vencida":
        await insertar_alerta_salida_forzado(
            session,
            uuid_sucursal=target_sucursal,
            uuid_salida=new_row.uuid,
            actor_uuid=ctx.actor_uuid,
            motivo=motivo or "(sin motivo)",
            tipo_alerta="subscripcion_vencida_forzado",
        )
    elif bypass_reason == "tarifa_no_vigente":
        await insertar_alerta_salida_forzado(
            session,
            uuid_sucursal=target_sucursal,
            uuid_salida=new_row.uuid,
            actor_uuid=ctx.actor_uuid,
            motivo=motivo or "(sin motivo)",
            tipo_alerta="tarifa_vigente_forzado",
        )
    await session.commit()  # UN solo commit (KD-S7 lock release)

    # REGRESSION fix (2026-09-22, directiva del operador): refresh the
    # ``prod.mv_ocupacion_diaria`` MV immediately after the salida
    # INSERT. Same rationale as ``create_ingreso`` above — without
    # this, the dashboard <OcupacionPanel /> keeps showing the
    # pre-mutation ``activos`` count for up to 10s (worker cadence)
    # and the operator perceived the Inventario panel as "hardcoded".
    #
    # The refresh is fire-and-forget relative to the operator's UX —
    # we log a warning and continue on failure (KD-5 + RIESCO-SUC-02).
    # The MV is the observability layer; the INSERT itself is already
    # committed at this point so the operator's flujo is not at risk.
    try:
        await session.execute(
            text("SELECT prod.refresh_mv_ocupacion_diaria()")
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        logger.warning(
            "salida_post_commit_refresh_failed",
            extra={
                "event": "salida_post_commit_refresh_failed",
                "uuid_ingreso": str(payload.uuid_ingreso),
                "uuid_salida": str(new_row.uuid),
                "exception_class": type(exc).__name__,
            },
        )

    # --- Step 10: derivar tipo_salida (DEC-SUC-21-NEW). ----------------
    # Already derived in Step 7. Documented here for AST walk literal.

    # --- Step 11: response shape. -------------------------------------
    apply_no_store_header(response)
    await session.refresh(new_row)
    base = SalidaRead.model_validate(new_row).model_dump()
    # Defense in depth (zero-bug-policy, 2026-09-23): when tarifa is
    # NOT vigente and the operator uses the V5 bypass, ``cotizacion``
    # is replaced with the placeholder dict ``{"cobrar": True}`` (line
    # 608) which has NO ``subtotal`` / ``iva`` / ``total`` /
    # ``tiempo_minutos`` fields. The previous code validated that
    # placeholder against :class:`CotizarFacturacion` and crashed
    # with ``ValidationError: subtotal input_value=None`` for every
    # tarifa_no_vigente bypass — a 500 to the operator.
    #
    # Fix: if bypass_reason is set (tarifa_no_vigente or
    # subscripcion_vencida), the cotizacion_snapshot is None. The
    # operator already knows it's a forced exit (``motivo_forzado``
    # carries the reason); the snapshot would be misleading anyway.
    #
    # MENSUALIDAD branch (migration 0050, operator directive
    # 2026-09-24): the snapshot is now populated for MENSUALIDAD too
    # (as :class:`CotizarMensualidad`, not :class:`CotizarFacturacion`)
    # -- the PL/pgSQL always computes the full fiscal breakdown now, and
    # the frontend needs it to build the discount factura (subtotal/
    # iva/total shown in full + a discount line netting to $0).
    cotizacion_snapshot: CotizarFacturacion | CotizarMensualidad | None = None
    if not bypass_reason:
        cotizacion_snapshot = (
            CotizarFacturacion.model_validate(cotizacion)
            if tipo_salida == "ROTACION"
            else CotizarMensualidad.model_validate(cotizacion)
        )
    return SalidaReadForzado(
        **base,
        tipo_salida=tipo_salida,  # type: ignore[arg-type]
        forzado_en_creacion=bypass_reason is not None,
        motivo_forzado=motivo if bypass_reason else None,
        cotizacion_snapshot=cotizacion_snapshot,
    )
    # --- Step 12: 201 SalidaReadForzado. ------------------------------


@router.post(
    "/salidas/{uuid_salida}/anular-no-pagada",
    response_model=AnulacionesRead,
    status_code=201,
    summary=(
        "F8.1-b (HU-F8.1-anular-salida-no-pagada, 2026-09-23): INSERT a "
        "``prod.anulaciones`` row with ``tipo_anulable='salida'`` so "
        "``V_INGRESO_ESTADO`` recalculates the ingreso back to "
        "``abierto``. Idempotent on retries via Idempotency-Key (F1.6) "
        "AND via the V2 guard (`SalidaYaAnulada` → 409). Mirror of "
        "``workflows_reimpresion.anular_reimpresion_ticket`` "
        "(custom endpoint per case — the generic `anulaciones` "
        "factory is `write_enabled=False` per PR6, so the factory "
        "cannot be reused here)."
    ),
    responses={
        403: {"description": "tenant_scope_violation"},
        404: {"description": "salida_no_encontrada (V1)"},
        409: {"description": "salida_ya_anulada (V2)"},
        422: {"description": "motivo_muy_corto (≥10 chars required)"},
    },
)
async def anular_salida_no_pagada_endpoint(
    uuid_salida: uuid_lib.UUID,
    payload: AnularSalidaNoPagadaPayload,
    response: Response,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _issuer: None = Depends(_anular_salida_issuer_dep),
    _perm: None = Depends(_anular_salida_perm_dep),  # requires 'anular_ingreso_salida'
) -> AnulacionesRead:
    """F8.1-b: annul a ``prod.salidas`` row that was never followed by
    a successful cobro (operator dismissed the F8.1 payment drawer).

    Sequence (defense in depth, mirrors the F1.7 12-step exit chain
    + the PR6 reimpresion-anular precedent):

        1. KD-3 issuer claims + no_store headers
        2. V1 salida exists (``SalidaNoEncontrada`` → 404)
        3. tenant scope post-V1 (403 if operador cross-branch)
        4. V2 no ``ejecutada`` annulment already references this
           salida (``SalidaYaAnulada` → 409)
        5. INSERT ``prod.anulaciones`` with
           ``tipo_anulable='salida'`` + ``estado='ejecutada'``
        6. KD-ANNUL single ``await session.commit()`` +
           ``Cache-Control: no-store`` + response shape

    Idempotency-Key: DEC-IDEM-01 (F1.6 reuse); middleware owns the
    cache, handler passes through. Combined with V2, the annulment
    is robust to network retries / double-clicks: the second call
    either reuses the cached 201 (Idempotency-Key dedup) or returns
    409 ``salida_ya_anulada`` (V2 guard).
    """
    no_store = no_store_headers()

    # --- V1: salida exists (handled by repo helper). -------------------
    # Implemented in repo/salida.py::anular_salida_no_pagada so the
    # `anuladas` existence check stays in the same TX as the INSERT.

    # --- tenant scope (post-V1, KD-S2 analog from F1.7). --------------
    # The repo helper reads ``salidas.uuid_sucursal`` for the new row.
    # We re-fetch the sucursal here only to enforce cross-branch.
    # `Salidas` has composite PK (uuid, fecha_retencion_hasta) so
    # `session.get()` would require both — use `select().where()`.
    stmt = select(Salidas).where(Salidas.uuid == uuid_salida)
    salida_for_scope = (await session.execute(stmt)).scalar_one_or_none()
    if salida_for_scope is None:
        # V1 catch (defensive — repo will re-check).
        raise HTTPException(
            status_code=404,
            detail={
                "error": "salida_no_encontrada",
                "uuid_salida": str(uuid_salida),
            },
            headers=no_store,
        )
    target_sucursal = salida_for_scope.uuid_sucursal
    if (
        ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or target_sucursal != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tenant_scope_violation",
                "uuid_salida": str(uuid_salida),
            },
            headers=no_store,
        )

    # --- V1+V2+INSERT, single repo call. ------------------------------
    try:
        new_row = await anular_salida_no_pagada(
            session,
            uuid_salida=uuid_salida,
            motivo=payload.motivo,
            actor_uuid=ctx.actor_uuid,
        )
    except SalidaNoEncontrada:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "salida_no_encontrada",
                "uuid_salida": str(uuid_salida),
            },
            headers=no_store,
        ) from None
    except SalidaYaAnulada:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "salida_ya_anulada",
                "uuid_salida": str(uuid_salida),
            },
            headers=no_store,
        ) from None

    await session.commit()
    await session.refresh(new_row)
    apply_no_store_header(response)
    return AnulacionesRead.model_validate(new_row)


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
    # F8.1-b (2026-09-23): the original query had a TODO to also
    # detect ``anulada`` once the anulaciones chain mounted. The
    # auto-annul endpoint now writes rows to ``prod.anulaciones`` so
    # this fallback path MUST exclude annulled salidas — otherwise
    # an operator who dismissed the payment drawer would see the
    # ingreso stuck in ``cerrado`` even though the annulment
    # succeeded. Same exclusion semantics as
    # ``repo/salida.py::buscar_ingreso_activo_por_uuid``.
    salidas_exists_stmt = text(
        """
        SELECT EXISTS(
            SELECT 1 FROM prod.salidas s
            WHERE s.uuid_ingreso = :ingreso_uuid
              AND NOT EXISTS (
                  SELECT 1 FROM prod.anulaciones a
                  WHERE a.uuid_salida = s.uuid
                    AND a.tipo_anulable = 'salida'
                    AND a.estado = 'ejecutada'
              )
        )
        """
    )
    salidas_exists = (await session.execute(salidas_exists_stmt, {"ingreso_uuid": str(uuid)})).scalar()

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
    consecutivo: str | None = None,
    activo: bool | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_ingreso_issuer_dep),
) -> list[IngresoRead]:
    """List recent ingresos (filters: uuid_sucursal, placa, consecutivo, activo).

    No cursor pagination (yet). ``activo=true`` (HU-F6.1, plan.md linea
    1518/2454) restringe a ingresos sin salida vigente -- misma
    semantica de exclusion que ``V_INGRESO_ESTADO`` /
    ``repo/salida.py::buscar_ingreso_activo_por_uuid``: un ingreso con
    una salida ``ejecutada``-anulada sigue contando como activo (el
    vehiculo nunca salio realmente, HU-F8.1).

    ``consecutivo`` (HU-F8.3, directiva del operador 2026-09-25): mismo
    patron que ``placa`` -- exact match, SIN el filtro ``activo`` --
    para que la reimpresion de tiquete pueda encontrar el cupo de un
    vehiculo sin placa aunque el ingreso ya tenga salida registrada.
    """
    stmt = select(Ingreso)
    if uuid_sucursal is not None:
        stmt = stmt.where(Ingreso.uuid_sucursal == uuid_sucursal)
    if placa is not None:
        stmt = stmt.where(Ingreso.placa == placa)
    if consecutivo is not None:
        stmt = stmt.where(Ingreso.consecutivo == consecutivo)
    if activo:
        salida_vigente = (
            select(Salidas.uuid)
            .where(Salidas.uuid_ingreso == Ingreso.uuid)
            .where(
                ~(
                    select(Anulaciones.uuid)
                    .where(Anulaciones.uuid_salida == Salidas.uuid)
                    .where(Anulaciones.tipo_anulable == "salida")
                    .where(Anulaciones.estado == "ejecutada")
                ).exists()
            )
        )
        stmt = stmt.where(~salida_vigente.exists())
    stmt = stmt.order_by(Ingreso.created_at.desc()).limit(min(limit, 200))
    result = await session.execute(stmt)
    return [IngresoRead.model_validate(r) for r in result.scalars().all()]


# ---------------------------------------------------------------------------
# HU-F1.8 (REQ-OPS-022..025) -- GET /operacion/cotizar
# ---------------------------------------------------------------------------


def _cotizar_no_store_headers() -> dict[str, str]:
    """Legacy F1.8 helper. Kept as a module-level shim that delegates to the
    shared :func:`api.v1._helpers.no_store_headers` (R-A6 mitigation)."""
    return no_store_headers()


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


# ---------------------------------------------------------------------------
# HU-F1.5 (REQ-OPS-030, REQ-OPS-031) -- GET /operacion/ocupacion
# ---------------------------------------------------------------------------


@router.get(
    "/ocupacion",
    response_model=OcupacionResponse,
    summary=(
        "HU-F1.5 / REQ-OPS-030: per-tipo occupancy breakdown for the "
        "branch, derived from prod.mv_ocupacion_diaria."
    ),
    responses={
        400: {"description": "missing_sucursal_context"},
        403: {
            "description": (
                "tenant_scope_violation (operador) | "
                "sucursal_not_permitted (admin)"
            )
        },
    },
)
async def get_ocupacion(
    response: Response,
    uuid_sucursal: uuid_lib.UUID | None = Query(  # noqa: B008
        None,
        description=(
            "uuid_sucursal to query. Default = ctx.sucursal_uuid. "
            "Operador- sees only ctx.sucursal_uuid; admin- sees only "
            "branches in claims['sucursales_permitidas']."
        ),
    ),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_ingreso_issuer_dep),
) -> OcupacionResponse:
    """REQ-OPS-030 + REQ-OPS-031: ``GET /operacion/ocupacion``.

    Dependency chain:
        ``_ingreso_issuer_dep`` -> ``requires_issuer('operador-', 'admin-')``
        ``get_tenant_ctx``      -> ``TenantContext { actor_uuid, sucursal_uuid, ... }``
        ``get_session``         -> ``AsyncSession`` (request-scoped)

    Body: thin pass-through to ``repo.ocupacion.get_ocupacion_puros_activos``,
    encapsulating the SQL JOIN (mv x tv LEFT JOIN cvs). KD-3 enforces
    per-sucursal authz: ``operador-`` pinned to ``ctx.sucursal_uuid``
    (cross-tenant -> ``403 tenant_scope_violation``); ``admin-`` bounded
    by ``claims['sucursales_permitidas']`` (missing -> ``400
    missing_sucursal_context``).

    The endpoint is read-only by contract (REQ-OPS-030 + REQ-OPS-031);
    defense in depth enforced by
    ``tests/static/test_no_write_in_ocupacion.py``.
    """
    # 1. Resolve target sucursal (KD-3 chain):
    #    - query param wins;
    #    - else ctx.sucursal_uuid;
    #    - else 400 missing_sucursal_context.
    target = uuid_sucursal or ctx.sucursal_uuid
    if target is None:
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_sucursal_context"},
        )

    # 2. Authorization (KD-3):
    #    - operador- pinned to ctx.sucursal_uuid (cross-tenant -> 403
    #      tenant_scope_violation);
    #    - admin- bounded by claims['sucursales_permitidas'] enforced by
    #      ``get_tenant_ctx`` itself, which already validated the
    #      ``X-Sucursal-Context`` header before this handler runs. An
    #      admin- token that reaches this handler has therefore already
    #      been validated for ``target`` -- no further check needed.
    if (
        ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or target != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "tenant_scope_violation"},
        )

    # 3. Repo call (READ-ONLY; encapsulated JOIN).
    items = await get_ocupacion_puros_activos(session, uuid_sucursal=target)

    # 4. Cache-Control: no-store (consistent with F1.3 R8 / F1.8 R8).
    response.headers["Cache-Control"] = "no-store"

    return OcupacionResponse(
        uuid_sucursal=target,
        items=[OcupacionItem.model_validate(it) for it in items],
        generado_en=datetime.now(tz=UTC),
    )


# ---------------------------------------------------------------------------
# HU-F12.1 (REQ-OPS-184..187) -- GET /operacion/mi-turno
# ---------------------------------------------------------------------------


@router.get(
    "/mi-turno",
    response_model=MiTurnoRead,
    response_model_by_alias=False,
    summary=(
        "HU-F12.1 / REQ-OPS-184: per-turn KPI aggregate (read-only). "
        "Returns 7-field MiTurnoRead over a Sesion open-window temporal "
        "JOIN, tenant-pinned to ctx.sucursal_uuid. Cache-Control: no-store."
    ),
    responses={
        403: {"description": "sesion_cross_branch_forbidden (REQ-OPS-185)"},
        404: {"description": "sesion_not_found (REQ-OPS-185)"},
    },
)
async def get_mi_turno(
    response: Response,
    uuid_sesion: uuid_lib.UUID = Query(  # noqa: B008
        ...,
        description="uuid_sesion of the operator's active turno.",
    ),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_ingreso_issuer_dep),
) -> MiTurnoRead:
    """REQ-OPS-184..187: read-only per-turn KPI aggregate.

    Pipeline (locked at ``tests/integration/test_mi_turno_endpoint.py``):

      1. Look up ``prod.sesion.uuid = uuid_sesion`` server-side.
         Unknown -> 404 ``sesion_not_found``.
      2. Compare the resolved ``Sesion.uuid_sucursal`` against
         ``ctx.sucursal_uuid`` (issuer-pinned). Mismatch -> 403
         ``sesion_cross_branch_forbidden`` (REQ-OPS-185, DA-F12.1-2).
      3. Delegate to :func:`repo.mi_turno.calcular_resumen_mi_turno`
         which runs the open-window temporal JOIN + the two
         ``SUM(factura_pagos)`` aggregates via the canonical F1.13
         helper (AD-3, R-F12.1-2).
      4. Attach ``Cache-Control: no-store`` to the response (R-A6).

    The handler does NOT write to any ``[A]`` or ``[V]`` table; the
    endpoint is purely a read aggregator.
    """
    from ...repo.mi_turno import SesionNotFoundError, calcular_resumen_mi_turno
    from ...repo.session_cycle import _now_naive

    no_store = no_store_headers()

    # Step 1 + 2: resolve the sesion AND enforce tenant pin BEFORE the
    # aggregator runs. The resolved ``uuid_sucursal`` is the SINGLE source
    # of branch scope; we never trust any ``uuid_sucursal`` from the wire.
    sesion_row = (
        await session.execute(select(Sesion).where(Sesion.uuid == uuid_sesion))
    ).scalar_one_or_none()
    if sesion_row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "sesion_not_found", "uuid_sesion": str(uuid_sesion)},
            headers=no_store,
        )
    if sesion_row.uuid_sucursal is None:
        # Sesion without branch scope is a data-integrity bug — surface
        # as 404 (the row is functionally incomplete).
        raise HTTPException(
            status_code=404,
            detail={"error": "sesion_not_found", "uuid_sesion": str(uuid_sesion)},
            headers=no_store,
        )
    if (
        ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or sesion_row.uuid_sucursal != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "sesion_cross_branch_forbidden",
                "uuid_sesion": str(uuid_sesion),
            },
            headers=no_store,
        )

    # Step 3: aggregator.
    try:
        resumen = await calcular_resumen_mi_turno(
            session,
            uuid_sesion=uuid_sesion,
            timestamp_calculo=_now_naive(),
        )
    except SesionNotFoundError as exc:
        # Race: sesion deleted between our SELECT and the aggregator.
        raise HTTPException(
            status_code=404,
            detail={"error": "sesion_not_found", "uuid_sesion": str(exc.uuid_sesion)},
            headers=no_store,
        ) from exc

    # Step 4: no-store header.
    apply_no_store_header(response)
    return resumen


__all__ = [
    "SubscriptionLookupResult",
    "cotizar_ingreso_handler",
    "get_mi_turno",
    "get_ocupacion",
    "resolve_active_subscription_for_exit",
    "router",
]
