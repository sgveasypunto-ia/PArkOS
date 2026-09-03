"""ORM model for ``prod.revoked_sync_jwts`` (REQ-OP-04 + design §21).

Tracks JWT ``kid`` / ``jti`` values that have been explicitly revoked by
an admin (e.g. after a key rotation compromise or a branch decommission).
The sync workers consult this table before accepting a sync token.

``[A]``-class: ``REVOKE UPDATE, DELETE`` from ``rol_app`` and a
``BEFORE UPDATE OR DELETE`` trigger block mutation. Revocations are
append-only: revoking a token a second time would be a no-op (the UK on
``key_uuid`` rejects the duplicate), and there is no UPDATE path.

Single PK on ``uuid`` — this table is NOT partitioned. Volume is bounded
by JWT rotation cadence.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class RevokedSyncJwts(AppendOnlyBase):
    """[A] JWT revocation registry (REQ-OP-04, design §21)."""

    __tablename__ = "revoked_sync_jwts"

    uuid: Mapped[uuid_lib.UUID] = mapped_column(  # type: ignore[override]
        PG_UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    # --- Business columns ---
    # ``key_uuid`` is the JWT ``kid`` (admin-/operador-/sync-agent-) or
    # ``jti`` (per-token id). The UK on this column makes the revocation
    # idempotent — a second revoke attempt raises IntegrityError at the
    # DB level, which the helper maps to a no-op return.
    key_uuid: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    revoked_by: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    __table_args__ = (
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["RevokedSyncJwts"]