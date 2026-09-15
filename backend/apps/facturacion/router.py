"""HU-F1.9 / REQ-OPS-053..063 -- Frontend-facing billing router stub.

This is the contract surface consumed by the F1.11 React app
(``apps/facturacion-web/src/api/cliente-factura.client.ts``). It re-exports
the same 2 endpoints as the canonical
``parkos_core.api.v1.facturacion.router`` so the frontend mounts a single
well-known prefix regardless of where the backend runs.

For F1.9 we expose the canonical handlers DIRECTLY (no transformation
layer). Future PRs (F1.11 frontend) may layer in:
- DTO → domain transformation
- Idempotency-Key cache (DEC-IDEM-01 reuse from F1.6, optional for F1.9)
- Per-frontend i18n error message mapping

Auth: JWT bearer via ``requires_issuer("operador-", "admin-")`` (F1.6
issuer chain, mirrored from the canonical router).

KD-FACT-01: the canonical handler commits exactly once; the stub does
NOT add any commits or transactions.
"""
from __future__ import annotations

from fastapi import APIRouter

# Re-export the canonical handlers so the frontend-facing mount point
# delegates to the SAME implementation. No re-implementation, no
# re-transformation: the spec surface IS the implementation.
from parkos_core.api.v1.facturacion import (
    create_factura,
    create_factura_pago,
)

router = APIRouter(prefix="/api/v1/facturacion", tags=["facturacion"])

# Mount the canonical handlers under the SAME paths as the backend
# router. The frontend mounts this stub and gets the exact same
# `/factura` + `/factura-pagos` URL contract.
router.add_api_route(
    "/factura",
    create_factura,
    methods=["POST"],
    summary=(
        "HU-F1.9 / REQ-OPS-053..063: atomic 4-table insert (frontend stub)"
    ),
)
router.add_api_route(
    "/factura-pagos",
    create_factura_pago,
    methods=["POST"],
    summary=(
        "HU-F1.9 / REQ-OPS-062: voucher validation (frontend stub)"
    ),
)


__all__ = ["router"]
