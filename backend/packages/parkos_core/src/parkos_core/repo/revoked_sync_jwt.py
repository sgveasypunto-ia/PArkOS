"""Revoked-JWT repo (T-PR8-11, design §21.3, REQ-OP-04).

Used by:

- ``sync_router.py`` middleware (PR8c) to reject 401 on revoked JWTs.
- ``repo/pairing.py`` to gate admin-revoked pairing tokens (the
  pairing_tokens [A] inmutable trigger blocks UPDATE so the revocation
  flows through this table — see pairing.py module docstring for the
  architectural rationale).

Per §21.3 the canonical lookup is::

    SELECT 1 FROM prod.revoked_sync_jwts
    WHERE jwt_kid = :k AND jwt_uuid = :j
      AND expires_at IS NOT NULL
      AND expires_at > NOW()

The ``expires_at`` filter is intentionally a server-side comparison
(via :func:`datetime.now(UTC).replace(tzinfo=None)`) — the table's
``expires_at`` column is ``timestamp without time zone`` so a naive
UTC datetime is the right shape.

The UK on ``(jwt_kid, jwt_uuid, vigente_desde, fecha_retencion_hasta)``
makes duplicate revocations fail with an ``IntegrityError`` (we catch
it and return silently — a no-op revocation is a 204, not an error).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.revoked_sync_jwts import RevokedSyncJwt


def _now_naive() -> datetime:
    """Naive UTC ``datetime`` matching the DB ``timestamp without time zone`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


async def revoke_jwt(
    session: AsyncSession,
    *,
    kid: str,
    jwt_uuid: str,
    motivo: str,
    actor_uuid: uuid_lib.UUID | None,
    expires_at: datetime,
) -> RevokedSyncJwt | None:
    """INSERT a new ``revoked_sync_jwts`` row (T-PR8-11).

    The UK on ``(jwt_kid, jwt_uuid, vigente_desde, fecha_retencion_hasta)``
    rejects duplicates. PR8b treats a duplicate as a successful no-op:
    the admin endpoint returns 204 regardless (re-revoking is idempotent).

    Args:
        session: Active ``AsyncSession`` (caller commits).
        kid: JWT ``kid`` header. For pairing-token revocations, use
            ``"pairing_token:<token_uuid>"`` (see ``repo.pairing``).
        jwt_uuid: JWT ``jti`` payload claim. For pairing-token
            revocations, use ``str(token_uuid)``.
        motivo: Free-text reason (e.g. ``"admin_revoked_at_<ts>"``).
        actor_uuid: Admin JWT subject — audit-only, NULL for system
            revocations.
        expires_at: When the revocation naturally expires and the
            middleware stops checking this entry (typically the JWT's
            own ``exp``).

    Returns:
        The new :class:`RevokedSyncJwt` row, or ``None`` if a duplicate
        already exists (UK violation caught and swallowed).
    """
    row = RevokedSyncJwt(
        jwt_kid=kid,
        jwt_uuid=jwt_uuid,
        motivo=motivo,
        revoked_by=actor_uuid,
        expires_at=expires_at,
        created_by=actor_uuid,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        # Duplicate revocation — UK violation on
        # (jwt_kid, jwt_uuid, vigente_desde, fecha_retencion_hasta).
        # Roll back the failed INSERT; the previous revocation row is
        # still in place and serves the same gate. Return None so the
        # caller knows it was a no-op.
        await session.rollback()
        return None
    await session.refresh(row)
    return row


async def is_revoked(
    session: AsyncSession,
    *,
    kid: str,
    jwt_uuid: str,
) -> bool:
    """Return ``True`` if the (kid, jwt_uuid) pair is currently revoked.

    Mirrors §21.3's canonical lookup. ``expires_at IS NOT NULL`` is
    asserted to keep nullability strict; the > NOW() predicate is
    enforced at the application side (naive UTC) so the test can stub
    the clock.

    Args:
        session: Active ``AsyncSession``.
        kid: JWT ``kid`` header.
        jwt_uuid: JWT ``jti`` payload claim.

    Returns:
        ``True`` if a non-expired revocation row exists.
    """
    now = _now_naive()
    stmt = select(RevokedSyncJwt.uuid).where(
        RevokedSyncJwt.jwt_kid == kid,
        RevokedSyncJwt.jwt_uuid == jwt_uuid,
        RevokedSyncJwt.expires_at.is_not(None),
        RevokedSyncJwt.expires_at > now,
    ).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


__all__ = [
    "is_revoked",
    "revoke_jwt",
]