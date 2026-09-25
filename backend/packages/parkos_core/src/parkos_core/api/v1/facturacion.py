"""Operations HTTP routes — facturacion (PR6, T-PR6-10, REQ-10, REQ-15, REQ-30).

5 non-cloud billing tables mounted via :func:`make_router`:

- ``facturas`` — ``[L-E]`` operational invoice event (branch writes;
  sibling ``ingreso`` event in PR5)
- ``factura-detalle`` — ``[A]`` invoice line items (one row per concept)
- ``factura-impuestos`` — ``[A]`` tax snapshot (IVA, INC, etc.)
- ``factura-otros-cobros`` — ``[A]`` surcharges (recargos, propinas)
- ``factura-pagos`` — ``[A]`` payment events + reversals
  (REQ-OP-09, SC-11). The reverso write path lives in
  :mod:`repo.factura_pagos` (T-PR6-05); the partial unique index
  ``uq_factura_pagos_reverso`` (T-PR6-06) blocks double-reversals at
  the DB layer.

Cloud-only ``factura-electronica`` lives in
:mod:`parkos_core.dian.cloud_router` (T-PR6-09, REQ-X3). This module
MUST NOT mount it — doing so re-exposes cloud-only endpoints on the
branch API.

READ-ONLY mounts (PR6):

These 5 tables are mounted with ``write_enabled=False``. None of the 5
has the ``vigente_hasta`` column that :func:`make_router`'s
``"versioned"`` branch requires for close+insert writes, and putting
:func:`repo.append_only.append_event` /
:func:`repo.event.record_event` /
:func:`repo.factura_pagos.reverse_payment` behind the generic factory
would conflate write paths. Custom write endpoints arrive in PR7
(monthly operations) and PR8 (reverso surface) — those PRs can reuse
the read endpoints already mounted here.

The read endpoints obey the standard cursor-paginated list contract
(REQ-OP-01) and the per-resource issuer + permission guard
(REQ-OP-13).

NO DELETE endpoint — defense in depth (design §3, AGENTS.md §3).
"""
from __future__ import annotations

import uuid as uuid_lib
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...db.engine import get_session
from ...models.A.factura_detalle import FacturaDetalle
from ...models.A.factura_impuestos import FacturaImpuestos
from ...models.A.factura_otros_cobros import FacturaOtrosCobros
from ...models.A.factura_pagos import FacturaPagos
from ...models.L_E.facturas import Facturas
from ...repo import factura as repo_factura
from ...repo.factura_detalle import crear_factura_detalle_bulk
from ...repo.impuestos import obtener_iva_vigente
from ...schemas.facturacion import (
    FacturaCreate,
    FacturaDetalleCreate,
    FacturaDetalleRead,
    FacturaDetalleReadList,
    FacturaDetalleUpdate,
    FacturaImpuestosCreate,
    FacturaImpuestosRead,
    FacturaImpuestosReadList,
    FacturaImpuestosUpdate,
    FacturaOtrosCobrosCreate,
    FacturaOtrosCobrosRead,
    FacturaOtrosCobrosReadList,
    FacturaOtrosCobrosUpdate,
    FacturaPagoAdicionalCreate,
    FacturaPagoRead,
    FacturaPagosCreate,
    FacturaPagosRead,
    FacturaPagosReadList,
    FacturaPagosUpdate,
    FacturaRead,
    FacturasCreate,
    FacturasRead,
    FacturasReadList,
    FacturasUpdate,
)
from ..deps import requires_issuer
from ..router_factory import make_router
from ._helpers import apply_no_store_header, no_store_headers
from ._factura_display import build_display_factura

router = APIRouter(prefix="/facturacion", tags=["facturacion"])

# Issuer-permission defaults per resource (T-PR6-10). All 5 tables use
# the same operator + admin scope because the operator mutates these
# (in custom endpoints shipping later) and the admin needs cross-branch
# read visibility.
_ROUTER_CONFIG = {
    "facturas": ("operador-,admin-", "emitir_factura"),
    "factura-detalle": ("operador-,admin-", "emitir_factura"),
    "factura-impuestos": ("operador-,admin-", "emitir_factura"),
    "factura-otros-cobros": ("operador-,admin-", "emitir_factura"),
    "factura-pagos": ("operador-,admin-", "emitir_factura"),
}


def _mount_factura(
    *,
    resource: str,
    model_cls: type,
    read_schema: type,
    read_list_schema: type,
    create_schema: type,
    update_schema: type,
) -> None:
    """Mount one facturacion C+Q+U router under ``/facturacion/{resource}``.

    ``write_enabled=False`` per PR6 rationale above.
    """
    issuer, perm = _ROUTER_CONFIG[resource]
    router.include_router(
        make_router(
            resource=resource,
            model_cls=model_cls,
            read_schema=read_schema,
            read_list_schema=read_list_schema,
            create_schema=create_schema,
            update_schema=update_schema,
            repo_kind="versioned",
            issuer_required=issuer,
            permission_required=perm,
            write_enabled=False,
        )
    )


