"""Admin bitácora HTTP routes (HU-F20.4).

Three endpoints, all read-only (KD-MOT-AUDIT-01: ``log_transaccional`` is
[A] / append-only -- every handler here does exactly ONE SELECT-shaped
repo call, NO INSERT/UPDATE/DELETE, NO ``await session.commit()``):

- ``GET /api/v1/admin/log-transaccional`` -- cross-branch, cursor-paginated
  bitácora listing with 5 additional filters over IT-12's single-branch
  ``GET /admin/audit/log`` (table, affected-record uuid, acting-user uuid,
  date range).
- ``GET /api/v1/admin/log-transaccional/verify-chain`` -- on-demand SHA-256
  hash-chain verification sweep (``sync.motor.verify_chain``) over one or
  every permitted branch.
- ``GET /api/v1/admin/log-transaccional/buscar`` -- bounded (<=10 results)
  typeahead search over ``tabla_afectada`` / ``uuid_registro_afectado``.

Deliberately a SEPARATE router/module from ``api/v1/audit.py`` (IT-12):
that file is the single/ambient-tenant audit-log dashboard (``get_tenant_ctx``
+ ``BranchScope``) and stays untouched -- these 3 endpoints are the
cross-branch admin surface (``extract_sucursales_permitidas_fresh``, same
pattern as ``admin_views.py``'s HU-F19.1 ``GET /admin/sync/log`` /
``GET /admin/sync/conflict``), which is a DIFFERENT authorization model
built on the SAME underlying table.

Cloud-only mount (REQ-X2, same reasoning as ``audit.py``/``admin_views.py``):
registered in ``api/v1/__init__.py``'s non-branch ``else:`` block.

Auth: ``admin-`` issuer (KD-3) + the existing ``audit_read`` permission
(KD-AUDIT-01 / DEC-AUDIT-02) -- same underlying resource as IT-12, so the
same permission code gates both surfaces.
"""
from __future__ import annotations

import logging
import uuid as uuid_lib
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_session, requires_issuer
from ...auth.permissions import require_permission
from ...db.tenancy import extract_sucursales_permitidas_fresh
from ...repo import log_transaccional as repo_audit
from ...schemas.log_transaccional import (
    AuditLogItem,
    AuditLogListResponse,
    BuscarPrefijoItem,
    BuscarPrefijoResponse,
    ChainAnomalyItem,
    LogTransaccionalListQueryParams,
    VerifyChainResponse,
)
from ...sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME, resolve_catalog_name
from ...sync.motor.verify_chain import ChainAnomaly, verify_chain_for_spec

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/log-transaccional", tags=["admin"])

_admin_issuer_dep = requires_issuer("admin-")
_audit_perm_dep = require_permission("audit_read")


def _resolve_actor_uuid(claims: dict[str, Any]) -> uuid_lib.UUID:
    """``claims['sub']`` -> uuid (mirrors ``admin_views.sync_log_list``)."""
    return uuid_lib.UUID(claims["sub"])


async def _resolve_permitidas_or_400(
    session: AsyncSession, *, actor_uuid: uuid_lib.UUID
) -> list[uuid_lib.UUID]:
    """Fresh permitted-branch list, fail-closed on empty (400).

    Mirrors ``admin_views.sync_log_list``: an admin with NO currently-open
    ``usuarios_sucursal`` row has nothing to scope a cross-branch query to.
    Returning an empty-but-200 result here would be silently
    indistinguishable from "this admin's permitted branches genuinely have
    zero matching rows" -- the explicit 400 makes the "you have no
    permitted branches at all" case visible instead of looking like a
    quiet empty page.
    """
    permitidas = await extract_sucursales_permitidas_fresh(session, actor_uuid=actor_uuid)
    if not permitidas:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "missing_sucursal_context"},
        )
    return permitidas


def _resolve_target_branches(
    *,
    uuid_sucursal: uuid_lib.UUID | None,
    permitidas: list[uuid_lib.UUID],
) -> list[uuid_lib.UUID]:
    """Narrow to one branch (membership-checked) or keep every permitted one."""
    if uuid_sucursal is not None:
        if uuid_sucursal not in permitidas:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "unauthorized_sucursal_context"},
            )
        return [uuid_sucursal]
    return list(permitidas)


