"""ORM model for ``prod.subscripciones_cliente`` (commercial domain [V] table, PR5).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 483-496).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

A customer subscribes to a plan at a specific branch; renewal = new version
(close current + insert new), not UPDATE. ``ingreso`` references this row
when the entry is under a subscription. No UK at the DB level — the
bi-temporal model keeps each version unique by ``vigente_desde`` and the
business key is the combination of all 3 FKs + dates enforced at the API
layer (T-PR5-04 schemas).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date

from sqlalchemy import Date
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class SubscripcionesCliente(VersionedBase):
    """[V] Customer subscription to a plan at a branch."""

    __tablename__ = "subscripciones_cliente"

    uuid_cliente: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_tipo_subscripcion: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    fecha_inicio_cobertura: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["SubscripcionesCliente"]
