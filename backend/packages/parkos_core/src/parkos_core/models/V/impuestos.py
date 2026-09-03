"""ORM model for ``prod.impuestos`` (catalog [V] table, PR3).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 266-280).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

Note: the invoice NEVER reads this catalog live — it copies a snapshot to
``factura_impuestos`` per design §10. This preserves the historical tax rate
even when the catalog version closes.

The 5 business columns mirror the ER ``impuestos`` block exactly:
``nombre`` (String), ``codigo`` (UK), ``porcentaje`` (Numeric(18,4)),
``tipo_calculo`` (String), ``base_calculo`` (String).
"""
from __future__ import annotations

from sqlalchemy import Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class Impuestos(VersionedBase):
    """[V] Catalog: tax catalog (IVA, INC, etc.). Invoice snapshots to ``factura_impuestos``."""

    __tablename__ = "impuestos"

    nombre: Mapped[str | None] = mapped_column(String, nullable=True)
    codigo: Mapped[str | None] = mapped_column(String, nullable=True)
    porcentaje: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    tipo_calculo: Mapped[str | None] = mapped_column(String, nullable=True)
    base_calculo: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("codigo", "vigente_desde", name="impuestos_uk01"),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["Impuestos"]
