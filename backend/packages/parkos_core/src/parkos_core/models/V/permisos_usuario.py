"""ORM model for ``prod.permisos_usuario`` (auth-domain [V] junction table).

Maps users to permission codes. The unique key includes ``vigente_desde`` so
multiple versions of the same (user, permission) relationship can coexist as
distinct rows — exactly the bi-temporal invariant the project enforces.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class PermisosUsuario(VersionedBase):
    """[V] Junction: which permission codes are currently held by which user.

    The ``require_permission()`` dependency (auth/permissions.py) joins through
    this table to verify the actor's authority.
    """

    __tablename__ = "permisos_usuario"

    # FK targets are referenced as strings to avoid import cycles between
    # ``models/V/usuarios.py`` and ``models/V/permisos.py``.
    uuid_usuario: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prod.usuarios.uuid"),
        nullable=True,
    )
    uuid_permiso: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prod.permisos.uuid"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "uuid_usuario",
            "uuid_permiso",
            "vigente_desde",
            name="permisos_usuario_uk01",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["PermisosUsuario"]