_mount_factura(
    resource="facturas",
    model_cls=Facturas,
    read_schema=FacturasRead,
    read_list_schema=FacturasReadList,
    create_schema=FacturasCreate,
    update_schema=FacturasUpdate,
)
_mount_factura(
    resource="factura-detalle",
    model_cls=FacturaDetalle,
    read_schema=FacturaDetalleRead,
    read_list_schema=FacturaDetalleReadList,
    create_schema=FacturaDetalleCreate,
    update_schema=FacturaDetalleUpdate,
)
_mount_factura(
    resource="factura-impuestos",
    model_cls=FacturaImpuestos,
    read_schema=FacturaImpuestosRead,
    read_list_schema=FacturaImpuestosReadList,
    create_schema=FacturaImpuestosCreate,
    update_schema=FacturaImpuestosUpdate,
)
_mount_factura(
    resource="factura-otros-cobros",
    model_cls=FacturaOtrosCobros,
    read_schema=FacturaOtrosCobrosRead,
    read_list_schema=FacturaOtrosCobrosReadList,
    create_schema=FacturaOtrosCobrosCreate,
    update_schema=FacturaOtrosCobrosUpdate,
)
_mount_factura(
    resource="factura-pagos",
    model_cls=FacturaPagos,
    read_schema=FacturaPagosRead,
    read_list_schema=FacturaPagosReadList,
    create_schema=FacturaPagosCreate,
    update_schema=FacturaPagosUpdate,
)

# ---------------------------------------------------------------------------
# HU-F1.9 — custom write endpoints (POST /factura + POST /factura-pagos).
#
# These two handlers CLOSE the billing half of CU-04. They do NOT replace the
# generic CRUD mounts above (read-only, PR6); they provide the
# transactional write path that the auto-generated CRUD cannot express
# (atomic 4-table INSERT in a single session.commit() — KD-FACT-01).
#
# DEC-FACT-01..09 + KD-FACT-01 + KD-FACT-02 invariants apply.
# ---------------------------------------------------------------------------

# KD-3: issuer chain. Operador (cajero role) emits facturas; admin may
# cross-branch. Aligned with the PR6 CRUD mount (operador-,admin-).
_facturacion_issuer_dep = requires_issuer("operador-", "admin-")


