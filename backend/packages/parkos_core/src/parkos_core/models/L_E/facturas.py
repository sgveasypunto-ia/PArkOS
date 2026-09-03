"""ORM model for ``prod.facturas`` (operations [L-E] event, PR6).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 607-626).

``LifecycleEventBase`` \u2014 insert-only. NO versioning columns. Composite PK on
``(uuid, fecha_retencion_hasta)`` because the retention date is NOT NULL and
participates in the DIAN 5-year retention partitioning (even though the
table itself is not currently range-partitioned, mirroring
``log_transaccional`` so future migrations can promote the partition axis
without breaking the PK).

The DIAN ``V_FACTURA_ESTADO`` view (PR6 schema work) materializes current
state (``emitida`` | ``anulada`` | ``pagada``) by joining with
``factura_pagos`` + ``anulaciones``. State is never stored on the row.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date

from sqlalchemy import Date, Numeric, PrimaryKeyConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import LifecycleEventBase


class Facturas(LifecycleEventBase):
    """[L-E] Operational invoice event \u2014 the local replica side of DIAN invoicing."""

    __tablename__ = "facturas"

    # --- Composite PK columns (override IdMixin's primary_key=True) ---
    uuid: Mapped[uuid_lib.UUID] = mapped_column(  # type: ignore[override]
        PG_UUID(as_uuid=True),
        nullable=False,
        server_default=func.gen_random_uuid(),
    )
    fecha_retencion_hasta: Mapped[date] = mapped_column(  # type: ignore[override]
        Date,
        nullable=False,
        server_default=func.current_date(),
    )

    # --- Business columns ---
    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    subtotal: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    descuento: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    total: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    uuid_ingreso: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_salida: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "uuid",
            "fecha_retencion_hasta",
            name="facturas_pk",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["Facturas"]