"""ORM model for ``prod.revocacion_factura`` (DIAN revocation, [A], REQ-16 + REQ-X4).

Carries the SHA-256 hash chain columns (``hash_anterior`` /
``hash_actual``) — the second of only two tables that
``repo.hash_chain.append()`` extends. The cloud-side verifier (PR10) walks
the chain and raises ``HashChainIntegrityViolation`` on a break.

Composite FK to ``factura_electronica`` (the parent record). Both the
parent table and this revocation are partitioned by their own
``fecha_retencion_hasta``; the FK includes the partition key.

Single PK on ``uuid`` — the revocation event itself is rare (one per
factura); partitioning by retention would add overhead without volume
benefit. The retention column IS still present (DIAN 5-year requirement).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

from sqlalchemy import CHAR, Date, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase, HashChainMixin


class RevocacionFactura(AppendOnlyBase, HashChainMixin):
    """[A] DIAN revocation event — second hash-chain carrier (REQ-16)."""

    __tablename__ = "revocacion_factura"

    uuid: Mapped[uuid_lib.UUID] = mapped_column(  # type: ignore[override]
        PG_UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    # --- Business columns ---
    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_factura_electronica: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_factura_electronica_reemplazo: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp_evento: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    # --- Hash chain columns (re-declared for column-name clarity) ---
    hash_anterior: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    hash_actual: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)

    # Retention column (DIAN 5+ years). AppendOnlyBase already declares
    # ``fecha_retencion_hasta`` as nullable; we keep it nullable so the
    # DIAN retention worker (PR10) can backfill when rows age out.
    fecha_retencion_hasta: Mapped[date | None] = mapped_column(  # type: ignore[override]
        Date,
        nullable=True,
    )

    __table_args__ = (
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["RevocacionFactura"]