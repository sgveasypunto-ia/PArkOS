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
import os
import uuid as uuid_lib
from datetime import UTC, datetime

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
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
    CambiarPasswordRequest,
    LoginRequest,
    RefreshRequest,
    SucursalItem,
    TokenPair,
    UserItem,
)

# HU-F16 must-change enforcement: when the user authenticated against a
# temporary credential, the login handler issues this short-lived JWT
# instead of a normal pair. The operator MUST exchange it at
# ``POST /auth/cambiar-password`` before the system treats them as
# logged in. The TTL is short because the only reason the token exists
# is to carry a freshly-issued password change; there is no UI flow
# that would justify a longer window.
MUST_CHANGE_TOKEN_TTL = 5 * 60  # 5 minutes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_TOKEN_TTL = 3600  # 1 hour
REFRESH_TOKEN_TTL = 7 * 24 * 3600  # 7 days

# HU-F13.2 (plan.md:3120) — roles that emit an ``operador-`` JWT issuer.
# ``"Usuario"`` is the CU-08 business-role label; ``"operador"`` is kept for
# retro-compatibility with existing data/tests. Every other role
# (Facturador, Supervisor, Administrador, Auditor, Desarrollo) emits
# ``admin-``.
ROLES_OPERADOR = {"operador", "Usuario"}

# PT-2 -- roles that emit an ``admin-`` JWT but are ALSO allowed to use the
# BRANCH app with their own user (``GET /auth/me`` answers them). Deliberately
# narrow: only the supervisor profile. Every other ``admin-`` role keeps the
# anti-enumeration 404 on ``/auth/me``. This grants NO permission: the app only
# READS the permissions the user already holds (``permisos_usuario``), and
# every write is still guarded by ``require_permission`` + tenancy.
ROLES_ADMIN_EN_SUCURSAL = frozenset({"Supervisor"})

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


async def _select_sucursales_permitidas(
    session: AsyncSession,
    usuario_uuid: uuid_lib.UUID,
):
    """Every ACTIVE branch assigned to ``usuario_uuid``, ordered by name.

    Single source of truth for the ``sucursales_permitidas`` scope: both
    the login claim and ``GET /auth/me`` read it. They used to be built
    separately (login pinned one branch, ``/me`` listed all of them), and
    that divergence is what let a login emit a scope the rest of the
    system would reject. Callers dereference ``.scalars().all()``.
    """
    return await session.execute(
        select(Sucursal)
        .join(UsuariosSucursal, UsuariosSucursal.uuid_sucursal == Sucursal.uuid)
        .where(
            UsuariosSucursal.uuid_usuario == usuario_uuid,
            UsuariosSucursal.vigente_hasta.is_(None),
            Sucursal.vigente_hasta.is_(None),
        )
        .order_by(Sucursal.nombre.asc())
    )


