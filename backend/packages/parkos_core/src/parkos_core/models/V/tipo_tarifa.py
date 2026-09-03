"""ORM model for ``prod.tipo_tarifa`` (catalog [V] table, PR3).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 212-222).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.
"""
from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class TipoTarifa(VersionedBase):
    """[V] Catalog: tariff modalities (``hora`` | ``fraccion`` | ``plena`` | ``nocturna`` etc.)."""

    __tablename__ = "tipo_tarifa"

    tipo: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("tipo", "vigente_desde", name="tipo_tarifa_uk01"),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["TipoTarifa"]
