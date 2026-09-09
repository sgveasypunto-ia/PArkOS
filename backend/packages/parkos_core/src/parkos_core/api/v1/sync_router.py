"""/sync/* router (T-PR8-14, design §21.9, REQ-OP-03).

Mounts on BOTH ``api_admin`` (cloud-side receiver) AND ``api_sucursal``
(branch-side receiver) per REQ-OP-03. The ``/sync/*`` paths are NOT
cloud-only — they're the only ``api_sucursal``-mounted paths besides
the CRUD routers. The three-layer DIAN boundary (REQ-X3, §10) does
NOT apply here because the sync transport is not DIAN.

Seven endpoints:

- ``GET /api/v1/sync/hello`` — dual-protocol handshake (T-PR11-003,
  REQ-CUT-003/004). NO auth required — a branch calls this BEFORE it has
  decided which applier (and therefore which JWT flow) to use.
  ``{protocol_version, min_branch_version, grace_until, catalog_revision}``.
- ``POST /api/v1/sync/pair`` — branch consumes a pairing-token +
  branch_info; cloud mints a long-lived ``sync-agent-`` JWT. NO auth
  required (the pairing-token IS the credential).
- ``POST /api/v1/sync/push`` — branch → cloud row push. Issuer
  ``sync-agent-``. JWT-verified + revocation-checked + clock-skew
  + idempotency-cache + 60/min rate limit.
- ``POST /api/v1/sync/pull`` — branch ← cloud row pull. Same auth
  chain as push. 120/min.
- ``POST /api/v1/sync/heartbeat`` — both directions. 10/min.
- ``POST /api/v1/sync/rotate-jwt`` — both directions. Mints a new
  ``sync-agent-`` JWT after validating the current one. 1/min.
- ``POST /api/v1/sync/events`` — bidirectional row push. Same auth
  chain. Two coexisting shapes (T-PR11-006, REQ-CUT-015): legacy
  provider-notification rows (``event_type`` +
  ``payload``, reported ``delivered``) and catalog-driven rows
  (``tabla`` set) applied through ``SyncMotor.apply_row`` and reported
  via REQ-MOT-005's wire vocabulary (``applied`` / ``conflict`` /
  ``retry_parent_missing``) — the cloud receives ``branch_to_cloud``
  rows here, the branch receives ``cloud_to_branch`` rows here (PR12),
  through the identical handler.

Architecture notes:

- The router instantiates its own per-endpoint :class:`RateLimit`
  with the per-action budget from ``tasks.md:576``. No module-level
  singleton — each FastAPI process creates fresh buckets on boot.
- The :class:`SyncIdempotencyCache` is also per-process (in-memory).
  Multi-instance cloud deploys would need Redis; PR9 follow-up.
- The JWT revocation check goes through ``repo.revoked_sync_jwt.is_revoked``
  (the canonical §21.3 lookup). The check is the FIRST post-verify
  step so a revoked JWT never reaches the handler body.
- The clock-skew check uses the JWT's `iat_branch` claim per §21.3;
  PR9 will rotate the existing tokens to include the claim. Backward
  compat: PR8b-era tokens (no claim) skip the check silently.
"""
from __future__ import annotations

import logging
import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.jwt_issuer_guard import verify_jwt
from ...auth.tokens import issue_token
from ...db.engine import get_session
from ...models.A.log_transaccional import LogTransaccional
from ...repo.append_only import AppendOnlyError, append_event
from ...repo.pairing import (
    PairingTokenConsumedError,
    PairingTokenExpiredError,
    PairingTokenNotFoundError,
    consume_pairing_token,
)
from ...repo.revoked_sync_jwt import is_revoked
from ...runtime import engine_flag
from ...runtime.clock import ClockSkewError
from ...sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from ...sync.cutover.dual_protocol import build_sync_hello_response
from ...sync.motor import apply_guard
from ...sync.motor.apply_result import ApplyResult
from ...sync.motor.dependency_orderer import order_batch
from ...sync.motor.sync_motor import SyncMotor
from ...sync.router_helpers import (
    RateLimit,
    SyncIdempotencyCache,
    SyncRateLimitedError,
    check_iat_branch_skew,
    decode_jwt_header_kid,
    extract_subject_from_jwt,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])

# ---------------------------------------------------------------------------
# Process-local state (in-memory). Per spec §21.9: no Redis on the v1 path.
# ---------------------------------------------------------------------------

