"""ORM model for ``prod.tipo_persona`` (catalog [V] table).

Smoke-mounted by ``api/v1/catalogos.py`` in PR1b to prove the router factory
works end-to-end. The remaining 8 catalog tables (``tipos_vehiculo``,
``tipo_subscripciones``, etc.) land in PR3.
"""
from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class TipoPersona(VersionedBase):
    """[V] Catalog: persona types (``natural`` | ``juridica`` etc.)."""

    __tablename__ = "tipo_persona"

    tipo: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("tipo", "vigente_desde", name="tipo_persona_uk01"),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["TipoPersona"]