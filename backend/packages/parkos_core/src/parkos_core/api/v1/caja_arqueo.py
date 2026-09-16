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

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...db.engine import get_session
from ...repo import arqueo as repo_arqueo
from ...schemas.caja import (
    ArqueoCreateV2,
    ArqueoReadForHandler,
    ArqueoResumenRead,
    CierreDiaNoAceptaSesionErrorRead,
    CierreDiarioQueryParams,
    JustificacionRequeridaErrorRead,
    SesionNoEncontradaErrorRead,
    SesionYaCerradaErrorRead,
    TipoArqueoNoEncontradoErrorRead,
    ToleranciaNoConfiguradaErrorRead,
)
from ..deps import requires_issuer
from . import _helpers

# Dedicated router -- mounted via ``router.include_router`` from
# ``api/v1/caja.py`` (DEC-ARQUEO-05). NOT via the ``make_router``
# factory because F1.13's write is cross-table atomic
# (1 [A] Arqueo + N [L-S] sesion + 1 [L-W] alerta + N+1 [A] log),
# which the read-only factory cannot model.
router = APIRouter(prefix="/caja", tags=["caja"])

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
    if tipo_arqueo.codigo == "cierre_dia":
        esperado_efectivo, esperado_datafono = (
            await repo_arqueo.calcular_esperado_cierre_dia(
                session,
                uuid_sucursal=target_sucursal,
                fecha=date_cls.today(),
            )
        )
    else:
        esperado_efectivo, esperado_datafono = (
            await repo_arqueo.calcular_esperado_sesion(
                session,
                uuid_sesion=payload.uuid_sesion,  # type: ignore[arg-type]
            )
        )
    diferencia_efectivo = repo_arqueo.calcular_diferencia(
        reportado=payload.valor_efectivo_reportado,
        esperado=esperado_efectivo,
    )
    diferencia_datafono = repo_arqueo.calcular_diferencia(
        reportado=payload.valor_datafono_reportado,
        esperado=esperado_datafono,
    )

    # --- Step 6 (DEC-ARQUEO-07): justificacion required on cierre_turno / cierre_dia + diferencia != 0.
    if tipo_arqueo.codigo != "auditoria" and (
        diferencia_efectivo != 0 or diferencia_datafono != 0
    ):
        if not payload.justificacion:
            raise HTTPException(
                status_code=400,
                detail={"error": "justificacion_requerida"},
                headers=no_store,
            )

    # --- Step 7 (DEC-ARQUEO-04 + KD-ARQUEO-04): descuadre decision (absolute monto).
    es_critico = repo_arqueo.es_descuadre_critico(
        diferencia_efectivo=diferencia_efectivo,
        diferencia_datafono=diferencia_datafono,
        tolerancia_efectivo=tolerancia.tolerancia_efectivo,
        tolerancia_datafono=tolerancia.tolerancia_datafono,
    )

    # --- Step 8 (KD-ARQUEO-02 + DEC-ARQUEO-02): INSERT prod.arqueo via append_event.
    descuadre_pct = None  # informational only (DEC-ARQUEO-04)
    esperado_total = esperado_efectivo + esperado_datafono
    if esperado_total > 0:
        descuadre_pct = (
            ((diferencia_efectivo + diferencia_datafono) / esperado_total) * 100
        )
    uuid_arqueo = (
        await repo_arqueo.insertar_arqueo(
            session,
            actor_uuid=ctx.actor_uuid,
            uuid_tipo_arqueo=tipo_arqueo.uuid,
            uuid_sesion=payload.uuid_sesion,
            valor_efectivo_esperado=esperado_efectivo,
            valor_datafono_esperado=esperado_datafono,
            valor_efectivo_reportado=payload.valor_efectivo_reportado,
            valor_datafono_reportado=payload.valor_datafono_reportado,
            diferencia_efectivo=diferencia_efectivo,
            diferencia_datafono=diferencia_datafono,
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
            fecha=date_cls.today(),
        )

    # --- Step 10 (KD-ARQUEO-05 + DEC-ARQUEO-05): conditional alerta INSERT via append_transition.
    alerta_uuid: uuid_lib.UUID | None = None
    alerta_generada = False
    if es_critico:
        alerta_row = await repo_arqueo.insertar_alerta_descuadre_critico(
            session,
            actor_uuid=ctx.actor_uuid,
            uuid_arqueo=uuid_arqueo,
            uuid_sucursal=target_sucursal,
            diferencia_efectivo=diferencia_efectivo,
            diferencia_datafono=diferencia_datafono,
            payload_json={
                "diferencia_efectivo": str(diferencia_efectivo),
                "diferencia_datafono": str(diferencia_datafono),
                "tolerancia_efectivo": (
                    str(tolerancia.tolerancia_efectivo)
                    if tolerancia.tolerancia_efectivo is not None
                    else None
                ),
                "tolerancia_datafono": (
                    str(tolerancia.tolerancia_datafono)
                    if tolerancia.tolerancia_datafono is not None
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
    _helpers.apply_no_store_header(response)
    return ArqueoReadForHandler(
        uuid=uuid_arqueo,
        uuid_tipo_arqueo=tipo_arqueo.uuid,
        codigo_tipo_arqueo=tipo_arqueo.codigo,
        uuid_sesion=payload.uuid_sesion,
        valor_efectivo_esperado=esperado_efectivo,
        valor_datafono_esperado=esperado_datafono,
        valor_efectivo_reportado=payload.valor_efectivo_reportado,
        valor_datafono_reportado=payload.valor_datafono_reportado,
        diferencia_efectivo=diferencia_efectivo,
        diferencia_datafono=diferencia_datafono,
        descuadre_pct=descuadre_pct,
        alerta_generada=alerta_generada,
        alerta_uuid=alerta_uuid,
    )


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


__all__ = ["router"]