@router.get(
    "",
    response_model=AuditLogListResponse,
    summary="Cross-branch bitácora listing, cursor-paginated (HU-F20.4).",
)
async def list_log_transaccional(
    response: Response,
    params: LogTransaccionalListQueryParams = Depends(),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    claims: dict[str, Any] = Depends(_admin_issuer_dep),  # noqa: B008
    _audit: None = Depends(_audit_perm_dep),
) -> AuditLogListResponse:
    """``GET /admin/log-transaccional`` -- cross-branch bitácora read.

    Step chain (mirrors ``admin_views.sync_log_list``'s exact wiring):

      1. ``admin-`` issuer + ``audit_read`` permission gate (Layer 1).
      2. Resolve ``permitidas`` fresh (``extract_sucursales_permitidas_fresh``,
         NEVER ``get_tenant_ctx``/``BranchScope`` -- this is the cross-branch
         admin pattern, not IT-12's ambient single-tenant one). Empty ->
         400 ``missing_sucursal_context``.
      3. ``uuid_sucursal`` narrows to one branch (403
         ``unauthorized_sucursal_context`` if not permitted); omitted, every
         permitted branch is scoped in via ``uuid_sucursales=permitidas``.
      4. 422 ``rango_fecha_invalido`` when both ``desde``/``hasta`` are given
         and ``desde > hasta`` (same shape as ``admin_views.py`` /
         ``reporteria.py`` / ``workflows_alerta.py``).
      5. KD-MOT-AUDIT-01: READ-ONLY via the extended
         :func:`repo.log_transaccional.listar_eventos_paginados`.
      6. ``Cache-Control: no-store`` (Layer 5, same as IT-12).
    """
    actor_uuid = _resolve_actor_uuid(claims)
    permitidas = await _resolve_permitidas_or_400(session, actor_uuid=actor_uuid)
    target = _resolve_target_branches(uuid_sucursal=params.uuid_sucursal, permitidas=permitidas)

    if params.desde is not None and params.hasta is not None and params.desde > params.hasta:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "rango_fecha_invalido"},
        )

    try:
        cursor = repo_audit.decode_audit_cursor(params.cursor)
    except repo_audit.InvalidAuditCursorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_cursor", "detail": str(exc)},
        ) from exc

    rows = await repo_audit.listar_eventos_paginados(
        session,
        uuid_sucursal=None,
        uuid_sucursales=target,
        tabla_afectada=params.tabla,
        uuid_registro_afectado=params.uuid_registro,
        uuid_usuario=params.uuid_usuario,
        desde=params.desde,
        hasta=params.hasta,
        cursor=cursor,
        limit=params.limit,
    )

    next_cursor = repo_audit.encode_audit_cursor(rows, params.limit)
    from . import _helpers

    _helpers.apply_no_store_header(response)

    items = [
        AuditLogItem(
            uuid=row.uuid,
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


@router.get(
    "/verify-chain",
    response_model=VerifyChainResponse,
    summary="On-demand SHA-256 hash-chain verification sweep (HU-F20.4).",
)
async def verify_chain_endpoint(
    response: Response,
    tabla: str = Query(
        default="log_transaccional",
        description="Chain-bearing catalog table name (resolved via SYNC_CATALOG_BY_NAME).",
    ),
    uuid_sucursal: uuid_lib.UUID | None = Query(  # noqa: B008
        default=None,
        description="Single branch to verify. Omitted: sweep every permitted branch.",
    ),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    claims: dict[str, Any] = Depends(_admin_issuer_dep),  # noqa: B008
    _audit: None = Depends(_audit_perm_dep),
) -> VerifyChainResponse:
    """``GET /admin/log-transaccional/verify-chain`` -- chain integrity sweep.

    ``tabla`` is resolved to a :class:`SyncCatalogEntry` via
    ``resolve_catalog_name`` (strips a pg_partman child-partition suffix,
    defensive -- ``log_transaccional``/``revocacion_factura`` are two of
    the 8 partitioned parents) + ``SYNC_CATALOG_BY_NAME``. Unknown table OR
    a catalog entry with ``verify_chain is not True`` -> 422
    ``tabla_no_verificable`` (consistent with this repo's
    ``{"error": <code>, "detail": ...}`` HTTPException-detail convention).

    Cross-branch semantics (deliberate design decision, REQ-CAT-009):

      - ``uuid_sucursal`` given: validated against ``permitidas`` (403
        ``unauthorized_sucursal_context`` otherwise), then
        :func:`verify_chain_for_spec` is called ONCE for that branch.
      - ``uuid_sucursal`` omitted: :func:`verify_chain_for_spec` is called
        ONCE PER permitted branch and the anomaly lists are concatenated.
        Calling it with ``uuid_sucursal=None`` instead would ONLY check the
        near-always-empty GLOBAL ``uuid_sucursal IS NULL`` partition (see
        that function's own docstring) -- not "every branch" -- so that is
        never done here as the "no branch given" default.
    """
    actor_uuid = _resolve_actor_uuid(claims)
    permitidas = await _resolve_permitidas_or_400(session, actor_uuid=actor_uuid)

    resolved_name = resolve_catalog_name(tabla)
    entry = SYNC_CATALOG_BY_NAME.get(resolved_name)
    if entry is None or not entry.verify_chain:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "tabla_no_verificable", "detail": tabla},
        )

    # One target branch (membership-checked) or every permitted branch --
    # either way, one verify_chain_for_spec call per branch in ``target``.
    target = _resolve_target_branches(uuid_sucursal=uuid_sucursal, permitidas=permitidas)
    anomalias: list[ChainAnomaly] = []
    for branch_uuid in target:
        anomalias.extend(await verify_chain_for_spec(session, entry, uuid_sucursal=branch_uuid))

    from . import _helpers

    _helpers.apply_no_store_header(response)
    return VerifyChainResponse(
        ok=len(anomalias) == 0,
        anomalias=[
            ChainAnomalyItem(
                tabla=a.tabla,
                uuid_sucursal=a.uuid_sucursal,
                uuid=a.uuid,
                expected=a.expected,
                actual=a.actual,
                seq=a.seq,
                reason=a.reason,
            )
            for a in anomalias
        ],
    )


