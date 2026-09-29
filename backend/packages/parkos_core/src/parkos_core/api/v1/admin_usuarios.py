"""Admin user-management HTTP endpoints (IT-1.4, IT-1.5 of
``openspec/_meta/iteration-plan.md``).

Cloud-only mount: this module is imported on ``api_admin`` only.
``api_sucursal`` does NOT mount admin user-management (REQ-X2: branch
operators have no business managing users, and the ``admin-`` issuer
guard denies ``operador-`` / ``sync-agent-`` tokens with 401 -- belt-
and-suspenders on top of the mount-level exclusion).

Endpoints
---------

- ``POST /api/v1/admin/usuarios`` -- create a new user (admin-only).
  Plaintext ``password`` is bcrypt-hashed in the repo before persisting;
  ``password_hash`` never crosses the HTTP edge in either direction.
  Body accepts an optional ``sucursales_asignadas`` list; if present
  one ``prod.usuarios_sucursal`` row + one ``prod.sync_queue`` row
  per UUID is written.
- ``GET /api/v1/admin/usuarios`` -- list active users. Read-only.
- ``GET /api/v1/admin/usuarios/{uuid}`` -- single user. Read-only.
- ``POST /api/v1/admin/usuarios/{uuid}/sucursales`` -- open a new
  branch assignment (admin-only). 409 if already assigned.
- ``GET /api/v1/admin/usuarios/{uuid}/sucursales`` -- list the user's
  currently-open branch assignments. Read-only.
- ``DELETE /api/v1/admin/usuarios/{uuid}/sucursales/{sucursal_uuid}``
  -- close the currently-open assignment (admin-only). 404 if no
  open assignment exists.

All endpoints require ``admin-`` issuer via
:func:`~parkos_core.auth.jwt_issuer_guard.requires_issuer`. The cross-
audience rejection test (IT-1.13) lives in the integration test suite.

Why the cloud-only mount
------------------------

Branch operators have no business creating users or assigning branches.
This is enforced at three layers per ``api/v1/__init__.py``'s DIAN
boundary (REQ-X3 belt-and-suspenders):

1. The ``admin-`` issuer guard at handler level -- ``operador-`` and
   ``sync-agent-`` get 401.
2. The router is only mounted on ``api_admin`` -- ``api_sucursal``'s
   ``openapi.json`` doesn't list these paths.
3. The handler still reads ``actor_uuid`` from the JWT subject; the
   audit log (``prod.log_transaccional``) records the action with
   that subject for forensic traceability.
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_session, requires_issuer
from ...models.V.usuarios import Usuarios
from ...repo import admin_usuarios as admin_repo
from ...schemas.admin import (
    AdminAsignarSucursalRequest,
    AdminSucursalAsignadaRead,
    AdminUsuarioCreateRequest,
    AdminUsuarioRead,
    AdminUsuarioReadList,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/usuarios", tags=["admin-usuarios"])

_admin_issuer_dep = requires_issuer("admin-")

AdminClaims = Annotated[dict[str, Any], Depends(_admin_issuer_dep)]
DbSession = Annotated[AsyncSession, Depends(get_session)]


def _actor_uuid_from_claims(claims: dict[str, Any]) -> uuid_lib.UUID:
    """Resolve the writer's UUID from the ``admin-`` JWT claims.

    The ``admin-`` issuer embeds the operator's ``actor_uuid`` in
    ``sub`` -- same convention ``auth.py::login`` uses for
    ``record_login``. Fallback to a system UUID if the claim is
    missing (defensive: a malformed token should never reach here
    because ``verify_jwt`` validates the claim set).
    """
    sub = claims.get("sub")
    if isinstance(sub, uuid_lib.UUID):
        return sub
    if isinstance(sub, str):
        try:
            return uuid_lib.UUID(sub)
        except ValueError:
            pass
    return uuid_lib.uuid4()


@router.post(
    "",
    response_model=AdminUsuarioRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (admin-only, bcrypt-hashed server-side).",
)
async def create_usuario(
    payload: AdminUsuarioCreateRequest,
    claims: AdminClaims,
    session: DbSession,
) -> AdminUsuarioRead:
    actor_uuid = _actor_uuid_from_claims(claims)
    try:
        user = await admin_repo.create_admin_usuario(
            session,
            actor_uuid=actor_uuid,
            nombre=payload.nombre,
            apellido=payload.apellido,
            cedula=payload.cedula,
            email=payload.email,
            password=payload.password,
            rol=payload.rol,
            sucursales_asignadas=payload.sucursales_asignadas,
        )
    except admin_repo.UsuarioYaAsignadoError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    await session.commit()
    # Refresh to populate server-side columns (``vigente_desde``,
    # ``created_at``) that ``close_and_insert`` set inside its TX.
    await session.refresh(user)
    logger.info(
        "admin_usuarios.create",
        extra={
            "actor": str(actor_uuid),
            "user_uuid": str(user.uuid),
            "email": payload.email,
            "rol": payload.rol,
            "sucursales_count": len(payload.sucursales_asignadas),
        },
    )
    return AdminUsuarioRead.model_validate(user)


@router.get(
    "",
    response_model=AdminUsuarioReadList,
    summary="List active users (admin-only, read-only). Each item embeds the user's open branch assignments in ``sucursales``.",
)
async def list_usuarios(
    claims: AdminClaims,
    session: DbSession,
) -> AdminUsuarioReadList:
    rows = await admin_repo.list_active_usuarios(session, limit=100)
    assignments_by_user = await admin_repo.list_branch_assignments_for_users(
        session, user_uuids=[r.uuid for r in rows]
    )
    items = [
        AdminUsuarioRead(
            **AdminUsuarioRead.model_validate(r).model_dump(),
            sucursales=assignments_by_user.get(r.uuid, []),
        )
        for r in rows
    ]
    return AdminUsuarioReadList(items=items, next_cursor=None)


@router.get(
    "/{uuid}",
    response_model=AdminUsuarioRead,
    summary="Get a single active user by UUID (admin-only). The ``sucursales`` field is populated with the user's open branch assignments.",
)
async def get_usuario(
    uuid: uuid_lib.UUID,
    claims: AdminClaims,  # type: ignore[assignment]
    session: DbSession,  # type: ignore[assignment]
) -> AdminUsuarioRead:
    from sqlalchemy import select

    stmt = select(Usuarios).where(
        Usuarios.uuid == uuid,
        Usuarios.vigente_hasta.is_(None),
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no active user with uuid={uuid}",
        )
    assignments = await admin_repo.list_branch_assignments_for_users(
        session, user_uuids=[user.uuid]
    )
    payload = AdminUsuarioRead.model_validate(user).model_dump()
    payload["sucursales"] = assignments.get(user.uuid, [])
    return AdminUsuarioRead.model_validate(payload)


@router.post(
    "/{uuid}/sucursales",
    response_model=AdminSucursalAsignadaRead,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a user to a branch (admin-only). 409 if already assigned.",
)
async def asignar_sucursal(
    payload: AdminAsignarSucursalRequest,
    uuid: uuid_lib.UUID,
    claims: AdminClaims,  # type: ignore[assignment]
    session: DbSession,  # type: ignore[assignment]
) -> AdminSucursalAsignadaRead:
    actor_uuid = _actor_uuid_from_claims(claims)
    try:
        row = await admin_repo.asignar_sucursal(
            session,
            actor_uuid=actor_uuid,
            usuario_uuid=uuid,
            sucursal_uuid=payload.uuid_sucursal,
        )
    except admin_repo.UsuarioYaAsignadoError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    await session.commit()
    await session.refresh(row)
    logger.info(
        "admin_usuarios.asignar",
        extra={
            "actor": str(actor_uuid),
            "usuario_uuid": str(uuid),
            "sucursal_uuid": str(payload.uuid_sucursal),
        },
    )
    return AdminSucursalAsignadaRead.model_validate(row)


@router.get(
    "/{uuid}/sucursales",
    response_model=list[AdminSucursalAsignadaRead],
    summary="List the user's currently-open branch assignments (admin-only).",
)
async def list_asignaciones(
    uuid: uuid_lib.UUID,
    claims: AdminClaims,  # type: ignore[assignment]
    session: DbSession,  # type: ignore[assignment]
) -> list[AdminSucursalAsignadaRead]:
    rows = await admin_repo.list_active_asignaciones_usuario(session, usuario_uuid=uuid)
    return [AdminSucursalAsignadaRead.model_validate(r) for r in rows]


@router.delete(
    "/{uuid}/sucursales/{sucursal_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Close a branch assignment (admin-only). 404 if not currently assigned.",
)
async def desasignar_sucursal(
    response: Response,
    uuid: uuid_lib.UUID,
    sucursal_uuid: uuid_lib.UUID,
    claims: AdminClaims,  # type: ignore[assignment]
    session: DbSession,  # type: ignore[assignment]
) -> Response:
    actor_uuid = _actor_uuid_from_claims(claims)
    # Detect "no open assignment" so we can 404 instead of 204.
    rows = await admin_repo.list_active_asignaciones_usuario(session, usuario_uuid=uuid)
    has_open = any(r.uuid_sucursal == sucursal_uuid for r in rows)
    if not has_open:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no open assignment for user={uuid} branch={sucursal_uuid}",
        )
    await admin_repo.desasignar_sucursal(
        session,
        actor_uuid=actor_uuid,
        usuario_uuid=uuid,
        sucursal_uuid=sucursal_uuid,
    )
    await session.commit()
    logger.info(
        "admin_usuarios.desasignar",
        extra={
            "actor": str(actor_uuid),
            "usuario_uuid": str(uuid),
            "sucursal_uuid": str(sucursal_uuid),
        },
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
