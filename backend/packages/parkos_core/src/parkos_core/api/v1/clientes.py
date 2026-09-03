"""Commercial HTTP routes (PR5 — clientes + vehículos + subscripciones).

Branch-originated data (operator writes locally, admin reads cross-branch).
``make_router`` does NOT emit DELETE routes (REQ-33 / defense in depth).
"""
from __future__ import annotations

from fastapi import APIRouter

from ...models.V.clientes import Clientes
from ...models.V.clientes_b2b import ClientesB2B
from ...models.V.subscripcion_vehiculos import SubscripcionVehiculos
from ...models.V.subscripciones_cliente import SubscripcionesCliente
from ...models.V.vehiculos import Vehiculos
from ...schemas.clientes import (
    ClientesB2BCreate,
    ClientesB2BRead,
    ClientesB2BReadList,
    ClientesB2BUpdate,
    ClientesCreate,
    ClientesRead,
    ClientesReadList,
    ClientesUpdate,
    SubscripcionesClienteCreate,
    SubscripcionesClienteRead,
    SubscripcionesClienteReadList,
    SubscripcionesClienteUpdate,
    SubscripcionVehiculosCreate,
    SubscripcionVehiculosRead,
    SubscripcionVehiculosReadList,
    SubscripcionVehiculosUpdate,
    VehiculosCreate,
    VehiculosRead,
    VehiculosReadList,
    VehiculosUpdate,
)
from ..router_factory import make_router

router = APIRouter(prefix="/clientes", tags=["clientes"])

_ROUTER_CONFIG = {
    "clientes": ("operador-,admin-", "admin_clientes"),
    "clientes-b2b": ("operador-,admin-", "admin_clientes_b2b"),
    "subscripciones-cliente": ("operador-,admin-", "admin_subscripciones"),
    "vehiculos": ("operador-,admin-", "admin_vehiculos"),
    "subscripcion-vehiculos": ("operador-,admin-", "admin_subscripcion_vehiculos"),
}


def _mount_cliente(
    *,
    resource: str,
    model_cls: type,
    read_schema: type,
    read_list_schema: type,
    create_schema: type,
    update_schema: type,
) -> None:
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


_mount_cliente(
    resource="clientes",
    model_cls=Clientes,
    read_schema=ClientesRead,
    read_list_schema=ClientesReadList,
    create_schema=ClientesCreate,
    update_schema=ClientesUpdate,
)
_mount_cliente(
    resource="clientes-b2b",
    model_cls=ClientesB2B,
    read_schema=ClientesB2BRead,
    read_list_schema=ClientesB2BReadList,
    create_schema=ClientesB2BCreate,
    update_schema=ClientesB2BUpdate,
)
_mount_cliente(
    resource="subscripciones-cliente",
    model_cls=SubscripcionesCliente,
    read_schema=SubscripcionesClienteRead,
    read_list_schema=SubscripcionesClienteReadList,
    create_schema=SubscripcionesClienteCreate,
    update_schema=SubscripcionesClienteUpdate,
)
_mount_cliente(
    resource="vehiculos",
    model_cls=Vehiculos,
    read_schema=VehiculosRead,
    read_list_schema=VehiculosReadList,
    create_schema=VehiculosCreate,
    update_schema=VehiculosUpdate,
)
_mount_cliente(
    resource="subscripcion-vehiculos",
    model_cls=SubscripcionVehiculos,
    read_schema=SubscripcionVehiculosRead,
    read_list_schema=SubscripcionVehiculosReadList,
    create_schema=SubscripcionVehiculosCreate,
    update_schema=SubscripcionVehiculosUpdate,
)


__all__ = ["router"]
