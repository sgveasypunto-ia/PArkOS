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

    WHY THIS IS AN EXISTENCE CHECK, NOT A UNIQUENESS CHECK
    ------------------------------------------------------
    ``prod.permisos`` has NO unique index on ``permiso`` alone --
    ``permisos_uk01`` is ``(permiso, vigente_desde)``, and the bitemporal
    model intentionally allows one logical code to have several rows. A
    join that filters on ``permiso == codigo`` can therefore legitimately
    return more than one row, and an actor can hold open grants pointing
    at more than one of them.

    ``scalar_one_or_none()`` RAISES ``MultipleResultsFound`` in that case
    rather than returning the first row, which turned an authorization
    decision into an unhandled HTTP 500. Live impact before this fix:
    ``operador@parkos.local`` hit 500 on 16 codes -- including
    ``gestionar_dian``, ``emitir_factura``, ``audit_read`` and
    ``crear_arqueo`` -- in BOTH the cloud and branch databases.

    Two independent defects, both required:

    1. ``scalars().first()`` -- the question is "does an open grant exist
       for this code", so more than one match must still authorize. This
       keeps the check correct even though the catalogue currently holds 15
       codes with more than one open row.

    2. ``Permisos.vigente_hasta.is_(None)`` -- a grant pointing at a
       CLOSED permission version must not authorize. The 16 grants that
       were inflating the join are exactly the ones pointing at closed
       rows, so this filter both corrects the authorization semantics and
       removes the current duplication. It is not cosmetic.

    Fixing only one leaves the other defect armed: ``.first()`` alone
    keeps authorizing closed codes, and the filter alone still explodes
    the moment an actor is granted both open rows of a duplicated code.
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
                Permisos.vigente_hasta.is_(None),
            )
        )
        if result.scalars().first() is None:
            raise HTTPException(
                status_code=403,
                detail={"error": "permission_denied", "detail": codigo},
            )
        return claims

    return _dep


__all__ = ["require_permission"]