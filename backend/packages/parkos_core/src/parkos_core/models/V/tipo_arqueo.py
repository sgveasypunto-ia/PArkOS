"""ORM model for ``prod.tipo_arqueo`` (catalog [V] table, PR3).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 239-251).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

The 3 business columns mirror the ER ``tipo_arqueo`` block exactly:
``codigo`` (UK), ``nombre`` (String), ``descripcion`` (Text).
"""
from __future__ import annotations

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class TipoArqueo(VersionedBase):
    """[V] Catalog: cash-count classifications (turn-closure, surprise-audit, session-close)."""

    __tablename__ = "tipo_arqueo"

    codigo: Mapped[str | None] = mapped_column(String, nullable=True)
    nombre: Mapped[str | None] = mapped_column(String, nullable=True)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("codigo", "vigente_desde", name="tipo_arqueo_uk01"),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["TipoArqueo"]