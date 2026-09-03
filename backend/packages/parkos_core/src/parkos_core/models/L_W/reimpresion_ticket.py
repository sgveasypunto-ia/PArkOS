"""ORM model for ``prod.reimpresion_ticket`` (operations [L-W] reprint, PR6).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 893-910).

``WorkflowBase`` \u2014 carries ``vigente_desde`` / ``vigente_hasta`` /
``estado``. Writes flow through ``repo.workflow.append_transition``
(REQ-21). The chain tip is read by
``repo.workflow.read_chain_tip(uuid_ingreso)`` walking the
``uuid_reimpresion_padre`` self-FK \u2014 no UK on the table because
``vigente_desde`` participates in identity.

The branch enables ``reimpresion_ticket`` ONLY after the cloud
``SyncBackEvent`` arrives with the real ``numero_oficial`` \u2014 enforced in
the Pydantic schema, not here.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import WorkflowBase


class ReimpresionTicket(WorkflowBase):
    """[L-W] Ticket reprint chain tip (one row per reprint event)."""

    __tablename__ = "reimpresion_ticket"

    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_ingreso: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_usuario: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_costo_servicio: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    costo_aplicado: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    uuid_factura: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    motivo: Mapped[str | None] = mapped_column(String, nullable=True)
    uuid_reimpresion_padre: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    timestamp_evento: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    # --- Versioning columns (re-declared from VersionedMixin) ---
    # WorkflowBase does NOT inherit VersionedMixin, but the migration adds
    # these columns via ``*_versioning_columns()``. We mirror the
    # ``log_transaccional`` HashChainMixin pattern (PR2) and re-declare
    # them here so the ORM exposes them.
    vigente_desde: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        server_default=text("NOW()"),
    )
    vigente_hasta: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    estado: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        server_default="activo",
    )  # 'activo' | 'inactivo'

    __table_args__ = (
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["ReimpresionTicket"]