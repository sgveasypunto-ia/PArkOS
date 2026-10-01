"""ORM model for ``prod.usuarios`` (auth-domain [V] table).

Maps 1:1 to the migration in ``0001_initial_schema.py``. The bootstrap migration
owns the canonical column types; this ORM model re-asserts them for SQLAlchemy
introspection only (``extend_existing=True`` in ``__table_args__``).

Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``. See design §4.1.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
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

    # HU-F16 must-change enforcement (migration 0065). ``False`` for every
    # existing open row (the default) and for every close+insert that is NOT
    # a password reset. ``True`` is written only by
    # ``repo.admin_usuarios.reset_admin_password`` and cleared only by
    # ``api.v1.auth.cambiar_password``. The login handler reads this column
    # to decide whether to issue the normal pair or to issue a 5-minute JWT
    # with ``purpose="must_change"`` that the operator must exchange at
    # ``POST /auth/cambiar-password`` before the system treats them as logged in.
    debe_cambiar_password: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )

    # ``uuid`` is inherited as-is from ``IdMixin`` (``primary_key=True,
    # server_default=func.gen_random_uuid()``, matching the migration's
    # ``_uuid_pk()``). A PR6 bug fix removed a re-declaration that shadowed
    # it with ``server_default=None`` — that stripped the server default
    # from SQLAlchemy's metadata entirely (explicitly passing
    # ``server_default=None`` to ``mapped_column()`` does NOT "reuse the
    # mixin default", it OVERRIDES it with "no default"), so any INSERT
    # relying on Postgres to generate the PK (no client-side ``uuid`` in
    # the payload) failed with ``FlushError: ... has a NULL identity key``.
    # Every ``VFixtureFactory``-built test row masked this by always
    # supplying an explicit client-side ``uuid``; ``repo.versioned.
    # close_and_insert(Usuarios, ..., new_attrs={... no uuid ...})`` — the
    # real production path — did not.

    __table_args__ = (
        UniqueConstraint("cedula", "vigente_desde", name="usuarios_uk01"),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["Usuarios"]