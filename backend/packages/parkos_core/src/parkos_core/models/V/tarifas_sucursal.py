"""ORM model for ``prod.tarifas_sucursal`` ([V] table, PR4).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 357-371).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

The 5 business columns mirror the ER ``tarifas_sucursal`` block exactly:
``uuid_sucursal`` / ``uuid_tipo_vehiculo`` / ``uuid_tipo_tarifa`` (PG_UUID)
and ``valor`` / ``valor_plena`` (Numeric(18,4)). The full UK01 prevents two
overlapping rates for the same (branch, vehicle type, tariff mode); versions
are distinguished by ``vigente_desde``, which also accepts a future date so
operators can schedule a rate change.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class TarifasSucursal(VersionedBase):
    """[V] Per-branch rate by vehicle type and tariff mode (hour, fraction, full)."""

    __tablename__ = "tarifas_sucursal"

    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_tipo_vehiculo: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_tipo_tarifa: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    valor: Mapped[float | None] = mapped_column(
        Numeric(precision=18, scale=4),
        nullable=True,
    )
    valor_plena: Mapped[float | None] = mapped_column(
        Numeric(precision=18, scale=4),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "uuid_sucursal",
            "uuid_tipo_vehiculo",
            "uuid_tipo_tarifa",
            "vigente_desde",
            name="tarifas_sucursal_uk01",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["TarifasSucursal"]