@router.post(
    "/factura",
    response_model=FacturaRead,
    status_code=201,
    summary=(
        "HU-F1.9 / REQ-OPS-053..063: atomic 4-table insert — facturas + "
        "factura_detalle + factura_impuestos + factura_pagos in one "
        "await session.commit() (KD-FACT-01)."
    ),
    responses={
        400: {
            "description": (
                "voucher_requerido (V7 -- medio_pago='datafono' sin "
                "referencia)"
            )
        },
        403: {"description": "tenant_scope_violation (cajero)"},
        404: {
            "description": (
                "salida_no_encontrada (V1) | cliente_no_encontrado (V2)"
            )
        },
        409: {"description": "factura_duplicada (one_factura_per_salida)"},
        422: {
            "description": (
                "nit_invalido (V5) | email_invalido | "
                "detalle_invalido (V4) | total_no_coherente (V6)"
            )
        },
        500: {"description": "iva_no_configurado (V3, post-0026: never)"},
    },
)
async def create_factura(
    response: Response,
    payload: FacturaCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_facturacion_issuer_dep),
) -> FacturaRead:
    """REQ-OPS-053..063: atomic billing transaction.

    Dependency chain (same as create_ingreso / create_salida F1.6/F1.7):
        _facturacion_issuer_dep -> requires_issuer("operador-", "admin-")
        get_tenant_ctx          -> TenantContext { actor_uuid, sucursal_uuid, ... }
        get_session             -> AsyncSession (request-scoped)

    Sequence (D-HU-F1.9-11 13-step chain, locked by AST walk):
        1. KD-3 issuer claims + no_store headers
        2. V1 salida existe y es facturable (404 if None)
        3. tenant scope post-V1 (403 if cajero cross-branch)
        4. V2 cliente existe cuando fe_con_datos=true (404 if None)
        5. V3 IVA configurado (500 iva_no_configurado if False)
        6. V4 detalle items coherentes (422 detalle_invalido if empty)
        6.5 V7 voucher_requerido if medio_pago='datafono' AND referencia
            empty/whitespace (400 voucher_requerido, CU-04 BR6 backfill)
        7. KD-FACT-02 lock FOR SHARE per-row on tarifas_sucursal
        8. V6 server-side recompute total (±0.01 COP)
        9. INSERT prod.facturas [L-E] (DEC-FACT-01: NO UPDATE anywhere)
       10. INSERT factura_detalle (N) + factura_impuestos (1) + pagos (1)
       11. single await session.commit() (KD-FACT-01, KD-FACT-02 release)
       12. response shape FacturaRead with uuid_cliente derived (DEC-FACT-06)

    Lock continuity (KD-FACT-02): the FOR SHARE lock acquired in Step 7
    is held through Step 10 INSERTs. Released at session.commit() in
    Step 11. NO sub-transactions, NO SAVEPOINT.

    Idempotency-Key header is handled by FastAPI middleware (DEC-IDEM-01
    reuse from F1.6).
    """
    no_store = no_store_headers()

    # --- Step 1: KD-3 (issuer claims + no_store). ----------------------
    # Resolved via dependency injection.

    # --- Step 2: V1 (salida existe y es facturable). -------------------
    salida = await repo_factura.buscar_salida_facturable(
        session, uuid_salida=payload.uuid_salida
    )
    if salida is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "salida_no_encontrada",
                "uuid_salida": str(payload.uuid_salida),
            },
            headers=no_store,
        )

    # --- Step 3: tenant scope (post-V1, KD-S2 analog from F1.7). -------
    target_sucursal = salida.uuid_sucursal
    if (
        ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or target_sucursal != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tenant_scope_violation",
                "uuid_salida": str(payload.uuid_salida),
            },
            headers=no_store,
        )

    # --- Step 4: V2 cliente existe cuando fe_con_datos=true. -----------
    # Defense in depth (zero-bug-policy, 2026-09-23): the request body
    # schema declares ``fe_datos_cliente: FacturaItemConDatosPropios |
    # None = None``. A client can send ``{"fe_con_datos": true, ...}``
    # WITHOUT ``fe_datos_cliente``, in which case the previous code crashed
    # at line 298 with ``AttributeError: 'NoneType' object has no
    # attribute 'numero_identificacion'``. We now reject that case
    # explicitly with 422 cliente_invalido so the operator gets a clear
    # error instead of a 500.
    cliente_uuid: uuid_lib.UUID | None = None
    if payload.fe_con_datos:
        if payload.fe_datos_cliente is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "cliente_invalido",
                    "reason": "fe_datos_cliente_requerido_cuando_fe_con_datos",
                },
                headers=no_store,
            )
        cliente = await repo_factura.buscar_o_crear_cliente_por_nit(
            session,
            numero_identificacion=payload.fe_datos_cliente.numero_identificacion,
            datos=payload.fe_datos_cliente,
        )
        if cliente is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "cliente_no_encontrado",
                    "numero_identificacion": (
                        payload.fe_datos_cliente.numero_identificacion
                    ),
                },
                headers=no_store,
            )
        cliente_uuid = cliente.uuid

    # --- Step 5: V3 (IVA configurado). ---------------------------------
    # DEC-FACT-03: source the IVA rate from prod.impuestos (NOT a hardcoded
    # constant). The same rate is then used in Step 8 (compute_total) and
    # Step 10b (crear_factura_impuesto_iva) to keep the total coherent
    # with the IVA snapshot.
    iva_porcentaje = await obtener_iva_vigente(session)
    if iva_porcentaje is None:
        raise HTTPException(
            status_code=500,
            detail={"error": "iva_no_configurado"},
            headers=no_store,
        )

    # --- Step 6: V4 detalle items coherentes. --------------------------
    items_validados = repo_factura.validar_items(payload.items)
    if not items_validados:
        raise HTTPException(
            status_code=422,
            detail={"error": "detalle_invalido", "min_items": 1},
            headers=no_store,
        )

    # --- Step 6.5: V7 voucher_requerido (datafono sin referencia). ----
    # Backfill V7 in the primary create_factura endpoint (CU-04 BR6,
    # plan.md line 899). Mirrors the inline guard at create_factura_pago
    # :449-457 and the F1.12 V8 mirror at clientes_venta.py:265-273. The
    # Pydantic schema (FacturaCreate.referencia = StringConstraints(
    # min_length=1) | None) blocks empty strings at the schema gate but
    # lets ``None`` and whitespace-only strings through, so the handler
    # MUST enforce ``datafono + (None | '' | whitespace)`` here. The
    # typed exception :class:`VoucherRequeridoError` (declared in
    # repo/factura.py:68-69) documents V7 but is intentionally dead
    # code across the codebase -- the HTTP boundary uses HTTPException
    # directly, matching every other V1..V7 step in this handler.
    if payload.medio_pago == "datafono" and (
        not payload.referencia or payload.referencia.strip() == ""
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "voucher_requerido",
                "medio_pago": "datafono",
            },
            headers=no_store,
        )

    # --- Step 7: KD-FACT-02 lock FOR SHARE per-row. --------------------
    await repo_factura.lock_tarifas_sucursal_para_items(
        session, items=items_validados
    )

    # --- Step 8: V6 server-side recompute total (±0.01 COP). -----------
    total_server = repo_factura.compute_total(
        items=items_validados, iva=iva_porcentaje, retencion=Decimal(0)
    )
    if abs(total_server - payload.total) > Decimal("0.01"):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "total_no_coherente",
                "total_recibido": str(payload.total),
                "total_calculado": str(total_server),
                "diferencia": str(abs(total_server - payload.total)),
            },
            headers=no_store,
        )

    # --- Step 9: INSERT prod.facturas [L-E]. ---------------------------
    # ``descuento`` (2026-09-24, salida-mensualidad factura): real sum
    # of the request's ``tipo="descuento"`` lines, not a hardcoded
    # Decimal(0) -- see ``repo.factura.compute_descuento``.
    descuento_server = repo_factura.compute_descuento(items_validados)
    new_factura = await repo_factura.crear_factura_evento(
        session,
        actor_uuid=ctx.actor_uuid,
        new_attrs={
            "uuid_sucursal": target_sucursal,
            "uuid_ingreso": salida.uuid_ingreso,
            "uuid_salida": salida.uuid,
            "subtotal": payload.subtotal,
            "descuento": descuento_server,
            "total": payload.total,
        },
    )

    # --- Step 10: INSERT factura_detalle (N) + impuestos (1) + pago. --
    detalles_creados = await crear_factura_detalle_bulk(
        session, uuid_factura=new_factura.uuid, items=items_validados
    )
    await repo_factura.crear_factura_impuesto_iva(
        session, uuid_factura=new_factura.uuid, base=total_server, iva=iva_porcentaje
    )
    await repo_factura.crear_factura_pago(
        session,
        uuid_factura=new_factura.uuid,
        medio_pago=payload.medio_pago,
        valor=payload.total,
        referencia=payload.referencia,
        uuid_sesion=ctx.uuid_sesion,
    )

    # --- Step 11: KD-FACT-01 single commit. ---------------------------
    await session.commit()  # UN solo commit (lock release, KD-FACT-02)

    # --- Step 12: response shape. -------------------------------------
    apply_no_store_header(response)
    await session.refresh(new_factura)
    # HU-F8.4: enrichment for `<FacturaDisplayModal />` (apps/electron-
    # sucursal) lives in ``_factura_display.build_display_factura`` so
    # the handler stays focused on the 12-step chain. The helper reads
    # the joined rows the handler just committed and assembles the
    # enriched ``FacturaRead``. Notable fixes the helper carries:
    # - ``item.tipo`` AttributeError (pre-existing): ``FacturaDetalle``
    #   has no ``tipo`` column in the DB; the helper hard-codes
    #   ``"servicio"`` per the parking-lot assumption (every line is
    #   a service). See _factura_display.py docstring.
    # - Numeric columns map SQLAlchemy float → Pydantic Decimal; the
    #   helper does the conversion once, centrally.
    # - numero_recibo is derived server-side per plan.md:473
    #   (sucursal-YYYYMMDD-NNNNNN, O(N) per emission; column promotion
    #   deferred post-MVP).
    return await build_display_factura(
        session,
        new_factura=new_factura,
        detalles_creados=detalles_creados,
        payload=payload,
        total_server=total_server,
        cliente_uuid=cliente_uuid,
    )


