"""ORM model for ``prod.reclamos`` (operations [L-W] claims, PR6).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 936-950).

``WorkflowBase`` \u2014 carries ``vigente_desde`` / ``vigente_hasta`` /
``estado``. The polymorphic pointer ``tipo_reclamable``
(``ingreso`` | ``salida`` | ``factura``) + ``uuid_reclamable`` is
validated at the Pydantic layer (``ReclamoCreate``) via
``polymorphic_row_exists()`` which hits the appropriate table per
``tipo_reclamable`` (REQ-23-W-POLYMORPHIC-FK, REQ-OP-08).

The chain tip is read via ``uuid_reclamo_padre`` self-FK \u2014 NO UK on the
table because ``vigente_desde`` participates in identity.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import WorkflowBase


class Reclamos(WorkflowBase):
    """[L-W] Claim against an ingreso/salida/factura (polymorphic FK, REQ-23)."""

    __tablename__ = "reclamos"

    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    tipo_reclamable: Mapped[str | None] = mapped_column(String, nullable=True)
    uuid_reclamable: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    uuid_reclamo_padre: Mapped[uuid_lib.UUID | None] = mapped_column(
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


__all__ = ["Reclamos"]