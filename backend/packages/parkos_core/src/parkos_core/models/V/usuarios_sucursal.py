"""ORM model for ``prod.usuarios_sucursal`` (auth-domain [V] junction table).

Maps users to branches. The ``operador-`` JWT issuer pins a single branch
through this table — see ``auth/tenancy.py`` and design §9.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class UsuariosSucursal(VersionedBase):
    """[V] Junction: which branches a user is currently assigned to."""

    __tablename__ = "usuarios_sucursal"

    # String FK references avoid cross-model circular imports.
    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prod.sucursal.uuid"),
        nullable=True,
    )
    uuid_usuario: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prod.usuarios.uuid"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "uuid_sucursal",
            "uuid_usuario",
            "vigente_desde",
            name="usuarios_sucursal_uk01",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["UsuariosSucursal"]