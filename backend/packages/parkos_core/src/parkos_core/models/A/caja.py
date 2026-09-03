"""ORM model for ``prod.caja`` (cash-drawer snapshot, [A] table, REQ-26-A-CAJA).

A ``caja`` row records a point-in-time snapshot of the cash + datafono
balances at the close of a sesion (PR7). The reverso pattern (insert a
``compensating`` row with negative deltas) handles corrections; there is
no UPDATE path on this table.

Partitioned monthly by ``fecha_retencion_hasta`` (pg_partman). DIAN
retention worker refreshes the column when rows age out.

Composite primary key (``uuid``, ``fecha_retencion_hasta``) — required by
``pg_partman`` range partitioning.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric, PrimaryKeyConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class Caja(AppendOnlyBase):
    """[A] Cash-drawer snapshot. INSERT-only; corrections are compensating rows."""

    __tablename__ = "caja"

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
    valor_efectivo: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=4),
        nullable=True,
    )
    valor_datafono: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=4),
        nullable=True,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "uuid",
            "fecha_retencion_hasta",
            name="caja_pk",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
            "postgresql_partition_by": "RANGE (fecha_retencion_hasta)",
        },
    )


__all__ = ["Caja"]