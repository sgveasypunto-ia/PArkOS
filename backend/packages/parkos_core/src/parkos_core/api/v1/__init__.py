"""parkos_core FastAPI v1 router package (PR1c + PR3 + PR4 + PR5).

PR4 enforces the DIAN boundary at the router-aggregation level
(design §10 + REQ-X3): the branch image physically lacks
``parkos_core.dian.cloud_router`` (belt-and-suspenders) AND the v1 router
skips cloud-only resources when ``PARKOS_DEPLOY=branch``.

Cloud-only resources (excluded from branch deploy, REQ-X3):

- ``empresa.resolucion-facturacion`` — DIAN root; cloud is the single writer.

Replicated resources (mounted in BOTH deploys):

- ``auth`` — login + refresh + logout
- ``catalogos`` — 9 [V] catalogs (PR3)
- ``empresa`` (excluding resolucion-facturacion) — empresa, sucursal,
  documentos, tarifas_sucursal, cantidad_vehiculos_sucursal (PR4)
- ``configuracion`` — configuracion-tolerancias + configuracion-seguridad (PR4)
- ``sucursal`` — pairing-token (route is callable from cloud-admin; the
  ``admin-`` issuer guard denies branch tokens with 401) (PR4)
- ``clientes`` — 5 [V] commercial tables: clientes, clientes-b2b,
  subscripciones-cliente, vehiculos, subscripcion-vehiculos (PR5)
- ``operacion`` — ingreso [L-E] lifecycle event + derived /estado
  endpoint (PR5)

T-PR4-11 keeps the path layout ``/api/v1/empresa/{resource}/...`` intact by
rebuilding a custom empresa router with the same ``/empresa`` prefix the
aggregated ``empresa.router`` exposes. The aggregated router is preserved
for backward-compat direct imports.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter

logger = logging.getLogger(__name__)

_DEPLOY = os.environ.get("PARKOS_DEPLOY", "cloud").lower()
_IS_BRANCH = _DEPLOY == "branch"

# Resources excluded from branch deploy (DIAN boundary, REQ-X3).
_CLOUD_ONLY_EMPRESA_RESOURCES: frozenset[str] = frozenset(
    {"resolucion-facturacion"}
)

# Side-effect imports: each submodule registers its router at module load.
from . import auth, catalogos, clientes, configuracion, empresa, operacion, sucursal

# Re-use the same per-resource sub-routers that ``empresa.router``
# aggregates. Including them individually here lets us apply the DIAN
# boundary at the v1-aggregation level without modifying the aggregated
# ``empresa.router`` itself.
_EMPRESA_SUB_ROUTERS = empresa._SUB_ROUTERS


def _build_empresa_router() -> APIRouter:
    """Build the empresa sub-router, applying the DIAN boundary (REQ-X3).

    On branch deploy, cloud-only resources are skipped so they are absent
    from ``api_sucursal/openapi.json`` (T-PR4-11 acceptance). The router
    keeps the same ``/empresa`` prefix as the aggregated ``empresa.router``
    so the path layout ``/api/v1/empresa/{resource}/...`` is preserved.
    """
    r = APIRouter(prefix="/empresa", tags=["empresa"])
    for resource, sub in _EMPRESA_SUB_ROUTERS.items():
        if _IS_BRANCH and resource in _CLOUD_ONLY_EMPRESA_RESOURCES:
            logger.info(
                "DIAN boundary: excluding empresa.%s on branch deploy",
                resource,
            )
            continue
        r.include_router(sub)
    return r


def _build_router() -> APIRouter:
    """Build the v1 router, applying DIAN boundary rules."""
    r = APIRouter(prefix="/api/v1")

    # Always-mounted routers (replicated on cloud + branch).
    r.include_router(auth.router)
    r.include_router(catalogos.router)
    r.include_router(configuracion.router)
    r.include_router(sucursal.router)
    r.include_router(clientes.router)
    r.include_router(operacion.router)

    # Empresa resources — selectively mounted (DIAN boundary, REQ-X3).
    r.include_router(_build_empresa_router())

    if _IS_BRANCH:
        logger.info(
            "PARKOS_DEPLOY=branch: DIAN boundary active. Excluded resources: %s",
            sorted(_CLOUD_ONLY_EMPRESA_RESOURCES),
        )
    else:
        logger.info(
            "PARKOS_DEPLOY=%s: full router set (cloud); no DIAN boundary active.",
            _DEPLOY,
        )

    return r


router = _build_router()


__all__ = ["router"]