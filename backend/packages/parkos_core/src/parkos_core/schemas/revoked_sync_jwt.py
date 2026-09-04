"""Pydantic v2 schemas for ``prod.revoked_sync_jwts`` (T-PR8-09, design §21.3).

Single read shape — :class:`RevokedSyncJwtRead` — because the table is
strictly [A]-append-only: revocations are INSERT-only (the UK on
``(jwt_kid, jwt_uuid, vigente_desde, fecha_retencion_hasta)`` rejects
duplicates as a no-op). No Create / Update / Filter shapes are
required by the bi-temporal canon — the canonical write path is
``repo/revoked_sync_jwt.py::revoke_jwt`` (lands in PR8b) which
populates every business column server-side.

Read shape mirrors the ORM 1:1 (including ``vigente_desde`` which
the bi-temporal canon requires in the UK). Inherits :class:`_Base`
(``extra='forbid'``, ``from_attributes=True``) from
:mod:`parkos_core.schemas.common`.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

from .common import _Base

# ---------------------------------------------------------------------------
# RevokedSyncJwt ([A] JWT revocation registry, REQ-OP-04, design §21)
# ---------------------------------------------------------------------------


class RevokedSyncJwtRead(_Base):
    """Full read-back for ``prod.revoked_sync_jwts`` (composite PK, [A]).

    The 5 business columns exposed:

    - ``jwt_kid`` — JWT ``kid`` header (admin-/operador-/sync-agent-
      authority identifier)
    - ``jwt_uuid`` — JWT ``jti`` payload claim (per-token id)
    - ``expires_at`` — when the revocation naturally expires (and the
      middleware stops checking this row)
    - ``revoked_by`` — admin UUID who issued the revocation
    - ``motivo`` — free-text reason recorded for audit

    Plus the audit + sync bookkeeping from :class:`AuditMixin` /
    :class:`SyncMixin`, and the explicit ``vigente_desde`` column
    (added so the UK can include it per the bi-temporal canon;
    server-defaulted to ``NOW()``).
    """

    uuid: uuid_lib.UUID
    fecha_retencion_hasta: date
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    vigente_desde: datetime
    jwt_kid: str
    jwt_uuid: str
    expires_at: datetime
    revoked_by: uuid_lib.UUID | None
    motivo: str | None


__all__ = ["RevokedSyncJwtRead"]
