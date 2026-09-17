"""ORM model for ``prod.sesion`` (cash session [L-S] table, PR7).

``SessionBase`` — session lifecycle. NO versioning columns. Writes MUST
go through ``repo.session_cycle.open_session`` / ``close_session_with_log``
(REQ-40, REQ-41). NO direct UPDATE/DELETE outside ``repo/session_cycle.py``
(enforced by AST test ``test_no_raw_dml_on_ls_tables.py``, PR1c).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import DateTime, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import SessionBase


class Sesion(SessionBase):
    """[L-S] Cash session — open on shift start, close on shift end.

    Lifecycle:
    - ``open_session``: INSERT row with ``timestamp_apertura`` + initial cash.
    - ``close_session_with_log``: UPDATE row with ``timestamp_cierre`` +
      ``uuid_usuario_cierre`` + co-transactional ``log_transaccional`` row.

    The session-guard trigger ``ls_session_guard`` (migration 0001) blocks
    UPDATE without a log_transaccional row in the same TX (SC-40, SC-42).
    """

    __tablename__ = "sesion"

    valor_inicial_efectivo: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    valor_inicial_datafono: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    uuid_usuario: Mapped[uuid_lib.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    timestamp_apertura: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    timestamp_cierre: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    uuid_usuario_cierre: Mapped[uuid_lib.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    # REQ-OPS-135 (Bug 5 of qa-2026-09-17): free-text notes supplied at
    # open time by the F3.3 frontend. NULL is the legitimate value
    # (an operator who has nothing to say). Column added by migration
    # 0035 (PG11+ instant, no rewrite). When non-NULL on open, the
    # value is mirrored into ``prod.log_transaccional.datos_nuevos``
    # via ``repo.session_cycle.open_session`` for audit (REQ-OPS-021).
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    __table_args__ = (
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["Sesion"]
