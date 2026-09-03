"""ORM model for ``prod.login`` (auth-domain [L-S] table, REQ-42, REQ-46).

Lifecycle event with a state field (``estado``). Every login attempt writes a
new row; the ``timestamp_cierre`` + state transition happens via
``repo.session_cycle.close_login_with_log`` (PR7) — which also writes a
``log_transaccional`` row in the same TX to satisfy the DB-layer session guard
trigger.

Note: despite the [L-S] base not declaring versioning columns in design §3.2,
the migration carries ``vigente_desde``, ``vigente_hasta``, ``estado`` for
this table. The base's audit/version mixins are inherited unchanged; the
marker ``__session_only__`` is what the AST tests look for.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import SessionBase


class Login(SessionBase):
    """[L-S] Login attempt lifecycle event."""

    __tablename__ = "login"

    uuid_usuario: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prod.usuarios.uuid"),
        nullable=True,
    )
    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prod.sucursal.uuid"),
        nullable=True,
    )
    timestamp_evento: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    timestamp_cierre: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    __table_args__ = (
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["Login"]