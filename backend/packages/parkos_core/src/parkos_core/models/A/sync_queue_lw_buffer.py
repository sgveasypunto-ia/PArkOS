"""ORM model for ``prod.sync_queue_lw_buffer`` (T-PR8-001, design §2 Issue #2/#8).

[A] dependency buffer — holds a row whose declared ``depends_on`` parent is
neither local nor already applied earlier in the same batch (D18). Keyed
generically on ``(tabla_padre, uuid_padre)`` so any catalog entry, not only
``[L-W]``, can be buffered (design.md §2 Issue #2's amendment). See
:mod:`parkos_core.sync.motor.dependency_buffer` for the insert/drain/TTL-sweep
mechanics.

Composite PK on ``(uuid, buffered_at)`` — required by ``pg_partman`` daily
range partitioning (the partition key must be part of every unique/PK
index), same pattern as every other partitioned ``[A]`` table
(``sync_queue``, ``sync_log``, ``log_transaccional``, ...).

``fecha_retencion_hasta`` (inherited from ``AppendOnlyBase``'s
``RetentionMixin``) is present but unused here — ``buffered_at`` is THIS
table's actual partition key, not the DIAN retention column. Same
unused-but-present precedent as ``sync_conflict`` (nullable, never set).

**Carve-out, not a blanket ``[A]`` REVOKE.** ``estado``/``ultimo_error``
transition after insert (``'pendiente' -> 'aplicado'`` on drain,
``'pendiente' -> 'fallido'`` on TTL timeout) — the SAME tension design §12
resolved for ``prod.sync_queue`` via a carve-out. The migration
(``0012_add_sync_queue_lw_buffer.py``) therefore ``REVOKE``s only
``DELETE`` (never deleted, T-PR8-008) and allows ``UPDATE`` — NOT the
blanket ``REVOKE UPDATE, DELETE`` + ``BEFORE UPDATE OR DELETE`` trigger
every OTHER ``[A]`` table in this schema carries. Only
:mod:`parkos_core.sync.motor.dependency_buffer` writes to this table.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, PrimaryKeyConstraint, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class SyncQueueLwBuffer(AppendOnlyBase):
    """[A] Dependency buffer row — see module docstring."""

    __tablename__ = "sync_queue_lw_buffer"

    # --- Composite PK columns (override IdMixin's primary_key=True) ---
    uuid: Mapped[uuid_lib.UUID] = mapped_column(  # type: ignore[override]
        PG_UUID(as_uuid=True),
        nullable=False,
        server_default=func.gen_random_uuid(),
    )
    buffered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )

    # --- Business columns ---
    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    tabla: Mapped[str] = mapped_column(String, nullable=False)
    uuid_registro: Mapped[uuid_lib.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )
    tabla_padre: Mapped[str] = mapped_column(String, nullable=False)
    uuid_padre: Mapped[uuid_lib.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )
    datos: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    estado: Mapped[str] = mapped_column(
        String(length=16),
        nullable=False,
        server_default="pendiente",
    )  # 'pendiente' | 'aplicado' | 'fallido'
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    ultimo_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint(
            "uuid",
            "buffered_at",
            name="sync_queue_lw_buffer_pk",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
            "postgresql_partition_by": "RANGE (buffered_at)",
        },
    )


__all__ = ["SyncQueueLwBuffer"]
