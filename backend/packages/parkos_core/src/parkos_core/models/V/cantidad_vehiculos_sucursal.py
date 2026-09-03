"""ORM model for ``prod.cantidad_vehiculos_sucursal`` ([V] table, PR4).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 373-385).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

The 3 business columns mirror the ER ``cantidad_vehiculos_sucursal`` block
exactly: ``uuid_sucursal`` / ``uuid_tipo_vehiculo`` (PG_UUID) and ``cantidad``
(Integer). Scope decision (per the ER comment): capacity is aggregated by
vehicle type — no individual parking-spot assignment.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class CantidadVehiculosSucursal(VersionedBase):
    """[V] Maximum capacity of the branch per vehicle type."""

    __tablename__ = "cantidad_vehiculos_sucursal"

    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_tipo_vehiculo: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    cantidad: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "uuid_sucursal",
            "uuid_tipo_vehiculo",
            "vigente_desde",
            name="cantidad_vehiculos_sucursal_uk01",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["CantidadVehiculosSucursal"]