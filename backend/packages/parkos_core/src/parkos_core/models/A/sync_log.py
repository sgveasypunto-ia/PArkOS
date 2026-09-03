"""ORM model for ``prod.sync_log`` (sync-infra [A] table, REQ-14-A-SYNC-LOG).

Diagnostic log written by the sync workers every N minutes: timestamps,
operation counts (sent/succeeded/failed/conflicts), and duration. Used by
operators to detect stalled workers and to size the ``sync_batch_size``
tuning knob.

Composite primary key (``uuid``, ``fecha_retencion_hasta``) — required by
``pg_partman`` range partitioning on the retention column.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import (
    Date,
    DateTime,
    Integer,
    PrimaryKeyConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class SyncLog(AppendOnlyBase):
    """[A] Diagnostic record written by ``job_sync_sucursal`` / ``job_sync_cloud``."""

    __tablename__ = "sync_log"

    # --- Composite PK columns (override IdMixin's primary_key=True) ---
    uuid: Mapped[uuid_lib.UUID] = mapped_column(  # type: ignore[override]
        PG_UUID(as_uuid=True),
        nullable=False,
        server_default=func.gen_random_uuid(),
    )
    fecha_retencion_hasta: Mapped[Date] = mapped_column(  # type: ignore[override]
        Date,
        nullable=False,
        server_default=func.current_date(),
    )

    # --- Business columns ---
    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    timestamp_evento: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    operaciones_enviadas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operaciones_exitosas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operaciones_fallidas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conflictos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duracion_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint(
            "uuid",
            "fecha_retencion_hasta",
            name="sync_log_pk",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
            "postgresql_partition_by": "RANGE (fecha_retencion_hasta)",
        },
    )


__all__ = ["SyncLog"]