def _branch_scope_uuid() -> uuid_lib.UUID | None:
    """This node's own branch uuid when serving the BRANCH API, else ``None``.

    ``PARKOS_DEPLOY=branch`` + ``PARKOS_SUCURSAL_UUID`` pin the node to one
    sucursal; the cloud admin API (``PARKOS_DEPLOY=cloud``) is multi-tenant
    and returns ``None`` (no membership enforcement). Read at call time, not
    import time. A branch node whose uuid is malformed fails closed (503); an
    UNSET uuid is skipped with a warning because ``api_sucursal`` already
    refuses to boot without it (``runtime.env.load_config``).
    """
    if os.environ.get("PARKOS_DEPLOY") != "branch":
        return None
    raw = os.environ.get("PARKOS_SUCURSAL_UUID")
    if not raw:
        logger.warning("branch_login_scope_unset_membership_not_enforced")
        return None
    try:
        return uuid_lib.UUID(raw)
    except ValueError:
        logger.error("branch_login_scope_invalid_uuid")
        raise HTTPException(status_code=503, detail={"error": "branch_misconfigured"}) from None


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
    #
    #    On the BRANCH API the membership is looked up for THIS branch only
    #    (never "the first branch of any"): see ``_branch_scope_uuid``.
    branch_scope = _branch_scope_uuid()
    asg_stmt = select(UsuariosSucursal).where(
        UsuariosSucursal.uuid_usuario == user.uuid,
        UsuariosSucursal.vigente_hasta.is_(None),
    )
    if branch_scope is not None:
        asg_stmt = asg_stmt.where(UsuariosSucursal.uuid_sucursal == branch_scope)
    asg = await session.execute(asg_stmt.limit(1))
    branch_assignment = asg.scalar_one_or_none()
    branch_uuid = branch_assignment.uuid_sucursal if branch_assignment else None

    max_intentos, minutos = await _resolve_lockout_params(
        session,
        sucursal_uuid=branch_scope or branch_uuid,
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

    # 3b. Branch membership (defense in depth). A valid password is not
    #     enough on the branch API: the usuario needs a vigente
    #     ``usuarios_sucursal`` row for THIS branch. Checked AFTER bcrypt so
    #     cost/shape match a bad password, answered with the SAME generic
    #     401, and recorded as ``fallido`` (so it counts toward lockout: a
    #     non-counting path would be a "valid password" oracle). The reason
    #     code ``no_branch_membership`` is internal (log line only).
    if branch_scope is not None and branch_assignment is None:
        logger.warning(
            "branch_login_rejected_no_membership",
            extra={"uuid_usuario": str(user.uuid), "uuid_sucursal": str(branch_scope)},
        )
        await record_login(
            session,
            usuario_uuid=user.uuid,
            sucursal_uuid=branch_scope,
            actor_uuid=user.uuid,
            success=False,
            motivo="no_branch_membership",
        )
        await session.commit()
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_credentials"},
        )

    # 4. HU-F16 must-change enforcement (KD-1). The user authenticated
    #    against a bcrypt hash that the system marked as temporary via
    #    ``prod.usuarios.debe_cambiar_password`` (set to ``True`` by
    #    ``repo.admin_usuarios.reset_admin_password`` after an admin
    #    reset). The handler returns the SAME 200 status with a body
    #    variant: ``must_change_password=True`` and ``temporary_token``
    #    carrying a 5-minute JWT scoped to that one user with
    #    ``purpose="must_change"``. The frontend routes to
    #    ``<CambiarPasswordForm>`` which POSTs to ``/auth/cambiar-password``
    #    and exchanges the temp token for a real TokenPair.
    #
    #    We log a successful login (``estado='exitoso'``) regardless of
    #    must_change -- the audit trail needs to know the operator
    #    authenticated, and ``motivo`` carries the nuance.
    #
    #    The temp token claims include ``sub`` and ``purpose`` only --
    #    NO ``rol`` or ``sucursales_permitidas``. Until the operator
    #    chooses a real password the system refuses to attach them to
    #    a branch context (KD-2 / KD-3): a temporary operator with
    #    branch scope is a security hole, not a feature.
    if user.debe_cambiar_password:
        temp_token = issue_token(
            subject_uuid=user.uuid,
            issuer="operador-" if user.rol in ROLES_OPERADOR else "admin-",
            claims={
                "purpose": "must_change",
                "must_change_password": True,
            },
            expires_in=MUST_CHANGE_TOKEN_TTL,
        )
        await record_login(
            session,
            usuario_uuid=user.uuid,
            sucursal_uuid=branch_uuid,
            actor_uuid=user.uuid,
            success=True,
            motivo="must_change_password",
        )
        await session.commit()
        return TokenPair(
            must_change_password=True,
            temporary_token=temp_token,
            token_type="Bearer",
            expires_in=MUST_CHANGE_TOKEN_TTL,
        )

    # 5. Pin the JWT to the branch already resolved before the lockout
    #    pre-check (step 2). ``branch_uuid`` is None for a cloud admin with
    #    no ``usuarios_sucursal`` row, and None is the honest value:
    #    ``login.uuid_sucursal`` is a nullable FK to ``prod.sucursal(uuid)``,
    #    so substituting a user uuid there is a ForeignKeyViolationError.
    #    Do not reintroduce a ``or user.uuid`` fallback.
    # 6. Record the successful login (REQ-42).
    await record_login(
        session,
        usuario_uuid=user.uuid,
        sucursal_uuid=branch_uuid,
        actor_uuid=user.uuid,
        success=True,
    )

    # 7. Issue tokens. ``sucursales_permitidas`` carries the FULL set of
    #    active assignments from the same source ``GET /auth/me`` reads, not
    #    just the pinned branch: ``tenancy.require_tenant`` fail-closes an
    #    empty or missing list (``WHERE FALSE``), so a single-branch list
    #    would lock an admin out of every other branch they legitimately own.
    permitidas = [
        str(s.uuid)
        for s in (await _select_sucursales_permitidas(session, user.uuid)).scalars().all()
    ]
    issuer = "operador-" if user.rol in ROLES_OPERADOR else "admin-"
    claims = {
        "rol": user.rol or "operador",
        "sucursales_permitidas": permitidas,
        "sucursal": str(branch_uuid) if branch_uuid else None,
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


@router.post(
    "/cambiar-password",
    response_model=TokenPair,
    status_code=status.HTTP_200_OK,
    summary=(
        "Exchange a temporary credential issued by ``/auth/login`` (when "
        "``must_change_password=True``) for a real TokenPair. Closes the "
        "current ``prod.usuarios`` row and inserts a new one with the new "
        "bcrypt hash and ``debe_cambiar_password=false``. Validates that the "
        "incoming ``temporary_token`` carries ``purpose='must_change'`` "
        "(any other token, including the operator's regular pair, is "
        "rejected with ``401 invalid_temporary_token``)."
    ),
    responses={
        200: {"description": "Password changed, normal TokenPair returned."},
        401: {"description": "Token invalid, expired, or not a must-change token."},
        404: {"description": "User no longer exists (must-change token points at a deleted user)."},
    },
)
async def cambiar_password(
    payload: CambiarPasswordRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> TokenPair:
    """Resolve the must-change token to its subject, hash the new password,
    close+insert the user row, and return the regular TokenPair.

    Errors are deliberately narrow: a 401 with a typed ``detail`` (instead of
    a 500) when the token is malformed/expired/not-must-change keeps the
    operator UI honest. The handler does NOT log a ``prod.login`` row --
    ``/auth/login`` already did, and ``/auth/cambiar-password`` is a
    credential lifecycle event, not an authentication event.
    """
    try:
        claims = verify_token(payload.temporary_token)
    except (JWTValidationError, JWTIssuerPrefixError) as e:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_temporary_token", "detail": str(e)},
        ) from e

    if claims.get("purpose") != "must_change":
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_temporary_token", "detail": "purpose must be 'must_change'"},
        )

    try:
        subject_uuid = uuid_lib.UUID(claims["sub"])
    except (KeyError, ValueError) as e:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_temporary_token", "detail": f"missing sub: {e}"},
        ) from e

    # Find the active open row. If the user was deactivated between the
    # temp-token mint and the change, refuse with 404 instead of leaving
    # the system in an inconsistent state.
    stmt = select(Usuarios).where(
        Usuarios.uuid == subject_uuid,
        Usuarios.vigente_hasta.is_(None),
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="user_not_found",
        )

    # Bcrypt-hash the new password using the same pipeline as
    # ``repo.admin_usuarios.reset_admin_password`` -- a fresh cost
    # factor, no plaintext persisted, only the hash lands in
    # ``prod.usuarios.password_hash``.
    new_hash = bcrypt.hashpw(
        payload.new_password.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode("utf-8")

    # Close+insert: the new row carries ``debe_cambiar_password=False``,
    # clearing the flag. We also stamp ``fecha_cambio_password=NOW()`` so
    # future compliance / DIAN retention reviews can reason about the
    # rotation cadence without per-byte SQL on ``log_transaccional``.
    from ...repo.versioned import close_and_insert

    await close_and_insert(
        session,
        Usuarios,
        current_uuid=user.uuid,
        new_attrs={
            "password_hash": new_hash,
            "debe_cambiar_password": False,
            "fecha_cambio_password": datetime.now(UTC).replace(tzinfo=None),
        },
        actor_uuid=user.uuid,
        log_tx=True,
    )
    await session.flush()

    # Re-resolve the same fields login() does for the normal path. The
    # operator just changed their password; they now deserve the full
    # pair with their branch scope attached.
    asg = await session.execute(
        select(UsuariosSucursal)
        .where(
            UsuariosSucursal.uuid_usuario == user.uuid,
            UsuariosSucursal.vigente_hasta.is_(None),
        )
        .limit(1)
    )
    branch_assignment = asg.scalar_one_or_none()
    branch_uuid = branch_assignment.uuid_sucursal if branch_assignment else None

    permitidas = [
        str(s.uuid)
        for s in (await _select_sucursales_permitidas(session, user.uuid)).scalars().all()
    ]
    issuer = "operador-" if user.rol in ROLES_OPERADOR else "admin-"
    claims_for_pair = {
        "rol": user.rol or "operador",
        "sucursales_permitidas": permitidas,
        "sucursal": str(branch_uuid) if branch_uuid else None,
    }
    access = issue_token(
        subject_uuid=user.uuid,
        issuer=issuer,
        claims=claims_for_pair,
        expires_in=ACCESS_TOKEN_TTL,
    )
    refresh = issue_token(
        subject_uuid=user.uuid,
        issuer=issuer,
        claims={"type": "refresh", **claims_for_pair},
        expires_in=REFRESH_TOKEN_TTL,
    )

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

    logger.info(
        "auth.cambiar_password",
        extra={"actor": str(user.uuid)},
    )

    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        token_type="Bearer",
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
    x_sucursal_context: str | None = Header(None, alias="X-Sucursal-Context"),
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
    es_admin_token = iss.startswith("admin-")
    if not (iss.startswith("operador-") or es_admin_token):
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found"},
        )
    if es_admin_token and (
        claims.get("purpose") or claims.get("type") == "refresh" or not claims.get("rol")
    ):
        # Temporary (must-change) and refresh tokens never open a session
        # profile; an access token always carries ``rol``.
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found"},
        )
    # ``admin-`` (supervisor in the branch app): the branch comes from the
    # ``X-Sucursal-Context`` header (same contract as every other admin-
    # call), falling back to the login-pinned ``sucursal`` claim. Membership
    # is verified against the DB below, never trusted from the header/claim.
    sucursal_str = (
        (x_sucursal_context or claims.get("sucursal"))
        if es_admin_token
        else claims.get("sucursal")
    )
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
        issuer_prefix="admin-" if es_admin_token else "operador-",
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
    if es_admin_token:
        # Authority is the DB role (not the claim snapshot) and the branch
        # must be one of the user's CURRENT assignments (fresh read, like
        # ``get_tenant_ctx``). Anything else collapses to the same 404.
        permitidas_uuids = {
            s.uuid
            for s in (await _select_sucursales_permitidas(session, ctx.actor_uuid))
            .scalars()
            .all()
        }
        if user.rol not in ROLES_ADMIN_EN_SUCURSAL or sucursal_uuid not in permitidas_uuids:
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
    suc_row = await session.execute(select(Sucursal).where(Sucursal.uuid == ctx.sucursal_uuid))
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
    # ``.limit(1)`` (KD-4). Same helper the login claim reads.
    sucursales_permitidas = [
        SucursalItem(uuid=s.uuid, nombre=s.nombre, prefijo_nombre=s.prefijo_nombre)
        for s in (await _select_sucursales_permitidas(session, ctx.actor_uuid)).scalars().all()
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
    permisos = [p for p in (await session.execute(permisos_stmt)).scalars().all() if p is not None]

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
