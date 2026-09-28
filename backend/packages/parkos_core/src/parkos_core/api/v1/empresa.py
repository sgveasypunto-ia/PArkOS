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

HU-F1.4: a dedicated ``GET /tarifas-sucursal`` handler is registered BELOW
(``_mount_empresa`` is called for the same resource AFTER this dedicated
route is declared, so FastAPI's order-of-registration resolver picks the
dedicated handler for the bare ``GET`` list path and lets the factory
still own POST / PUT / GET-by-uuid / GET-history on the same resource).
The dedicated handler adds the optional ``vigente_en`` query param and
applies the canonical bi-temporal predicate
``vigente_desde <= :v AND (vigente_hasta IS NULL OR vigente_hasta > :v)
AND estado = 'activo'``. The factory (HU-F1.1) remains untouched.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.tenancy import TenantContext
from ...models.V.cantidad_vehiculos_sucursal import CantidadVehiculosSucursal
from ...models.V.documentos import Documentos
from ...models.V.empresa import Empresa
from ...models.V.resolucion_facturacion import ResolucionFacturacion
from ...models.V.sucursal import Sucursal
from ...models.V.tarifas_sucursal import TarifasSucursal
from ...repo.tarifas_vigencia import list_tarifas_vigentes
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
    TarifasSucursalFilter,
    TarifasSucursalRead,
    TarifasSucursalReadList,
    TarifasSucursalUpdate,
)
from ..deps import get_session, get_tenant_ctx, requires_issuer
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


# HU-F1.4 — dedicated handler for ``GET /empresa/tarifas-sucursal``.
# The dedicated handler is registered on its OWN sub-router (same prefix
# as the factory) and that sub-router is ``include_router``'d BEFORE the
# factory sub-router, so FastAPI's order-of-registration resolver picks
# THIS handler over the factory's ``list_endpoint`` for the bare ``GET``
# list path on this resource. POST / PUT / GET-by-uuid / GET-history
# still flow through the factory (KD-4 of the design). The dedicated
# handler delegates the SELECT to
# ``repo.tarifas_vigencia.list_tarifas_vigentes`` so the predicate, tz
# normalization, cursor and order are shared with the unit tests
# (REQ-OPS-019..020).

_tarifas_issuer_dep = requires_issuer("admin-", "operador-")


_tarifas_dedicated_router = APIRouter(prefix="/tarifas-sucursal", tags=["tarifas-sucursal"])


@_tarifas_dedicated_router.get(
    "",
    response_model=TarifasSucursalReadList,
)
async def list_tarifas_sucursal_vigente_en(
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    vigente_en: datetime | None = Query(
        None,
        description=(
            "Punto en el tiempo para el predicado de vigencia. "
            "Acepta ISO-8601 con o sin tz (naive = UTC). "
            "Default: datetime.now(UTC)."
        ),
    ),
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_tarifas_issuer_dep),
) -> TarifasSucursalReadList:
    """HU-F1.4 — bi-temporal ``GET /empresa/tarifas-sucursal``.

    Same response shape as the factory's list endpoint
    (``{items: [...], next_cursor: str | None}``). ``vigente_en`` is
    evaluated per-request to ``datetime.now(UTC)`` when omitted (KD-3).
    """
    v = vigente_en if vigente_en is not None else datetime.now(UTC)
    rows, nxt = await list_tarifas_vigentes(
        session,
        vigente_en=v,
        filter=TarifasSucursalFilter(vigente_en=v),
        cursor=cursor,
        limit=limit,
    )
    items = [TarifasSucursalRead.model_validate(r) for r in rows]
    return TarifasSucursalReadList(items=items, next_cursor=nxt)


