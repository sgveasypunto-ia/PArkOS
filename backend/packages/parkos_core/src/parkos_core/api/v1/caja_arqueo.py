"""HU-F1.13 / REQ-OPS-091..097 + REQ-OPS-XR6 -- caja arqueo endpoints.

Dedicated ``APIRouter`` mounted via ``router.include_router`` from
``api/v1/caja.py`` (DEC-ARQUEO-05). Two handlers:

* ``post_arqueo`` -- 12-step atomic chain on
  ``POST /api/v1/caja/arqueo``. KD-ARQUEO-01 single-commit
  invariant enforced by AST walk ``tests/static/test_arqueo_handler_single_commit.py``.
* ``get_arqueo_resumen`` -- 6-step read chain on
  ``GET /api/v1/caja/arqueo/resumen`` (added by T4.1).

Defense in depth (REQ-OPS-XR6 cross-cutting):

  * Layer 1: KD-3 issuer chain ``requires_issuer("operador-", "admin-")``
    + permission gate ``realizar_arqueo`` (post-GAP-BE-05 fix).
  * Layer 2: tenant scope post-V1 (KD-S2 F1.7 analog).
  * Layer 3: KD-ARQUEO-01 single-commit + KD-ARQUEO-08 lock ordering
    (SELECT FOR UPDATE on prod.tipo_arqueo at Step 1).
  * Layer 4: Pydantic ``extra='forbid'`` (ArqueoCreateV2._Base inheritance).
  * Layer 5: handler 422/409/404/403/400 mapping + ``Cache-Control: no-store``
    on every response (DEC-ARQUEO-06).

KD-ARQUEO-01 single-commit invariant (AST walk enforced): exactly one
``await session.commit()`` per handler body. The repo layer NEVER
commits -- this is the only commit point.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date as date_cls
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.permissions import require_permission
from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...db.engine import get_session
from ...repo import arqueo as repo_arqueo
from ...runtime.tiempo import hoy_bogota
from ...schemas.caja import (
    AdminResumenQueryParams,
    ArqueoCreateV2,
    ArqueoEsperadoParcialRead,
    ArqueoListQueryParams,
    ArqueoReadForHandler,
    ArqueoReadList,
    ArqueoRequiereJustificacionRead,
    ArqueoResumenAdminItem,
    ArqueoResumenAdminRead,
    ArqueoResumenItem,
    ArqueoResumenRead,
    CierreDiaNoAceptaSesionErrorRead,
    CierreDiarioQueryParams,
    EsperadoParcialQueryParams,
    JustificacionRequeridaErrorRead,
    RequiereJustificacionQueryParams,
    SesionNoEncontradaErrorRead,
    SesionYaCerradaErrorRead,
    TipoArqueoNoEncontradoErrorRead,
    ToleranciaNoConfiguradaErrorRead,
    _Base,
)
from ..deps import requires_issuer
from . import _helpers

# Dedicated router -- mounted via ``router.include_router`` from
# ``api/v1/caja.py`` (DEC-ARQUEO-05). NOT via the ``make_router``
# factory because F1.13's write is cross-table atomic
# (1 [A] Arqueo + N [L-S] sesion + 1 [L-W] alerta + N+1 [A] log),
# which the read-only factory cannot model.
#
# Prefix-less on purpose: the parent ``caja.router`` ALREADY has
# ``prefix="/caja"`` (api/v1/caja.py:25). Carrying the same prefix
# here AND including without ``prefix=""`` caused the F11.3 path
# doubling -- ``POST /api/v1/caja/arqueo`` and ``GET /api/v1/caja/arqueo/
# resumen`` registered at the doubled ``/api/v1/caja/caja/arqueo``
# (openapi.json confirmed pre-fix). The FE was hitting 405 because
# the canonical path ``/api/v1/caja/arqueo`` only had GET registered
# (factory mount). Removing the prefix lets the parent's prefix carry
# the canonical path.
router = APIRouter(tags=["caja"])
admin_router = APIRouter(tags=["caja"])


# ---------------------------------------------------------------------------
# HU-F18.1 admin list (REQ-OPS-152) -- GET /api/v1/caja/arqueo
# ---------------------------------------------------------------------------
# Mounted ABOVE the dedicated router block so the module-level
# ``router = APIRouter(...)`` below captures it. The GET endpoint is
# admin-only (admin- issuer) + audit_read permission; it does NOT
# share the operador- + realizar_arqueo gate of the write handler
# below (operators do not list arqueos -- they only POST their own).
# ---------------------------------------------------------------------------


_admin_arqueo_list_issuer_dep = requires_issuer("admin-")
_admin_arqueo_list_perm_dep = require_permission("audit_read")


@router.get(
    "/arqueo",
    response_model=ArqueoReadList,
    status_code=200,
    summary=(
        "HU-F18.1: cursor-paginated admin list of arqueos (REQ-OPS-152). "
        "All four selectors -- ``uuid_sucursal``, ``fecha_desde``, "
        "``fecha_hasta``, ``uuid_tipo_arqueo`` -- are optional. When "
        "none are provided, returns the most-recent ``limit`` arqueos "
        "across every branch."
    ),
)
async def list_arqueos(
    response: Response,
    params: ArqueoListQueryParams = Depends(),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _claims: None = Depends(_admin_arqueo_list_issuer_dep),
    _perm: None = Depends(_admin_arqueo_list_perm_dep),
) -> ArqueoReadList:
    """``GET /api/v1/caja/arqueo`` -- 4-step read chain.

    Step chain (mirrors the audit listing pattern):

      1. Layer 1 issuer dep + permission gate (``admin-`` + ``audit_read``).
      2. Layer 4 Pydantic validation: each query param is optional and
         ``extra='forbid'`` rejects unknown keys with 422 before the
         handler body runs.
      3. KD-MOT-AUDIT-01: SELECT via 1 typed helper
         ``repo.arqueo.listar_arqueos_admin``. NO UPDATE/DELETE, NO commit.
      4. Build the cursor via ``repo.arqueo.encode_arqueo_cursor`` --
         returns ``None`` at EOF (the SQL returns ``limit + 1`` rows; if
         ``len(items) <= limit`` the page was the last one).

    Empty case: zero rows returns ``items=[]`` + ``next_cursor=None``
    with HTTP 200 (NEVER 404 -- the absence of arqueos is a valid result,
    not a "branch not found" error).

    Cursor validation: ``decode_arqueo_cursor`` raises
    :class:`InvalidArqueoCursorError` on malformed base64/JSON/missing
    keys; this handler maps that to ``400 invalid_cursor``.

    Cache: ``Cache-Control: no-store`` (XR6 Layer 5) -- listing
    stale arqueos is worse than no list at all.
    """
    try:
        decoded_cursor = repo_arqueo.decode_arqueo_cursor(params.cursor)
    except repo_arqueo.InvalidArqueoCursorError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_cursor", "detail": str(exc)},
        ) from exc

    rows = await repo_arqueo.listar_arqueos_admin(
        session,
        uuid_sucursal=params.uuid_sucursal,
        fecha_desde=params.fecha_desde,
        fecha_hasta=params.fecha_hasta,
        uuid_tipo_arqueo=params.uuid_tipo_arqueo,
        cursor=decoded_cursor,
        limit=params.limit,
    )

    page_rows = rows[: params.limit]
    next_cursor = repo_arqueo.encode_arqueo_cursor(rows, params.limit)

    # QA backlog cleanup (2026-10-02, AlertaLink): one batched lookup for
    # the whole page instead of N+1 per-row queries.
    alerta_uuids = await repo_arqueo.get_alerta_uuids_for_arqueos(
        session, [r.uuid for r in page_rows]
    )

    _helpers.apply_no_store_header(response)
    return ArqueoReadList(
        items=[_to_arqueo_read(r, alerta_uuids.get(r.uuid)) for r in page_rows],
        next_cursor=next_cursor,
    )


def _to_arqueo_read(
    row: repo_arqueo.Arqueo, alerta_uuid: uuid_lib.UUID | None = None
) -> "ArqueoRead":
    """Shrink an ``Arqueo`` ORM row to the wire schema ``ArqueoRead``.

    The repo hands ``Arqueo`` with composite PK (``uuid`` +
    ``fecha_retencion_hasta``); the wire schema mirrors the column set
    1:1 (see ``schemas/caja.py::ArqueoRead``). Single-row mapper; the
    list endpoint wraps it inside ``items=[...]`` of the envelope.
    ``alerta_uuid`` is NOT an ``Arqueo`` column (see
    ``repo.arqueo.get_alerta_uuids_for_arqueos``) -- the caller resolves
    it separately and passes it in.
    """
    from ...schemas.caja import ArqueoRead

    return ArqueoRead(
        uuid=row.uuid,
        created_at=row.created_at,
        created_by=row.created_by,
        sync_status=row.sync_status,
        sync_timestamp=row.sync_timestamp,
        sync_attempts=row.sync_attempts,
        fecha_retencion_hasta=row.fecha_retencion_hasta,
        uuid_sucursal=row.uuid_sucursal,
        uuid_tipo_arqueo=row.uuid_tipo_arqueo,
        uuid_sesion=row.uuid_sesion,
        valor_efectivo_esperado=row.valor_efectivo_esperado,
        valor_datafono_esperado=row.valor_datafono_esperado,
        valor_efectivo_reportado=row.valor_efectivo_reportado,
        valor_datafono_reportado=row.valor_datafono_reportado,
        alerta_uuid=alerta_uuid,
    )

# KD-3 issuer chain + ``realizar_arqueo`` permission gate (DEC-ARQUEO-05).
_caja_arqueo_issuer_dep = requires_issuer("operador-", "admin-")
# Same dep reused for the GET resumen handler (T4.1) -- single
# permission ``realizar_arqueo`` covers both endpoints.
_caja_resumen_issuer_dep = requires_issuer("operador-", "admin-")


@router.post(
    "/arqueo",
    response_model=ArqueoReadForHandler,
    status_code=201,
    responses={
        400: {"model": CierreDiaNoAceptaSesionErrorRead},
        404: {"model": TipoArqueoNoEncontradoErrorRead},
        409: {"model": SesionYaCerradaErrorRead},
    },
)
async def post_arqueo(
    response: Response,
    payload: ArqueoCreateV2,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_caja_arqueo_issuer_dep),
) -> ArqueoReadForHandler:
    """POST /api/v1/caja/arqueo -- 12-step atomic handler.

    See module docstring for the full step chain + defense in depth.
    KD-ARQUEO-01 single-commit invariant: this handler owns the ONLY
    ``await session.commit()`` in the chain.

    Step chain:
        1. SELECT FOR UPDATE on prod.tipo_arqueo (KD-ARQUEO-08).
        2. cierre_dia cross-validation (cierre_dia requires uuid_sesion=null).
        2a. Tenant scope post-V1.
        3. SELECT vigente prod.configuracion_tolerancias.
        4. Validate sesion is open (cierre_turno / auditoria only).
        5. Compute esperado + diferencia (DEC-ARQUEO-04 + DEC-ARQUEO-10).
        6. Justificacion required when diferencia != 0 (DEC-ARQUEO-07).
        7. es_descuadre_critico (KD-ARQUEO-04).
        8. INSERT prod.arqueo via append_event (KD-ARQUEO-02).
        9. cerrar_sesiones_del_dia_bulk (cierre_dia only).
       10. conditional alerta INSERT via append_transition (KD-ARQUEO-05).
       12. SINGLE commit + response shape + Cache-Control: no-store.
    """
    no_store = _helpers.no_store_headers()

    # --- Step 1 (KD-ARQUEO-08 + DEC-ARQUEO-09): SELECT FOR UPDATE on prod.tipo_arqueo.
    try:
        tipo_arqueo = await repo_arqueo.resolver_tipo_arqueo_por_uuid(
            session,
            uuid_tipo_arqueo=payload.uuid_tipo_arqueo,
        )
    except repo_arqueo.TipoArqueoNoEncontradoError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "tipo_arqueo_no_encontrado",
                "uuid_tipo_arqueo": str(exc.uuid_tipo_arqueo),
            },
            headers=no_store,
        ) from exc

    # --- Step 2 (V2): cierre_dia MUST have uuid_sesion NULL; others MUST have uuid_sesion.
    if tipo_arqueo.codigo == "cierre_dia" and payload.uuid_sesion is not None:
        raise HTTPException(
            status_code=400,
            detail={"error": "cierre_dia_no_acepta_uuid_sesion"},
            headers=no_store,
        )
    if tipo_arqueo.codigo != "cierre_dia" and payload.uuid_sesion is None:
        raise HTTPException(
            status_code=400,
            detail={"error": "sesion_requerida_para_auditoria_o_cierre_turno"},
            headers=no_store,
        )

    # --- Step 2a (Layer 2): Tenant scope post-V1 (KD-S2 F1.7 analog). ---
    target_sucursal = ctx.sucursal_uuid
    if (
        ctx.issuer_prefix == "operador-"
        and target_sucursal is not None
        and target_sucursal != ctx.sucursal_uuid
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tenant_scope_violation",
                "uuid_sucursal_context": str(target_sucursal),
            },
            headers=no_store,
        )

    # --- Step 3 (V3): tolerance vigente row by target_sucursal (branch override -> global fallback).
    try:
        tolerancia = await repo_arqueo.resolver_tolerancia_vigente(
            session,
            uuid_sucursal=target_sucursal,
        )
    except repo_arqueo.ToleranciaNoConfiguradaError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "tolerancia_no_configurada",
                "uuid_sucursal": (
                    str(exc.uuid_sucursal) if exc.uuid_sucursal is not None else None
                ),
            },
            headers=no_store,
        ) from exc

    # --- Step 4 (V4 + REQ-OPS-096): validate sesion is open (cierre_turno / auditoria only).
    if payload.uuid_sesion is not None:
        try:
            await repo_arqueo.validar_sesion_abierta_para_arqueo(
                session,
                uuid_sesion=payload.uuid_sesion,
                target_sucursal=target_sucursal,
            )
        except repo_arqueo.SesionNoEncontradaError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "sesion_no_encontrada",
                    "uuid_sesion": str(exc.uuid_sesion),
                },
                headers=no_store,
            ) from exc
        except repo_arqueo.SesionYaCerradaError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "sesion_ya_cerrada",
                    "uuid_sesion": str(exc.uuid_sesion),
                },
                headers=no_store,
            ) from exc

    # --- Step 5 (V5 + DEC-ARQUEO-04 + DEC-ARQUEO-10): compute esperado + diferencia.
    # F12.1.1 / REQ-OPS-194: ``calcular_esperado_*`` returns a single
    # ``Decimal`` (effective only) -- the datafono dimension is no
    # longer in the calculation.
    # H9: the business day is the Bogota calendar day. ``date.today()``
    # is the server (UTC) date and flips to tomorrow at 19:00 Bogota,
    # which made the close pick tomorrow's (empty) sessions.
    fecha_negocio = hoy_bogota()
    if tipo_arqueo.codigo == "cierre_dia":
        esperado_efectivo = (
            await repo_arqueo.calcular_esperado_cierre_dia(
                session,
                uuid_sucursal=target_sucursal,
                fecha=fecha_negocio,
            )
        )
    else:
        esperado_efectivo = (
            await repo_arqueo.calcular_esperado_sesion(
                session,
                uuid_sesion=payload.uuid_sesion,  # type: ignore[arg-type]
            )
        )
    diferencia_efectivo = repo_arqueo.calcular_diferencia(
        reportado=payload.valor_efectivo_reportado,
        esperado=esperado_efectivo,
    )

    # --- Step 6 (DEC-ARQUEO-07 + REQ-OPS-094 modified): justificacion
    # required on cierre_turno / cierre_dia + diferencia_efectivo != 0.
    # The datafono dimension MUST NOT gate the justificacion requirement.
    if (
        tipo_arqueo.codigo != "auditoria"
        and diferencia_efectivo != 0
        and not payload.justificacion
    ):
        raise HTTPException(
            status_code=400,
            detail={"error": "justificacion_requerida"},
            headers=no_store,
        )

    # --- Step 7 (DEC-ARQUEO-04 + KD-ARQUEO-04 + REQ-OPS-195): descuadre
    # decision (effective only per F12.1.1).
    es_critico = repo_arqueo.es_descuadre_critico(
        diferencia_efectivo=diferencia_efectivo,
        tolerancia_efectivo=tolerancia.tolerancia_efectivo,
    )

    # --- Step 8 (KD-ARQUEO-02 + DEC-ARQUEO-02 + REQ-OPS-093 modified):
    # INSERT prod.arqueo via append_event. ``descuadre_pct`` is
    # informational only (DEC-ARQUEO-04), now computed on the effective
    # dimension only (datafono removed from the formula).
    descuadre_pct = None  # informational only (DEC-ARQUEO-04)
    if esperado_efectivo > 0:
        descuadre_pct = (diferencia_efectivo / esperado_efectivo) * 100
    uuid_arqueo = (
        await repo_arqueo.insertar_arqueo(
            session,
            actor_uuid=ctx.actor_uuid,
            uuid_sucursal=target_sucursal,
            uuid_tipo_arqueo=tipo_arqueo.uuid,
            uuid_sesion=payload.uuid_sesion,
            valor_efectivo_esperado=esperado_efectivo,
            valor_efectivo_reportado=payload.valor_efectivo_reportado,
            diferencia_efectivo=diferencia_efectivo,
            descuadre_pct=descuadre_pct,
            justificacion=payload.justificacion,
        )
    ).uuid

    # --- Step 9 (DEC-ARQUEO-03 + KD-ARQUEO-03): cierre_dia path only -- mass close sesiones.
    if tipo_arqueo.codigo == "cierre_dia":
        await repo_arqueo.cerrar_sesiones_del_dia_bulk(
            session,
            actor_uuid=ctx.actor_uuid,
            target_sucursal=target_sucursal,  # type: ignore[arg-type]
            fecha=fecha_negocio,
        )

    # --- Step 10 (KD-ARQUEO-05 + DEC-ARQUEO-05 + REQ-OPS-094 modified):
    # conditional alerta INSERT via append_transition. The datafono keys
    # are REMOVED from the payload (REQ-OPS-094); historical alertas with
    # the field populated stay in the bitácora (D3 drill-down).
    alerta_uuid: uuid_lib.UUID | None = None
    alerta_generada = False
    if es_critico:
        alerta_row = await repo_arqueo.insertar_alerta_descuadre_critico(
            session,
            actor_uuid=ctx.actor_uuid,
            uuid_arqueo=uuid_arqueo,
            uuid_sucursal=target_sucursal,
            diferencia_efectivo=diferencia_efectivo,
            payload_json={
                "diferencia_efectivo": str(diferencia_efectivo),
                "tolerancia_efectivo": (
                    str(tolerancia.tolerancia_efectivo)
                    if tolerancia.tolerancia_efectivo is not None
                    else None
                ),
                "descuadre_pct": (
                    str(descuadre_pct) if descuadre_pct is not None else None
                ),
                "codigo_tipo_arqueo": tipo_arqueo.codigo,
                "uuid_sesion": (
                    str(payload.uuid_sesion) if payload.uuid_sesion else None
                ),
            },
        )
        alerta_uuid = alerta_row.uuid
        alerta_generada = True

    # --- Step 12: KD-ARQUEO-01 SINGLE COMMIT (covers 4 table families).
    await session.commit()

    # --- Step 13: DEC-ARQUEO-06 -- Cache-Control: no-store + response shape.
    # REQ-OPS-192: datafono fields are NOT serialized in this response.
    _helpers.apply_no_store_header(response)
    return ArqueoReadForHandler(
        uuid=uuid_arqueo,
        uuid_tipo_arqueo=tipo_arqueo.uuid,
        codigo_tipo_arqueo=tipo_arqueo.codigo,
        uuid_sesion=payload.uuid_sesion,
        valor_efectivo_esperado=esperado_efectivo,
        valor_efectivo_reportado=payload.valor_efectivo_reportado,
        diferencia_efectivo=diferencia_efectivo,
        descuadre_pct=descuadre_pct,
        alerta_generada=alerta_generada,
        alerta_uuid=alerta_uuid,
    )


# ---------------------------------------------------------------------------
# HU-F10.2 follow-up -- GET /api/v1/caja/arqueo/requiere-justificacion
# ---------------------------------------------------------------------------


@router.get(
    "/arqueo/requiere-justificacion",
    response_model=ArqueoRequiereJustificacionRead,
    status_code=200,
    responses={
        404: {"model": SesionNoEncontradaErrorRead},
        409: {"model": SesionYaCerradaErrorRead},
    },
)
async def get_arqueo_requiere_justificacion(
    response: Response,
    params: RequiereJustificacionQueryParams = Depends(),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_caja_arqueo_issuer_dep),
) -> ArqueoRequiereJustificacionRead:
    """GET /api/v1/caja/arqueo/requiere-justificacion -- conteo ciego pre-flight.

    Bugfix (2026-10-01, cierre de turno): the FE used to guess whether a
    justificacion would be required by comparing the operator's reported
    count against ``sesion.valor_inicial_*`` -- a false negative whenever
    the session had ANY transactions, since the real esperado is
    ``inicial + SUM(factura_pagos)`` (server-side only, DEC-ARQUEO-10).
    That false negative hid the Justificacion field until the real
    ``POST /caja/arqueo`` rejected the submit with 400
    ``justificacion_requerida``, leaving the operator stuck resubmitting
    the identical payload.

    This handler runs the SAME Step 5/6 diferencia check ``post_arqueo``
    runs, scoped to ``tipo_arqueo='cierre_turno'`` semantics (diferencia
    != 0 always requires justificacion here -- unlike ``auditoria``,
    which never does), and returns ONLY the boolean verdict. The
    computed ``esperado_efectivo``/``esperado_datafono``/signed
    diferencia are intentionally NEVER serialized here -- conteo ciego
    (plan.md HU-F10.2) requires the expected totals stay server-side
    even over the wire, not just unrendered in the DOM.

    Reuses ``validar_sesion_abierta_para_arqueo`` (V4) for tenant scope
    + open/closed validation -- identical 404/409 semantics as the POST
    handler's Step 4.
    """
    no_store = _helpers.no_store_headers()
    target_sucursal = ctx.sucursal_uuid

    try:
        await repo_arqueo.validar_sesion_abierta_para_arqueo(
            session,
            uuid_sesion=params.uuid_sesion,
            target_sucursal=target_sucursal,
        )
    except repo_arqueo.SesionNoEncontradaError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "sesion_no_encontrada",
                "uuid_sesion": str(exc.uuid_sesion),
            },
            headers=no_store,
        ) from exc
    except repo_arqueo.SesionYaCerradaError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "sesion_ya_cerrada",
                "uuid_sesion": str(exc.uuid_sesion),
            },
            headers=no_store,
        ) from exc

    esperado_efectivo = await repo_arqueo.calcular_esperado_sesion(
        session,
        uuid_sesion=params.uuid_sesion,
    )
    diferencia_efectivo = repo_arqueo.calcular_diferencia(
        reportado=params.valor_efectivo_reportado,
        esperado=esperado_efectivo,
    )
    # REQ-OPS-193: datafono dimension is excluded; the gate is
    # effective-only.
    _helpers.apply_no_store_header(response)
    return ArqueoRequiereJustificacionRead(
        requiere_justificacion=diferencia_efectivo != 0,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/caja/arqueo/esperado-parcial -- efectivo esperado del turno abierto
# ---------------------------------------------------------------------------


@router.get(
    "/arqueo/esperado-parcial",
    response_model=ArqueoEsperadoParcialRead,
    status_code=200,
    responses={
        404: {"model": SesionNoEncontradaErrorRead},
        409: {"model": SesionYaCerradaErrorRead},
    },
)
async def get_arqueo_esperado_parcial(
    response: Response,
    params: EsperadoParcialQueryParams = Depends(),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_caja_arqueo_issuer_dep),
) -> ArqueoEsperadoParcialRead:
    """Efectivo esperado (base + cobros en efectivo - reversos) del turno abierto.

    Existe para el arqueo PARCIAL, que muestra el esperado al operador y antes
    lo reemplazaba en pantalla por la base sola (falso faltante). Usa la misma
    ``calcular_esperado_sesion`` que ``post_arqueo``, asi que pantalla y registro
    nunca divergen. El cierre de turno (conteo ciego) no consume este endpoint.
    """
    no_store = _helpers.no_store_headers()
    try:
        await repo_arqueo.validar_sesion_abierta_para_arqueo(
            session,
            uuid_sesion=params.uuid_sesion,
            target_sucursal=ctx.sucursal_uuid,
        )
    except repo_arqueo.SesionNoEncontradaError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "sesion_no_encontrada", "uuid_sesion": str(exc.uuid_sesion)},
            headers=no_store,
        ) from exc
    except repo_arqueo.SesionYaCerradaError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "sesion_ya_cerrada", "uuid_sesion": str(exc.uuid_sesion)},
            headers=no_store,
        ) from exc

    esperado = await repo_arqueo.calcular_esperado_sesion(
        session, uuid_sesion=params.uuid_sesion
    )
    _helpers.apply_no_store_header(response)
    return ArqueoEsperadoParcialRead(valor_efectivo_esperado=esperado)


# ---------------------------------------------------------------------------
# T4 -- GET /api/v1/caja/arqueo/resumen (REQ-OPS-097)
# ---------------------------------------------------------------------------


@router.get(
    "/arqueo/resumen",
    response_model=ArqueoResumenRead,
    status_code=200,
)
async def get_arqueo_resumen(
    response: Response,
    params: CierreDiarioQueryParams = Depends(),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_caja_resumen_issuer_dep),
) -> ArqueoResumenRead:
    """GET /api/v1/caja/arqueo/resumen -- 6-step read chain.

    Step chain:
        1. Layer 1 issuer dep + permission gate (KD-3 + GAP-BE-05
           ``realizar_arqueo``).
        2. Layer 2 tenant scope post-V1 (KD-S2 analog from F1.7):
           ``operador-`` cross-branch rejected with 403
           ``tenant_scope_violation``.
        3. G3 list sesiones of the day at branch.
        4. G4 per-sesion ``construir_resumen_sesion`` (aggregate arqueo
           + factura_pagos SUM).
        5. G5 ``obtener_cierre_dia_del_dia`` (cierre_dia aggregate at
           bottom of response).
        6. G6 build ``ArqueoResumenRead`` + apply no-store.
    """
    no_store = _helpers.no_store_headers()

    # --- Step 1+2: Layer 2 tenant scope post-V1 ---
    if (
        ctx.issuer_prefix == "operador-"
        and ctx.sucursal_uuid is not None
        and ctx.sucursal_uuid != params.uuid_sucursal
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "tenant_scope_violation"},
            headers=no_store,
        )

    # --- Step 3 (G3): list sesiones of the day at branch ---
    sesiones = await repo_arqueo.listar_sesiones_del_dia(
        session,
        uuid_sucursal=params.uuid_sucursal,
        fecha=params.fecha,
    )

    # --- Step 4 (G4): aggregate arqueo per sesion ---
    from ...schemas.caja import ArqueoResumenItem  # local import to keep top tidy

    items: list[ArqueoResumenItem] = []
    for sesion in sesiones:
        resumen_dict = await repo_arqueo.construir_resumen_sesion(
            session, sesion=sesion
        )
        items.append(ArqueoResumenItem(**resumen_dict))

    # --- Step 5 (G5): cierre_dia aggregate (if exists for fecha+sucursal) ---
    cierre_dia_dict = await repo_arqueo.obtener_cierre_dia_del_dia(
        session,
        uuid_sucursal=params.uuid_sucursal,
        fecha=params.fecha,
    )
    cierre_dia_item: ArqueoResumenItem | None = (
        ArqueoResumenItem(**cierre_dia_dict) if cierre_dia_dict is not None else None
    )

    # --- Step 6 (G6): build ArqueoResumenRead + apply no-store ---
    resumen = ArqueoResumenRead(
        fecha=params.fecha,
        uuid_sucursal=params.uuid_sucursal,
        sesiones=items,
        cierre_dia=cierre_dia_item,
    )
    _helpers.apply_no_store_header(response)
    return resumen


# ---------------------------------------------------------------------------
# HU-F18.3 admin resumen cross-branch (REQ-OPS-153)
#
# Mounted on ``admin_router`` (prefix="/admin/caja") so the path lives
# under a separate admin tree, mirroring the F18.1 split. The operator
# tree at ``/caja/...`` is unchanged (operadores continue to see only
# their own branch via ``CierreDiarioQueryParams.uuid_sucursal``).
# ---------------------------------------------------------------------------


_admin_arqueo_resumen_issuer_dep = requires_issuer("admin-")
_admin_arqueo_resumen_perm_dep = require_permission("audit_read")


class AdminResumenQueryParams(_Base):
    """Query params for ``GET /api/v1/admin/caja/arqueo/resumen``.

    ``fecha`` is the ONLY required param (ISO YYYY-MM-DD, validated
    as a real ``date``). The endpoint returns one ``ArqueoResumenAdminItem``
    per vigente ``prod.sucursal`` regardless of branch filter -- the
    admin sees everything by default; per-branch filtering is the
    operator side's concern.

    Validation: ``fecha`` is required. ``extra='forbid'`` rejects
    client smuggling (the endpoint will gain more filters in
    subsequent commits).
    """

    fecha: date_cls


@admin_router.get(
    "/arqueo/resumen-admin",
    response_model=ArqueoResumenAdminRead,
    status_code=200,
    summary=(
        "HU-F18.3: cross-branch admin resumen por día (REQ-OPS-153). "
        "One item per vigente ``prod.sucursal`` with the day's expected "
        "totals + cierre_dia (if any) + total_arqueos. Empty days "
        "return ``items=[]`` with HTTP 200, not 404."
    ),
)
async def get_admin_arqueo_resumen(
    response: Response,
    params: AdminResumenQueryParams = Depends(),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _claims: None = Depends(_admin_arqueo_resumen_issuer_dep),
    _perm: None = Depends(_admin_arqueo_resumen_perm_dep),
) -> ArqueoResumenAdminRead:
    """``GET /api/v1/admin/caja/arqueo/resumen`` -- 4-step read chain.

      1. Layer 1 issuer dep (admin- only) + audit_read perm gate.
      2. Layer 4 Pydantic validation (fecha required, extra='forbid').
      3. KD-MOT-2025-10-01: SELECT via 1 typed helper
         ``repo.arqueo.resumen_admin_del_dia``. NO UPDATE/DELETE,
         NO commit (read-only).
      4. Build ``ArqueoResumenAdminRead`` from the per-branch dicts.

    Cache-Control: no-store (XR6 Layer 5, same as the operator
    resumen). Stale arqueo summary is worse than no summary.

    Empty case: a day with zero arqueos returns ``items=[]`` + 200,
    never 404. Cross-branch visibility was a prereq for the operator
    F18.2 detail per plan.md:4048 -- this is its counterpart for the
    admin cross-branch read.
    """
    items = await repo_arqueo.resumen_admin_del_dia(
        session,
        fecha=params.fecha,
    )
    _helpers.apply_no_store_header(response)
    return ArqueoResumenAdminRead(
        fecha=params.fecha,
        items=[_row_to_admin_item(i) for i in items],
    )


def _row_to_admin_item(row: dict) -> ArqueoResumenAdminItem:
    """Convert a repo-dict row from ``resumen_admin_del_dia`` to the
    wire-shape ``ArqueoResumenAdminItem``.

    The repo produces ``dict[str, Any]`` because its return type is
    shared across helpers; the route handler does the conversion at
    the wire boundary.

    The ``esperado_datafono`` key is dropped from the response per
    REQ-OPS-097 modified (F12.1.1): the repo still emits the key for
    backward-compat but the wire shape no longer surfaces it. Phase 5
    will remove the key entirely from the repo dict.
    """
    cierre = row.get("cierre_dia")
    return ArqueoResumenAdminItem(
        uuid_sucursal=row["uuid_sucursal"],
        nombre=row.get("nombre"),
        esperado_efectivo=row.get("esperado_efectivo"),
        cierre_dia=(
            ArqueoResumenItem(**cierre) if cierre is not None else None
        ),
        total_arqueos=row.get("total_arqueos", 0),
    )


__all__ = ["router", "admin_router"]
