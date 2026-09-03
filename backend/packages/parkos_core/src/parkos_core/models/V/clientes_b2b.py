"""ORM model for ``prod.clientes_b2b`` (commercial domain [V] table, PR5).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 467-481).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

1:1 extension of ``clientes`` for corporate accounts with a convenio
(flotas, empresas). UK01 is ``(uuid_cliente, vigente_desde)`` — a single
customer can carry at most one active B2B extension per version.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date

from sqlalchemy import Date, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class ClientesB2B(VersionedBase):
    """[V] B2B extension of a customer (corporate convenio)."""

    __tablename__ = "clientes_b2b"

    uuid_cliente: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    cantidad: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registro: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    fecha_inicio_convenio: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        UniqueConstraint("uuid_cliente", "vigente_desde", name="clientes_b2b_uk01"),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["ClientesB2B"]