@_tarifas_dedicated_router.get(
    "/{uuid}",
    response_model=TarifasSucursalRead,
    responses={404: {"description": "tarifa_no_encontrada"}},
)
async def get_tarifa_sucursal_by_uuid(
    uuid: uuid_lib.UUID = Path(  # noqa: B008
        ...,
        description="UUIDv4 de la fila de prod.tarifas_sucursal a leer.",
    ),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_tarifas_issuer_dep),
) -> TarifasSucursalRead:
    """HU-F1.4 / CU-02 (operador, 2026-09-22): detalle de una tarifa específica.

    El handler de listado (``list_tarifas_sucursal_vigente_en`` arriba)
    devuelve un ``TarifasSucursalReadList`` paginado para alimentar el
    hook FE ``useTarifasVigentes``. El cotizador de salida
    (``GET /operacion/cotizar``) retorna ``tarifa_uuid`` (el UUID de la
    fila aplicada) sin el detalle — el UI solo podía mostrar el UUID
    crudo. Este endpoint complementa: el FE hace un lookup
    ``getTarifaSucursalByUuid(uuid)`` para mostrar ``valor``,
    ``valor_plena``, ``vigente_desde/hasta`` y ``estado`` en el panel
    de cotizacion.

    Read-only por contrato (KD-4): sin UPDATE/DELETE, sin commit. La
    fila es ``[V]`` bi-temporal; el factory router conserva la cadena
    versionada (close+insert en escritura). El query directo via
    ``session.execute`` es read-only y consistente con la invariante
    del feature.

    Tenant scope: el handler valida via ``_tarifas_dedicated_router_
    issuer_dep`` (``admin-,operador-``) + KD-3 ``get_tenant_ctx``. El
    operador- está pinned a su sucursal, pero este endpoint NO filtra
    por ``uuid_sucursal`` porque la tarifa aplicada al cobro ya fue
    validada upstream por ``prod.calcular_cotizacion`` (FOR SHARE
    sobre la fila correcta) — el uuid que viene del cotizar es
    autoritativo. Permitir lectura cross-branch sería un leak; el cotizar
    con KD-3 ya previene eso (operador no puede cobrar en otra
    sucursal).

    404 si la fila no existe (uuid mal tipeado o fila cerrada). El FE
    muestra el UUID como fallback si 404.
    """
    row = (
        await session.execute(
            select(TarifasSucursal).where(TarifasSucursal.uuid == uuid)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "tarifa_no_encontrada", "uuid": str(uuid)},
        )
    return TarifasSucursalRead.model_validate(row)


router.include_router(_tarifas_dedicated_router)


_mount_empresa(
    resource="tarifas-sucursal",
    model_cls=TarifasSucursal,
    read_schema=TarifasSucursalRead,
    read_list_schema=TarifasSucursalReadList,
    create_schema=TarifasSucursalCreate,
    update_schema=TarifasSucursalUpdate,
)

# Register the dedicated handler on the same per-resource sub-routers
# dict that ``api/v1/__init__.py`` reads to build the v1 router — the
# aggregated ``empresa.router`` is for backward-compat direct imports,
# but the real HTTP path goes through the v1 router. Stash the
# dedicated handler under a synthetic key so the v1 router picks it
# up BEFORE the factory sub-router (Python dict preserves insertion
# order; ``_build_empresa_router`` iterates ``_SUB_ROUTERS.items()``
# in declaration order).
_SUB_ROUTERS["tarifas-sucursal__dedicated_hu_f1_4"] = _tarifas_dedicated_router
# Move the dedicated sub-router to the FRONT of the dict so it is
# registered first by ``_build_empresa_router``.
_reordered: dict[str, APIRouter] = {}
_reordered["tarifas-sucursal__dedicated_hu_f1_4"] = _tarifas_dedicated_router
for k, v in _SUB_ROUTERS.items():
    if k == "tarifas-sucursal__dedicated_hu_f1_4":
        continue
    _reordered[k] = v
_SUB_ROUTERS.clear()
_SUB_ROUTERS.update(_reordered)
_mount_empresa(
    resource="cantidad-vehiculos-sucursal",
    model_cls=CantidadVehiculosSucursal,
    read_schema=CantidadVehiculosSucursalRead,
    read_list_schema=CantidadVehiculosSucursalReadList,
    create_schema=CantidadVehiculosSucursalCreate,
    update_schema=CantidadVehiculosSucursalUpdate,
)


__all__ = ["_SUB_ROUTERS", "router"]