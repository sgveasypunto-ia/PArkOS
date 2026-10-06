"""ORM model for ``prod.tipo_subscripciones`` (catalog [V] table, PR3).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 195-210).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

The 6 business columns mirror the ER ``tipo_subscripciones`` block exactly:
``tipo`` (UK), ``valor`` (Numeric(18,4)), ``duracion_dias`` (Integer),
``cantidad_maxima_vehiculos`` (Integer), ``mismo_tipo_vehiculo`` (Boolean),
``tipo_cliente_permitido`` (String).

Migration 0087 adds ``uuid_tipo_vehiculo`` (nullable FK to ``tipos_vehiculo``;
NULL = plan valid for any vehicle type). As elsewhere, the FK lives only in
the migration, not in the ORM.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import Boolean, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class TipoSubscripciones(VersionedBase):
    """[V] Catalog: commercial subscription plans."""

    __tablename__ = "tipo_subscripciones"

    tipo: Mapped[str | None] = mapped_column(String, nullable=True)
    valor: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    duracion_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cantidad_maxima_vehiculos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mismo_tipo_vehiculo: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tipo_cliente_permitido: Mapped[str | None] = mapped_column(String, nullable=True)
    uuid_tipo_vehiculo: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("tipo", "vigente_desde", name="tipo_subscripciones_uk01"),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["TipoSubscripciones"]
