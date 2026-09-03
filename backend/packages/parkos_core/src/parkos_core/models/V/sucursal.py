"""ORM model for ``prod.sucursal`` ([V] table, PR4).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 311-328).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

The 8 business columns mirror the ER ``sucursal`` block exactly: ``nombre``,
``direccion``, ``telefono``, ``prefijo_nombre`` (UK), ``ciudad``, ``horario``
(all String) and ``uuid_tipo_sucursal`` / ``uuid_empresa`` (PG_UUID). FK
relationships to ``tipo_sucursal`` and ``empresa`` are application-enforced —
the migration does not declare FK constraints at the SQL level, which keeps
the bi-temporal version lifecycle flexible across deploys.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class Sucursal(VersionedBase):
    """[V] Branch master; partitioning axis of the local replica per branch."""

    __tablename__ = "sucursal"

    nombre: Mapped[str | None] = mapped_column(String, nullable=True)
    direccion: Mapped[str | None] = mapped_column(String, nullable=True)
    telefono: Mapped[str | None] = mapped_column(String, nullable=True)
    prefijo_nombre: Mapped[str | None] = mapped_column(String, nullable=True)
    ciudad: Mapped[str | None] = mapped_column(String, nullable=True)
    horario: Mapped[str | None] = mapped_column(String, nullable=True)
    uuid_tipo_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_empresa: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("prefijo_nombre", "vigente_desde", name="sucursal_uk01"),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["Sucursal"]