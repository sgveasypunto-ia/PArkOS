"""ORM model for ``prod.costos_servicios`` (catalog [V] table, PR3).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 297-309).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

The 3 business columns mirror the ER ``costos_servicios`` block exactly:
``concepto`` (UK), ``costo`` (Numeric(18,4)), ``tipo_calculo`` (String).
"""
from __future__ import annotations

from sqlalchemy import Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class CostosServicios(VersionedBase):
    """[V] Catalog: internal operational services (e.g. ticket reprint)."""

    __tablename__ = "costos_servicios"

    concepto: Mapped[str | None] = mapped_column(String, nullable=True)
    costo: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    tipo_calculo: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("concepto", "vigente_desde", name="costos_servicios_uk01"),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["CostosServicios"]
