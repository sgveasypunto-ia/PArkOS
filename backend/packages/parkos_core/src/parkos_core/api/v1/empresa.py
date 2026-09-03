"""Empresa + Sucursal + per-branch config HTTP routes (PR4).

REQ-OP-05 (1MB cap on documentos.b64), REQ-OP-12 (config override), REQ-X3
(DIAN boundary on resolucion_facturacion). All routers are bi-temporal
``repo_kind="versioned"`` (close+insert writes via ``repo.versioned.close_and_insert``).

NO DELETE endpoint — defense in depth (design §3, AGENTS.md §3).

T-PR4-11 extends this module with ``_SUB_ROUTERS``: a dict that maps each
resource slug to its APIRouter. The v1 package (``api/v1/__init__.py``) reads
``_SUB_ROUTERS`` and applies the DIAN boundary (REQ-X3) at router-aggregation
time — branch deploy skips cloud-only resources so they are physically absent
from ``api_sucursal/openapi.json``. The aggregated ``router`` is preserved for
direct imports (backward compat) and to keep the path layout
``/api/v1/empresa/{resource}/...`` intact for cloud.
"""
from __future__ import annotations

from fastapi import APIRouter

from ...models.V.cantidad_vehiculos_sucursal import CantidadVehiculosSucursal
from ...models.V.documentos import Documentos
from ...models.V.empresa import Empresa
from ...models.V.resolucion_facturacion import ResolucionFacturacion
from ...models.V.sucursal import Sucursal
from ...models.V.tarifas_sucursal import TarifasSucursal
from ...schemas.empresa import (
    CantidadVehiculosSucursalCreate,
    CantidadVehiculosSucursalRead,
    CantidadVehiculosSucursalReadList,
    CantidadVehiculosSucursalUpdate,
    DocumentosCreate,
    DocumentosRead,
    DocumentosReadList,
    DocumentosUpdate,
    EmpresaCreate,
    EmpresaRead,
    EmpresaReadList,
    EmpresaUpdate,
    ResolucionFacturacionCreate,
    ResolucionFacturacionRead,
    ResolucionFacturacionReadList,
    ResolucionFacturacionUpdate,
    SucursalCreate,
    SucursalRead,
    SucursalReadList,
    SucursalUpdate,
    TarifasSucursalCreate,
    TarifasSucursalRead,
    TarifasSucursalReadList,
    TarifasSucursalUpdate,
)
from ..router_factory import make_router

router = APIRouter(prefix="/empresa", tags=["empresa"])

# Issuer-permission defaults per resource (see T-PR4-03 table).
# Cloud-only resource (DIAN root) gets strict admin- issuer.
_ROUTER_CONFIG = {
    "empresa": ("admin-,operador-", "config_empresa"),
    "sucursal": ("admin-,operador-", "config_sucursal"),
    "documentos": ("admin-,operador-", "admin_documentos"),
    "resolucion-facturacion": ("admin-", "admin_resolucion_facturacion"),
    "tarifas-sucursal": ("admin-,operador-", "config_tarifas"),
    "cantidad-vehiculos-sucursal": ("admin-,operador-", "config_cupos"),
}

# Per-resource sub-routers exposed for the v1 package's selective mounting
# (T-PR4-11, REQ-X3). Keys are the resource slugs from ``_ROUTER_CONFIG``;
# values are the APIRouters returned by ``make_router``. Populated below by
# ``_mount_empresa``.
_SUB_ROUTERS: dict[str, APIRouter] = {}


def _mount_empresa(
    *,
    resource: str,
    model_cls: type,
    read_schema: type,
    read_list_schema: type,
    create_schema: type,
    update_schema: type,
) -> APIRouter:
    """Build, stash, and mount one empresa C+Q+U router.

    The returned sub-router is:

    1. Stored in ``_SUB_ROUTERS[resource]`` so the v1 package can include
       individual resources selectively (DIAN boundary).
    2. Mounted on the aggregated ``router`` for backward-compat direct
       imports.
    """
    issuer, perm = _ROUTER_CONFIG[resource]
    sub = make_router(
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
    _SUB_ROUTERS[resource] = sub
    router.include_router(sub)
    return sub


_mount_empresa(
    resource="empresa",
    model_cls=Empresa,
    read_schema=EmpresaRead,
    read_list_schema=EmpresaReadList,
    create_schema=EmpresaCreate,
    update_schema=EmpresaUpdate,
)
_mount_empresa(
    resource="sucursal",
    model_cls=Sucursal,
    read_schema=SucursalRead,
    read_list_schema=SucursalReadList,
    create_schema=SucursalCreate,
    update_schema=SucursalUpdate,
)
_mount_empresa(
    resource="documentos",
    model_cls=Documentos,
    read_schema=DocumentosRead,
    read_list_schema=DocumentosReadList,
    create_schema=DocumentosCreate,
    update_schema=DocumentosUpdate,
)
_mount_empresa(
    resource="resolucion-facturacion",
    model_cls=ResolucionFacturacion,
    read_schema=ResolucionFacturacionRead,
    read_list_schema=ResolucionFacturacionReadList,
    create_schema=ResolucionFacturacionCreate,
    update_schema=ResolucionFacturacionUpdate,
)
_mount_empresa(
    resource="tarifas-sucursal",
    model_cls=TarifasSucursal,
    read_schema=TarifasSucursalRead,
    read_list_schema=TarifasSucursalReadList,
    create_schema=TarifasSucursalCreate,
    update_schema=TarifasSucursalUpdate,
)
_mount_empresa(
    resource="cantidad-vehiculos-sucursal",
    model_cls=CantidadVehiculosSucursal,
    read_schema=CantidadVehiculosSucursalRead,
    read_list_schema=CantidadVehiculosSucursalReadList,
    create_schema=CantidadVehiculosSucursalCreate,
    update_schema=CantidadVehiculosSucursalUpdate,
)


__all__ = ["_SUB_ROUTERS", "router"]