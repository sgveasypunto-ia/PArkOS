"""ORM model for ``prod.login`` (auth-domain [L-S] table, REQ-42, REQ-46).

Lifecycle event with a state field (``estado``). Every login attempt writes a
new row; the ``timestamp_cierre`` + state transition happens via
``repo.session_cycle.close_login_with_log`` (PR7) — which also writes a
``log_transaccional`` row in the same TX to satisfy the DB-layer session guard
trigger.

The migration (``0001_initial_schema.py``, ``*_versioning_columns()``) gives
``prod.login`` its own ``vigente_desde``/``vigente_hasta``/``estado`` columns,
reusing the bi-temporal column names for session semantics rather than [V]
audit versioning: ``vigente_desde`` = session start, ``vigente_hasta`` =
session end, ``estado`` = the lifecycle value (``exitoso``/``fallido``/
``cerrado``, not [V]'s ``activo``/``inactivo``). They are declared directly
below rather than via ``VersionedMixin`` because that mixin's server defaults
(``NOW()`` / ``'activo'``) belong to the [V] domain and don't apply here — the
migration itself declares these columns with no server-side default. The
base's audit/session mixins are otherwise inherited unchanged; the marker
``__session_only__`` (from ``SessionBase``) is what the AST tests look for.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
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
    vigente_desde: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )  # session start (repo.session_cycle.record_login)
    vigente_hasta: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )  # session end (repo.session_cycle.close_login_with_log)
    estado: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )  # 'exitoso' | 'fallido' | 'cerrado'

    __table_args__ = (
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["Login"]