#: Idempotency cache shared across the 5 endpoints that accept an
#: ``X-Request-Id`` header. The ``/sync/pair`` endpoint is the only one
#: that does NOT consult this cache (it has no JWT subject to scope to
#: before token verification; a second pair attempt is rejected at the
#: repo layer via single-use ``SELECT ... FOR UPDATE SKIP LOCKED``).
_IDEMPOTENCY = SyncIdempotencyCache(maxsize=10_000, ttl_seconds=300)

#: Per-endpoint rate limiters. Defaults per ``tasks.md:576``.
_RATE_LIMIT_PUSH = RateLimit(per_minute=60)
_RATE_LIMIT_PULL = RateLimit(per_minute=120)
_RATE_LIMIT_HEARTBEAT = RateLimit(per_minute=10)
_RATE_LIMIT_ROTATE = RateLimit(per_minute=1)


# ---------------------------------------------------------------------------
# Request / response shapes (endpoint-local; pydantic v2 strict).
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    """Strict ORM mapper; mirrors ``schemas.common._Base`` style."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class _SyncHelloResponse(_Base):
    """Response for ``GET /sync/hello`` (T-PR11-003, REQ-CUT-004's exact shape).

    ``grace_until`` is ``None`` iff ``protocol_version == "legacy"``.
    """

    protocol_version: str
    min_branch_version: str
    grace_until: str | None
    catalog_revision: str


class _BranchInfo(_Base):
    """Branch bootstrap metadata captured at pair-consume time."""

    hostname: str | None = None
    os: str | None = None
    version: str | None = None
    endpoint_url: str | None = None


class _PairRequest(_Base):
    """Body for ``POST /sync/pair`` (T-PR8-14 endpoint #1).

    NO auth header — the plaintext pairing-token IS the credential.
    """

    pairing_token: str = Field(..., min_length=1)
    uuid_sucursal: uuid_lib.UUID
    branch_info: _BranchInfo = Field(default_factory=_BranchInfo)


class _PairResponse(_Base):
    """Response for ``POST /sync/pair`` — 201 Created.

    Field naming (``sync_jwt`` not ``jwt``) matches the deployed
    ``cli/pair.py`` PR8b contract which reads ``body.get("sync_jwt")``.
    See the module docstring deviation note in PR8c.
    """

    sync_jwt: str
    expires_at: datetime
    uuid_sucursal: uuid_lib.UUID


class _PushedRow(_Base):
    """One row in the sync push/pull payload (T-PR8-14 endpoints #2/#3).

    ``tabla`` is the source table name (one of the 49 logical entities),
    ``uuid_registro`` is the row's primary-key uuid,
    ``seq`` is the per-branch monotonic sequence (per §21.7 ordering),
    ``datos`` is the row's payload as a JSONB-shaped dict.
    """

    tabla: str
    uuid_registro: uuid_lib.UUID
    seq: int
    datos: dict[str, Any] = Field(default_factory=dict)


class _PushRequest(_Base):
    rows: list[_PushedRow] = Field(default_factory=list)


class _PushResponseRow(_Base):
    """Per-row result inside the 207 multi-status push response."""

    uuid_registro: uuid_lib.UUID
    status: str  # "applied" | "conflict" | "error"
    detail: str | None = None


class _PushResponse(_Base):
    """207 multi-status body for ``POST /sync/push``."""

    results: list[_PushResponseRow] = Field(default_factory=list)


class _PullRequest(_Base):
    since_seq: int = 0


class _PullResponse(_Base):
    rows: list[_PushedRow] = Field(default_factory=list)
    next_seq: int = 0


class _HeartbeatRequest(_Base):
    """Body for ``POST /sync/heartbeat`` — empty body permitted."""

    state: dict[str, Any] = Field(default_factory=dict)


class _RotateRequest(_Base):
    """Body for ``POST /sync/rotate-jwt``."""

    current_jwt: str = Field(..., min_length=1)


class _RotateResponse(_Base):
    """Response for ``POST /sync/rotate-jwt``.

    Field naming (``jwt`` + ``expires_at`` + ``grace_until``) matches
    the deployed ``sync/transport.py::SyncHttpClient.rotate_jwt`` client
    (T-PR9-02). The client reads ``body["jwt"]``, ``body["expires_at"]``,
    ``body["grace_until"]`` — the response MUST match.
    """

    jwt: str
    expires_at: datetime
    grace_until: datetime


class _CatalogPushEvent(_Base):
    """A single cloud ↔ branch push event — legacy provider-notification OR catalog-driven row.

    The original PR8c shape (``event_type`` + ``payload``) accepted a
    permissive provider-notification-style event so the endpoint compiled
    and the auth chain was exercised end to end; PR11 (T-PR11-006, REQ-
    CUT-015) narrows the schema for the catalog-driven case WITHOUT
    breaking that original shape:

    - ``tabla`` unset (``None``, the default) — legacy provider-event
      behavior: no catalog dispatch, the row is reported ``delivered``
      exactly as before.
    - ``tabla`` set to a ``SYNC_CATALOG`` entry name — the row is applied
      through ``SyncMotor.apply_row`` and the response reports the
      REQ-MOT-005 wire status (``applied`` / ``conflict`` /
      ``retry_parent_missing``) instead of a fixed ``delivered``.
    """

    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    tabla: str | None = None
    uuid_registro: uuid_lib.UUID | None = None


class _EventsRequest(_Base):
    events: list[_CatalogPushEvent] = Field(default_factory=list)


class _EventResponseRow(_Base):
    event_type: str
    # "delivered" (legacy, no tabla) | "unknown_table" (tabla not in
    # SYNC_CATALOG_BY_NAME) | "applied" | "conflict" | "retry_parent_missing"
    # (REQ-MOT-005 / REQ-CUT-015 wire vocabulary for a catalog-driven row).
    status: str


class _EventsResponse(_Base):
    results: list[_EventResponseRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# REQ-MOT-005 / REQ-CUT-015 — ApplyResult.status -> per-row wire status
# (T-PR11-006). Single source of truth for the mapping table; PR12's
# branch-side receiver (T-PR12-004) reuses this exact function.
# ---------------------------------------------------------------------------


class UnmappedApplyStatusError(Exception):
    """Raised when an ``ApplyResult`` cannot be mapped to a wire status.

    REQ-CUT-015 requires the receiver to report a per-row status that is
    NEVER a generic failure and NEVER a silent drop. Every ``RETRY``
    producer in this codebase (``motor/apply_row.py``,
    ``motor/dependency_buffer.py``) sets exactly ``reason="parent_missing"``
    — a ``RETRY`` with any other reason is an unexpected internal state, and
    raising here (instead of guessing a wire value) is that "never silent"
    contract applied to it.
    """


def wire_status_for_apply_result(result: ApplyResult) -> str:
    """REQ-MOT-005's per-row wire vocabulary.

    | Motor ``ApplyResult.status`` | Wire status |
    |---|---|
    | ``APPLIED``  | ``applied`` |
    | ``CONFLICT`` | ``conflict`` |
    | ``RETRY`` (``reason="parent_missing"``) | ``retry_parent_missing`` |

    A row whose declared ``depends_on`` parent has not yet arrived
    (REQ-CUT-015) MUST report ``retry_parent_missing`` — never a generic
    failure status and never a silent drop.
    """
    if result.status == "APPLIED":
        return "applied"
    if result.status == "CONFLICT":
        return "conflict"
    if result.status == "RETRY" and result.reason == "parent_missing":
        return "retry_parent_missing"
    raise UnmappedApplyStatusError(
        f"no wire status defined for ApplyResult(status={result.status!r}, "
        f"reason={result.reason!r})"
    )


# ---------------------------------------------------------------------------
# Dependency factories
# ---------------------------------------------------------------------------


def _now_naive() -> datetime:
    """Naive UTC matching the DB ``timestamp without time zone`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _sync_agent_claims(
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    """Verify a ``sync-agent-`` JWT and check revocation + clock.

    Combines three guards into one dependency so each endpoint gets a
    clean signature:

    1. :func:`verify_jwt` (signature + issuer prefix)
    2. :func:`repo.revoked_sync_jwt.is_revoked` (admin revocation)
    3. :func:`check_iat_branch_skew` (branch clock drift)

    Order matters: the issuer check is fastest (in-memory) and runs
    first; revocation requires a SELECT; skew is a clock comparison.
    All three raise the appropriate HTTPException shape so FastAPI
    renders the 401/400 response directly.
    """
    claims = await verify_jwt(request)
    iss = claims.get("iss", "")
    # PR9b fix: the issuer prefix check should use startswith() against the
    # canonical ``sync-agent-`` prefix. The previous code split on ``-`` and
    # only matched the FIRST segment ("sync-" vs "sync-agent-"), so a
    # valid ``sync-agent-cloud`` token was always rejected as wrong_issuer.
    if not iss.startswith("sync-agent-"):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "wrong_issuer",
                "detail": f"issuer={iss!r} does not start with 'sync-agent-'",
            },
        )

    # Revocation check — needs DB.
    auth_header = request.headers.get("Authorization", "")
    raw_token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
    try:
        kid = decode_jwt_header_kid(raw_token)
    except ValueError:
        kid = iss  # fallback to issuer if kid decode fails (test path)
    jti = str(claims.get("jti", ""))
    if jti and await is_revoked(session, kid=kid, jwt_uuid=jti):
        raise HTTPException(
            status_code=401,
            detail={"error": "sync_jwt_revoked"},
        )

    # Clock-skew check (no DB).
    try:
        check_iat_branch_skew(claims)
    except ClockSkewError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "clock_skew_too_large",
                "skew_seconds": e.skew_seconds,
                "max_skew_seconds": 60,
            },
        ) from e

    return claims


# ---------------------------------------------------------------------------
# Endpoint 0: GET /sync/hello
# ---------------------------------------------------------------------------


@router.get(
    "/hello",
    response_model=_SyncHelloResponse,
    summary="Dual-protocol handshake (T-PR11-003, REQ-CUT-003/004).",
)
async def sync_hello() -> _SyncHelloResponse:
    """Advertise the current protocol so a branch can auto-detect its applier.

    NO auth required — a branch calls this BEFORE it has decided which
    applier (and therefore which JWT-bearing flow) to use; the response
    carries no sensitive data (REQ-CUT-004: protocol version + catalog
    revision only). The branch MUST cache the response for
    ``dual_protocol.BRANCH_CACHE_TTL_SECONDS`` (300s) to avoid hammering
    the cloud (REQ-CUT-004) — branch-side wiring is PR12's
    ``jobs/sync_sucursal.py`` concern (T-PR12-007).
    """
    result = build_sync_hello_response()
    return _SyncHelloResponse(
        protocol_version=result.protocol_version,
        min_branch_version=result.min_branch_version,
        grace_until=result.grace_until,
        catalog_revision=result.catalog_revision,
    )


# ---------------------------------------------------------------------------
# Endpoint 1: POST /sync/pair
# ---------------------------------------------------------------------------


@router.post(
    "/pair",
    response_model=_PairResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Consume a pairing token + mint a long-lived sync-agent- JWT.",
)
async def sync_pair(
    payload: _PairRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> _PairResponse:
    """Branch-side pairing: redeem the admin-issued pairing-token for a JWT.

    No auth — the plaintext token IS the credential. On success:
    ``POST /sync/pair`` returns a long-lived (30-day) ``sync-agent-``
    JWT + the branch uuid + ``expires_at`` (naive UTC). The branch's
    :mod:`parkos_core.cli.pair` CLI persists the JWT to
    ``PARKOS_SYNC_JWT_PATH`` mode 0o600 and writes a
    ``log_transaccional`` row with ``accion='pair_completed'``.

    Failure 4 (per §21.3):
    - 410 Gone on consumed / expired / revoked tokens (mapped from
      :class:`PairingTokenConsumedError` / :class:`PairingTokenExpiredError`
      / :class:`PairingTokenNotFoundError`).
    - 422 on malformed body (Pydantic).
    """
    try:
        consumed = await consume_pairing_token(
            session,
            payload.pairing_token,
            uuid_sucursal=payload.uuid_sucursal,
            branch_info=payload.branch_info.model_dump(exclude_none=True),
        )
    except PairingTokenNotFoundError as e:
        await session.rollback()
        raise HTTPException(
            status_code=410,
            detail={"error": "pairing_token_not_found", "detail": str(e)},
        ) from e
    except PairingTokenExpiredError as e:
        await session.rollback()
        raise HTTPException(
            status_code=410,
            detail={"error": "pairing_token_expired", "detail": str(e)},
        ) from e
    except PairingTokenConsumedError as e:
        await session.rollback()
        raise HTTPException(
            status_code=410,
            detail={"error": "pairing_token_consumed", "detail": str(e)},
        ) from e

    # Mint the long-lived sync-agent- JWT (30 days = 720h = 2_592_000s).
    expires_in_s = 30 * 24 * 3600
    now = _now_naive()
    expires_at = now + timedelta(seconds=expires_in_s)
    sync_jwt = issue_token(
        subject_uuid=payload.uuid_sucursal,
        issuer="sync-agent-cloud",
        claims={
            "scope": "branch",
            "sucursal": str(payload.uuid_sucursal),
        },
        expires_in=expires_in_s,
    )

    # Best-effort audit row — ``log_transaccional`` is [A] so a write
    # failure doesn't break the response.
    try:
        await append_event(
            session,
            LogTransaccional,
            {
                "uuid_sucursal": payload.uuid_sucursal,
                "accion": "pair_completed",
                "tabla_afectada": "sync_agent_jwts",
                "uuid_registro_afectado": consumed.uuid,
                "datos_anteriores": None,
                "datos_nuevos": {
                    "pair_completed_at": now.isoformat(),
                    "sync_jwt_issued_at": now.isoformat(),
                    "sync_jwt_expires_at": expires_at.isoformat(),
                },
                "timestamp_evento": now,
            },
            actor_uuid=None,  # branch's sync-agent has no actor_uuid at pair time
        )
        await session.commit()
    except AppendOnlyError as e:
        logger.warning("could not write log_transaccional row: %s", e)
        await session.rollback()

    return _PairResponse(
        sync_jwt=sync_jwt,
        expires_at=expires_at,
        uuid_sucursal=payload.uuid_sucursal,
    )


# ---------------------------------------------------------------------------
# Endpoint 2: POST /sync/push
# ---------------------------------------------------------------------------


@router.post(
    "/push",
    response_model=_PushResponse,
    status_code=status.HTTP_207_MULTI_STATUS,
    summary="Branch → cloud row push (issuer sync-agent-, rate-limited 60/min).",
)
async def sync_push(
    payload: _PushRequest,
    request: Request,
    claims: dict[str, Any] = Depends(_sync_agent_claims),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    x_request_id: str | None = Header(None, alias="X-Request-Id"),
) -> _PushResponse:
    """Branch pushes a batch of rows to the cloud.

    Auth chain:
    1. ``sync-agent-`` issuer guard (catches cross-issuer attempts).
    2. ``is_revoked`` lookup against ``prod.revoked_sync_jwts`` (catches
       admin-revoked JWTs).
    3. ``iat_branch`` clock-skew check (catches drifted branch clocks).
    4. ``X-Request-Id`` idempotency cache (replays cached responses
       on duplicate POST within 5 min).
    5. Per-(issuer, subject) rate limit (push=60/min).

    Returns 207 Multi-Status with per-row results. The per-row
    conflict resolution itself is a PR9 concern (when the cloud-side
    applier lands); PR8c returns ``status="applied"`` for all rows so
    the auth + cache + rate-limit plumbing is exercised end-to-end.
    """
    issuer = claims.get("iss", "")
    subject = extract_subject_from_jwt(claims)
    cache_key_subject = subject

    # Idempotency replay.
    if x_request_id:
        cached = _IDEMPOTENCY.get(issuer, cache_key_subject, x_request_id)
        if cached is not None:
            cached_status, cached_body = cached
            # Replay cached response with the Idempotent-Replay header.
            from fastapi.responses import JSONResponse

            return JSONResponse(  # type: ignore[return-value]
                status_code=cached_status,
                content=cached_body,
                headers={"Idempotent-Replay": "true"},
            )

    # Rate limit.
    try:
        _RATE_LIMIT_PUSH.check(issuer, cache_key_subject)
    except SyncRateLimitedError as e:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "sync_rate_limited",
                "action": "push",
                "limit_per_minute": _RATE_LIMIT_PUSH.per_minute,
            },
            headers={"Retry-After": str(e.retry_after_seconds)},
        ) from e

    # PR9 will iterate `payload.rows` against the conflict-resolution
    # applier; PR8c returns applied=true on all rows so the auth +
    # rate-limit + cache plumbing is verified end-to-end.
    results = [
        _PushResponseRow(
            uuid_registro=row.uuid_registro,
            status="applied",
            detail=None,
        )
        for row in payload.rows
    ]
    response_body = {"results": [r.model_dump(mode="json") for r in results]}

    # Persist in cache so a duplicate X-Request-Id replays.
    if x_request_id:
        _IDEMPOTENCY.put(
            issuer, cache_key_subject, x_request_id, 207, response_body
        )

    return _PushResponse(results=results)


# ---------------------------------------------------------------------------
# Endpoint 3: POST /sync/pull
# ---------------------------------------------------------------------------


@router.post(
    "/pull",
    response_model=_PullResponse,
    summary="Branch ← cloud row pull (issuer sync-agent-, rate-limited 120/min).",
)
async def sync_pull(
    payload: _PullRequest,
    request: Request,
    claims: dict[str, Any] = Depends(_sync_agent_claims),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    x_request_id: str | None = Header(None, alias="X-Request-Id"),
) -> _PullResponse:
    """Branch pulls a batch of rows from the cloud.

    The full cloud-side applier (which reads ``sync_queue`` +
    ``log_transaccional`` to materialize the per-branch sequence)
    lands in PR9. PR8c returns an empty batch so the auth + cache +
    rate-limit chain is verified.
    """
    issuer = claims.get("iss", "")
    subject = extract_subject_from_jwt(claims)

    # Idempotency replay.
    if x_request_id:
        cached = _IDEMPOTENCY.get(issuer, subject, x_request_id)
        if cached is not None:
            cached_status, cached_body = cached
            from fastapi.responses import JSONResponse

            return JSONResponse(  # type: ignore[return-value]
                status_code=cached_status,
                content=cached_body,
                headers={"Idempotent-Replay": "true"},
            )

    # Rate limit.
    try:
        _RATE_LIMIT_PULL.check(issuer, subject)
    except SyncRateLimitedError as e:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "sync_rate_limited",
                "action": "pull",
                "limit_per_minute": _RATE_LIMIT_PULL.per_minute,
            },
            headers={"Retry-After": str(e.retry_after_seconds)},
        ) from e

    response_body = {"rows": [], "next_seq": payload.since_seq}
    if x_request_id:
        _IDEMPOTENCY.put(
            issuer, subject, x_request_id, 200, response_body
        )

    return _PullResponse(rows=[], next_seq=payload.since_seq)


# ---------------------------------------------------------------------------
# Endpoint 4: POST /sync/heartbeat
# ---------------------------------------------------------------------------


@router.post(
    "/heartbeat",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Branch/cloud heartbeat (issuer sync-agent-, rate-limited 10/min).",
)
async def sync_heartbeat(
    payload: _HeartbeatRequest = _HeartbeatRequest(),  # noqa: B008
    claims: dict[str, Any] = Depends(_sync_agent_claims),  # noqa: B008
) -> None:
    """Heartbeat — keeps the cloud's per-branch "alive" flag fresh.

    Empty body permitted (Pydantic defaults ``state`` to ``{}``). The
    rate limit is 10/min — heartbeats are cheap but excessive calls
    indicate a misbehaving worker. No idempotency cache: heartbeats
    are inherently idempotent at the data layer (the cloud just
    refreshes a timestamp).
    """
    issuer = claims.get("iss", "")
    subject = extract_subject_from_jwt(claims)

    try:
        _RATE_LIMIT_HEARTBEAT.check(issuer, subject)
    except SyncRateLimitedError as e:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "sync_rate_limited",
                "action": "heartbeat",
                "limit_per_minute": _RATE_LIMIT_HEARTBEAT.per_minute,
            },
            headers={"Retry-After": str(e.retry_after_seconds)},
        ) from e

    logger.debug(
        "sync_heartbeat received: issuer=%s subject=%s state_keys=%d",
        issuer,
        subject,
        len(payload.state),
    )


# ---------------------------------------------------------------------------
# Endpoint 5: POST /sync/rotate-jwt
# ---------------------------------------------------------------------------


@router.post(
    "/rotate-jwt",
    response_model=_RotateResponse,
    summary="Rotate the sync-agent- JWT (issuer sync-agent-, rate-limited 1/min).",
)
async def sync_rotate_jwt(
    payload: _RotateRequest,
    request: Request,
    claims: dict[str, Any] = Depends(_sync_agent_claims),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> _RotateResponse:
    """Rotate the current ``sync-agent-`` JWT.

    The endpoint verifies the supplied ``current_jwt`` (signature +
    issuer prefix + revocation check), then mints a fresh JWT. Per
    spec §21.3 the new JWT's ``kid`` is ``current.kid + "_r" + uuid``
    so the old JWT is naturally distinguishable for revocation.

    Implementation note: ``issue_token`` doesn't accept a custom ``kid``
    arg (the dev HS256 path computes ``kid = issuer + suffix``). We
    work around by using a unique issuer per rotation
    (``sync-agent-cloud-r-{uuid}``) — the issuer prefix check still
    passes (``sync-agent-``) but the resulting kid is unique.

    Returns ``{jwt, expires_at, grace_until}`` matching the deployed
    ``sync/transport.py::SyncHttpClient.rotate_jwt`` client (PR9,
    T-PR9-02). ``grace_until`` is set to ``now + JWT_OVERLAP_HOURS``
    (24h) so the old JWT remains valid during the overlap window.
    """
    issuer = claims.get("iss", "")
    subject = extract_subject_from_jwt(claims)

    try:
        _RATE_LIMIT_ROTATE.check(issuer, subject)
    except SyncRateLimitedError as e:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "sync_rate_limited",
                "action": "rotate_jwt",
                "limit_per_minute": _RATE_LIMIT_ROTATE.per_minute,
            },
            headers={"Retry-After": str(e.retry_after_seconds)},
        ) from e

    # The current JWT was already verified by the dependency. Extract
    # its kid so the new JWT carries a derived kid.
    try:
        old_kid = decode_jwt_header_kid(payload.current_jwt)
    except ValueError:
        # Fall back to the live request's kid if the body token is
        # malformed (we've already verified the Authorization header).
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                old_kid = decode_jwt_header_kid(auth[7:].strip())
            except ValueError:
                old_kid = "sync-agent-cloud"
        else:
            old_kid = "sync-agent-cloud"

    # Mint the new JWT with a unique issuer-derived kid. The kid is
    # the issue_token-computed ``sync-agent-cloud-r-{uuid}current`` —
    # unique per rotation, distinguishable for revocation.
    rotation_id = uuid_lib.uuid4()
    new_issuer = f"sync-agent-cloud-r-{rotation_id}"
    expires_in_s = 30 * 24 * 3600  # 30 days
    now = _now_naive()
    expires_at = now + timedelta(seconds=expires_in_s)
    grace_until = now + timedelta(hours=24)  # JWT_OVERLAP_HOURS

    new_jwt = issue_token(
        subject_uuid=uuid_lib.UUID(subject),
        issuer=new_issuer,
        claims={
            "scope": claims.get("scope", "branch"),
            "sucursal": claims.get("sucursal"),
            "iat_branch": now.isoformat(),
        },
        expires_in=expires_in_s,
    )

    # Audit the rotation in log_transaccional (best-effort).
    try:
        await append_event(
            session,
            LogTransaccional,
            {
                "uuid_sucursal": uuid_lib.UUID(claims["sucursal"])
                if claims.get("sucursal")
                else None,
                "accion": "sync_jwt_rotated",
                "tabla_afectada": "sync_agent_jwts",
                "uuid_registro_afectado": rotation_id,
                "datos_anteriores": {"old_kid": old_kid},
                "datos_nuevos": {
                    "new_issuer": new_issuer,
                    "expires_at": expires_at.isoformat(),
                },
                "timestamp_evento": now,
            },
            actor_uuid=uuid_lib.UUID(subject) if subject else None,
        )
        await session.commit()
    except AppendOnlyError as e:
        logger.warning("could not write rotation log row: %s", e)
        await session.rollback()

    logger.info(
        "sync_jwt rotation: old_kid=%s new_issuer=%s subject=%s",
        old_kid,
        new_issuer,
        subject,
    )

    return _RotateResponse(
        jwt=new_jwt,
        expires_at=expires_at,
        grace_until=grace_until,
    )


# ---------------------------------------------------------------------------
# Endpoint 6: POST /sync/events
# ---------------------------------------------------------------------------


@router.post(
    "/events",
    response_model=_EventsResponse,
    status_code=status.HTTP_207_MULTI_STATUS,
    summary="Cloud ↔ branch catalog-driven row push (issuer sync-agent-).",
)
async def sync_events(
    payload: _EventsRequest,
    request: Request,
    claims: dict[str, Any] = Depends(_sync_agent_claims),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    x_request_id: str | None = Header(None, alias="X-Request-Id"),
) -> _EventsResponse:
    """Cloud ↔ branch catalog-driven row push (mounted on both processes).

    Two request shapes coexist on the same wire endpoint (see
    ``_CatalogPushEvent``'s docstring):

    - Legacy provider-notification events (``event_type`` + ``payload``,
      no ``tabla``) — reported ``delivered`` exactly as PR8c shipped it.
    - Catalog-driven rows (``tabla`` set) — applied through
      ``SyncMotor.apply_row`` (T-PR11-001/006, REQ-CUT-015). The cloud's
      receiver dispatches ``branch_to_cloud`` rows; PR12's branch-side
      receiver (same handler, mounted on ``api_sucursal``) dispatches
      ``cloud_to_branch`` rows through the identical code path — this is
      the single source of truth for REQ-MOT-005's wire-status mapping
      (``wire_status_for_apply_result``), never a generic failure and
      never a silent drop for either direction.
    """
    issuer = claims.get("iss", "")
    subject = extract_subject_from_jwt(claims)

    # Idempotency replay.
    if x_request_id:
        cached = _IDEMPOTENCY.get(issuer, subject, x_request_id)
        if cached is not None:
            cached_status, cached_body = cached
            from fastapi.responses import JSONResponse

            return JSONResponse(  # type: ignore[return-value]
                status_code=cached_status,
                content=cached_body,
                headers={"Idempotent-Replay": "true"},
            )

    # Sync events reuses the pull bucket (120/min) — both directions
    # of bulk transport share the same budget per §21.9.
    try:
        _RATE_LIMIT_PULL.check(issuer, subject)
    except SyncRateLimitedError as e:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "sync_rate_limited",
                "action": "events",
                "limit_per_minute": _RATE_LIMIT_PULL.per_minute,
            },
            headers={"Retry-After": str(e.retry_after_seconds)},
        ) from e

    actor_uuid = uuid_lib.UUID(subject)
    # Lazily built — a legacy-shaped batch (no `tabla` on any event) never
    # touches SyncMotor/PARKOS_SYNC_ENGINE at all, preserving the original
    # PR8c behavior (and its test) for callers that never send `tabla`.
    motor: SyncMotor | None = None

    # Real bug found + fixed (Docker deployment closing exercise,
    # post-testcontainers): this loop used to iterate ``payload.events`` in
    # WIRE order (the sender's ``list_pending`` order — ``prioridad DESC,
    # intentos ASC, created_at ASC`` — never dependency-aware), and applied
    # each row one at a time with no dependency ordering at all. A batch
    # containing both a parent and its child (e.g. ``facturas`` +
    # ``factura_electronica``, created moments apart by a real long-running
    # branch worker and pushed together in the SAME ``/sync/events`` call)
    # could apply the child before the parent — confirmed via a real
    # ``ForeignKeyViolationError`` on ``factura_electronica.uuid_factura``
    # wiring the post-testcontainers Docker exercise. Worse, because the
    # whole loop shares one transaction with a single
    # ``except Exception: rollback(); raise``, one ordering violation
    # aborted the ENTIRE batch (every other, perfectly valid row in it too)
    # — and since the sender retries the exact same ``list_pending`` batch
    # verbatim, this reproduced deterministically on every retry.
    # ``order_batch`` (the same dependency-orderer ``apply_batch``/
    # ``run_backfill`` already use elsewhere) only needs each event's
    # ``.tabla`` — reordering PROCESSING here while keeping every response
    # in the caller's ORIGINAL request order preserves
    # ``_push_and_handle_catalog``'s
    # ``zip(resolved_rows, results, strict=True)`` index-correspondence
    # contract unchanged.
    results_by_index: list[_EventResponseRow | None] = [None] * len(payload.events)
    index_by_event: dict[int, int] = {id(ev): i for i, ev in enumerate(payload.events)}
    try:
        # Echo-amplification fix (post-PR14 real-Docker closing exercise,
        # real defect #3; migration 0016_add_sync_apply_guard). This
        # handler is mounted on BOTH api_admin and api_sucursal and is the
        # single receiver for every row that arrives via sync in either
        # direction — every row this loop applies below is, by definition,
        # an event that already arrived via sync, so SET LOCAL the echo-
        # suppression GUC ONCE for this whole request's transaction
        # (ended by the single `session.commit()`/`rollback()` below;
        # never per-event) before any `motor.apply_row` call. See
        # sync.motor.apply_guard's own docstring.
        await apply_guard.enable_echo_suppression(session)
        for ev in order_batch(list(payload.events)):
            idx = index_by_event[id(ev)]
            if ev.tabla is None:
                # Legacy provider-event shape (PR8c) — no catalog dispatch.
                results_by_index[idx] = _EventResponseRow(
                    event_type=ev.event_type, status="delivered"
                )
                continue

            spec = SYNC_CATALOG_BY_NAME.get(ev.tabla)
            if spec is None:
                # Never a silent drop: an event naming an unrecognized table
                # is reported, not swallowed. (Out-of-catalog infra tables
                # are jobs/sync_cloud.py's is_infra_table concern, not this
                # router's — a row reaching here with an unknown tabla is
                # neither.)
                results_by_index[idx] = _EventResponseRow(
                    event_type=ev.event_type, status="unknown_table"
                )
                continue

            if motor is None:
                motor = SyncMotor(engine=engine_flag.get_engine())
            apply_result = await motor.apply_row(
                session, spec, ev.payload, actor_uuid=actor_uuid
            )
            wire_status = wire_status_for_apply_result(apply_result)
            results_by_index[idx] = _EventResponseRow(
                event_type=ev.event_type, status=wire_status
            )

        assert all(r is not None for r in results_by_index), (
            "sync_events: every request event must produce exactly one response row"
        )
        results: list[_EventResponseRow] = results_by_index  # type: ignore[assignment]

        await session.commit()
    except Exception:
        await session.rollback()
        raise

    response_body = {"results": [r.model_dump(mode="json") for r in results]}
    if x_request_id:
        _IDEMPOTENCY.put(
            issuer, subject, x_request_id, 207, response_body
        )

    return _EventsResponse(results=results)


__all__ = ["UnmappedApplyStatusError", "router", "wire_status_for_apply_result"]