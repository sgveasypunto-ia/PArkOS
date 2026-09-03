"""Cloud-only atomic ``(prefijo, consecutivo)`` allocator (T-PR11-05, REQ-OP-12 / REQ-34).

Serializes on ``prod.resolucion_facturacion`` via ``SELECT FOR UPDATE`` so
the MAX + 1 + INSERT sequence in :mod:`parkos_core.dian.cloud_router` is
race-free inside one transaction. Caller owns the INSERT + commit (pure
helper, easy to test). Cloud-only by T-PR11-07 layer-2 mirror; branch
deploys bail at module load before any SQLAlchemy mapping is touched.
"""
from __future__ import annotations

import os
import uuid as uuid_lib

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# T-PR11-07 \u2014 DIAN boundary layer 2 mirror (helper is cloud-only).
if os.environ.get("PARKOS_DEPLOY", "cloud").lower() == "branch":
    raise ImportError(
        "dian_cloud_unavailable_on_branch (T-PR11-05, REQ-X3, design \u00a710 Layer 2)"
    )

from ...models.V.resolucion_facturacion import ResolucionFacturacion


class ResolucionNotFoundError(RuntimeError):
    """Resolution row missing (caller maps to HTTP 404)."""


class PrefijoMissingError(RuntimeError):
    """Row's ``prefijo`` is ``NULL`` (caller maps to HTTP 409)."""


async def next_consecutivo(
    session: AsyncSession,
    *,
    uuid_resolucion_facturacion: uuid_lib.UUID,
) -> tuple[str, int]:
    """Return ``(prefijo, consecutivo)`` for the next factura_electronica row.

    ``consecutivo = COALESCE(MAX(consecutivo), rango_desde - 1) + 1`` scoped
    to the resolution (first row lands on ``rango_desde``).

    TODO(T-PR11c): migrate to ``prod.v_resolucion_consecutivo`` VIEW; the
    raw MAX() is a stand-in matching the cloud_router.py bootstrap behavior.

    Raises:
        ResolucionNotFoundError / PrefijoMissingError (both RuntimeError).
    """
    row = (
        await session.execute(
            select(ResolucionFacturacion)
            .where(ResolucionFacturacion.uuid == uuid_resolucion_facturacion)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise ResolucionNotFoundError(
            f"resolucion_facturacion {uuid_resolucion_facturacion} not found"
        )
    if row.prefijo is None:
        raise PrefijoMissingError(
            f"resolucion_facturacion {uuid_resolucion_facturacion} has no prefijo"
        )
    start = (row.rango_desde - 1) if row.rango_desde is not None else -1
    # scalar_one: COALESCE always returns exactly one value.
    max_consecutivo = (
        await session.execute(
            text(
                "SELECT COALESCE(MAX(consecutivo), :start) "
                "FROM prod.factura_electronica "
                "WHERE uuid_resolucion_facturacion = :uuid"
            ),
            {"start": start, "uuid": str(uuid_resolucion_facturacion)},
        )
    ).scalar_one()
    return row.prefijo, int(max_consecutivo) + 1


__all__ = ["PrefijoMissingError", "ResolucionNotFoundError", "next_consecutivo"]