@router.post(
    "/factura-pagos",
    response_model=FacturaPagoRead,
    status_code=201,
    summary=(
        "HU-F1.9 / REQ-OPS-062: voucher validation for datáfono + "
        "additional payment record on existing factura."
    ),
    responses={
        400: {"description": "voucher_requerido (datafono sin referencia)"},
        404: {"description": "factura_no_encontrada"},
        409: {"description": "pago_duplicado (init pago ya existe)"},
        422: {"description": "valor_invalido (factura_pagos schema gate)"},
    },
)
async def create_factura_pago(
    response: Response,
    payload: FacturaPagoAdicionalCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_facturacion_issuer_dep),
) -> FacturaPagoRead:
    """REQ-OPS-062: 5-step chain for additional factura_pagos INSERT.

    Sequence (locked by AST walk, file 5):
        1. KD-3 issuer claims + no_store headers (DI)
        2. V7 voucher_requerido if medio_pago='datafono' AND referencia empty
        3. INSERT prod.factura_pagos [A] + flush
        4. single await session.commit()
        5. response shape FacturaPagoRead

    Idempotency: same Idempotency-Key header (DEC-IDEM-01 reuse from F1.6).
    """
    no_store = no_store_headers()

    # --- Step 1: KD-3 (issuer claims + no_store). ----------------------
    # Resolved via dependency injection.

    # --- Step 2: V7 voucher_requerido. ---------------------------------
    if payload.medio_pago == "datafono" and not payload.referencia:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "voucher_requerido",
                "medio_pago": "datafono",
            },
            headers=no_store,
        )

    # --- Step 3: INSERT prod.factura_pagos [A]. -----------------------
    new_pago = await repo_factura.crear_factura_pago(
        session,
        uuid_factura=payload.uuid_factura,
        medio_pago=payload.medio_pago,
        valor=payload.valor,
        referencia=payload.referencia,
        uuid_sesion=payload.uuid_sesion or ctx.uuid_sesion,
    )

    # --- Step 4: single commit. ----------------------------------------
    await session.commit()

    # --- Step 5: response shape. ---------------------------------------
    apply_no_store_header(response)
    return FacturaPagoRead(
        uuid=new_pago.uuid,
        uuid_factura=new_pago.uuid_factura,
        medio_pago=new_pago.medio_pago,
        valor=new_pago.valor,
        referencia=new_pago.referencia,
        timestamp_evento=new_pago.timestamp_evento,
    )


