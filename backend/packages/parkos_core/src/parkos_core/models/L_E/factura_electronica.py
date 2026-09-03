"""ORM model for ``prod.factura_electronica`` (DIAN invoice [L-E], CLOUD-ONLY, PR6).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 875-891).

Cloud-only by deployment topology: the schema is created in both cloud and
branch DBs, but the BRANCH service MUST NOT insert here \u2014 only
``api_admin`` writes, via :mod:`parkos_core.dian.cloud_router` which is
import-guarded by ``PARKOS_DEPLOY=cloud``. The T-PR6-13 static test
verifies the boundary (REQ-X3, SC-X6).

The UK ``(uuid_resolucion_facturacion, consecutivo)`` enforces uniqueness
inside a ``resolucion_facturacion``'s range \u2014 the DIAN
``numero_oficial`` invariant. Atomic ``consecutivo_actual++`` happens in
``dian/cloud_router.py`` via ``SELECT ... FOR UPDATE`` on the
``resolucion_facturacion`` row.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import BigInteger, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import LifecycleEventBase


class FacturaElectronica(LifecycleEventBase):
    """[L-E] DIAN official invoice event (cloud-only, REQ-30, REQ-34, REQ-35)."""

    __tablename__ = "factura_electronica"

    # --- Business columns ---
    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_factura: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_cliente: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_resolucion_facturacion: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    prefijo: Mapped[str | None] = mapped_column(String, nullable=True)
    consecutivo: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    descuento: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "uuid_resolucion_facturacion",
            "consecutivo",
            name="factura_electronica_uk01",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["FacturaElectronica"]