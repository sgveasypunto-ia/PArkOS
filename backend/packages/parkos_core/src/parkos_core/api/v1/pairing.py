"""Admin pairing-token HTTP routes (T-PR8-12, design §21.3, REQ-OP-15).

Four cloud-only endpoints (issuer ``admin-``, permission
``gestionar_dian``):

1. ``POST /api/v1/admin/pairing-tokens`` — admin-issued token; response
   returns the plaintext ONCE + the SHA-256 hash + uuid + ``expires_at``.
   Rate-limited to 5/hour per actor (T-PR8-13).
2. ``GET  /api/v1/admin/pairing-tokens/{uuid}`` — read-back. Returns
   the row's audit metadata but STRIPS ``pairing_token_hash`` from the
   JSON output (defense in depth — the server's invariant "the server
   never returns the hash via the public API" is enforced here, not in
   the schema; see the docstring in ``schemas/pairing.py``).
3. ``POST /api/v1/admin/pairing-tokens/{uuid}/revoke`` — replaces the
   spec's forbidden ``DELETE`` route (AGENTS.md §3 forbids DELETE at
   any layer). Inserts a ``revoked_sync_jwts`` row carrying
   ``jwt_kid="pairing_token:<uuid>"`` + ``jwt_uuid=<uuid>`` +
   ``motivo="admin_revoked_at_<ts>"`` + ``expires_at=<row.expires_at>``.
   Returns 204.
4. ``POST /api/v1/admin/sucursales/{uuid}/revoke-sync`` — stub for
   PR8c's sync-router wiring (the sync-router PR consumes this path to
   revoke the branch's persistent ``sync-agent-`` JWT). Returns 501 in
   PR8b — the endpoint is registered so the contract is fixed, but the
   implementation lives in PR8c.

The endpoints depend on ``requires_issuer("admin-")`` +
``require_permission("gestionar_dian")``; the JWT tenant context is
loaded by ``get_tenant_ctx`` (which also enforces the
``X-Sucursal-Context`` header against ``sucursales_permitidas`` for
``admin-`` tokens).

ARCHITECTURAL DEVIATION: the spec lists a ``DELETE`` endpoint for
revocation. Per AGENTS.md §3 (``NO ESTÁ PERMITIDA LA ELIMINACIÓN DE
NINGÚN REGISTRO`` at any layer) + the [A] inmutable trigger on
``pairing_tokens`` (migration 0006) which blocks UPDATE on the row,
the revocation is expressed as a POST-shaped INSERT into
``revoked_sync_jwts``. The static test
``tests/static/test_no_delete_routes.py`` enforces the no-DELETE rule
at the AST + OpenAPI level.

Mount: ``api/v1/__init__.py`` includes this router only on cloud deploy
(belt-and-suspenders with the issuer guard).
"""
from __future__ import annotations