# ---------------------------------------------------------------------------
# HU-F1.10 — Numeración FE + estado DIAN + reintento (T4.2 full impl).
#
# Three new handlers on the existing router (DEC-FE-01..07 + KD-FE-01..02):
#   - POST   /factura-electronica                       (12-step chain)
#   - GET    /factura-electronica/{uuid}                (3-step chain, view JOIN)
#   - POST   /factura-electronica/{uuid}/reintentar     (8-step chain, NEVER UPDATE)
#
# Defense in depth: KD-3 issuer chain + tenant scope post-V1 + DB
# partial UK `one_fe_per_factura` (MIGRATION 0028 Op 2) + `assign_consecutivo`
# SELECT FOR UPDATE (KD-FE-02, REUSE from F1.9) + handler 409 mapping
# (8 typed error schemas).
# ---------------------------------------------------------------------------
from ...repo import factura_electronica as repo_factura_electronica
from ...repo.alert_types import AlertaFactory
from ...repo.resolucion_facturacion import (
    ConsecutivoRangeExhaustedError,
    assign_consecutivo,
    buscar_resolucion_vigente_por_sucursal,
)
from ...schemas.facturacion import (
    EnvioDianRead,
    EnvioDianRetryRead,
    FacturaElectronicaCreate,
    FacturaElectronicaRead,
)

_fe_issuer_dep = requires_issuer("operador-", "admin-")


