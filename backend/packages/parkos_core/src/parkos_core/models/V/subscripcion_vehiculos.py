"""ORM model for ``prod.subscripcion_vehiculos`` (commercial domain [V] table, PR5).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 498-509).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

Junction table between ``subscripciones_cliente`` and ``vehiculos``: which
vehicles are covered by which subscription. UK01 includes ``vigente_desde``
so the same vehicle can be re-associated across versions of a subscription.

REQ-OP-08 invariant (enforced by the Pydantic ``SubscripcionVehiculosCreate``
validator in T-PR5-04): the count of active rows for a given
``uuid_subscripcion_cliente`` must never exceed ``cantidad_maxima_vehiculos``
of the plan. The validator serializes concurrent inserts with
``pg_advisory_xact_lock(uuid_subscripcion_cliente)``.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class SubscripcionVehiculos(VersionedBase):
    """[V] Junction: vehicles covered by a given subscription."""

    __tablename__ = "subscripcion_vehiculos"

    uuid_subscripcion_cliente: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_vehiculo: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "uuid_subscripcion_cliente",
            "uuid_vehiculo",
            "vigente_desde",
            name="subscripcion_vehiculos_uk01",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["SubscripcionVehiculos"]
