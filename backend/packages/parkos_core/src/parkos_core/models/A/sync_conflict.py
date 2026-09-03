"""ORM model for ``prod.sync_conflict`` (sync-infra [A] table, REQ-14-A-SYNC-CONFLICT).

Records a sync-time disagreement between cloud and branch. Both sides
preserve their own snapshot (``datos_local``, ``datos_cloud``) for offline
review. The ``alerta`` workflow (PR6) escalates unresolved conflicts.

Single PK on ``uuid`` — this table is NOT partitioned. Conflicts are rare
events; volume does not warrant monthly partitioning.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class SyncConflict(AppendOnlyBase):
    """[A] Conflict snapshot captured when cloud + branch rows disagree."""

    __tablename__ = "sync_conflict"

    uuid: Mapped[uuid_lib.UUID] = mapped_column(  # type: ignore[override]
        PG_UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    tabla: Mapped[str | None] = mapped_column(String, nullable=True)
    uuid_registro: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    datos_local: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    datos_cloud: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    politica: Mapped[str | None] = mapped_column(String, nullable=True)
    resolucion: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp_evento: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    __table_args__ = (
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["SyncConflict"]