@router.get(
    "/buscar",
    response_model=BuscarPrefijoResponse,
    summary="Bounded bitácora typeahead search (HU-F20.4, max 10 results).",
)
async def buscar_log_transaccional(
    response: Response,
    prefijo: str = Query(
        ..., min_length=1, description="Prefix to match (ILIKE 'prefijo%')."
    ),
    limit: int = Query(default=10, ge=1, le=10),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    claims: dict[str, Any] = Depends(_admin_issuer_dep),  # noqa: B008
    _audit: None = Depends(_audit_perm_dep),
) -> BuscarPrefijoResponse:
    """``GET /admin/log-transaccional/buscar`` -- typeahead, no cursor.

    Scoped to every branch the admin is permitted to see
    (``extract_sucursales_permitidas_fresh``) -- a typeahead must not leak
    another tenant's ``tabla_afectada``/``uuid_registro_afectado``
    combinations. ``limit`` is capped at 10 (``le=10``, literal spec:
    "límite 10 resultados").
    """
    actor_uuid = _resolve_actor_uuid(claims)
    permitidas = await _resolve_permitidas_or_400(session, actor_uuid=actor_uuid)

    rows = await repo_audit.buscar_prefijo(
        session,
        prefijo=prefijo,
        uuid_sucursales=permitidas,
        limit=limit,
    )

    from . import _helpers

    _helpers.apply_no_store_header(response)
    return BuscarPrefijoResponse(
        items=[
            BuscarPrefijoItem(
                uuid=row.uuid,
                tabla_afectada=row.tabla_afectada,
                uuid_registro_afectado=row.uuid_registro_afectado,
                uuid_sucursal=row.uuid_sucursal,
                timestamp_evento=cast(datetime, row.timestamp_evento),
            )
            for row in rows
        ]
    )


__all__ = ["router"]
