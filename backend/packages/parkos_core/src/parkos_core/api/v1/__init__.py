"""parkos_core FastAPI v1 router package (PR1c + PR3 + PR4 + PR5 + PR6 + PR7 + PR8c).

The DIAN boundary (design §10 + REQ-X3) is enforced at TWO layers:

1. **Image-level** (Layer 1, design §10): the ``Dockerfile`` for branch
   images physically excludes the ``parkos_core/dian/`` directory.
2. **Import-level** (Layer 2, this module + ``dian.cloud_router``): the
   top-level guard in :mod:`parkos_core.dian.cloud_router` raises
   ``ImportError`` when ``PARKOS_DEPLOY=branch``, and THIS module
   lazy-imports :mod:`parkos_core.dian.cloud_router` only when
   ``PARKOS_DEPLOY != "branch"``. On branch deploy the lazy import is
   skipped entirely so we never even attempt to load the cloud-only
   file.

Cloud-only resources (excluded from branch deploy, REQ-X3):

- ``empresa.resolucion-facturacion`` — DIAN root; cloud is the single writer.
- ``POST /api/v1/factura-electronica`` — atomic ``consecutivo`` issuance.
- ``POST /api/v1/envio-dian`` — DIAN send/ack workflow transition.
- ``POST /api/v1/validacion-evento`` — admin validation workflow transition.
- ``POST /api/v1/revocacion-factura-webhook`` — DIAN revocation + chain.
- ``admin_views`` (PR10, REQ-X2) — ``GET /api/v1/sucursales``,
  ``GET /api/v1/admin/sucursales/{uuid}/dashboard``, ``GET /api/v1/admin/me``.
  Multi-branch visibility is an admin-only capability; branch operators
  must never see other branches.
- ``admin/pairing-tokens`` + ``admin/sucursales/{uuid}/revoke-sync``
  (PR8b/PR8c) — admin-issued pairing tokens + admin-side branch JWT
  revocation. The ``admin-`` issuer guard denies branch operators with
  401, but the routers themselves live in ``api/v1/pairing.py`` and are
  NOT mounted on branch deploy (belt-and-suspenders for the same
  reason as the cloud-only list above).

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
- ``facturacion`` — 5 non-cloud billing tables (PR6): facturas,
  factura-detalle, factura-impuestos, factura-otros-cobros, factura-pagos
- ``workflows`` — 4 branch-originated [L-W] tables (PR6):
  reimpresion-ticket, anulaciones, reclamos, alerta
- ``caja`` — caja + arqueo [A] cash-drawer + cash-count snapshots (PR7).
  Read-only this PR; writes land in PR11 via ``repo.append_only``.
- ``caja-sesion`` — sesion [L-S] cash session + custom endpoints
  (PR7, REQ-40/REQ-41): ``POST /sesiones`` opens, ``PUT
  /sesion/{uuid}/cerrar`` closes (log-first), ``GET
  /arqueos/{uuid}/diferencias`` reads expected-vs-reported deltas.
- ``sync`` (PR8c, REQ-OP-03) — ``/sync/pair``, ``/sync/push``,
  ``/sync/pull``, ``/sync/heartbeat``, ``/sync/rotate-jwt``,
  ``/sync/events``. Mounted on BOTH ``api_admin`` AND
  ``api_sucursal``: ``/sync/pair`` is the branch→cloud one-shot
  consumer; the other five are the bidirectional transport used by
  the cloud-side receiver AND the branch-side receiver. The
  three-layer DIAN boundary does NOT apply because the sync transport
  is not DIAN — see ``api/v1/sync_router.py`` docstring.

T-PR4-11 keeps the path layout ``/api/v1/empresa/{resource}/...`` intact by
rebuilding a custom empresa router with the same ``/empresa`` prefix the
aggregated ``empresa.router`` exposes. The aggregated router is preserved
for backward-compat direct imports. T-PR6-11 adds the DIAN cloud router
mount at the v1 root only on cloud deploys (REQ-X3 belt-and-suspenders).
T-PR8-16 adds the sync router at the v1 root on BOTH deploys
(non-DIAN, REQ-OP-03).
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
from . import (
    auth,
    caja,  # T-PR7-09 wire-in
    caja_sesion,  # T-PR7-09 wire-in
    catalogos,
    clientes,
    configuracion,
    empresa,
    facturacion,
    operacion,
    sucursal,
    sync_estado,  # HU-F1.14 wire-in: GET /sync/estado (fix 2026-09-24: was nested under /caja, see caja.py note)
    sync_router,  # T-PR8-16 wire-in: /sync/* (REQ-OP-03, both deploys)
    usuarios_login,  # HU-F1.15: GET /usuarios/{uuid}/login (DEC-LOGIN-01.A)
    workflows,
    workflows_alert_types,  # HU-F11.2 fix 2026-09-24: GET /workflows/alert-types
    workflows_reimpresion,  # HU-F1.11: POST /workflows/reimpresion-ticket + .../{uuid}/anular
)

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
    """Build the v1 router, applying DIAN boundary rules (REQ-X3, T-PR6-11)."""
    r = APIRouter(prefix="/api/v1")

    # Always-mounted routers (replicated on cloud + branch).
    r.include_router(auth.router)
    r.include_router(catalogos.router)
    r.include_router(configuracion.router)
    r.include_router(sucursal.router)
    r.include_router(clientes.router)
    r.include_router(operacion.router)
    r.include_router(facturacion.router)  # PR6
    r.include_router(workflows.router)  # PR6
    # HU-F1.11 / DEC-TKT-06: POST /workflows/reimpresion-ticket + /{uuid}/anular
    # live on a dedicated router to keep the factory path reserved for C+Q.
    r.include_router(workflows_reimpresion.router)
    # HU-F11.2 fix 2026-09-24: GET /workflows/alert-types (see module docstring
    # for the field-translation this dedicated router does over the generic factory).
    r.include_router(workflows_alert_types.router)
    r.include_router(caja.router)  # T-PR7-09
    r.include_router(caja_sesion.router)  # T-PR7-09
    r.include_router(sync_router.router)  # T-PR8-16: /sync/* (both deploys, REQ-OP-03)
    r.include_router(sync_estado.router)  # HU-F1.14: GET /sync/estado (both deploys)
    r.include_router(usuarios_login.router)  # HU-F1.15: GET /usuarios/{uuid}/login (DEC-LOGIN-01.A)

    # Empresa resources — selectively mounted (DIAN boundary, REQ-X3).
    r.include_router(_build_empresa_router())

    # T-PR10: admin_views — cloud-only (REQ-X2). Branch operators have no
    # cross-branch visibility, so ``api_sucursal`` never mounts these routes.
    if _IS_BRANCH:
        logger.info(
            "Branch deploy: admin_views SKIPPED (cloud-only admin views, REQ-X2)"
        )
    else:
        try:
            from . import admin_views as _admin_views

            r.include_router(_admin_views.router)
            logger.info(
                "Admin views mounted (cloud deploy): /sucursales + "
                "/admin/sucursales/{uuid}/dashboard + /admin/me"
            )
        except ImportError as e:
            logger.error("Failed to import admin_views: %s", e)
            raise

    # T-PR8b: pairing admin endpoints — cloud-only (REQ-OP-15 +
    # design §21.3). Pairing is an admin-only operation; branch
    # operators have no business accessing these. Two routers:
    # ``pairing.router`` (4 admin pairing-token endpoints) +
    # ``pairing.sync_revoke_router`` (PR8c stub for branch sync JWT
    # revocation).
    if _IS_BRANCH:
        logger.info(
            "Branch deploy: pairing admin endpoints SKIPPED "
            "(cloud-only, REQ-OP-15)"
        )
    else:
        try:
            from . import pairing as _pairing

            r.include_router(_pairing.router)
            r.include_router(_pairing.sync_revoke_router)
            logger.info(
                "Pairing admin endpoints mounted (cloud deploy): "
                "/admin/pairing-tokens + /admin/sucursales/{uuid}/revoke-sync"
            )
        except ImportError as e:
            logger.error("Failed to import pairing endpoints: %s", e)
            raise

    # T-PR6-11: lazy-import the DIAN cloud router ONLY on cloud deploy.
    # Branch images physically lack ``parkos_core/dian/`` (Layer 1) AND
    # the import-time guard inside ``cloud_router`` would raise
    # ``ImportError`` even if the file were present (Layer 2). We gate
    # here so we never attempt the import on branch.
    if _IS_BRANCH:
        logger.info(
            "Branch deploy: dian.cloud_router SKIPPED (DIAN boundary, REQ-X3)"
        )
    else:
        try:
            # Late import — keeps the cloud-only module off branch
            # import graphs entirely. The module's own top-level guard
            # is the belt-and-suspenders second layer.
            from ...dian import cloud_router as _dian_cloud

            r.include_router(_dian_cloud.router)
            logger.info(
                "DIAN cloud router mounted (cloud deploy): "
                "/factura-electronica + /envio-dian + "
                "/validacion-evento + /revocacion-factura-webhook"
            )
        except ImportError as e:
            # Only swallow ImportError from the cloud-only guard —
            # propagate any other ImportError (e.g. missing dep).
            if "cloud_router" in str(e) and "branch deploy" in str(e):
                logger.error(
                    "Cloud deploy attempted to import cloud_router but "
                    "received branch-guard ImportError: %s",
                    e,
                )
                raise
            logger.error("Failed to import dian.cloud_router: %s", e)
            raise

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