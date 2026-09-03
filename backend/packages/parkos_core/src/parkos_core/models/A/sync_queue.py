"""ORM model for ``prod.sync_queue`` (sync-infra [A] table, REQ-14-A-SYNC-FACADE).

The DB-side ``AFTER INSERT`` trigger on every replicated ``[A]`` table fires
``prod.fn_enqueue_sync()`` and inserts a row here. The DB trigger has an
internal recursion guard (``IF TG_TABLE_NAME = 'sync_queue' RETURN NULL``)
so re-inserting into ``sync_queue`` itself does NOT create a second row.

This is the carved-out ``[A]`` table (design §12) — ``rol_app`` keeps
``UPDATE, DELETE`` grants so the sync workers can mutate state via the
whitelisted columns only: ``estado``, ``intentos``, ``next_retry_at``,
``ultimo_error``. See :data:`parkos_core.repo.sync_queue.ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS`.

Partitioned monthly by ``fecha_retencion_hasta`` (pg_partman). The retention
worker refreshes the column when rows age out.

Composite primary key (``uuid``, ``fecha_retencion_hasta``) — required by
``pg_partman`` range partitioning. We override IdMixin's ``primary_key=True``
on ``uuid`` so the composite PK takes effect (see the same pattern in
``models/A/log_transaccional.py``).
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import (
    Date,
    DateTime,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class SyncQueue(AppendOnlyBase):
    """[A] Sync outbox — every replicated ``[A]`` table writes one row here
    via the DB trigger ``prod.fn_enqueue_sync()``.

    Carved-out from the default [A] inmutability (design §12): ``rol_app``
    keeps UPDATE/DELETE grants so the worker can flip ``estado`` and
    increment ``intentos``. The actual mutation is gated to the four
    whitelisted columns (enforced in ``repo.sync_queue`` helpers — the DB
    trigger does not enforce the column whitelist at write time; it
    accepts any UPDATE since the carve-out is at GRANT level).
    """

    __tablename__ = "sync_queue"

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
    operacion: Mapped[str | None] = mapped_column(String, nullable=True)
    tabla: Mapped[str | None] = mapped_column(String, nullable=True)
    uuid_registro: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    datos: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    prioridad: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[str | None] = mapped_column(String, nullable=True)
    intentos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_retry_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    ultimo_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint(
            "uuid",
            "fecha_retencion_hasta",
            name="sync_queue_pk",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
            "postgresql_partition_by": "RANGE (fecha_retencion_hasta)",
        },
    )


__all__ = ["SyncQueue"]