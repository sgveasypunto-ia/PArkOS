"""ORM model for ``prod.validacion_evento`` (admin [L-W] validation chain, CLOUD-ONLY, PR6).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 995-1011).

``WorkflowBase`` \u2014 carries versioning columns. Cloud-only by deployment:
the schema exists in both cloud and branch DBs but the BRANCH service
MUST NOT write here. Writes flow through
:mod:`parkos_core.dian.cloud_router` (T-PR6-09, REQ-25).

The ``hash_evento`` column is ``CHAR(64)`` to hold a SHA-256 hex digest
of the validated event payload \u2014 admin auditors use this to detect
tampering between branch-originated events and cloud-stored state.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import CHAR, DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import WorkflowBase


class ValidacionEvento(WorkflowBase):
    """[L-W] Admin validation chain for received events (cloud-only, REQ-25)."""

    __tablename__ = "validacion_evento"

    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_usuario: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    tabla_origen: Mapped[str | None] = mapped_column(String, nullable=True)
    uuid_registro: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    hash_evento: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    uuid_validacion_padre: Mapped[uuid_lib.UUID | None] = mapped_column(
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


__all__ = ["ValidacionEvento"]