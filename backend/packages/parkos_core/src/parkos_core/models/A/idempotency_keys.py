"""ORM model for ``prod.idempotency_keys`` (REQ-OP-04 + design §8).

Caches HTTP responses keyed by ``sha256(issuer + ":" + idem_key)``. The
middleware checks this table on every POST; on a hit within the 24h TTL
it replays the cached response, on a hit past the TTL it returns 410
Gone, and on a miss it lets the request through and writes the row on
response.

``[A]``-class: ``REVOKE UPDATE, DELETE`` from ``rol_app`` and a
``BEFORE UPDATE OR DELETE`` trigger block mutation. The single carve-out
is the TTL sweep (nightly ``DELETE WHERE expires_at < NOW()``) which
runs as the ``postgres`` role, not ``rol_app``.

Single PK on ``uuid`` — this table is NOT partitioned. Idempotency keys
expire within 24h; volume is bounded.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import CHAR, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class IdempotencyKeys(AppendOnlyBase):
    """[A] Idempotency-Key response cache (REQ-OP-04, design §8)."""

    __tablename__ = "idempotency_keys"

    uuid: Mapped[uuid_lib.UUID] = mapped_column(  # type: ignore[override]
        PG_UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    # --- Business columns ---
    # ``issuer`` identifies which JWT issuer minted the request
    # (``admin-``, ``operador-``, ``sync-agent-``). Together with
    # ``key_hash`` it forms the cache lookup key.
    issuer: Mapped[str | None] = mapped_column(String(length=32), nullable=True)
    key_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    method: Mapped[str | None] = mapped_column(String(length=16), nullable=True)
    path: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    request_body_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
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


__all__ = ["IdempotencyKeys"]