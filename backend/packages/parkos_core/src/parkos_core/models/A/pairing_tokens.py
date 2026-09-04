"""ORM model for ``prod.pairing_tokens`` (T-PR8-05, design §21.3).

Cloud-side [A] table for short-lived (24h) admin-issued pairing tokens.
A branch presents the plaintext token ONCE in the ``POST /sync/pair``
body; the cloud verifies ``sha256(plaintext) == pairing_token_hash``,
mints a long-lived ``sync-agent-`` JWT, and persists it to
``PARKOS_SYNC_JWT_PATH`` on the branch (chmod 0o600). Subsequent
boots skip pairing.

PLAIN-TEXT NEVER PERSISTS in this table — only the SHA-256 hex digest
(``String(64)``). The plaintext is returned to the admin ONCE at
issuance time and never again; admins who lose it must mint a new
token and revoke the old one via the [``DELETE``] admin endpoint
(PR8b's ``POST /admin/sucursales/{uuid_sucursal}/revoke-sync``).

Composite primary key (``uuid``, ``fecha_retencion_hasta``) — required
by ``pg_partman`` range partitioning. We override IdMixin's
``primary_key=True`` on ``uuid`` so the composite PK takes effect
(mirrors ``log_transaccional.py``).

``[A]``-class: ``REVOKE UPDATE, DELETE`` from ``rol_app`` and a
``BEFORE UPDATE OR DELETE`` trigger block mutation, with the future
PR8b carve-out for revocation via a separate non-[A] helper
(postgres-role out-of-band). For now the table is strictly
append-only; revocation is expressed as a new row in this same table.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    PrimaryKeyConstraint,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class PairingToken(AppendOnlyBase):
    """[A] Admin-issued pairing token (24h TTL) — design §21.3, REQ-OP-04.

    INSERT-only: REVOKE UPDATE, DELETE FROM rol_app is asserted by
    migration 0006. The BEFORE UPDATE OR DELETE trigger raises
    ``PAIRING_TOKENS_INMUTABLE`` on any mutation attempt.

    Composite PK (``uuid``, ``fecha_retencion_hasta``) for pg_partman
    range partitioning by monthly retention (DIAN-style 5-year
    retention even though these are short-lived; a 24h token is cheap
    to retain 5 years and the audit value is non-zero).
    """

    __tablename__ = "pairing_tokens"

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
    # ``uuid_sucursal`` is NULLABLE on purpose: a token issued before the
    # branch is registered (early-boot admin tooling) still needs to be
    # valid. The FK stays advisory so a deleted branch's history is
    # still inspectable in audit.
    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prod.sucursal.uuid"),
        nullable=True,
    )
    # ``pairing_token_hash`` = sha256(plaintext), hex-encoded CHAR(64).
    # The plaintext is returned ONCE at issuance and never again; the
    # server never re-hashes for any purpose (defense in depth — even a
    # rogue admin cannot recover the plaintext from the row).
    pairing_token_hash: Mapped[str] = mapped_column(String(length=64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("FALSE"),
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    # ``used_by_branch_info`` captures the branch's bootstrap metadata
    # at consume time: ``{hostname, os, version, endpoint_url}``. Stored
    # as JSONB so the cloud's audit dashboard can render it without
    # knowing the schema ahead of time.
    used_by_branch_info: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # The cancellation fields (``revoked_at`` / ``revoked_by``) track
    # the admin who revoked the token. Per spec, the [A] canon keeps
    # the table append-only — revocation is expressed via a new row in
    # this same table (with ``used=True`` set) until the carve-out
    # (PR8b) lands. The columns exist here for forward compatibility.
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    revoked_by: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prod.usuarios.uuid"),
        nullable=True,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "uuid",
            "fecha_retencion_hasta",
            name="pairing_tokens_pk",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
            "postgresql_partition_by": "RANGE (fecha_retencion_hasta)",
        },
    )


__all__ = ["PairingToken"]
