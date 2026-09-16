"""Auth-domain HTTP routes (REQ-42, REQ-43, REQ-45).

- ``POST /api/v1/auth/login`` — credentials → JWT pair + ``parkos_session`` cookie.
- ``POST /api/v1/auth/refresh`` — refresh token → new access token.
- ``POST /api/v1/auth/logout`` — close the active ``login`` row.
- ``GET /api/v1/auth/me`` — operator session profile (HU-F1.2).

PR1b shipped the login + logout skeleton. HU-F1.2 (PR7) ADDS:

- ``GET /auth/me`` (TASK-F1.2-14): operator session profile derived from
  ``TenantContext`` + ``permisos_usuario`` + ``usuarios_sucursal``.
- Lockout enforcement on ``POST /auth/login`` (TASK-F1.2-11 + R-F1.2-2):
  count rows in ``prod.login WHERE estado='fallido'`` in the
  ``minutos_bloqueo_login`` window; if ``>= max_intentos_login``,
  respond ``429 account_locked`` with ``Retry-After: minutos*60``.
- INSERT ``prod.login`` with ``estado='fallido'`` on bad password
  (TASK-F1.2-12 + R-F1.2-1) — required so the lockout counter above
  has something to count.
- Cookie ``parkos_session`` on successful login (TASK-F1.2-13 +
  R-F1.2-4): same JWT, ``httponly=True, secure=True, samesite="lax",
  max_age=3600, path="/"``.

No Alembic migration. No new columns. No new tables. Counter is
derived from rows already in ``prod.login`` (KD-1).
"""
from __future__ import annotations

