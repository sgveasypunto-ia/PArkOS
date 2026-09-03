"""Operations HTTP routes — facturacion (PR6, T-PR6-10, REQ-10, REQ-15, REQ-30).

5 non-cloud billing tables mounted via :func:`make_router`:

- ``facturas`` — ``[L-E]`` operational invoice event (branch writes;
  sibling ``ingreso`` event in PR5)
- ``factura-detalle`` — ``[A]`` invoice line items (one row per concept)
- ``factura-impuestos`` — ``[A]`` tax snapshot (IVA, INC, etc.)
- ``factura-otros-cobros`` — ``[A]`` surcharges (recargos, propinas)
- ``factura-pagos`` — ``[A]`` payment events + reversals
  (REQ-OP-09, SC-11). The reverso write path lives in
  :mod:`repo.factura_pagos` (T-PR6-05); the partial unique index
  ``uq_factura_pagos_reverso`` (T-PR6-06) blocks double-reversals at
  the DB layer.

Cloud-only ``factura-electronica`` lives in
:mod:`parkos_core.dian.cloud_router` (T-PR6-09, REQ-X3). This module
MUST NOT mount it — doing so re-exposes cloud-only endpoints on the
branch API.

READ-ONLY mounts (PR6):

These 5 tables are mounted with ``write_enabled=False``. None of the 5
has the ``vigente_hasta`` column that :func:`make_router`'s
``"versioned"`` branch requires for close+insert writes, and putting
:func:`repo.append_only.append_event` /
:func:`repo.event.record_event` /
:func:`repo.factura_pagos.reverse_payment` behind the generic factory
would conflate write paths. Custom write endpoints arrive in PR7
(monthly operations) and PR8 (reverso surface) — those PRs can reuse
the read endpoints already mounted here.

The read endpoints obey the standard cursor-paginated list contract
(REQ-OP-01) and the per-resource issuer + permission guard
(REQ-OP-13).

NO DELETE endpoint — defense in depth (design §3, AGENTS.md §3).
"""
from __future__ import annotations

from fastapi import APIRouter

from ...models.A.factura_detalle import FacturaDetalle
from ...models.A.factura_impuestos import FacturaImpuestos
from ...models.A.factura_otros_cobros import FacturaOtrosCobros
from ...models.A.factura_pagos import FacturaPagos
from ...models.L_E.facturas import Facturas
from ...schemas.facturacion import (
    FacturaDetalleCreate,
    FacturaDetalleRead,
    FacturaDetalleReadList,
    FacturaDetalleUpdate,
    FacturaImpuestosCreate,
    FacturaImpuestosRead,
    FacturaImpuestosReadList,
    FacturaImpuestosUpdate,
    FacturaOtrosCobrosCreate,
    FacturaOtrosCobrosRead,
    FacturaOtrosCobrosReadList,
    FacturaOtrosCobrosUpdate,
    FacturaPagosCreate,
    FacturaPagosRead,
    FacturaPagosReadList,
    FacturaPagosUpdate,
    FacturasCreate,
    FacturasRead,
    FacturasReadList,
    FacturasUpdate,
)
from ..router_factory import make_router

router = APIRouter(prefix="/facturacion", tags=["facturacion"])

# Issuer-permission defaults per resource (T-PR6-10). All 5 tables use
# the same operator + admin scope because the operator mutates these
# (in custom endpoints shipping later) and the admin needs cross-branch
# read visibility.
_ROUTER_CONFIG = {
    "facturas": ("operador-,admin-", "emitir_factura"),
    "factura-detalle": ("operador-,admin-", "emitir_factura"),
    "factura-impuestos": ("operador-,admin-", "emitir_factura"),
    "factura-otros-cobros": ("operador-,admin-", "emitir_factura"),
    "factura-pagos": ("operador-,admin-", "emitir_factura"),
}


def _mount_factura(
    *,
    resource: str,
    model_cls: type,
    read_schema: type,
    read_list_schema: type,
    create_schema: type,
    update_schema: type,
) -> None:
    """Mount one facturacion C+Q+U router under ``/facturacion/{resource}``.

    ``write_enabled=False`` per PR6 rationale above.
    """
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
            write_enabled=False,
        )
    )


_mount_factura(
    resource="facturas",
    model_cls=Facturas,
    read_schema=FacturasRead,
    read_list_schema=FacturasReadList,
    create_schema=FacturasCreate,
    update_schema=FacturasUpdate,
)
_mount_factura(
    resource="factura-detalle",
    model_cls=FacturaDetalle,
    read_schema=FacturaDetalleRead,
    read_list_schema=FacturaDetalleReadList,
    create_schema=FacturaDetalleCreate,
    update_schema=FacturaDetalleUpdate,
)
_mount_factura(
    resource="factura-impuestos",
    model_cls=FacturaImpuestos,
    read_schema=FacturaImpuestosRead,
    read_list_schema=FacturaImpuestosReadList,
    create_schema=FacturaImpuestosCreate,
    update_schema=FacturaImpuestosUpdate,
)
_mount_factura(
    resource="factura-otros-cobros",
    model_cls=FacturaOtrosCobros,
    read_schema=FacturaOtrosCobrosRead,
    read_list_schema=FacturaOtrosCobrosReadList,
    create_schema=FacturaOtrosCobrosCreate,
    update_schema=FacturaOtrosCobrosUpdate,
)
_mount_factura(
    resource="factura-pagos",
    model_cls=FacturaPagos,
    read_schema=FacturaPagosRead,
    read_list_schema=FacturaPagosReadList,
    create_schema=FacturaPagosCreate,
    update_schema=FacturaPagosUpdate,
)


__all__ = ["router"]
