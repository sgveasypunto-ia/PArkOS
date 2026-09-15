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
    FacturaItemRead,
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

    Sequence (D-HU-F1.9-11 12-step chain, locked by AST walk):
        1. KD-3 issuer claims + no_store headers
        2. V1 salida existe y es facturable (404 if None)
        3. tenant scope post-V1 (403 if cajero cross-branch)
        4. V2 cliente existe cuando fe_con_datos=true (404 if None)
        5. V3 IVA configurado (500 iva_no_configurado if False)
        6. V4 detalle items coherentes (422 detalle_invalido if empty)
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
    cliente_uuid: uuid_lib.UUID | None = None
    if payload.fe_con_datos:
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
    new_factura = await repo_factura.crear_factura_evento(
        session,
        actor_uuid=ctx.actor_uuid,
        new_attrs={
            "uuid_sucursal": target_sucursal,
            "uuid_ingreso": salida.uuid_ingreso,
            "uuid_salida": salida.uuid,
            "subtotal": payload.subtotal,
            "descuento": Decimal(0),
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
    return FacturaRead(
        uuid=new_factura.uuid,
        created_at=new_factura.created_at,
        uuid_sucursal=new_factura.uuid_sucursal,
        uuid_ingreso=new_factura.uuid_ingreso,
        uuid_salida=new_factura.uuid_salida,
        subtotal=new_factura.subtotal,
        descuento=new_factura.descuento,
        total=new_factura.total,
        uuid_cliente=cliente_uuid,  # DEC-FACT-06 derivado, no persistido
        items=[
            FacturaItemRead(
                uuid=item.uuid,
                tipo=item.tipo,
                concepto=item.concepto,
                cantidad=item.cantidad,
                valor_unitario=item.valor_unitario,
                subtotal=item.subtotal,
            )
            for item in detalles_creados
        ],
        estado="emitida",  # derived (always "emitida" at create time)
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


__all__ = ["router"]
