"""ORM model for ``prod.alerta`` (operations [L-W] cash-count anomalies, PR6).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 952-974).

Range-partitioned monthly by ``fecha_retencion_hasta`` (DIAN 5+ year
retention, pg_partman parent). Composite PK on
``(uuid, fecha_retencion_hasta)``.

REJECTED state machine: only an admin user may transition
``alerta.estado`` to ``en_revision`` \u2014 enforced by the Pydantic layer
(REQ-26-W-ALERTA-DESCARTADA). The ORM carries no special marker for
that \u2014 the state machine + actor check live in the API surface.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Numeric, PrimaryKeyConstraint, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import WorkflowBase


class Alerta(WorkflowBase):
    """[L-W] Cash-count anomaly surfaced by an ``arqueo`` (REQ-26)."""

    __tablename__ = "alerta"

    # --- Composite PK columns (override IdMixin's primary_key=True) ---
    uuid: Mapped[uuid_lib.UUID] = mapped_column(  # type: ignore[override]
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
    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_usuario: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_arqueo: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    tipo_alerta: Mapped[str | None] = mapped_column(String, nullable=True)
    valor_diferencia_efectivo: Mapped[float | None] = mapped_column(
        Numeric(precision=18, scale=4),
        nullable=True,
    )
    valor_diferencia_datafono: Mapped[float | None] = mapped_column(
        Numeric(precision=18, scale=4),
        nullable=True,
    )
    uuid_alerta_padre: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    timestamp_evento: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    # HU-F1.6 / REQ-OPS-041.C — JSONB payload carried by
    # ``capacidad_agotada_forzado`` alerts (motivo + uuid_ingreso).
    # Added by migration 0025; column is nullable for pre-existing rows.
    datos_nuevos: Mapped[dict | None] = mapped_column(
        JSONB,
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
        PrimaryKeyConstraint(
            "uuid",
            "fecha_retencion_hasta",
            name="alerta_pk",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
            "postgresql_partition_by": "RANGE (fecha_retencion_hasta)",
        },
    )


__all__ = ["Alerta"]