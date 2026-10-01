"""Admin audit-log HTTP route (IT-12 of
``openspec/_meta/iteration-plan.md``).

Single endpoint:

- ``GET /api/v1/admin/audit/log`` -- cursor-paginated audit-log feed
  for one branch (admin-only). Reads from ``prod.log_transaccional``
  ordered ``(timestamp_evento DESC, uuid ASC)``.

Cloud-only mount: imported on ``api_admin`` only (per
``api/v1/__init__.py``'s DIAN boundary + ``pairing`` + ``admin_usuarios``
+ ``admin_views`` belt-and-suspenders). ``api_sucursal`` does NOT
mount this router -- the audit log is for cross-branch visibility,
which an operador cannot have (REQ-X2).

Issuer + permission gate:

- ``admin-`` issuer (KD-3): ``operador-`` and ``sync-agent-`` tokens
  get 401.
- ``audit_read`` permission (KD-AUDIT-01 + DEC-AUDIT-02): the
  permission code is ``audit_read`` (``permisos`` row seeded by
  migration 0002). The dep raises 403 if the admin token lacks
  this grant. The seed operator (``admin@parkos.local``) carries
  the grant per migration 0053/0054 (PR9 admin permissions seed).

Why a CURSOR here (not just LIMIT/OFFSET): the table is partitioned
by ``fecha_retencion_hasta`` (DIAN retention, monthly buckets) and
contains 100K+ rows per branch over a 5+ year retention. OFFSET-based
pagination is O(N) on the rows it skips; cursor-based is O(page_size).
The dashboard renders the first 20 rows on every poll, so OFFSET
would scan 99,980 rows on the second page -- a hot path that adds
unbounded latency. The F1.15 cursor contract already covers this
exact case.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_session, requires_issuer
from ...auth.permissions import require_permission
from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...repo import log_transaccional as repo_audit
from ...schemas.log_transaccional import (
    AuditLogItem,
    AuditLogListResponse,
    AuditLogQueryParams,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/audit", tags=["admin"])

_admin_issuer_dep = requires_issuer("admin-")
_audit_perm_dep = require_permission("audit_read")


@router.get(
    "/log",
    response_model=AuditLogListResponse,
    summary="Cursor-paginated audit log for one branch (admin-only, IT-12).",
)
async def list_audit_log(
    response: Response,
    params: AuditLogQueryParams = Depends(),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_admin_issuer_dep),
    _audit: None = Depends(_audit_perm_dep),
) -> AuditLogListResponse:
    """``GET /api/v1/admin/audit/log`` -- 7-step read chain.

    Step chain (mirrors the F1.15 T4.2 8-step chain, simplified):

      1. Layer 1 issuer dep + permission gate. The dep already
         enforced KD-3 + audit_read. ``ctx`` carries the resolved
         claims; the permission dep raised 403 if the admin lacks it.
      2. Layer 2 tenant scope (KD-S2 F1.7 analog) -- ``operador-``
         tokens see only their own branch; ``admin-`` bypasses. The
         filter is enforced by the SELECT (Step 4) on
         ``uuid_sucursal``. ``admin-`` callers also get a 200 with the
         branch's full log -- this is the cross-branch visibility an
         operador cannot have (REQ-X2).
      3. Layer 4 Pydantic validation (FastAPI Depends): ``uuid_sucursal``
         required, ``limit`` 1..100, ``cursor`` optional. Malformed
         values get 422 before the handler body runs.
      4. KD-MOT-AUDIT-01: READ-ONLY via 1 typed helper
         :func:`repo.log_transaccional.listar_eventos_paginados`.
         NO UPDATE/DELETE/INSERT, NO ``await session.commit()``.
      5. Build ``next_cursor`` via
         :func:`repo.log_transaccional.encode_audit_cursor` -- returns
         ``None`` at EOF.
      6. Layer 5 (XR6 mirror from F1.10/F1.11/F1.12/F1.13/F1.14/F1.15):
         ``Cache-Control: no-store`` on success AND error (an audit
         dashboard that serves stale rows would be worse than no
         dashboard).
      7. Build ``{items, next_cursor}`` envelope.

    Empty branch contract: zero rows for a branch returns
    ``items=[]`` + ``next_cursor=None`` with HTTP 200 (NEVER 404 --
    the branch UUID is a valid input, just an empty result).

    Cursor validation: ``decode_audit_cursor`` raises
    :class:`InvalidAuditCursorError` on malformed base64/JSON/missing
    keys; this handler maps that to HTTP 400 (Layer 4 violation).
    """
    # --- Step 4 (KD-MOT-AUDIT-01): SELECT via 1 typed helper ---
    # NO UPDATE/DELETE/INSERT in this body (AST walk enforces).
    # NO await session.commit() -- GET is naturally idempotent.
    try:
        cursor = repo_audit.decode_audit_cursor(params.cursor)
    except repo_audit.InvalidAuditCursorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_cursor",
                "detail": str(exc),
            },
        ) from exc

    # KD-MOT-2025-10-01 (HU-F15.2): the schema validator rejects the
    # no-selector case, but FastAPI's Depends() does NOT translate the
    # raw ``pydantic_core.ValidationError`` raised by ``model_validator``
    # into a 422 -- the validator's ``ValueError`` propagates as a 500.
    # We re-check here and raise a typed 422 explicitly so the FE sees
    # the same shape as the rest of the Layer-4 violations.
    if params.uuid_sucursal is None and not params.tabla_afectada:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "missing_selector",
                "detail": (
                    "audit_log requires at least one of uuid_sucursal "
                    "or tabla_afectada -- the table is partitioned by "
                    "fecha_retencion_hasta, not by branch, so a missing "
                    "selector would scan the whole partition range."
                ),
            },
        )

    # KD-MOT-2025-10-01 (HU-F15.2): ``tabla_afectada`` filter is now wired
    # alongside the branch selector. Both compose with AND.
    rows = await repo_audit.listar_eventos_paginados(
        session,
        uuid_sucursal=params.uuid_sucursal,
        tabla_afectada=params.tabla_afectada,
        cursor=cursor,
        limit=params.limit,
    )

    # --- Step 5: build next_cursor (pure math) ---
    next_cursor = repo_audit.encode_audit_cursor(rows, params.limit)

    # --- Step 6 (Layer 5): no-store header on success ---
    from . import _helpers

    _helpers.apply_no_store_header(response)

    # --- Step 7: build {items, next_cursor} envelope ---
    items = [
        AuditLogItem(
            uuid=row.uuid,
            # ``timestamp_evento`` is nullable in the ORM contract but
            # always stamped by ``append_only.append_event`` per the
            # [A] audit invariant. The cast bridges SQL-level typing
            # to the Pydantic-validated non-null contract at the wire.
            timestamp_evento=cast(datetime, row.timestamp_evento),
            uuid_usuario=row.uuid_usuario,
            uuid_sucursal=row.uuid_sucursal,
            uuid_referencia=row.uuid_referencia,
            accion=row.accion,
            tabla_afectada=row.tabla_afectada,
            datos_anteriores=row.datos_anteriores,
            datos_nuevos=row.datos_nuevos,
            hash_anterior=row.hash_anterior,
            hash_actual=row.hash_actual,
        )
        for row in rows[: params.limit]
    ]
    return AuditLogListResponse(items=items, next_cursor=next_cursor)


__all__ = ["router"]