@router.post(
    "/factura-electronica",
    response_model=FacturaElectronicaRead,
    status_code=201,
    summary=(
        "HU-F1.10 / REQ-OPS-064..067: assign prefijo+consecutivo via "
        "assign_consecutivo (SELECT FOR UPDATE), INSERT prod.factura_electronica "
        "+ initial prod.envio_dian in single await session.commit() (KD-FE-01)."
    ),
    responses={
        403: {"description": "tenant_scope_violation"},
        404: {"description": "factura_no_encontrada (V1)"},
        409: {
            "description": (
                "factura_electronica_ya_existe | resolucion_no_vigente | "
                "numeracion_agotada"
            )
        },
    },
)
async def create_factura_electronica(
    response: Response,
    payload: FacturaElectronicaCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_fe_issuer_dep),
) -> FacturaElectronicaRead:
    """REQ-OPS-064..067: create FE + initial envio row atomically (KD-FE-01).

    Sequence (locked by AST walk, file tests/static/test_fe_handler_single_commit.py):
        1. KD-3 issuer claims + no_store headers (DI)
        2. V1 prod.facturas.uuid exists (404 if None)
        3. tenant scope post-V1 (403 if operador- cross-branch)
        4. V2 NO existing prod.factura_electronica row for uuid_factura (409)
        5. V3 vigente prod.resolucion_facturacion row for the sucursal (409)
        6. KD-FE-01 assign_consecutivo (SELECT FOR UPDATE on resolucion row)
           On ConsecutivoRangeExhaustedError -> 409 numeracion_agotada + alerta
        7. INSERT prod.factura_electronica [L-E] with prefijo snapshot
        8. INSERT initial prod.envio_dian row (estado='pendiente', uuid_envio_padre=NULL)
        9. Mock DIAN POST (real deferred Fase 4; cloud dispatcher reads via sync)
       10. KD-FE-01 single commit (lock release, FE row + envio row atomic)
       11. Response shape FacturaElectronicaRead with envio_actual
       12. DEC-FE-06: Cache-Control: no-store header

    Idempotency-Key: same header (DEC-IDEM-01 reuse from F1.6 + F1.9).
    """
    no_store = no_store_headers()

    # --- Step 2: V1 (prod.facturas.uuid exists). -----------------------
    factura = await repo_factura_electronica.buscar_factura_por_uuid(
        session, uuid_factura=payload.uuid_factura
    )
    if factura is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "factura_no_encontrada",
                "uuid_factura": str(payload.uuid_factura),
            },
            headers=no_store,
        )

    # --- Step 3: tenant scope (post-V1, KD-S2 analog from F1.7). -------
    target_sucursal = factura.uuid_sucursal
    if (
        target_sucursal is not None
        and ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or target_sucursal != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tenant_scope_violation",
                "uuid_factura": str(payload.uuid_factura),
            },
            headers=no_store,
        )

    # --- Step 4: V2 (NO existing prod.factura_electronica row). -------
    existing_fe = await repo_factura_electronica.buscar_factura_electronica_por_factura(
        session, uuid_factura=payload.uuid_factura
    )
    if existing_fe is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "factura_electronica_ya_existe",
                "uuid_factura": str(payload.uuid_factura),
            },
            headers=no_store,
        )

    # --- Step 5: V3 (vigente prod.resolucion_facturacion row). ---------
    if target_sucursal is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "resolucion_no_vigente",
                "uuid_sucursal": "null",
            },
            headers=no_store,
        )
    resolucion = await buscar_resolucion_vigente_por_sucursal(
        session, uuid_sucursal=target_sucursal
    )
    if resolucion is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "resolucion_no_vigente",
                "uuid_sucursal": str(target_sucursal),
            },
            headers=no_store,
        )

    # --- Step 6: KD-FE-01 assign_consecutivo (SELECT FOR UPDATE). ------
    try:
        consecutivo = await assign_consecutivo(
            session,
            resolucion_uuid=resolucion.uuid,
            source_event_uuid=payload.uuid_factura,
        )
    except ConsecutivoRangeExhaustedError as exc:
        # DEC-FE-03: fire alerta + 409 numeracion_agotada
        await AlertaFactory(session, ctx).fire(
            "fe_numbering_exhausted", motivo=str(exc)
        )
        raise HTTPException(
            status_code=409,
            detail={
                "error": "numeracion_agotada",
                "uuid_resolucion_facturacion": str(resolucion.uuid),
                "rango_hasta": resolucion.rango_hasta,
                "prefijo": resolucion.prefijo,
            },
            headers=no_store,
        ) from exc

    # --- Step 7: INSERT prod.factura_electronica [L-E] (snapshot prefijo). ---
    new_fe = await repo_factura_electronica.crear_factura_electronica_inicial(
        session,
        actor_uuid=ctx.actor_uuid,
        uuid_sucursal=target_sucursal,
        uuid_factura=payload.uuid_factura,
        uuid_resolucion_facturacion=resolucion.uuid,
        prefijo=resolucion.prefijo,  # snapshot from V3 (REQ-OPS-074)
        consecutivo=consecutivo,
        # 2026-09-24: mirror the internal factura's real descuento (0
        # for every ordinary rotacion factura; the subscription value
        # for a salida-mensualidad factura) onto the DIAN document.
        descuento=factura.descuento or Decimal(0),
    )

    # --- Step 8: INSERT initial prod.envio_dian row. --------------------
    new_envio = await repo_factura_electronica.crear_envio_dian_inicial(
        session,
        actor_uuid=ctx.actor_uuid,
        uuid_sucursal=target_sucursal,
        uuid_factura_electronica=new_fe.uuid,
        uuid_resolucion_facturacion=resolucion.uuid,
        payload={
            "prefijo": resolucion.prefijo,
            "consecutivo": consecutivo,
            "uuid_factura": str(payload.uuid_factura),
        },
    )

    # --- Step 9: Mock DIAN POST (real deferred Fase 4). ---------------
    # Cloud dispatcher reads via sync (branch_to_cloud direction per
    # MIGRATION 0028 Op 1) and writes transition rows asynchronously.
    # No synchronous DIAN call.

    # --- Step 10: KD-FE-01 single commit (FE row + envio row atomic). -
    await session.commit()  # UN solo commit (lock release, KD-FE-02)

    # --- Step 11: response shape. -------------------------------------
    # --- Step 12: DEC-FE-06 (Cache-Control: no-store header). ---------
    apply_no_store_header(response)
    return FacturaElectronicaRead(
        uuid=new_fe.uuid,
        prefijo=new_fe.prefijo,  # type: ignore[arg-type]
        consecutivo=new_fe.consecutivo,  # type: ignore[arg-type]
        uuid_factura=new_fe.uuid_factura,  # type: ignore[arg-type]
        uuid_resolucion_facturacion=new_fe.uuid_resolucion_facturacion,  # type: ignore[arg-type]
        created_at=new_fe.created_at,  # type: ignore[arg-type]
        envio_actual=EnvioDianRead(
            uuid=new_envio.uuid,
            uuid_factura_electronica=new_fe.uuid,
            estado="pendiente",
            timestamp_evento=new_envio.timestamp_evento,
            uuid_envio_padre=None,
            cufe=None,
            motivo_rechazo=None,
        ),
    )


# ---------------------------------------------------------------------------
# HU-F1.10 / T5 — GET /factura-electronica/{uuid}
#
# 3-step handler. Read-only endpoint that returns the FE row + the LATEST
# envio_dian chain tip via the JOIN to ``prod.v_factura_electronica_acuse``.
# Reuses ``leer_factura_electronica_con_envio_via_view`` (repo
# helper, T2.1). Defense in depth:
#   - KD-3 issuer chain (``operador-,admin-``)
#   - tenant scope (post-V1) — operador cross-branch → 403
#   - Defensive null mapping (REQ-OPS-068 Scenario 2): an FE with zero
#     envio rows still returns 200, with ``envio_actual`` constructed from
#     a synthesized "pendiente" placeholder — NOT a fabricated
#     ``reportado_dian`` boolean (plan.md línea 947 FORBIDDEN).
# ---------------------------------------------------------------------------