import logging
import uuid as uuid_lib
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_session, requires_issuer
from ...auth.permissions import require_permission
from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...auth.tokens import JWT_OVERLAP_HOURS
from ...models.A.pairing_tokens import PairingToken
from ...repo.pairing import (
    DEFAULT_TTL_HOURS,
    generate_pairing_token,
)
from ...repo.revoked_sync_jwt import revoke_jwt
from ..rate_limit_pairing import (
    PairingTokenRateLimitedError,
    default_limiter,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/pairing-tokens", tags=["admin"])

# Sibling router for the 4th endpoint (sync JWT revoke). Lives in the
# same module so the contract is co-located with the PR8a pairing
# endpoint; both share the same issuer + permission deps.
sync_revoke_router = APIRouter(prefix="/admin/sucursales", tags=["admin"])

_admin_issuer_dep = requires_issuer("admin-")
_manage_perm_dep = require_permission("gestionar_dian")

# Max TTL an admin may request. Bounds the plaintext's lifetime even if
# the operator misconfigures the env; 7 days is generous (typical pair
# happens within minutes of issuance).
MAX_TTL_HOURS: int = 168


# ---------------------------------------------------------------------------
# Request / response shapes (endpoint-local).
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    """Strict ORM mapper; mirrors ``schemas.common._Base`` style."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class PairingTokenIssueRequest(_Base):
    """Body for ``POST /admin/pairing-tokens``.

    ``uuid_sucursal`` is OPTIONAL (the issuance may be pre-branch — the
    model accepts a NULL FK to ``prod.sucursal``). ``ttl_hours`` is
    bounded 1..168 (max 7 days) so a misconfigured admin can't mint a
    long-lived plaintext secret.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    ttl_hours: int = DEFAULT_TTL_HOURS


class PairingTokenIssueResponse(_Base):
    """Response for ``POST /admin/pairing-tokens`` (T-PR8-12 endpoint #1).

    Carries the plaintext ONCE — the server never persists the
    plaintext, so the admin MUST capture it before the response is
    consumed (a re-issue is the only recovery path; the admin revokes
    the old via the /revoke endpoint below).
    """

    token: str  # plaintext — returned ONCE
    pairing_token_uuid: uuid_lib.UUID
    pairing_token_hash: str  # 64-char hex — admin's diagnostic only
    expires_at: datetime
    uuid_sucursal: uuid_lib.UUID | None
    ttl_hours: int


class PairingTokenReadPublic(_Base):
    """Public read shape for ``GET /admin/pairing-tokens/{uuid}``.

    Same as :class:`PairingTokenRead` minus ``pairing_token_hash`` (the
    hash is admin-only diagnostic data — never on the wire). The
    server-side invariant "the server never returns the hash via the
    public API" is enforced here at the endpoint layer (defense in
    depth — the canonical ``PairingTokenRead`` still exposes the
    field for internal callers).
    """

    uuid: uuid_lib.UUID
    # ORM column is ``Date``; the schema exposes it as ``date`` for
    # the public surface.
    fecha_retencion_hasta: date
    created_at: datetime
    created_by: uuid_lib.UUID | None
    uuid_sucursal: uuid_lib.UUID | None
    expires_at: datetime
    used: bool
    used_at: datetime | None
    revoked_at: datetime | None
    revoked_by: uuid_lib.UUID | None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _now_naive() -> datetime:
    """Naive UTC ``datetime`` matching the DB ``timestamp without time zone`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


@router.post(
    "",
    response_model=PairingTokenIssueResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_admin_issuer_dep), Depends(_manage_perm_dep)],
    summary="Issue a 24h pairing token (admin-only, rate-limited 5/hour).",
)
async def issue_pairing_token(
    payload: PairingTokenIssueRequest,
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> PairingTokenIssueResponse:
    """Mint a fresh pairing token. Returns the plaintext ONCE.

    - 429 on the 6th request in a 60-min window per ``actor_uuid``.
    - The response's ``token`` field carries the plaintext; the DB
      stores only the SHA-256 hash. The admin MUST capture the
      plaintext before the response is consumed.
    """
    # TTL bounds — defense against a misconfigured admin minting a
    # year-long plaintext.
    if not 1 <= payload.ttl_hours <= MAX_TTL_HOURS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_ttl_hours",
                "detail": f"ttl_hours must be 1..{MAX_TTL_HOURS}",
            },
        )

    # Rate limit — 5 issuances per hour per admin (T-PR8-13).
    try:
        default_limiter.check(ctx.actor_uuid)
    except PairingTokenRateLimitedError as e:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "pairing_token_rate_limited",
                "detail": f"{e.limit}/hour per admin",
            },
        ) from e

    # Mint locally so the response pairs plaintext + hash together.
    # The repo's ``create_pairing_token`` mints internally but never
    # surfaces the plaintext (correct for the repo contract). For the
    # admin endpoint we mint ONCE here + INSERT the row directly with
    # the matching hash.
    plaintext, sha256_hex = generate_pairing_token()
    now = _now_naive()
    expires_at = now + timedelta(hours=payload.ttl_hours)

    row = PairingToken(
        uuid_sucursal=payload.uuid_sucursal,
        pairing_token_hash=sha256_hex,
        expires_at=expires_at,
        used=False,
        created_by=ctx.actor_uuid,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return PairingTokenIssueResponse(
        token=plaintext,
        pairing_token_uuid=row.uuid,
        pairing_token_hash=sha256_hex,
        expires_at=expires_at,
        uuid_sucursal=row.uuid_sucursal,
        ttl_hours=payload.ttl_hours,
    )


@router.get(
    "/{pairing_token_uuid}",
    response_model=PairingTokenReadPublic,
    dependencies=[Depends(_admin_issuer_dep), Depends(_manage_perm_dep)],
    summary="Read a pairing token's metadata (hash is stripped from JSON).",
)
async def read_pairing_token(
    pairing_token_uuid: uuid_lib.UUID = Path(...),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> PairingTokenReadPublic:
    """Return the row's audit metadata. ``pairing_token_hash`` is NEVER on the wire.

    The full read shape (:class:`PairingTokenRead`) keeps the hash for
    internal callers (audit dashboard, offline replay-protection).
    This public endpoint drops the hash at the serialization boundary
    (defense in depth — the schema permits the field, the endpoint
    filters it).
    """
    row = await _load_pairing_token(session, pairing_token_uuid)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "uuid": str(pairing_token_uuid)},
        )

    # Tenant scope check — the admin's permitted branches filter.
    if (
        row.uuid_sucursal is not None
        and ctx.sucursal_uuid is not None
        and row.uuid_sucursal != ctx.sucursal_uuid
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "tenant_scope_violation"},
        )

    # Build the response manually to strip ``pairing_token_hash``.
    # ``PairingTokenReadPublic`` is the public shape; the ORM row is
    # 1:1 minus the hash column.
    return PairingTokenReadPublic(
        uuid=row.uuid,
        fecha_retencion_hasta=row.fecha_retencion_hasta,
        created_at=row.created_at,
        created_by=row.created_by,
        uuid_sucursal=row.uuid_sucursal,
        expires_at=row.expires_at,
        used=row.used,
        used_at=row.used_at,
        revoked_at=row.revoked_at,
        revoked_by=row.revoked_by,
    )


@router.post(
    "/{pairing_token_uuid}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_admin_issuer_dep), Depends(_manage_perm_dep)],
    summary="Revoke a pairing token (POST-shaped — DELETE forbidden by canon).",
)
async def revoke_pairing_token(
    pairing_token_uuid: uuid_lib.UUID = Path(...),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    """Record the revocation in ``revoked_sync_jwts`` (INSERT, never UPDATE).

    Architectural note: the ``pairing_tokens`` table's inmutable trigger
    blocks UPDATE on the row, so we cannot set ``revoked_at`` +
    ``revoked_by`` directly. Instead, we INSERT a sibling row into
    ``revoked_sync_jwts`` with ``jwt_kid="pairing_token:<uuid>"`` —
    the same lookup the sync-router middleware uses to reject 401 on
    revoked JWTs. The :func:`consume_pairing_token` helper also
    checks via ``is_revoked`` so a revoked token cannot be consumed
    even if its issuance row's ``revoked_at`` is still NULL.

    Returns 204 (idempotent — re-revoking is a UK violation swallowed
    by the repo and still returns 204).
    """
    row = await _load_pairing_token(session, pairing_token_uuid)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "uuid": str(pairing_token_uuid)},
        )

    # Tenant scope check (admin's permitted branches).
    if (
        row.uuid_sucursal is not None
        and ctx.sucursal_uuid is not None
        and row.uuid_sucursal != ctx.sucursal_uuid
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "tenant_scope_violation"},
        )

    now_iso = _now_naive().isoformat()
    result = await revoke_jwt(
        session,
        kid=f"pairing_token:{row.uuid}",
        jwt_uuid=str(row.uuid),
        motivo=f"admin_revoked_at_{now_iso}",
        actor_uuid=ctx.actor_uuid,
        expires_at=row.expires_at,
    )
    if result is None:
        # Duplicate revocation (UK violation caught). The row is
        # already revoked — 204 anyway.
        logger.info("pairing token %s already revoked", row.uuid)
    else:
        logger.info("pairing token %s revoked by %s", row.uuid, ctx.actor_uuid)

    await session.commit()


class _SyncRevokeRequest(_Base):
    """Body for ``POST /admin/sucursales/{uuid}/revoke-sync`` (PR8c wire-up).

    The admin supplies the JWT ``kid`` header + ``jti`` payload claim of
    the branch's currently-issued ``sync-agent-`` token. The cloud
    records the revocation in ``revoked_sync_jwts`` (the [A] inmutable
    trigger blocks UPDATE on ``pairing_tokens`` so all revocations flow
    through this sibling table — see ``repo/pairing.py`` module
    docstring). The branch-side ``sync`` worker drops the JWT from
    ``PARKOS_SYNC_JWT_PATH`` on the next heartbeat via the canonical
    ``is_revoked`` lookup (design §21.3).
    """

    jwt_kid: str = Field(..., min_length=1, max_length=64)
    jwt_uuid: str = Field(..., min_length=1, max_length=64)


@sync_revoke_router.post(
    "/{uuid_sucursal}/revoke-sync",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_admin_issuer_dep), Depends(_manage_perm_dep)],
    summary="Revoke a branch's persistent sync-agent- JWT (PR8c wire-up).",
)
async def revoke_branch_sync_token(
    payload: _SyncRevokeRequest,
    uuid_sucursal: uuid_lib.UUID = Path(...),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    """PR8c wire-up — inserts a ``revoked_sync_jwts`` row for the branch's JWT.

    The cloud has no direct view of the branch's persisted
    ``PARKOS_SYNC_JWT_PATH`` (the file lives on the branch's local
    filesystem), so the admin supplies the ``kid`` + ``jti`` values to
    revoke. The revocation is scoped to (``jwt_kid``, ``jwt_uuid``,
    ``vigente_desde``, ``fecha_retencion_hasta``) per the table's UK —
    duplicate revocations are swallowed by ``revoke_jwt`` (returns
    ``None``) and the endpoint still answers 204 (idempotent).

    The sync-router's ``is_revoked`` lookup catches the revocation on
    the next ``POST /sync/push`` / ``/pull`` / ``/heartbeat`` call
    (returns 401 with ``{"error": "sync_jwt_revoked"}``). ``expires_at``
    is set to ``now + JWT_OVERLAP_HOURS`` (24h) — the JWT's own
    ``exp`` claim may be further out, but the revocation only needs to
    outlast the rotation grace window; once the JWT expires naturally
    the revocation row's filter (``expires_at > now``) drops it from
    the active set.
    """
    now_naive = _now_naive()
    now_iso = now_naive.isoformat()
    expires_at = now_naive + timedelta(hours=JWT_OVERLAP_HOURS)
    result = await revoke_jwt(
        session,
        kid=payload.jwt_kid,
        jwt_uuid=payload.jwt_uuid,
        motivo=f"admin_revoked_at_{now_iso}",
        actor_uuid=ctx.actor_uuid,
        expires_at=expires_at,
    )
    if result is None:
        logger.info(
            "sync-agent JWT (kid=%s jti=%s) already revoked — 204 idempotent",
            payload.jwt_kid,
            payload.jwt_uuid,
        )
    else:
        logger.info(
            "sync-agent JWT (kid=%s jti=%s) revoked by %s for branch %s",
            payload.jwt_kid,
            payload.jwt_uuid,
            ctx.actor_uuid,
            uuid_sucursal,
        )
    await session.commit()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _load_pairing_token(
    session: AsyncSession,
    pairing_token_uuid: uuid_lib.UUID,
) -> PairingToken | None:
    """Load a ``PairingToken`` by uuid (composite PK — uuid is the discriminator).

    Returns the row matching the uuid, ordered by ``fecha_retencion_hasta
    DESC`` so the most recent partition row wins (the partition key
    changes daily; only the current-month partition typically has the
    live row).
    """
    stmt = (
        select(PairingToken)
        .where(PairingToken.uuid == pairing_token_uuid)
        .order_by(PairingToken.fecha_retencion_hasta.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


__all__ = ["router", "sync_revoke_router"]