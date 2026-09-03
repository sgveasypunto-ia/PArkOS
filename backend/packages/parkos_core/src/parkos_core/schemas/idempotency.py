"""Pydantic v2 schemas for ``prod.idempotency_keys`` (PR7, T-PR7-08).

Read-only module — the table is owned by the ``IdempotencyKeyMiddleware``
(see :mod:`parkos_core.repo.idempotency`) and is never written by
client code. ``REVOKE UPDATE, DELETE`` + ``BEFORE UPDATE OR DELETE``
trigger (migration ``0002``) enforce immutability; the single carve-out
is the TTL sweep (nightly ``DELETE WHERE expires_at < NOW()``) which
runs as ``postgres``, not ``rol_app``.

Public-facing names diverge from the ORM column names because the
middleware contract uses different vocabulary:

- ORM ``path`` → schema ``endpoint`` (the logical route path).
- ORM ``request_body_hash`` → schema ``request_payload_hash`` (the
  public name matches the helper signature ``guard(...,
  request_payload_hash=...)``).

The other business columns keep their ORM names (``key_hash``,
``response_status``, ``response_body``, ``expires_at``). The
``:class:`Field` ``alias`` attribute handles the from-ORM mapping
without renaming the JSON contract.

Two shapes are exposed:

- :class:`IdempotencyKeyRead` — full ORM mapping (admin / audit
  dashboards, debugging).
- :class:`IdempotencyKeyListItem` — lightweight list view; the
  ``key_hash_prefix`` field is a display prefix (callers truncate
  before constructing the response) so a full SHA-256 hash never
  leaves the cache table in a list response.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

from pydantic import Field

from .common import _Base

# ---------------------------------------------------------------------------
# IdempotencyKeys ([A] response cache, REQ-OP-04 + design §4.7)
# ---------------------------------------------------------------------------


class IdempotencyKeyRead(_Base):
    """Full read-back for ``prod.idempotency_keys`` (single PK, [A]).

    All ORM columns are exposed (audit + debug). ``endpoint`` and
    ``request_payload_hash`` are aliased to the ORM ``path`` and
    ``request_body_hash`` columns respectively.
    """

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    fecha_retencion_hasta: date | None
    issuer: str | None
    key_hash: str | None
    method: str | None
    endpoint: str | None = Field(default=None, alias="path")
    request_payload_hash: str | None = Field(default=None, alias="request_body_hash")
    response_status: int | None
    response_body: dict | None
    expires_at: datetime | None


class IdempotencyKeyListItem(_Base):
    """Lightweight list shape for ``prod.idempotency_keys``.

    Used by admin / audit dashboards; the full ``key_hash`` (CHAR(64))
    is intentionally NOT exposed — callers truncate it before
    populating this schema (``key_hash_prefix`` is the display
    prefix). The ``endpoint`` and ``key_hash_prefix`` fields are
    aliased to their ORM source attributes for ``from_attributes``
    mapping.
    """

    endpoint: str | None = Field(default=None, alias="path")
    key_hash_prefix: str | None = Field(default=None, alias="key_hash")
    response_status: int | None = None
    expires_at: datetime | None = None


__all__ = [
    "IdempotencyKeyListItem",
    "IdempotencyKeyRead",
]
