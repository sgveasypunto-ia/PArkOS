"""ORM model for ``prod.empresa`` ([V] table, PR4).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 137-151).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

The 5 business columns mirror the ER ``empresa`` block exactly: ``nombre``
(String), ``nit`` (UK), ``mensaje_bienvenida`` (String), ``mensaje_salida``
(String), ``regimen`` (String). DIAN numeration was moved out to
``resolucion_facturacion`` (one resolution per branch).
"""
from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class Empresa(VersionedBase):
    """[V] Tax-identity of the operator before DIAN."""

    __tablename__ = "empresa"

    nombre: Mapped[str | None] = mapped_column(String, nullable=True)
    nit: Mapped[str | None] = mapped_column(String, nullable=True)
    mensaje_bienvenida: Mapped[str | None] = mapped_column(String, nullable=True)
    mensaje_salida: Mapped[str | None] = mapped_column(String, nullable=True)
    regimen: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("nit", "vigente_desde", name="empresa_uk01"),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["Empresa"]