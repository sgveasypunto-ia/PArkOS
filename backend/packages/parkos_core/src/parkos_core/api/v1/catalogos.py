"""Catalog-domain HTTP routes (REQ-OP-13, REQ-02-V-CONSULTA, SC-01-V-CATALOG-CRUD).

PR3 mounts all 9 catalog tables — see ``tasks.md`` T-PR3-01..T-PR3-09. Each
router is built by ``make_router`` with:

- ``repo_kind="versioned"`` — bi-temporal close+insert writes (REQ-04, REQ-05)
- ``issuer_required="admin-,operador-"`` — admin writes, operador reads the
  replicated catalogs (catalogs are cloud-authored + replicated down)
- ``permission_required="config_catalogo"`` — write-side guard (REQ-OP-13)

The 9 catalogs (all ``[V]`` per design §2):

1. ``tipo-persona``         — natural | juridica
2. ``tipos-vehiculo``       — carro | moto | bicicleta
3. ``tipo-subscripciones``  — commercial plans
4. ``tipo-tarifa``          — hora | fraccion | plena | nocturna
5. ``tipo-sucursal``        — branch operating model (with JSONB ``caracteristicas``)
6. ``tipo-arqueo``          — cierre_turno | auditoria | cierre_sesion
7. ``impuestos``            — tax catalog (IVA, INC); invoice snapshots to
                              ``factura_impuestos`` (design §10)
8. ``otros-cobros``         — additional billable charges; invoice snapshots to
                              ``factura_otros_cobros``
9. ``costos-servicios``     — internal services (ticket reprint, etc.)

NO DELETE endpoint at any layer — defense in depth (design §3, AGENTS.md §3).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.engine import get_session
from ...models.V.costos_servicios import CostosServicios
from ...models.V.impuestos import Impuestos
from ...models.V.otros_cobros import OtrosCobros
from ...models.V.tipo_arqueo import TipoArqueo
from ...models.V.tipo_persona import TipoPersona
from ...models.V.tipo_subscripciones import TipoSubscripciones
from ...models.V.tipo_sucursal import TipoSucursal
from ...models.V.tipo_tarifa import TipoTarifa
from ...models.V.tipos_vehiculo import TiposVehiculo
from ...repo.tipos_vehiculo_subscripcion import get_tipos_vehiculo_con_subscripcion
from ...schemas.costos_servicios import (
    CostosServiciosCreate,
    CostosServiciosRead,
    CostosServiciosReadList,
    CostosServiciosUpdate,
)
from ...schemas.impuestos import (
    ImpuestosCreate,
    ImpuestosRead,
    ImpuestosReadList,
    ImpuestosUpdate,
)
from ...schemas.otros_cobros import (
    OtrosCobrosCreate,
    OtrosCobrosRead,
    OtrosCobrosReadList,
    OtrosCobrosUpdate,
)
from ...schemas.tipo_arqueo import (
    TipoArqueoCreate,
    TipoArqueoRead,
    TipoArqueoReadList,
    TipoArqueoUpdate,
)
from ...schemas.tipo_persona import (
    TipoPersonaCreate,
    TipoPersonaRead,
    TipoPersonaReadList,
    TipoPersonaUpdate,
)
from ...schemas.tipo_subscripciones import (
    TipoSubscripcionesCreate,
    TipoSubscripcionesRead,
    TipoSubscripcionesReadList,
    TipoSubscripcionesUpdate,
)
from ...schemas.tipo_sucursal import (
    TipoSucursalCreate,
    TipoSucursalRead,
    TipoSucursalReadList,
    TipoSucursalUpdate,
)
from ...schemas.tipo_tarifa import (
    TipoTarifaCreate,
    TipoTarifaRead,
    TipoTarifaReadList,
    TipoTarifaUpdate,
)
from ...schemas.tipos_vehiculo import (
    TiposVehiculoCreate,
    TiposVehiculoRead,
    TiposVehiculoReadList,
    TiposVehiculoUpdate,
)
from ..router_factory import make_router

router = APIRouter(prefix="/catalogos", tags=["catalogos"])

_CATALOG_DEFAULTS = {
    "repo_kind": "versioned",
    "issuer_required": "admin-,operador-",
    "permission_required": "config_catalogo",
}


def _mount_catalog(
    *,
    resource: str,
    model_cls: type,
    read_schema: type,
    read_list_schema: type,
    create_schema: type,
    update_schema: type,
) -> None:
    """Mount one catalog C+Q+U router under ``/catalogos/{resource}``.

    Centralises the ``make_router`` defaults so all 9 catalogs share the same
    issuer/permission/repo policy (REQ-OP-13, SC-01-V-CATALOG-CRUD).
    """
    router.include_router(
        make_router(
            resource=resource,
            model_cls=model_cls,
            read_schema=read_schema,
            read_list_schema=read_list_schema,
            create_schema=create_schema,
            update_schema=update_schema,
            **_CATALOG_DEFAULTS,
        )
    )


_mount_catalog(
    resource="tipo-persona",
    model_cls=TipoPersona,
    read_schema=TipoPersonaRead,
    read_list_schema=TipoPersonaReadList,
    create_schema=TipoPersonaCreate,
    update_schema=TipoPersonaUpdate,
)
_mount_catalog(
    resource="tipos-vehiculo",
    model_cls=TiposVehiculo,
    read_schema=TiposVehiculoRead,
    read_list_schema=TiposVehiculoReadList,
    create_schema=TiposVehiculoCreate,
    update_schema=TiposVehiculoUpdate,
)
_mount_catalog(
    resource="tipo-subscripciones",
    model_cls=TipoSubscripciones,
    read_schema=TipoSubscripcionesRead,
    read_list_schema=TipoSubscripcionesReadList,
    create_schema=TipoSubscripcionesCreate,
    update_schema=TipoSubscripcionesUpdate,
)
_mount_catalog(
    resource="tipo-tarifa",
    model_cls=TipoTarifa,
    read_schema=TipoTarifaRead,
    read_list_schema=TipoTarifaReadList,
    create_schema=TipoTarifaCreate,
    update_schema=TipoTarifaUpdate,
)
_mount_catalog(
    resource="tipo-sucursal",
    model_cls=TipoSucursal,
    read_schema=TipoSucursalRead,
    read_list_schema=TipoSucursalReadList,
    create_schema=TipoSucursalCreate,
    update_schema=TipoSucursalUpdate,
)
_mount_catalog(
    resource="tipo-arqueo",
    model_cls=TipoArqueo,
    read_schema=TipoArqueoRead,
    read_list_schema=TipoArqueoReadList,
    create_schema=TipoArqueoCreate,
    update_schema=TipoArqueoUpdate,
)
_mount_catalog(
    resource="impuestos",
    model_cls=Impuestos,
    read_schema=ImpuestosRead,
    read_list_schema=ImpuestosReadList,
    create_schema=ImpuestosCreate,
    update_schema=ImpuestosUpdate,
)
_mount_catalog(
    resource="otros-cobros",
    model_cls=OtrosCobros,
    read_schema=OtrosCobrosRead,
    read_list_schema=OtrosCobrosReadList,
    create_schema=OtrosCobrosCreate,
    update_schema=OtrosCobrosUpdate,
)
_mount_catalog(
    resource="costos-servicios",
    model_cls=CostosServicios,
    read_schema=CostosServiciosRead,
    read_list_schema=CostosServiciosReadList,
    create_schema=CostosServiciosCreate,
    update_schema=CostosServiciosUpdate,
)


# ---------------------------------------------------------------------------
# HU-F11.x (REQ-OPS-200) — tipos_vehiculo subset para ingreso con override
# ---------------------------------------------------------------------------


@router.get(
    "/tipos-vehiculo-con-subscripcion",
    response_model=list[TiposVehiculoRead],
    response_model_by_alias=False,
    summary=(
        "HU-F11.x: vigentes ``prod.tipos_vehiculo`` cuyo ``tipo`` aparece "
        "como sufijo de al menos un ``prod.tipo_subscripciones`` vigente. "
        "Usado por ``<IngresoPanel />`` para el dropdown de override del "
        "tipo detectado por regex. Caching 5min (DEC-F4.1-04)."
    ),
    responses={
        200: {"description": "Lista de ``TiposVehiculoRead`` filtrada por subscripcion."},
    },
)
async def list_tipos_vehiculo_con_subscripcion(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[TiposVehiculoRead]:
    """Tipos de vehículo cubiertos por al menos un plan de subscripción
    vigente. La selección se hace por convención del string
    ``tipo_subscripciones.tipo`` (último segmento después de ``_``).

    Operador-issuer: el dropdown es parte del flujo de ingreso. Mismas
    reglas de caché que ``GET /catalogos/tipos-vehiculo`` (catalog reference
    data, no realtime).
    """
    rows = await get_tipos_vehiculo_con_subscripcion(session)
    return [TiposVehiculoRead.model_validate(r) for r in rows]


__all__ = ["router"]