"""Auth-domain HTTP routes (REQ-42, REQ-43, REQ-45).

- ``POST /api/v1/auth/login`` — credentials → JWT pair.
- ``POST /api/v1/auth/refresh`` — refresh token → new access token.
- ``POST /api/v1/auth/logout`` — close the active ``login`` row.

PR1b ships the login + logout skeleton. The full failure-path (counter
increment + lockout after N failed attempts, REQ-43) lands in PR7.
"""
from __future__ import annotations

import logging
import uuid as uuid_lib

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
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
from ...models.V.usuarios import Usuarios
from ...repo.session_cycle import record_login
from ...schemas.auth import LoginRequest, RefreshRequest, TokenPair

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_TOKEN_TTL = 3600  # 1 hour
REFRESH_TOKEN_TTL = 7 * 24 * 3600  # 7 days


@router.post("/login", response_model=TokenPair, status_code=status.HTTP_200_OK)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenPair:
    """Authenticate ``email`` + ``password`` and issue a JWT pair.

    Failure path (PR7): increment counter on bad password, lockout after N.
    PR1b returns 401 on any failure (anti-enumeration; same shape regardless
    of cause).
    """
    # 1. Look up the active user
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

    # 2. Verify password — real bcrypt comparison (REQ-43).
    if not user.password_hash or not bcrypt.checkpw(
        payload.password.encode("utf-8"), user.password_hash.encode("utf-8")
    ):
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_credentials"},
        )

    # 3. Pick a branch for the login (the user's first assigned branch).
    # PR7 reads the X-Sucursal-Context header explicitly; PR1b defaults to
    # the first row in usuarios_sucursal for the user.
    from ...models.V.usuarios_sucursal import UsuariosSucursal

    asg = await session.execute(
        select(UsuariosSucursal)
        .where(
            UsuariosSucursal.uuid_usuario == user.uuid,
            UsuariosSucursal.vigente_hasta.is_(None),
        )
        .limit(1)
    )
    assignment = asg.scalar_one_or_none()
    sucursal_uuid = assignment.uuid_sucursal if assignment else user.uuid

    # 4. Record the login (REQ-42)
    await record_login(
        session,
        usuario_uuid=user.uuid,
        sucursal_uuid=sucursal_uuid or user.uuid,
        actor_uuid=user.uuid,
        success=True,
    )

    # 5. Issue tokens
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


__all__ = ["router"]