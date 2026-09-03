"""ORM model for ``prod.envio_dian`` (DIAN [L-W] send/ack workflow, CLOUD-ONLY, PR6).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 976-993).

``WorkflowBase`` \u2014 carries versioning columns. Cloud-only by deployment:
the schema exists in both cloud and branch DBs but the BRANCH service
MUST NOT write here. Writes flow through
:mod:`parkos_core.dian.cloud_router` (T-PR6-09, REQ-25-W-CLOUD-ONLY).

The chain tip walks the ``uuid_envio_padre`` self-FK to capture retries
(a network hiccup -> new envio_dian row pointing at the prior).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import DateTime, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import WorkflowBase


class EnvioDian(WorkflowBase):
    """[L-W] DIAN send/ack retry chain (cloud-only, REQ-25-W-CLOUD-ONLY)."""

    __tablename__ = "envio_dian"

    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_factura_electronica: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_resolucion_facturacion: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    respuesta_proveedor: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cufe: Mapped[str | None] = mapped_column(String, nullable=True)
    uuid_envio_padre: Mapped[uuid_lib.UUID | None] = mapped_column(
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


__all__ = ["EnvioDian"]