@router.get(
    "/factura-electronica/{uuid}",
    response_model=FacturaElectronicaRead,
    status_code=200,
    summary=(
        "HU-F1.10 / REQ-OPS-068: GET FE row + latest envio_dian chain tip "
        "via prod.v_factura_electronica_acuse view."
    ),
    responses={
        403: {"description": "tenant_scope_violation"},
        404: {"description": "factura_electronica_no_encontrada (V1)"},
    },
)
async def get_factura_electronica(
    response: Response,
    uuid: uuid_lib.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_fe_issuer_dep),
) -> FacturaElectronicaRead:
    """REQ-OPS-068: 3-step GET chain.

    Sequence:
        1. KD-3 issuer claims + no_store headers (DI)
        2. V1 SELECT prod.factura_electronica by uuid (404 if None)
        3. Tenant scope post-V1 (403 if operador cross-branch)
        4. JOIN prod.v_factura_electronica_acuse → latest envio_dian
           tip (defensive null mapping when the chain is empty)
        5. Response shape FacturaElectronicaRead with envio_actual
        6. DEC-FE-06: Cache-Control: no-store header
    """
    no_store = no_store_headers()

    # --- Step 2: V1 (FE row exists). -----------------------------------
    fe_row, ack_row = await repo_factura_electronica.leer_factura_electronica_con_envio_via_view(
        session, uuid=uuid
    )
    if fe_row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "factura_electronica_no_encontrada",
                "uuid_factura_electronica": str(uuid),
            },
            headers=no_store,
        )

    # --- Step 3: tenant scope (post-V1, KD-S2 analog from F1.7). -------
    target_sucursal = fe_row.uuid_sucursal
    if (
        target_sucursal is not None
        and ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or target_sucursal != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tenant_scope_violation",
                "uuid_factura_electronica": str(uuid),
            },
            headers=no_store,
        )

    # --- Step 4: defensive null mapping (REQ-OPS-068 Scenario 2). -----
    # The view returns NULL when the FE has zero envio rows (defensive —
    # should not happen because KD-FE-01 always creates the initial envio
    # row in the same TX as the FE row, but the read path must tolerate
    # either case).
    envio_actual: EnvioDianRead
    if ack_row is None:
        envio_actual = EnvioDianRead(
            uuid=uuid_lib.uuid4(),  # defensive placeholder; not persisted
            uuid_factura_electronica=fe_row.uuid,  # type: ignore[arg-type]
            estado="pendiente",
            timestamp_evento=fe_row.created_at,  # type: ignore[arg-type]
            uuid_envio_padre=None,
            cufe=None,
            motivo_rechazo=None,
        )
    else:
        envio_actual = EnvioDianRead(
            uuid=ack_row["uuid"],
            uuid_factura_electronica=fe_row.uuid,  # type: ignore[arg-type]
            estado=ack_row["estado"],
            timestamp_evento=ack_row["timestamp_evento"],
            uuid_envio_padre=None,  # chain tip is the row itself; no parent
            cufe=ack_row.get("cufe"),
            motivo_rechazo=ack_row.get("motivo_rechazo"),
        )

    # --- Step 5: response shape. ---------------------------------------
    apply_no_store_header(response)
    return FacturaElectronicaRead(
        uuid=fe_row.uuid,  # type: ignore[arg-type]
        prefijo=fe_row.prefijo,  # type: ignore[arg-type]
        consecutivo=fe_row.consecutivo,  # type: ignore[arg-type]
        uuid_factura=fe_row.uuid_factura,  # type: ignore[arg-type]
        uuid_resolucion_facturacion=fe_row.uuid_resolucion_facturacion,  # type: ignore[arg-type]
        created_at=fe_row.created_at,  # type: ignore[arg-type]
        envio_actual=envio_actual,
    )


# ---------------------------------------------------------------------------
# HU-F1.10 / T6 — POST /factura-electronica/{uuid}/reintentar
#
# 8-step handler. Creates a NEW envio_dian retry row (NEVER UPDATE on the
# existing chain). The chain IS the audit trail — DEC-FE-02 + DEC-FE-07.
#
# Defense in depth:
#   - KD-3 issuer chain (``operador-,admin-``)
#   - tenant scope (post-V1)
#   - V2 chain-tip state machine (4 valid states):
#       aceptado  → 409 reintento_no_permitido (DEC-FE-04)
#       pendiente → 409 envio_dian_already_pending (rapid-retry guard)
#       rechazado → proceed (insert NEW retry row)
#       enviado   → proceed (DIAN timed out; insert NEW retry row)
#   - KD-FE-01 single commit (same as POST /factura-electronica).
# ---------------------------------------------------------------------------


