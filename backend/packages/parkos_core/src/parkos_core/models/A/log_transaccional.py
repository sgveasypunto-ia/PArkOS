"""ORM model for ``prod.log_transaccional`` (audit [A] table, REQ-16, REQ-X4).

Partitioned monthly by ``fecha_retencion_hasta`` (DIAN retention, 5+ years).
Carries the SHA-256 hash chain columns (``hash_anterior`` / ``hash_actual``)
that ``repo/hash_chain.append()`` extends on every commit.

This is the ONLY [A] table that ``close_and_insert`` writes to in PR1b
(versioned.py → append_only.append_event → log_transaccional). Every other [A]
table gets its own ORM file in PR2.

Composite primary key (``uuid``, ``fecha_retencion_hasta``) — required by
``pg_partman`` range partitioning. We override IdMixin's ``primary_key=True``
on ``uuid`` so the composite PK takes effect.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

from sqlalchemy import (
    CHAR,
    Date,
    DateTime,
    ForeignKey,
    PrimaryKeyConstraint,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase, HashChainMixin


class LogTransaccional(AppendOnlyBase, HashChainMixin):
    """[A] Append-only audit log with SHA-256 chain integrity per ``uuid_sucursal``.

    INSERT-only: REVOKE UPDATE, DELETE FROM rol_app is asserted by migration
    0001. The BEFORE UPDATE OR DELETE trigger raises ``LOG_TRANSACCIONAL_INMUTABLE``
    on any mutation attempt.
    """

    __tablename__ = "log_transaccional"

    # --- Composite PK columns (override IdMixin's primary_key=True) ---
    uuid: Mapped[uuid_lib.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        server_default=func.gen_random_uuid(),
    )
    fecha_retencion_hasta: Mapped[date] = mapped_column(  # type: ignore[override]
        Date,
        nullable=False,
        server_default=func.current_date(),
    )

    # --- Business columns ---
    uuid_usuario: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prod.usuarios.uuid"),
        nullable=True,
    )
    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    accion: Mapped[str | None] = mapped_column(String, nullable=True)
    tabla_afectada: Mapped[str | None] = mapped_column(String, nullable=True)
    uuid_registro_afectado: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_referencia: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    datos_anteriores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    datos_nuevos: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    timestamp_evento: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    # --- Hash chain columns (from HashChainMixin) ---
    # Re-declared here with explicit names; the mixin's Mapped[...] annotations
    # are inherited via MRO but the column name must match the migration.
    hash_anterior: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    hash_actual: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint(
            "uuid",
            "fecha_retencion_hasta",
            name="log_transaccional_pk",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
            "postgresql_partition_by": "RANGE (fecha_retencion_hasta)",
        },
    )


__all__ = ["LogTransaccional"]