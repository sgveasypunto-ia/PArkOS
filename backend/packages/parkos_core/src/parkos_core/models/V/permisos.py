"""ORM model for ``prod.permisos`` (auth-domain [V] table, REQ-OP-13).

Carries the permission code string (``permiso``). The canonical 15-permission
seed lives in migration ``0003_seed_permisos_canonicos.py`` (PR1c).
"""
from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class Permisos(VersionedBase):
    """[V] Permission code catalog. The ``permiso`` column carries the code
    string (``config_catalogo``, ``admin_usuarios``, etc.).
    """

    __tablename__ = "permisos"

    permiso: Mapped[str | None] = mapped_column(  # noqa: A003 - column name is `permiso`
        String,
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("permiso", "vigente_desde", name="permisos_uk01"),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["Permisos"]