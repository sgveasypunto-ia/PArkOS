"""ORM model for ``prod.clientes`` (commercial domain [V] table, PR5).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 435-452).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

The 8 business columns mirror the ER ``clientes`` block exactly. ``uuid``
+ audit + versioning + sync columns are inherited from ``VersionedBase``
(see ``models/base.py``); only the 8 business columns are declared here.
FK relationships (``uuid_tipo_persona``) are application-enforced — the
migration does not declare FK constraints at the SQL level, same as PR3/PR4.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class Clientes(VersionedBase):
    """[V] Customer master (facturación electrónica / suscripciones)."""

    __tablename__ = "clientes"

    tipo_identificador: Mapped[str | None] = mapped_column(String, nullable=True)
    numero_identificacion: Mapped[str | None] = mapped_column(String, nullable=True)
    nombre: Mapped[str | None] = mapped_column(String, nullable=True)
    apellido: Mapped[str | None] = mapped_column(String, nullable=True)
    telefono: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    uuid_tipo_persona: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    registro: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "tipo_identificador",
            "numero_identificacion",
            "vigente_desde",
            name="clientes_uk01",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["Clientes"]
