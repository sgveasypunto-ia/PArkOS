"""ORM model for ``prod.usuarios`` (auth-domain [V] table).

Maps 1:1 to the migration in ``0001_initial_schema.py``. The bootstrap migration
owns the canonical column types; this ORM model re-asserts them for SQLAlchemy
introspection only (``extend_existing=True`` in ``__table_args__``).

Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``. See design §4.1.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class Usuarios(VersionedBase):
    """[V] Auth-domain user. Closes the previous version and inserts a new one
    on every Actualización — see ``repo.versioned.close_and_insert``.
    """

    __tablename__ = "usuarios"

    # Business-key columns (per migration)
    nombre: Mapped[str | None] = mapped_column(String, nullable=True)
    apellido: Mapped[str | None] = mapped_column(String, nullable=True)
    cedula: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    fecha_cambio_password: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    rol: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )  # 'admin' | 'operador'

    # Re-declare uuid without primary_key inheritance collision if any subclass
    # ever wanted to override; keeping the inherited PK is correct here.
    uuid: Mapped[uuid_lib.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=None,  # inherited default from IdMixin is fine; explicit None reuses mixin
    )

    __table_args__ = (
        UniqueConstraint("cedula", "vigente_desde", name="usuarios_uk01"),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["Usuarios"]