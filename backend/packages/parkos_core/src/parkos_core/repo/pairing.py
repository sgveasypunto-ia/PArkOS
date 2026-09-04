"""Pairing-token repo (T-PR8-10, design §21.3, REQ-OP-15).

Tokens are 32 random bytes base64url-encoded (43 chars); only SHA-256
hex digests persist in the DB. The plaintext is returned to the admin
ONCE at issuance and never again. The atomic consume path uses
``SELECT ... FOR UPDATE SKIP LOCKED`` so concurrent session attempts
don't double-spend the token (the loser sees
:class:`PairingTokenConsumedError`).

NOTE on revocation: the ``pairing_tokens`` table is [A] with a
``BEFORE UPDATE OR DELETE`` inmutable trigger (migration 0006), so we
cannot UPDATE the row to set ``revoked_at`` + ``revoked_by``. Instead,
admin revocation is recorded by INSERTing a row into
``prod.revoked_sync_jwts`` with ``jwt_kid="pairing_token:<uuid>"`` +
``jwt_uuid=<token_uuid>`` + ``motivo="admin_revoked_at_<ts>"``. The
``repo/revoked_sync_jwt.is_revoked`` query catches it; the consume
path also checks via ``is_revoked`` so a revoked token cannot be
consumed even if its issuance row's ``revoked_at`` is still NULL.

This deviates from the literal T-PR8-10 spec text "logical revocation
using revoked_at and revoked_by columns" because the [A] inmutable
trigger makes UPDATE impossible (defense in depth — AGENTS.md §1 + §3).
The carve-out was deferred per the PR8a model docstring and the PR8a
audit. PR8b's audit points the conflict; this module docstring is the
canonical record.

The consume path is expressed as a NEW row in ``pairing_tokens``
carrying ``used=True`` + ``used_at`` + ``used_by_branch_info`` (since
UPDATE is blocked). The active row query filters on
``used = False AND expires_at > now`` AND ``NOT IN revoked_sync_jwts``
so the consumed sibling is invisible to subsequent callers. Two rows
with the same ``pairing_token_hash`` coexist (no UK on hash, only the
composite PK ``(uuid, fecha_retencion_hasta)``); the newer
``created_at`` always wins in ``ORDER BY created_at DESC LIMIT 1``
queries.

Cites design §21.3 (REQ-OP-15 single-use consume), REQ-OP-04 (5/hour
admin rate limit lives in ``api/rate_limit_pairing``, this module is
DB-only), §21.13 (the literal "revoked_at" carve-out deferred).
"""
from __future__ import annotations

import hashlib
import secrets
import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.pairing_tokens import PairingToken
from ..schemas.pairing import PairingTokenRead

#: Default token lifetime (24h, design §21.3).
DEFAULT_TTL_HOURS: int = 24


class PairingTokenError(Exception):
    """Base class for pairing-token repo failures."""


class PairingTokenNotFoundError(PairingTokenError):
    """No row matches the supplied plaintext hash."""


class PairingTokenExpiredError(PairingTokenError):
    """The matching row's ``expires_at`` is in the past."""


class PairingTokenConsumedError(PairingTokenError):
    """Already consumed, revoked, cross-branch, or mid-consume elsewhere."""