@router.post(
    "/factura-electronica/{uuid}/reintentar",
    response_model=EnvioDianRetryRead,
    status_code=201,
    summary=(
        "HU-F1.10 / REQ-OPS-069..070: insert NEW envio_dian retry row "
        "with uuid_envio_padre=<chain_tip.uuid> (DEC-FE-02 + DEC-FE-07). "
        "NEVER UPDATE on existing envio rows."
    ),
    responses={
        403: {"description": "tenant_scope_violation"},
        404: {"description": "factura_electronica_no_encontrada (V1)"},
        409: {
            "description": (
                "reintento_no_permitido | envio_dian_already_pending"
            )
        },
    },
)
async def retry_envio_dian(
    response: Response,
    uuid: uuid_lib.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_fe_issuer_dep),
) -> EnvioDianRetryRead:
    """REQ-OPS-069..070: 8-step retry chain.

    Sequence (locked by AST walk, file tests/static/test_retry_no_update.py):
        1. KD-3 issuer claims + no_store headers (DI)
        2. V1 SELECT prod.factura_electronica by uuid (404 if None)
        3. Tenant scope post-V1 (403 if operador cross-branch)
        4. V2 chain-tip lookup (buscar_envio_dian_chain_tip)
        5. V2 state-machine validation:
           - aceptado  → 409 reintento_no_permitido
           - pendiente → 409 envio_dian_already_pending
           - rechazado → proceed
           - enviado   → proceed (DIAN timed out; retry)
           - None      → proceed (defensive; empty chain)
        6. KD-FE-01 INSERT NEW prod.envio_dian retry row
           (uuid_envio_padre=<tip.uuid>, estado='pendiente')
        7. KD-FE-01 single commit (atomic)
        8. DEC-FE-06: Cache-Control: no-store header + response shape
    """
    no_store = no_store_headers()

    # --- Step 2: V1 (FE row exists). -----------------------------------
    fe_row = await repo_factura_electronica.buscar_factura_electronica_por_uuid(
        session, uuid=uuid
    )
    if fe_row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "factura_electronica_no_encontrada",
                "uuid_factura_electronica": str(uuid),
            },
            headers=no_store,
        )

    # --- Step 3: tenant scope (post-V1). -------------------------------
    target_sucursal = fe_row.uuid_sucursal
    if (
        target_sucursal is not None
        and ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or target_sucursal != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tenant_scope_violation",
                "uuid_factura_electronica": str(uuid),
            },
            headers=no_store,
        )

    # --- Step 4: V2 chain-tip lookup. ----------------------------------
    chain_tip = await repo_factura_electronica.buscar_envio_dian_chain_tip(
        session, uuid_factura_electronica=fe_row.uuid  # type: ignore[arg-type]
    )

    # --- Step 5: V2 state-machine validation. -------------------------
    if chain_tip is not None:
        tip_estado = chain_tip.estado
        if tip_estado == "aceptado":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "reintento_no_permitido",
                    "uuid_factura_electronica": str(uuid),
                    "estado_actual": tip_estado,
                },
                headers=no_store,
            )
        if tip_estado == "pendiente":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "envio_dian_already_pending",
                    "uuid_factura_electronica": str(uuid),
                    "uuid_envio_pendiente": str(chain_tip.uuid),
                },
                headers=no_store,
            )
        # tip_estado in ('rechazado', 'enviado', None) → proceed
        uuid_envio_padre = chain_tip.uuid
    else:
        # Defensive: empty chain (shouldn't happen post-KD-FE-01). Allow
        # retry by creating an orphan row with uuid_envio_padre=None.
        uuid_envio_padre = None  # type: ignore[assignment]

    # --- Step 6: INSERT NEW envio_dian retry row (DEC-FE-02). --------
    new_envio = await repo_factura_electronica.crear_envio_dian_reintento(
        session,
        actor_uuid=ctx.actor_uuid,
        uuid_sucursal=target_sucursal,
        uuid_factura_electronica=fe_row.uuid,  # type: ignore[arg-type]
        uuid_resolucion_facturacion=fe_row.uuid_resolucion_facturacion,  # type: ignore[arg-type]
        payload={
            "prefijo": fe_row.prefijo,
            "consecutivo": fe_row.consecutivo,
            "uuid_factura_electronica": str(fe_row.uuid),
            "trigger": "manual_retry",
        },
        uuid_envio_padre=uuid_envio_padre,  # type: ignore[arg-type]
    )

    # --- Step 7: KD-FE-01 single commit. ------------------------------
    await session.commit()

    # --- Step 8: response shape. ---------------------------------------
    apply_no_store_header(response)
    return EnvioDianRetryRead(
        uuid=new_envio.uuid,
        uuid_factura_electronica=fe_row.uuid,  # type: ignore[arg-type]
        estado="pendiente",
        timestamp_evento=new_envio.timestamp_evento,  # type: ignore[arg-type]
        uuid_envio_padre=uuid_envio_padre,  # type: ignore[arg-type]
    )


__all__ = ["router"]