import logging
import uuid as uuid_lib
from datetime import UTC, datetime

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.jwt_issuer_guard import (
    CrossIssuerError,
    InvalidTokenError,
    verify_jwt,
)
from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...auth.tokens import (
    JWTIssuerPrefixError,
    JWTValidationError,
    issue_token,
    verify_token,
)
from ...db.engine import get_session
from ...models.L_S.login import Login
from ...models.V.permisos import Permisos
from ...models.V.permisos_usuario import PermisosUsuario
from ...models.V.sucursal import Sucursal
from ...models.V.usuarios import Usuarios
from ...models.V.usuarios_sucursal import UsuariosSucursal
from ...repo.config_override import resolve_efectiva_seguridad
from ...repo.session_cycle import record_login
from ...schemas.auth import (
    AuthMeResponse,
    LoginRequest,
    RefreshRequest,
    SucursalItem,
    TokenPair,
    UserItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_TOKEN_TTL = 3600  # 1 hour
REFRESH_TOKEN_TTL = 7 * 24 * 3600  # 7 days

# HU-F1.2 defaults (KD-3, plan.md:609) — used when
# ``resolve_efectiva_seguridad`` returns ``None`` (no per-branch override
# AND no global default row in ``configuracion_seguridad``). Logging a
# ``WARNING configuracion_seguridad_missing_fallback_to_defaults`` is
# part of the same fallback contract so the operator can correlate
# the missing seed with the pending config load.
DEFAULT_MAX_INTENTOS = 5
DEFAULT_MINUTOS_BLOQUEO = 15


async def _resolve_lockout_params(
    session: AsyncSession,
    *,
    sucursal_uuid: uuid_lib.UUID | None,
    actor_uuid: uuid_lib.UUID,
) -> tuple[int, int]:
    """Return ``(max_intentos_login, minutos_bloqueo_login)``.

    Resolves per-branch override first, falling back to the global
    default row in ``configuracion_seguridad``; if neither exists,
    logs a structured ``WARNING`` and returns the hardcoded plan
    defaults ``(5, 15)``.

    The lockout COUNTER is per-actor (matches the per-user
    ``login.uuid_usuario`` rows). The lockout POLICY
    (``max_intentos_login`` / ``minutos_bloqueo_login``) is per-branch
    via ``configuracion_seguridad`` with global fallback. So we take
    the actor's first active branch (the same ``limit(1)`` selection
    the success path uses) and pass that uuid to
    ``resolve_efectiva_seguridad``.
    """
    cfg = await resolve_efectiva_seguridad(session, sucursal_uuid) if sucursal_uuid else None
    if cfg is None:
        logger.warning(
            "configuracion_seguridad_missing_fallback_to_defaults",
            extra={"uuid_sucursal": str(sucursal_uuid or actor_uuid)},
        )
        return DEFAULT_MAX_INTENTOS, DEFAULT_MINUTOS_BLOQUEO
    # ``max_intentos_login`` / ``minutos_bloqueo_login`` can be NULL on
    # a freshly seeded row; the cast keeps mypy --strict happy and
    # gives a defensible fallback if the column is incomplete.
    max_intentos = int(cfg.max_intentos_login or DEFAULT_MAX_INTENTOS)
    minutos = int(cfg.minutos_bloqueo_login or DEFAULT_MINUTOS_BLOQUEO)
    return max_intentos, minutos


async def _count_failed_logins_in_window(
    session: AsyncSession,
    *,
    user_uuid: uuid_lib.UUID,
    minutos: int,
) -> int:
    """Return the count of ``login`` rows with ``estado='fallido'`` for
    ``user_uuid`` whose ``timestamp_evento`` is within the last
    ``minutos`` minutes.

    Implemented as a coroutine using SQL ``func.count``; kept inline in
    the handler rather than as a ``session_cycle`` helper because the
    spec (R-F1.2-2) binds the SQL shape exactly:
    ``WHERE uuid_usuario=:u AND estado='fallido' AND timestamp_evento
    >= now() - :minutos * interval '1 minute'``.
    """
    from datetime import timedelta

    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=minutos)
    stmt = select(func.count(Login.uuid)).where(
        Login.uuid_usuario == user_uuid,
        Login.estado == "fallido",
        Login.timestamp_evento >= cutoff,
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


@router.post("/login", response_model=TokenPair, status_code=status.HTTP_200_OK)
async def login(
    payload: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> TokenPair:
    """Authenticate ``email`` + ``password`` and issue a JWT pair.

    Order (KD-2):

    1. SELECT the active user by email (``vigente_hasta IS NULL``).
    2. **Anti-enumeration**: unknown email → ``401 invalid_credentials``
       WITHOUT inserting a ``fallido`` row and WITHOUT a 429 — there is
       no ``uuid_usuario`` to count against (R-F1.2-11).
    3. Resolve ``max_intentos_login`` / ``minutos_bloqueo_login`` via
       ``resolve_efectiva_seguridad`` (fallback ``(5, 15)`` if None).
    4. **PRE-CHECK lockout** (NEW): if the count of
       ``prod.login`` rows with ``estado='fallido'`` for this user in
       the last ``minutos`` minutes is ``>= max_intentos``, return
       ``429 account_locked`` with ``Retry-After: minutos*60`` BEFORE
       running bcrypt (S-F1.2-2).
    5. bcrypt.compare; on failure, INSERT ``login`` with
       ``estado='fallido'`` (R-F1.2-1) and return
       ``401 invalid_credentials``.
    6. Pick the operator's first active ``usuarios_sucursal`` (existing
       behaviour); INSERT ``login`` with ``estado='exitoso'``; emit
       HS256 access+refresh; **set cookie** ``parkos_session`` with the
       same JWT and ``httponly=True, secure=True, samesite="lax"``
       attributes (R-F1.2-4).
    """
    # 1. Look up the active user.
    result = await session.execute(
        select(Usuarios).where(
            Usuarios.email == payload.email,
            Usuarios.vigente_hasta.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        # Anti-enumeration: same response shape on any failure.
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_credentials"},
        )

    # 2. PRE-CHECK lockout — count ``fallido`` rows for this user in the
    #    lockout window BEFORE running bcrypt (S-F1.2-2). The spec binds
    #    this BEFORE bcrypt so the response cost is predictable when
    #    an attacker is hammering an account.
    #
    #    Pick the operator's first active branch NOW so the lockout
    #    POLICY (configuracion_seguridad override) can resolve per-branch
    #    before bcrypt. The success path also uses ``limit(1)`` on the
    #    same SELECT — keeping the two paths aligned.
    asg = await session.execute(
        select(UsuariosSucursal).where(
            UsuariosSucursal.uuid_usuario == user.uuid,
            UsuariosSucursal.vigente_hasta.is_(None),
        ).limit(1)
    )
    branch_assignment = asg.scalar_one_or_none()
    branch_uuid = branch_assignment.uuid_sucursal if branch_assignment else None

    max_intentos, minutos = await _resolve_lockout_params(
        session,
        sucursal_uuid=branch_uuid,
        actor_uuid=user.uuid,
    )
    failed_count = await _count_failed_logins_in_window(
        session, user_uuid=user.uuid, minutos=minutos
    )
    if failed_count >= max_intentos:
        retry_after_seconds = minutos * 60
        raise HTTPException(
            status_code=429,
            detail={
                "error": "account_locked",
                "retry_after_seconds": retry_after_seconds,
            },
            headers={"Retry-After": str(retry_after_seconds)},
        )

    # 3. Verify password — real bcrypt comparison (REQ-43).
    if not user.password_hash or not bcrypt.checkpw(
        payload.password.encode("utf-8"), user.password_hash.encode("utf-8")
    ):
        # CRITICAL (R-F1.2-1, R1 of explore): insert the ``fallido`` row
        # BEFORE raising. Without this, the pre-check above would
        # always see count=0 and the lockout would never fire —
        # making the whole feature decorative. The ``sucursal_uuid=None``
        # signals "no branch resolved yet"; the FK column is nullable.
        await record_login(
            session,
            usuario_uuid=user.uuid,
            sucursal_uuid=None,
            actor_uuid=user.uuid,
            success=False,
            motivo="bad_password",
        )
        await session.commit()
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_credentials"},
        )

    # 4. Reuse the branch assignment already fetched before the lockout
    #    pre-check (step 2 above). The success path shares the same
    #    ``limit(1)`` selection so the two paths can't disagree on
    #    which branch gets pinned.
    sucursal_uuid = branch_uuid or user.uuid

    # 5. Record the successful login (REQ-42).
    await record_login(
        session,
        usuario_uuid=user.uuid,
        sucursal_uuid=sucursal_uuid or user.uuid,
        actor_uuid=user.uuid,
        success=True,
    )

    # 6. Issue tokens.
    issuer = "operador-" if user.rol == "operador" else "admin-"
    claims = {
        "rol": user.rol or "operador",
        "sucursales_permitidas": [str(sucursal_uuid)] if sucursal_uuid else [],
        "sucursal": str(sucursal_uuid) if sucursal_uuid else None,
    }
    access = issue_token(
        subject_uuid=user.uuid,
        issuer=issuer,
        claims=claims,
        expires_in=ACCESS_TOKEN_TTL,
    )
    refresh = issue_token(
        subject_uuid=user.uuid,
        issuer=issuer,
        claims={"type": "refresh", **claims},
        expires_in=REFRESH_TOKEN_TTL,
    )

    # 7. Set the ``parkos_session`` cookie (R-F1.2-4). Same JWT as the
    #    body — whichever channel the client uses (browser cookie jar vs
    #    CLI/mobile body) authenticates identically.
    response.set_cookie(
        key="parkos_session",
        value=access,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=ACCESS_TOKEN_TTL,
        path="/",
    )

    await session.commit()

    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=ACCESS_TOKEN_TTL,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
) -> TokenPair:
    """Exchange a refresh token for a new access token.

    PR1b accepts the same JWT shape; PR7 adds the refresh-token-store
    and rotation-counter. Returns the SAME pair (no rotation in PR1b).
    """
    try:
        claims = verify_token(payload.refresh_token)
    except (JWTValidationError, JWTIssuerPrefixError) as e:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_refresh_token", "detail": str(e)},
        ) from e

    if claims.get("type") != "refresh":
        raise HTTPException(
            status_code=401,
            detail={"error": "not_a_refresh_token"},
        )

    subject_uuid = uuid_lib.UUID(claims["sub"])
    issuer = claims["iss"]
    new_claims = {k: v for k, v in claims.items() if k != "type"}
    new_claims.pop("exp", None)
    new_claims.pop("iat", None)

    access = issue_token(
        subject_uuid=subject_uuid,
        issuer=issuer,
        claims=new_claims,
        expires_in=ACCESS_TOKEN_TTL,
    )
    return TokenPair(
        access_token=access,
        refresh_token=payload.refresh_token,
        expires_in=ACCESS_TOKEN_TTL,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
) -> None:
    """Close the active ``login`` row (REQ-45).

    The full implementation (close_login_with_log) is in
    ``repo/session_cycle.py``. PR1b writes the log row + UPDATE.
    """
    try:
        claims = await verify_jwt(request)
    except (InvalidTokenError, CrossIssuerError) as e:
        raise HTTPException(status_code=401, detail=str(e.detail)) from e

    # PR1b: mark the latest active login row as closed. PR7 reads
    # ``login_uuid`` from the body for a precise close.
    from ...repo.session_cycle import close_login_with_log

    # For PR1b, accept the user's uuid and close any open login row.
    actor_uuid = uuid_lib.UUID(claims["sub"])
    # Find the latest open login for this user
    from ...models.L_S.login import Login

    result = await session.execute(
        select(Login)
        .where(
            Login.uuid_usuario == actor_uuid,
            Login.timestamp_cierre.is_(None),
        )
        .order_by(Login.timestamp_evento.desc())
        .limit(1)
    )
    open_login = result.scalar_one_or_none()
    if open_login is not None:
        await close_login_with_log(
            session,
            login_uuid=open_login.uuid,
            actor_uuid=actor_uuid,
        )
        await session.commit()


