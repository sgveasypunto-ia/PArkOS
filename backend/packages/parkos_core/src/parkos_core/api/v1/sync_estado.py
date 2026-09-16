"""HU-F1.14 / REQ-OPS-098..101 + REQ-OPS-XR6 -- ``GET /api/v1/sync/estado``.

Dedicated ``APIRouter`` mounted via ``router.include_router`` from
``api/v1/caja.py`` (DEC-SYNC-02, F1.13 mount precedent at ``caja.py:86``).
Single read-only handler:

* ``get_sync_estado`` -- 4-step chain on
  ``GET /api/v1/sync/estado?uuid_sucursal=X``. KD-SYNC-01 SELECT-only
  + KD-SYNC-02 read-only AST walk invariant.

Defense in depth (REQ-OPS-XR6 cross-cutting):

  * Layer 1: KD-3 issuer chain ``requires_issuer("operador-", "admin-")``
    + permission gate ``audit_read`` (DEC-SYNC-03.B, pre-seeded at
    ``0002_seed_permisos_canonicos.py:48``).
  * Layer 2: tenant scope post-V1 (KD-S2 F1.7 analog).
  * Layer 3: KD-SYNC-01 SELECT-only + KD-SYNC-02 read-only AST walk.
  * Layer 4: Pydantic ``extra='forbid'`` (``SyncEstadoQueryParams`` +
    ``SyncEstadoRead`` inherit from ``_Base``).
  * Layer 5: handler 200/422/403 mapping + ``Cache-Control: no-store``
    on every response (DEC-SYNC-04).

KD-SYNC-01 SELECT-only invariant (AST walk enforced): the handler
executes exactly 2 SELECT queries (one against ``prod.sync_log`` via
:func:`repo.sync_estado.get_ultima_sync_at`, one against
``prod.sync_queue`` via
:func:`repo.sync_estado.count_pendientes_sync_queue`). NO UPDATE/DELETE
on either [A] table. NO ``await session.commit()``. The handler is
purely read-only -- ``prod.log_operaciones`` is never written.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...db.engine import get_session
from ...repo import sync_estado as repo_sync_estado
from ...schemas.sync_infra import SyncEstadoQueryParams, SyncEstadoRead
from ..deps import requires_issuer
from . import _helpers

# Dedicated router -- mounted via ``router.include_router`` from
# ``api/v1/caja.py`` (DEC-SYNC-02). NOT via the ``make_router`` factory
# because the read endpoint has a typed response + a permission gate
# (``audit_read``) that the factory cannot model.
router = APIRouter(prefix="/sync", tags=["sync"])

# KD-3 issuer chain + ``audit_read`` permission gate (DEC-SYNC-01 +
# DEC-SYNC-03.B). Single dep reused for the GET handler.
_sync_estado_issuer_dep = requires_issuer("operador-", "admin-")


@router.get(
    "/estado",
    response_model=SyncEstadoRead,
    status_code=200,
)
async def get_sync_estado(
    response: Response,
    params: SyncEstadoQueryParams = Depends(),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_sync_estado_issuer_dep),
) -> SyncEstadoRead:
    """``GET /api/v1/sync/estado`` -- 4-step read chain.

    Step chain:
        1. Layer 1 issuer dep + permission gate ``audit_read`` (DI-resolved).
        2. Layer 2 tenant scope post-V1 (KD-S2 analog from F1.7):
           ``operador-`` cross-branch rejected with 403
           ``tenant_scope_violation`` + ``Cache-Control: no-store``.
        3. KD-SYNC-01 SELECT-only via 3 typed helpers from
           :mod:`repo.sync_estado` (no writes, no commit).
        4. Build ``SyncEstadoRead`` + apply no-store header.

    KD-SYNC-01: the handler body MUST NOT contain UPDATE/DELETE on
    ``prod.sync_log`` or ``prod.sync_queue``; the AST walk
    ``tests/static/test_sync_estado_read_only.py`` enforces this.
    """
    no_store = _helpers.no_store_headers()

    # --- Step 2 (Layer 2): tenant scope post-V1 (KD-S2 F1.7 analog) ---
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

    # --- Step 3a (KD-SYNC-01): SELECT MAX(timestamp_evento) FROM prod.sync_log ---
    ultima_sync_at = await repo_sync_estado.get_ultima_sync_at(
        session, uuid_sucursal=params.uuid_sucursal
    )

    # --- Step 3b: in-process lag compute (None when no rows, DEC-SYNC-08) ---
    now = datetime.now(UTC).replace(tzinfo=None)
    lag_seg = repo_sync_estado.calcular_lag_seg(ultima_sync_at, now)

    # --- Step 3c (KD-SYNC-01): SELECT count(*) FROM prod.sync_queue ---
    pendientes = await repo_sync_estado.count_pendientes_sync_queue(
        session, uuid_sucursal=params.uuid_sucursal
    )

    # --- Step 4 (Layer 4 + Layer 5): build SyncEstadoRead + no-store header ---
    _helpers.apply_no_store_header(response)
    return SyncEstadoRead(
        uuid_sucursal=params.uuid_sucursal,
        ultima_sync_at=ultima_sync_at,
        lag_seg=lag_seg,
        pendientes=pendientes,
    )


__all__ = ["router"]
