"""Pydantic v2 schemas for ``prod.pairing_tokens`` (T-PR8-08, design §21.3).

Five shapes:

- :class:`PairingTokenRead` — read-back for admin tooling. Mirrors the
  ORM 1:1 and INCLUDES ``pairing_token_hash`` because admin audit /
  replay-protection tooling needs the hash. PR8b's
  ``GET /admin/pairing-tokens/{uuid}`` endpoint MUST filter this field
  before serializing to the API surface (the spec's invariant: server
  never returns the hash via the public API).
- :class:`PairingTokenReadListItem` — list view; the
  ``pairing_token_hash_prefix`` is a display-only slice of the hash
  (callers truncate before populating), so the full hash never leaves
  the cache table in a list response. Mirrors the
  ``IdempotencyKeyListItem`` pattern.
- :class:`PairingTokenCreate` — admin-issuer only. Excludes
  ``pairing_token_hash`` (server-computed from a fresh token),
  ``used*`` (defaults to ``False``), ``revoked_*`` (the [A] canon
  keeps the table append-only; revocation is expressed via a new
  row, not a partial update here).
- :class:`PairingTokenFilter` — all-optional filter for list queries.
- :class:`PairingTokenReadList` — cursor-paginated list shape.

No ``Update`` shape — the [A] canon closes mutation: revoke-path
expressions land as new rows in the same table or are deferred to
PR8b's Postgres-role carve-out.

All schemas inherit :class:`_Base` (strict ORM mapper,
``extra='forbid'``).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

from pydantic import Field

from .common import FilterBase, ReadListBase, _Base

# ---------------------------------------------------------------------------
# PairingToken ([A] admin-issued token, design §21.3, REQ-OP-04)
# ---------------------------------------------------------------------------


class PairingTokenRead(_Base):
    """Full read-back for ``prod.pairing_tokens`` (composite PK, [A]).

    INCLUDES ``pairing_token_hash`` because admin tooling (the audit
    dashboard, the offline replay-protection tool) needs the digest.
    PR8b's public ``GET /admin/pairing-tokens/{uuid}`` endpoint MUST
    drop this field before serializing — the spec invariant
    "server never returns the hash via the public API" is enforced at
    the endpoint layer (defense in depth: the schema permits the hash
    for internal callers that legitimately need it).

    The plaintext is NEVER in this schema — it is returned ONCE at
    issuance (``PairingTokenCreate`` response in PR8b) and never again.
    """

    uuid: uuid_lib.UUID
    fecha_retencion_hasta: date
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    uuid_sucursal: uuid_lib.UUID | None
    pairing_token_hash: str
    expires_at: datetime
    used: bool
    used_at: datetime | None
    used_by_branch_info: dict | None
    revoked_at: datetime | None
    revoked_by: uuid_lib.UUID | None


class PairingTokenReadListItem(_Base):
    """Lightweight list shape for ``prod.pairing_tokens``.

    Used by the admin / audit dashboards; the full
    ``pairing_token_hash`` (CHAR(64)) is intentionally NOT exposed —
    callers truncate it before populating this schema so a full
    SHA-256 hash never leaves the cache table in a list response.
    Mirrors ``IdempotencyKeyListItem`` (the same pattern for
    ``key_hash``).
    """

    uuid: uuid_lib.UUID
    fecha_retencion_hasta: date
    uuid_sucursal: uuid_lib.UUID | None
    expires_at: datetime
    used: bool
    revoked_at: datetime | None = None
    pairing_token_hash_prefix: str | None = Field(
        default=None,
        alias="pairing_token_hash",
    )


class PairingTokenCreate(_Base):
    """Create shape for ``prod.pairing_tokens`` (admin-issuer only).

    The plaintext token is generated on the SERVER side in PR8b's
    ``repo/pairing.py::create_pairing_token``; this shape only carries
    the issuance metadata. Excluded columns:

    - ``pairing_token_hash`` — server-computed (sha256 of plaintext).
    - ``used`` + ``used_at`` + ``used_by_branch_info`` — set to
      ``False`` / ``NULL`` at creation; populated by the consume path.
    - ``revoked_at`` + ``revoked_by`` — [A] canon keeps the table
      append-only; revocation is expressed as a new row by PR8b's
      Postgres-role carve-out helper, not via partial update here.
    - ``vigente_*`` versioning columns — apply to [V]/[L] only; the
      [A] base uses composite PK + retention, not versioning.
    - ``created_at`` + ``created_by`` — server-set from the audit mixin.
    - ``sync_status`` + ``sync_timestamp`` + ``sync_attempts`` — set
      when the sync engine claims the row (PR8b's
      ``repo/sync_outbox`` helper).
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    expires_at: datetime


class PairingTokenFilter(FilterBase):
    """All-optional filter for ``prod.pairing_tokens`` list queries.

    Callers may combine any subset; the empty filter returns every
    row (paginated). Date ranges use half-open ``[start, end)``
    semantics — the same convention the rest of the codebase uses
    for retention / partitioning time windows.
    """

    uuid: uuid_lib.UUID | None = None
    uuid_sucursal: uuid_lib.UUID | None = None
    used: bool | None = None
    revoked: bool | None = None  # tri-state: True=revoked, False=active, None=either
    expires_after: datetime | None = None
    expires_before: datetime | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None


class PairingTokenReadList(ReadListBase[PairingTokenReadListItem]):
    """Cursor-paginated list shape for ``prod.pairing_tokens``.

    Parameterizes :class:`ReadListBase` with
    :class:`PairingTokenReadListItem` (list-view; the hash prefix, not
    the full hash). Callers that need the full read should hit
    ``GET /admin/pairing-tokens/{uuid}`` (lands in PR8b) which returns
    :class:`PairingTokenRead` minus the hash field.
    """



__all__ = [
    "PairingTokenCreate",
    "PairingTokenFilter",
    "PairingTokenRead",
    "PairingTokenReadList",
    "PairingTokenReadListItem",
]
