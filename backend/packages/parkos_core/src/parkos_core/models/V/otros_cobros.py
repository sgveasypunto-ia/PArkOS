"""ORM model for ``prod.otros_cobros`` (catalog [V] table, PR3).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 282-295).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

Note: the invoice NEVER reads this catalog live — it copies a snapshot to
``factura_otros_cobros`` per design §10 (same pattern as ``impuestos``).

The 4 business columns mirror the ER ``otros_cobros`` block exactly:
``nombre`` (UK), ``costo`` (Numeric(18,4)), ``tipo_calculo`` (String),
``base_calculo`` (String).
"""
from __future__ import annotations

from sqlalchemy import Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class OtrosCobros(VersionedBase):
    """[V] Catalog: additional billable charges (insurance, wash, etc.)."""

    __tablename__ = "otros_cobros"

    nombre: Mapped[str | None] = mapped_column(String, nullable=True)
    costo: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    tipo_calculo: Mapped[str | None] = mapped_column(String, nullable=True)
    base_calculo: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("nombre", "vigente_desde", name="otros_cobros_uk01"),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["OtrosCobros"]