"""HU-F11.2 fix (2026-09-24) — ``GET /api/v1/workflows/alert-types``.

Dedicated read-only router (mirrors the ``sync_estado.py`` precedent):
the generic ``make_router`` factory can't model the field-name/vocabulary
translation this endpoint needs between ``prod.alert_types`` (``tipo_
alerta``, ``severity`` info|warning|critical) and the FE contract
(``codigo``, ``severidad`` alta|media|baja, ``mensaje``) — see
``schemas/workflows.py::AlertTypeRead`` module note for the full
translation table and why ``mensaje`` reuses ``descripcion``.

Was previously 404 in production: the FE (``useAlertas.ts``, shipped
HU-F11.2) has always called this path, but no backend route ever existed
for it — confirmed via ``prod.alert_types`` model / ``router_factory.py``
comment ("no router in the codebase currently lists it").

``alert_types`` is out-of-catalog (plan.md HU-F19.4 BR1) — identical on
every node, no ``uuid_sucursal`` column. ``uuid_sucursal`` is still
accepted as a required query param (matching the FE's existing call
shape and the KD-3 issuer/tenant convention every other endpoint uses)
but is NOT used to filter — the catalog is the same for every branch.
"""
from __future__ import annotations

import uuid as uuid_lib

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.engine import get_session
from ...repo.alert_types import list_alert_types, severity_to_severidad
from ...schemas.workflows import AlertTypeRead
from ..deps import requires_issuer
from . import _helpers

router = APIRouter(prefix="/workflows", tags=["workflows"])

_alert_types_issuer_dep = requires_issuer("operador-", "admin-")


@router.get("/alert-types", response_model=list[AlertTypeRead])
async def get_alert_types(
    response: Response,
    uuid_sucursal: uuid_lib.UUID = Query(...),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _claims: None = Depends(_alert_types_issuer_dep),
) -> list[AlertTypeRead]:
    """Return the full ``prod.alert_types`` registry, FE-shaped.

    ``uuid_sucursal`` is accepted (contract parity with the FE's
    existing call + KD-3 precedent) but NOT used to filter: the
    registry is deploy-seeded identically on every node (out-of-catalog,
    plan.md HU-F19.4 BR1), so every branch sees the same rows.
    """
    _helpers.apply_no_store_header(response)
    rows = await list_alert_types(session)
    return [
        AlertTypeRead(
            codigo=row.tipo_alerta,
            severidad=severity_to_severidad(row.severity),
            descripcion=row.descripcion or "",
            mensaje=row.descripcion or "",
        )
        for row in rows
    ]


__all__ = ["router"]
