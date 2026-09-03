"""ORM model for ``prod.tipos_vehiculo`` (catalog [V] table, PR3).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 183-194).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.
"""
from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class TiposVehiculo(VersionedBase):
    """[V] Catalog: vehicle classes (``carro`` | ``moto`` | ``bicicleta`` etc.)."""

    __tablename__ = "tipos_vehiculo"

    tipo: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("tipo", "vigente_desde", name="tipos_vehiculo_uk01"),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["TiposVehiculo"]