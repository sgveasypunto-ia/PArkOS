"""ORM model for ``prod.tipo_sucursal`` (catalog [V] table, PR3).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 224-237).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

The 4 business columns mirror the ER ``tipo_sucursal`` block exactly:
``codigo`` (UK), ``nombre`` (String), ``descripcion`` (Text),
``caracteristicas`` (JSONB).
"""
from __future__ import annotations

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class TipoSucursal(VersionedBase):
    """[V] Catalog: branch operating-model classification."""

    __tablename__ = "tipo_sucursal"

    codigo: Mapped[str | None] = mapped_column(String, nullable=True)
    nombre: Mapped[str | None] = mapped_column(String, nullable=True)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    caracteristicas: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("codigo", "vigente_desde", name="tipo_sucursal_uk01"),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["TipoSucursal"]
