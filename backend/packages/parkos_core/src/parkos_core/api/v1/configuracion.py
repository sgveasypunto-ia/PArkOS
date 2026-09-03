"""Configuracion HTTP routes (PR4 per-branch config override).

REQ-OP-12 + SC-OP-06 (per-branch override OR global default). The
``/configuracion-seguridad/efectiva`` endpoint resolves the effective value
for a given branch — per-branch row wins; falls back to global default
(``uuid_sucursal IS NULL``).

NO DELETE endpoint — defense in depth (design §3, AGENTS.md §3).
"""
from __future__ import annotations

import uuid as uuid_lib

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.tenancy import TenantContext
from ...db.engine import get_session
from ...models.V.configuracion_seguridad import ConfiguracionSeguridad
from ...models.V.configuracion_tolerancias import ConfiguracionTolerancias
from ...repo.config_override import resolve_efectiva_seguridad
from ...schemas.configuracion import (
    ConfiguracionSeguridadCreate,
    ConfiguracionSeguridadRead,
    ConfiguracionSeguridadReadList,
    ConfiguracionSeguridadUpdate,
    ConfiguracionToleranciasCreate,
    ConfiguracionToleranciasRead,
    ConfiguracionToleranciasReadList,
    ConfiguracionToleranciasUpdate,
)
from ..deps import get_tenant_ctx
from ..router_factory import make_router

router = APIRouter(prefix="/configuracion", tags=["configuracion"])

# Issuer-permission defaults per resource (see T-PR4-04 table).
_ROUTER_CONFIG = {
    "configuracion-tolerancias": ("admin-,operador-", "config_tolerancias"),
    "configuracion-seguridad": ("admin-,operador-", "config_seguridad"),
}


def _mount_config(
    *,
    resource: str,
    model_cls: type,
    read_schema: type,
    read_list_schema: type,
    create_schema: type,
    update_schema: type,
) -> None:
    """Mount one configuracion C+Q+U router under ``/configuracion/{resource}``."""
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
        )
    )


_mount_config(
    resource="configuracion-tolerancias",
    model_cls=ConfiguracionTolerancias,
    read_schema=ConfiguracionToleranciasRead,
    read_list_schema=ConfiguracionToleranciasReadList,
    create_schema=ConfiguracionToleranciasCreate,
    update_schema=ConfiguracionToleranciasUpdate,
)
_mount_config(
    resource="configuracion-seguridad",
    model_cls=ConfiguracionSeguridad,
    read_schema=ConfiguracionSeguridadRead,
    read_list_schema=ConfiguracionSeguridadReadList,
    create_schema=ConfiguracionSeguridadCreate,
    update_schema=ConfiguracionSeguridadUpdate,
)


# --- Custom: GET /configuracion/configuracion-seguridad/efectiva ------------
# Resolves per-branch override OR global default (REQ-OP-12, SC-OP-06).
#
# Query: per-branch first; if None, global (uuid_sucursal IS NULL).
# Returns 404 if neither exists.

from ...api.deps import requires_issuer

_efectiva_issuer_dep = requires_issuer("admin-", "operador-")


@router.get(
    "/configuracion-seguridad/efectiva",
    response_model=ConfiguracionSeguridadRead,
    summary="Effective seguridad config for a branch (per-branch override OR global default)",
)
async def efectiva(
    uuid_sucursal: uuid_lib.UUID = Query(...),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_efectiva_issuer_dep),
) -> ConfiguracionSeguridadRead:
    """Resolve the effective ``configuracion_seguridad`` for ``uuid_sucursal``.

    Priority: per-branch row (uuid_sucursal = :requested, vigente_hasta IS NULL)
    → global default (uuid_sucursal IS NULL, vigente_hasta IS NULL)
    → 404 if neither.
    """
    row = await resolve_efectiva_seguridad(session, uuid_sucursal)

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "resource": "configuracion-seguridad",
                "uuid_sucursal": str(uuid_sucursal),
            },
        )

    return ConfiguracionSeguridadRead.model_validate(row)


__all__ = ["router"]