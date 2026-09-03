"""Pydantic v2 schemas for the DIAN boundary (PR6, T-PR6-08).

This module is a documentation re-export layer that makes the DIAN
cloud-only boundary explicit. The 2 cloud-only ``[L-W]`` workflow
tables re-exported here (``envio_dian``, ``validacion_evento``) are
consumed by the cloud router (``dian/cloud_router.py``, T-PR6-09) and
NEVER by the branch API.

The schemas themselves live in :mod:`.workflows` — this module
re-exports them so ``cloud_router.py`` can write:

    from parkos_core.schemas.dian import (
        EnvioDianCreate,
        ValidacionEventoCreate,
    )

…and have the cloud-only boundary visible at the **import statement**.
Combined with the static boundary test
(``tests/static/test_dian_boundary_branch.py``, T-PR6-13, REQ-X3,
SC-X6), this makes "cloud-only schemas" greppable.

``FacturaElectronica*`` is NOT re-exported here because it already
lives in :mod:`.facturacion` and is imported directly from there — it
is a single ``[L-E]`` event table, not a workflow chain.

``RevocacionFactura`` (the DIAN revocation webhook receiver, T-PR6-09
route ``POST /api/v1/revocacion-factura-webhook``) ships in PR6b with
its own schema module and is NOT re-exported here.
"""
from __future__ import annotations

from .workflows import (
    EnvioDianCreate,
    EnvioDianFilter,
    EnvioDianRead,
    EnvioDianReadList,
    EnvioDianUpdate,
    ValidacionEventoCreate,
    ValidacionEventoFilter,
    ValidacionEventoRead,
    ValidacionEventoReadList,
    ValidacionEventoUpdate,
)

__all__ = [
    "EnvioDianCreate",
    "EnvioDianFilter",
    "EnvioDianRead",
    "EnvioDianReadList",
    "EnvioDianUpdate",
    "ValidacionEventoCreate",
    "ValidacionEventoFilter",
    "ValidacionEventoRead",
    "ValidacionEventoReadList",
    "ValidacionEventoUpdate",
]