# ---------------------------------------------------------------------------
# GET /auth/me — HU-F1.2 (TASK-F1.2-14)
# ---------------------------------------------------------------------------


def _decode_exp_iso(jwt_token: str) -> str | None:
    """Decode the ``exp`` claim from ``jwt_token`` and format it as
    ISO 8601 UTC (``YYYY-MM-DDTHH:MM:SS+00:00``).

    Returns ``None`` if the token is malformed / the ``exp`` claim is
    missing. Used by ``GET /auth/me`` to populate ``expires_at`` in the
    response shape (R-F1.2-9).
    """
    try:
        claims = verify_token(jwt_token)
        exp = claims.get("exp")
        if not isinstance(exp, int):
            return None
        return datetime.fromtimestamp(exp, tz=UTC).isoformat()
    except (JWTValidationError, JWTIssuerPrefixError):
        return None


@router.get("/me", response_model=AuthMeResponse)
async def me(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AuthMeResponse:
    """Operator session profile (HU-F1.2, R-F1.2-5..9).

    Five populated blocks:

    - ``user`` — identity from ``prod.usuarios`` (R-F1.2-6).
    - ``sucursal`` — single branch pinned by the ``operador-`` JWT
      (R-F1.2-6).
    - ``sucursales_permitidas`` — ALL active ``usuarios_sucursal`` for
      the actor, ordered by ``sucursal.nombre ASC`` (R-F1.2-7). No
      ``.limit(1)`` — the JWT pinneado branch is just one of many.
    - ``permisos`` — list of permission codes for the actor
      (``[]`` if none — R-F1.2-8).
    - ``expires_at`` — ISO 8601 UTC derived from the JWT ``exp`` claim
      (R-F1.2-9).

    Antienumeration: any JWT problem (missing, malformed, expired,
    signature invalid, expired, or user no longer exists) collapses to
    a single ``404 not_found`` response — the same shape regardless of
    cause (R-F1.2-10, S-F1.2-6).
    """
    # Antienumeration wrapper: collapse every JWT failure mode to the
    # SAME 404. We do NOT let the dependency raise 401 first and then
    # patch the response — that path leaks the cause through headers and
    # timing. Instead we run ``verify_jwt`` directly (NOT via Depends,
    # because the ``X-Sucursal-Context`` ``Header(None, ...)`` default in
    # ``get_tenant_ctx`` stays unresolved when the function is awaited
    # outside the FastAPI dependency-injection chain) and build the
    # ``TenantContext`` inline. Any failure collapses to a single 404.
    try:
        claims = await verify_jwt(request)
    except Exception:  # noqa: BLE001 — intentional anti-enumeration collapse
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found"},
        ) from None

    # Build TenantContext inline — only the operador- branch is reachable
    # on /auth/me. Keep parity with get_tenant_ctx's operador branch
    # while sidestepping the Header default sentinel.
    iss = claims.get("iss", "")
    if not iss.startswith("operador-"):
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found"},
        )
    sucursal_str = claims.get("sucursal")
    if not sucursal_str:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found"},
        )
    try:
        actor_uuid = uuid_lib.UUID(claims["sub"])
        sucursal_uuid = uuid_lib.UUID(sucursal_str)
    except (ValueError, TypeError, KeyError):
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found"},
        ) from None
    actor_rol = claims.get("rol", "operador")
    ctx = TenantContext(
        actor_uuid=actor_uuid,
        actor_rol=actor_rol,
        issuer_prefix="operador-",
        sucursal_uuid=sucursal_uuid,
    )

    # The bearer JWT travels in the Authorization header; pull it out so
    # we can decode ``exp`` for the response.
    auth_header = request.headers.get("Authorization", "")
    bearer_token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""

    # ``user`` block.
    user_row = await session.execute(
        select(Usuarios).where(
            Usuarios.uuid == ctx.actor_uuid,
            Usuarios.vigente_hasta.is_(None),
        )
    )
    user = user_row.scalar_one_or_none()
    if user is None:
        # Token parsed fine but the user is gone (deleted / soft-closed
        # between token issuance and this request). Still a 404 — same
        # shape as a totally invalid token (R-F1.2-10).
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found"},
        )
    user_item = UserItem(
        uuid=user.uuid,
        email=user.email,
        nombre=user.nombre,
        apellido=user.apellido,
        rol=user.rol,
    )

    # ``sucursal`` block — single, JWT-pinned branch.
    if ctx.sucursal_uuid is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found"},
        )
    suc_row = await session.execute(
        select(Sucursal).where(Sucursal.uuid == ctx.sucursal_uuid)
    )
    suc = suc_row.scalar_one_or_none()
    if suc is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found"},
        )
    sucursal_item = SucursalItem(
        uuid=suc.uuid,
        nombre=suc.nombre,
        prefijo_nombre=suc.prefijo_nombre,
    )

    # ``sucursales_permitidas`` block — ALL active branches, no
    # ``.limit(1)`` (KD-4).
    suc_permitidas_rows = await session.execute(
        select(Sucursal)
        .join(UsuariosSucursal, UsuariosSucursal.uuid_sucursal == Sucursal.uuid)
        .where(
            UsuariosSucursal.uuid_usuario == ctx.actor_uuid,
            UsuariosSucursal.vigente_hasta.is_(None),
            Sucursal.vigente_hasta.is_(None),
        )
        .order_by(Sucursal.nombre.asc())
    )
    sucursales_permitidas = [
        SucursalItem(uuid=s.uuid, nombre=s.nombre, prefijo_nombre=s.prefijo_nombre)
        for s in suc_permitidas_rows.scalars().all()
    ]

    # ``permisos`` block — list of permission codes (``[]`` when none).
    permisos_stmt = (
        select(Permisos.permiso)
        .join(PermisosUsuario, PermisosUsuario.uuid_permiso == Permisos.uuid)
        .where(
            PermisosUsuario.uuid_usuario == ctx.actor_uuid,
            PermisosUsuario.vigente_hasta.is_(None),
            Permisos.vigente_hasta.is_(None),
        )
    )
    permisos = [
        p
        for p in (await session.execute(permisos_stmt)).scalars().all()
        if p is not None
    ]

    # ``expires_at`` block — ISO 8601 UTC from the JWT ``exp`` claim.
    expires_at = _decode_exp_iso(bearer_token) or datetime.now(UTC).isoformat()

    return AuthMeResponse(
        user=user_item,
        sucursal=sucursal_item,
        sucursales_permitidas=sucursales_permitidas,
        permisos=sorted(permisos),
        expires_at=expires_at,
    )


__all__ = ["router"]