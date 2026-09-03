"""Permission requirement dependency (REQ-OP-13, REQ-X7, SC-OP-04).

Layered AFTER the issuer guard. Joins ``permisos_usuario`` to ``permisos``
and verifies the actor currently holds the requested permission code.

The JWT itself does NOT carry permission claims — they are looked up live in
the DB on every request. This guarantees that revoking a permission takes
effect immediately (no token-cache window).
"""
from __future__ import annotations

import uuid as uuid_lib
from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.engine import get_session
from ..models.V.permisos import Permisos
from ..models.V.permisos_usuario import PermisosUsuario
from .jwt_issuer_guard import verify_jwt


def require_permission(codigo: str):
    """FastAPI dependency factory. 403 if the actor lacks the permission code.

    Args:
        codigo: The permission code (e.g. ``"config_catalogo"``).
    """

    async def _dep(
        request: Request,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, Any]:
        claims = getattr(request.state, "jwt_claims", None) or await verify_jwt(request)
        actor_uuid = uuid_lib.UUID(claims["sub"])

        result = await session.execute(
            select(PermisosUsuario)
            .join(Permisos, Permisos.uuid == PermisosUsuario.uuid_permiso)
            .where(
                PermisosUsuario.uuid_usuario == actor_uuid,
                PermisosUsuario.vigente_hasta.is_(None),
                Permisos.permiso == codigo,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=403,
                detail={"error": "permission_denied", "detail": codigo},
            )
        return claims

    return _dep


__all__ = ["require_permission"]