def _now_naive() -> datetime:
    """Naive UTC ``datetime`` matching the DB ``timestamp without time zone`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def generate_pairing_token() -> tuple[str, str]:
    """Generate a fresh (plaintext, sha256_hex) pair.

    Returns:
        ``(plaintext, sha256_hex)`` — 43-char URL-safe base64 plaintext
        + 64-char hex digest. The plaintext is intended to be returned to
        the admin ONCE in the issuance response; only the hex digest is
        persisted.
    """
    # ``token_urlsafe(32)`` yields a 43-char URL-safe string (no padding).
    plaintext = secrets.token_urlsafe(32)
    sha256_hex = hashlib.sha256(plaintext.encode("ascii")).hexdigest()
    return plaintext, sha256_hex


def hash_pairing_token(plaintext: str) -> str:
    """SHA-256 hex digest of the plaintext (canonical 64-char)."""
    return hashlib.sha256(plaintext.encode("ascii")).hexdigest()


async def create_pairing_token(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID | None,
    ttl_hours: int = DEFAULT_TTL_HOURS,
    actor_uuid: uuid_lib.UUID | None = None,
) -> PairingTokenRead:
    """INSERT a new ``pairing_tokens`` row + return the read-back schema.

    The plaintext is NEVER returned (only the SHA-256 hash + uuid +
    expires_at + metadata). The caller (the admin endpoint) is
    responsible for returning the plaintext to the admin in the SAME
    response payload — the server never persists the plaintext anywhere.

    Args:
        session: Active ``AsyncSession`` (caller commits).
        uuid_sucursal: Branch the token will pair (advisory FK — the
            column is NULLABLE for tokens issued before the branch is
            registered).
        ttl_hours: Token lifetime in hours (default 24, max 168 per the
            admin endpoint).
        actor_uuid: JWT subject — the admin issuing the token.

    Returns:
        :class:`PairingTokenRead` carrying ``pairing_token_hash`` + uuid
        + ``expires_at`` + audit fields. NEVER the plaintext.
    """
    plaintext, sha256_hex = generate_pairing_token()
    now = _now_naive()
    expires_at = now + timedelta(hours=ttl_hours)

    row = PairingToken(
        uuid_sucursal=uuid_sucursal,
        pairing_token_hash=sha256_hex,
        expires_at=expires_at,
        used=False,
        created_by=actor_uuid,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)

    # Note: we deliberately drop ``plaintext`` here — the caller has
    # already lost the only opportunity to surface it to the admin.
    # The repo layer is the wrong place to carry the plaintext across
    # the API surface; the endpoint holds the plaintext in a local
    # variable alongside this return value.
    _ = plaintext
    return PairingTokenRead.model_validate(row)


async def find_active_pairing_token(
    session: AsyncSession,
    plaintext: str,
) -> PairingToken | None:
    """Non-locking lookup of the currently-active row for a plaintext.

    "Active" = ``used = False AND expires_at > now AND NOT IN revoked_sync_jwts``.

    Used by the admin endpoint to inspect tokens; the result is a
    ORM instance (NOT a :class:`PairingTokenRead`) so the endpoint can
    decide which fields to expose (the hash is admin-only).

    Args:
        session: Active ``AsyncSession``.
        plaintext: Raw token from the admin's request.

    Returns:
        The :class:`PairingToken` ORM row, or ``None`` if no row
        matches the hash OR the row is consumed / expired / revoked.
    """
    # Local import — avoids a module-load cycle with revoked_sync_jwt
    # (which depends on this module for nothing but is convenient to
    # keep alongside).
    from .revoked_sync_jwt import is_revoked

    token_hash = hash_pairing_token(plaintext)
    now = _now_naive()

    # Step 1: candidate issuance row (most recent first; the consumed
    # sibling has a later ``created_at`` so it wins when present, but
    # the WHERE clause excludes used=True rows).
    stmt = (
        select(PairingToken)
        .where(
            PairingToken.pairing_token_hash == token_hash,
            PairingToken.used == False,
            PairingToken.expires_at > now,
        )
        .order_by(PairingToken.created_at.desc())
        .limit(1)
    )
    candidate = (await session.execute(stmt)).scalar_one_or_none()
    if candidate is None:
        return None

    # Step 2: revocation gate. The admin-revoked record lives in
    # ``revoked_sync_jwts`` (the [A] inmutable trigger blocks UPDATE
    # on pairing_tokens, so revocation goes through a sibling table —
    # see module docstring).
    if await is_revoked(
        session,
        kid=f"pairing_token:{candidate.uuid}",
        jwt_uuid=str(candidate.uuid),
    ):
        return None

    return candidate


async def consume_pairing_token(
    session: AsyncSession,
    plaintext: str,
    *,
    uuid_sucursal: uuid_lib.UUID,
    branch_info: dict[str, Any] | None = None,
    actor_uuid: uuid_lib.UUID | None = None,
) -> PairingTokenRead:
    """Atomic consume via ``SELECT ... FOR UPDATE SKIP LOCKED``.

    Returns the consumed-row read-back (``used=True`` + ``used_at`` +
    ``used_by_branch_info``). On any rejection, raises a
    :class:`PairingTokenError` subclass.

    The consume is expressed as a NEW row in ``pairing_tokens`` with
    ``used=True`` (the [A] canon forbids UPDATE — see module docstring).
    The issuance row stays at ``used=False``; ``find_active_pairing_token``
    picks the consumed sibling (later ``created_at``) and excludes it via
    the ``used = False`` filter.

    Raises:
        PairingTokenNotFoundError: no row matches the hash.
        PairingTokenExpiredError: row exists but ``expires_at <= now``.
        PairingTokenConsumedError: row exists and is consumed / revoked
            / cross-branch / currently held by another session's
            ``SELECT ... FOR UPDATE SKIP LOCKED``.
    """
    # Local import to keep the module-load order flexible.
    from .revoked_sync_jwt import is_revoked

    token_hash = hash_pairing_token(plaintext)
    now = _now_naive()

    # --- Step 1: existence + status check (non-locking, latest row). ---
    base_stmt = (
        select(PairingToken)
        .where(PairingToken.pairing_token_hash == token_hash)
        .order_by(PairingToken.created_at.desc())
        .limit(1)
    )
    existing = (await session.execute(base_stmt)).scalar_one_or_none()

    if existing is None:
        raise PairingTokenNotFoundError(
            "no pairing token matches the supplied plaintext"
        )
    if existing.used:
        # The consumed sibling is the latest row for this hash.
        raise PairingTokenConsumedError(
            f"pairing token {existing.uuid} already consumed"
        )
    if existing.expires_at <= now:
        raise PairingTokenExpiredError(
            f"pairing token {existing.uuid} expired at "
            f"{existing.expires_at.isoformat()}"
        )

    # --- Step 2: cross-branch gate (don't leak existence). ---
    # When the issuance row's uuid_sucursal is set (the common path),
    # it MUST match the consuming branch. Surface as ConsumedError so
    # we don't reveal whether the token exists for another branch.
    if (
        existing.uuid_sucursal is not None
        and existing.uuid_sucursal != uuid_sucursal
    ):
        raise PairingTokenConsumedError(
            f"pairing token {existing.uuid} does not belong to "
            f"branch {uuid_sucursal}"
        )

    # --- Step 3: revocation gate (admin-revoked via revoked_sync_jwts). ---
    if await is_revoked(
        session,
        kid=f"pairing_token:{existing.uuid}",
        jwt_uuid=str(existing.uuid),
    ):
        raise PairingTokenConsumedError(
            f"pairing token {existing.uuid} revoked"
        )

    # --- Step 4: atomic SKIP LOCKED claim. ---
    lock_stmt = (
        select(PairingToken)
        .where(
            PairingToken.pairing_token_hash == token_hash,
            PairingToken.used == False,
            PairingToken.revoked_at.is_(None),
            PairingToken.expires_at > now,
        )
        .with_for_update(skip_locked=True)
    )
    locked = (await session.execute(lock_stmt)).scalar_one_or_none()
    if locked is None:
        # Another session won the race (SKIP LOCKED returned nothing)
        # OR the row no longer matches (someone revoked between step 1
        # and step 4). Either way: surface as consumed so the caller
        # retries with a fresh token.
        raise PairingTokenConsumedError(
            "pairing token concurrently consumed or unavailable"
        )

    # --- Step 5: INSERT a consumed sibling row. ---
    consumed_row = PairingToken(
        uuid_sucursal=locked.uuid_sucursal,
        pairing_token_hash=locked.pairing_token_hash,
        expires_at=locked.expires_at,
        used=True,
        used_at=now,
        used_by_branch_info=branch_info or {},
        created_by=actor_uuid,
    )
    session.add(consumed_row)
    await session.flush()
    await session.refresh(consumed_row)

    return PairingTokenRead.model_validate(consumed_row)


__all__ = [
    "DEFAULT_TTL_HOURS",
    "PairingTokenConsumedError",
    "PairingTokenError",
    "PairingTokenExpiredError",
    "PairingTokenNotFoundError",
    "consume_pairing_token",
    "create_pairing_token",
    "find_active_pairing_token",
    "generate_pairing_token",
    "hash_pairing_token",
]