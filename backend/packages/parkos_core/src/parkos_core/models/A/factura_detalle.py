"""ORM model for ``prod.factura_detalle`` (billing [A] line items, PR6).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 628-654).

Range-partitioned monthly by ``fecha_retencion_hasta`` (DIAN 5+ year
retention, pg_partman parent). Composite PK on
``(uuid, fecha_retencion_hasta)`` \u2014 required by pg_partman range partitioning
(partition key must be part of the PK). IdMixin's inherited
``primary_key=True`` on ``uuid`` is overridden here.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date

from sqlalchemy import Date, Integer, Numeric, PrimaryKeyConstraint, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class FacturaDetalle(AppendOnlyBase):
    """[A] Invoice line item \u2014 one row per concept (servicio, producto, etc.)."""

    __tablename__ = "factura_detalle"

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
    uuid_factura: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    concepto: Mapped[str | None] = mapped_column(String, nullable=True)
    cantidad: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valor_unitario: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    subtotal: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint(
            "uuid",
            "fecha_retencion_hasta",
            name="factura_detalle_pk",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
            "postgresql_partition_by": "RANGE (fecha_retencion_hasta)",
        },
    )


__all__ = ["FacturaDetalle"]