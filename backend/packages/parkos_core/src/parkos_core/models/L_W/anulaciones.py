"""ORM model for ``prod.anulaciones`` (operations [L-W] annulment, PR6).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 912-934).

Range-partitioned monthly by ``fecha_retencion_hasta`` (DIAN 5+ year
retention, pg_partman parent). Composite PK on
``(uuid, fecha_retencion_hasta)``.

The polymorphic pointer ``tipo_anulable`` (``ingreso`` | ``salida``) +
``uuid_ingreso``/``uuid_salida`` is the source of the
``V_INGRESO_ESTADO`` derivation \u2014 an annulment writes a new row in this
table and the view joins here to surface ``anulada``. NO physical DELETE
is permitted (REQ-04, AGENTS.md \u00a72).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

from sqlalchemy import Date, DateTime, PrimaryKeyConstraint, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import WorkflowBase


class Anulaciones(WorkflowBase):
    """[L-W] Annulment event for an ingreso or salida (polymorphic, REQ-22)."""

    __tablename__ = "anulaciones"

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
    tipo_anulable: Mapped[str | None] = mapped_column(String, nullable=True)
    uuid_ingreso: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_salida: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_usuario: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    uuid_anulacion_padre: Mapped[uuid_lib.UUID | None] = mapped_column(
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
        PrimaryKeyConstraint(
            "uuid",
            "fecha_retencion_hasta",
            name="anulaciones_pk",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
            "postgresql_partition_by": "RANGE (fecha_retencion_hasta)",
        },
    )


__all__ = ["Anulaciones"]