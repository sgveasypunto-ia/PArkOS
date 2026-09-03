"""ORM model for ``prod.vehiculos`` (commercial domain [V] table, PR5).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 454-465).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

The 2 business columns mirror the ER ``vehiculos`` block exactly: ``placa``
(UK01 with ``vigente_desde``) and ``uuid_tipo_vehiculo`` (FK). FK is
application-enforced — same pattern as PR3/PR4.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class Vehiculos(VersionedBase):
    """[V] Registered vehicles (only required for suscripciones; ad-hoc vehicles ride on the placa column in ingreso)."""

    __tablename__ = "vehiculos"

    placa: Mapped[str | None] = mapped_column(String, nullable=True)
    uuid_tipo_vehiculo: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("placa", "vigente_desde", name="vehiculos_uk01"),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["Vehiculos"]
