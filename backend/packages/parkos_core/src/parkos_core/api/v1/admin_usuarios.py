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
  per UUID is written. 409 if an active user already holds the same
  email.
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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_session, requires_issuer
from ...db.tenancy import (
    TenantScopeViolationError,
    extract_sucursales_permitidas_fresh,
)
from ...models.V.usuarios import Usuarios
from ...repo import admin_usuarios as admin_repo
from ...schemas.admin import (
    AdminAsignarPermisoRequest,
    AdminAsignarSucursalRequest,
    AdminPermisoRead,
    AdminPermisoUsuarioRead,
    AdminResetPasswordRequest,
    AdminSesionRead,
    AdminSucursalAsignadaRead,
    AdminUsuarioCreateRequest,
    AdminUsuarioRead,
    AdminUsuarioReadList,
    AdminUsuarioUpdateRequest,
    SucursalAsignadaResumen,
)

# `LoginIntentoItem` MUST be resolvable at module scope. The
# `login_historico` route below declares `response_model=list["LoginIntentoItem"]`,
# and FastAPI resolves that string when it builds the OpenAPI document -- not
# when the handler runs. A function-local import (the previous form) leaves
# the name out of the module namespace, so Pydantic raised
# `TypeAdapter[Annotated[list['LoginIntentoItem'], FieldInfo(...)]] is not
# fully defined` and `GET /openapi.json` returned 500. That is the api-admin
# HEALTHCHECK: the container reported `unhealthy` while the API served fine,
# which is a worse failure than the one it was hiding.
# No circular import: `schemas.usuarios` is a leaf module (Pydantic models
# only), exactly like `schemas.admin` imported directly above. The sibling
# router `usuarios_login.py` has always imported it at module level.
from ...schemas.usuarios import LoginIntentoItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/usuarios", tags=["admin-usuarios"])

# Sub-router for the catalog endpoints that do NOT live under a
# specific ``uuid``. Mounted by ``api/v1/__init__.py`` alongside the
# main router with a different prefix so the path collision
# ``/permisos`` (literal here) vs ``/{uuid}/permisos`` (per-user
# under the main router) is resolved by URL prefix, not declaration
# order. Without this the literal ``/permisos`` would be picked up by
# the per-user route's ``{uuid}`` path-parameter and 422 with a
# UUID-validation error.
catalog_router = APIRouter(prefix="/admin", tags=["admin-usuarios"])

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


# ---------------------------------------------------------------------------
# Branch scope (SC1) -- same source of truth as ``admin_views`` and
# ``auth.tenancy.require_branch_scope``: the actor's OPEN ``usuarios_sucursal``
# rows, read FRESH from the DB (never the login-time JWT snapshot). A cloud
# "global" admin is simply one assigned to every branch. Empty scope fails
# closed. Users outside the scope answer 404 (existence is not disclosed);
# naming a branch outside the scope answers 403 ``tenant_scope_violation``.
# ---------------------------------------------------------------------------


async def _admin_scope(
    session: AsyncSession, claims: dict[str, Any]
) -> frozenset[uuid_lib.UUID]:
    return frozenset(
        await extract_sucursales_permitidas_fresh(
            session, actor_uuid=_actor_uuid_from_claims(claims)
        )
    )


async def _require_usuario_in_scope(
    session: AsyncSession, claims: dict[str, Any], usuario_uuid: uuid_lib.UUID
) -> frozenset[uuid_lib.UUID]:
    """Resolve the actor's scope and 404 unless ``usuario_uuid`` is inside it."""
    permitidas = await _admin_scope(session, claims)
    if not await admin_repo.usuario_visible(
        session, usuario_uuid=usuario_uuid, permitidas=permitidas
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no active user with uuid={usuario_uuid}",
        )
    return permitidas


def _require_branches_in_scope(
    permitidas: frozenset[uuid_lib.UUID], sucursales: list[uuid_lib.UUID]
) -> None:
    if not all(s in permitidas for s in sucursales):
        raise TenantScopeViolationError()


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
    permitidas = await _admin_scope(session, claims)
    if not permitidas:
        raise TenantScopeViolationError()
    _require_branches_in_scope(permitidas, payload.sucursales_asignadas)
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
    except admin_repo.EmailYaRegistradoError as exc:
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
    permitidas = await _admin_scope(session, claims)
    rows = await admin_repo.list_active_usuarios(
        session, limit=100, permitidas=permitidas
    )
    assignments_by_user = await admin_repo.list_branch_assignments_for_users(
        session, user_uuids=[r.uuid for r in rows]
    )
    items = []
    for r in rows:
        # ``exclude={"sucursales"}`` keeps the dump free of the field's
        # default value (``[]``) so we can override it with the real
        # branch assignments without colliding on a duplicate kwarg.
        payload = AdminUsuarioRead.model_validate(r).model_dump(
            exclude={"sucursales"}
        )
        payload["sucursales"] = [
            a for a in assignments_by_user.get(r.uuid, []) if a.uuid_sucursal in permitidas
        ]
        items.append(AdminUsuarioRead.model_validate(payload))
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
    permitidas = await _require_usuario_in_scope(session, claims, uuid)
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
    payload = AdminUsuarioRead.model_validate(user).model_dump(
        exclude={"sucursales"}
    )
    payload["sucursales"] = [
        a for a in assignments.get(user.uuid, []) if a.uuid_sucursal in permitidas
    ]
    return AdminUsuarioRead.model_validate(payload)


# ``list_permisos`` mounts on the global ``catalog_router`` (prefix
# ``/admin``) so the literal ``/permisos`` path lives at
# ``/admin/permisos`` -- outside the main ``/admin/usuarios/{uuid}``
# tree, so the per-user route's ``{uuid}`` path-parameter does not
# shadow it. See the docstring on ``catalog_router`` at the top of
# this module.
@catalog_router.get(
    "/permisos",
    response_model=list[AdminPermisoRead],
    summary="List the canonical permission catalog (admin-only, read-only).",
)
async def list_permisos(
    claims: AdminClaims,  # type: ignore[assignment]
    session: DbSession,  # type: ignore[assignment]
) -> list[AdminPermisoRead]:
    """Active permission codes only (``vigente_hasta IS NULL``).

    The catalog is bi-temporal too, but we expose only the open
    window so the admin UI shows codes the operator can still grant
    today. A closed (revoked) permission code stays in the table for
    audit but is hidden here.
    """
    _ = claims  # issuer guard only
    rows = await admin_repo.list_permisos(session)
    # ``descripcion`` column does not exist on ``prod.permisos`` yet;
    # the schema defaults to ``None`` so the wire contract is honest
    # without lying about a catalog enrichment that has not shipped.
    return [
        AdminPermisoRead(uuid=r.uuid, codigo=r.permiso, descripcion=None)
        for r in rows
    ]


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
    permitidas = await _require_usuario_in_scope(session, claims, uuid)
    _require_branches_in_scope(permitidas, [payload.uuid_sucursal])
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
    permitidas = await _require_usuario_in_scope(session, claims, uuid)
    rows = await admin_repo.list_active_asignaciones_usuario(session, usuario_uuid=uuid)
    return [
        AdminSucursalAsignadaRead.model_validate(r)
        for r in rows
        if r.uuid_sucursal in permitidas
    ]


@router.post(
    "/{uuid}/sucursales/{sucursal_uuid}/revocar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=(
        "Close a branch assignment (admin-only). POST despite the "
        "destructive verb because the underlying table is bi-temporal "
        "(AGENTS.md §3 -- [V] rows are NEVER physically deleted; the "
        "repo layer does ``close_only``). 404 if not currently assigned."
    ),
)
async def desasignar_sucursal(
    response: Response,
    uuid: uuid_lib.UUID,
    sucursal_uuid: uuid_lib.UUID,
    claims: AdminClaims,  # type: ignore[assignment]
    session: DbSession,  # type: ignore[assignment]
) -> Response:
    actor_uuid = _actor_uuid_from_claims(claims)
    permitidas = await _require_usuario_in_scope(session, claims, uuid)
    _require_branches_in_scope(permitidas, [sucursal_uuid])
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


@router.post(
    "/{uuid}/permisos/{permiso_uuid}/revocar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=(
        "Close a permission grant (admin-only). POST because the "
        "underlying table is bi-temporal (AGENTS.md §3 -- [V] rows are "
        "NEVER physically deleted; the repo layer does ``close_only``). "
        "404 if no open grant exists."
    ),
    responses={
        204: {"description": "Grant closed."},
        404: {"description": "No open grant for that user+permission pair."},
    },
)
async def revocar_permiso(
    response: Response,
    uuid: uuid_lib.UUID,
    permiso_uuid: uuid_lib.UUID,
    claims: AdminClaims,  # type: ignore[assignment]
    session: DbSession,  # type: ignore[assignment]
) -> Response:
    actor_uuid = _actor_uuid_from_claims(claims)
    from ...repo.admin_usuarios import revocar_permiso as _repo_revoke

    await _require_usuario_in_scope(session, claims, uuid)

    try:
        had_open = await _repo_revoke(
            session,
            actor_uuid=actor_uuid,
            usuario_uuid=uuid,
            permiso_uuid=permiso_uuid,
        )
    except admin_repo.UltimoAdminError as exc:
        # REQ-OPS-007: the repo's last-admin guard fires when revoking
        # the LAST active ``admin_usuarios`` grant. Surface as 409 with
        # a typed ``detail`` so the admin UI can render a targeted
        # warning (and so the test suite can assert on it directly).
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ultimo_admin",
        ) from exc
    if not had_open:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no open grant for user={uuid} permission={permiso_uuid}",
        )
    await session.commit()
    logger.info(
        "admin_usuarios.revocar_permiso",
        extra={
            "actor": str(actor_uuid),
            "usuario_uuid": str(uuid),
            "permiso_uuid": str(permiso_uuid),
        },
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


# ---------------------------------------------------------------------------
# HU-F16 -- remaining read/write endpoints
# ---------------------------------------------------------------------------


@router.put(
    "/{uuid}",
    response_model=AdminUsuarioRead,
    summary=(
        "Bi-temporal close+insert update of an admin-managed user "
        "(admin-only). Sparse patch: every field is optional + nullable; "
        "the handler maps ``None`` to 'leave the existing value alone'. "
        "404 if no open user row exists."
    ),
)
async def update_usuario(
    uuid: uuid_lib.UUID,
    payload: AdminUsuarioUpdateRequest,
    claims: AdminClaims,  # type: ignore[assignment]
    session: DbSession,  # type: ignore[assignment]
) -> AdminUsuarioRead:
    actor_uuid = _actor_uuid_from_claims(claims)
    await _require_usuario_in_scope(session, claims, uuid)
    try:
        user = await admin_repo.update_admin_usuario(
            session,
            actor_uuid=actor_uuid,
            usuario_uuid=uuid,
            nombre=payload.nombre,
            apellido=payload.apellido,
            cedula=payload.cedula,
            email=payload.email,
            rol=payload.rol,
        )
    except admin_repo.UsuarioNoEncontradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except admin_repo.EmailYaRegistradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"usuario {uuid} not found or not vigente",
        )
    await session.commit()
    await session.refresh(user)
    logger.info(
        "admin_usuarios.update",
        extra={
            "actor": str(actor_uuid),
            "user_uuid": str(user.uuid),
        },
    )
    return AdminUsuarioRead.model_validate(user)


@router.get(
    "/{uuid}/permisos",
    response_model=list[AdminPermisoUsuarioRead],
    summary="List the user's currently-open permission grants (admin-only).",
)
async def list_permisos_usuario(
    uuid: uuid_lib.UUID,
    claims: AdminClaims,  # type: ignore[assignment]
    session: DbSession,  # type: ignore[assignment]
) -> list[AdminPermisoUsuarioRead]:
    await _require_usuario_in_scope(session, claims, uuid)
    pairs = await admin_repo.list_active_permisos_usuario(
        session, usuario_uuid=uuid
    )
    return [
        AdminPermisoUsuarioRead(
            uuid=row.uuid,
            uuid_usuario=row.uuid_usuario,
            uuid_permiso=row.uuid_permiso,
            codigo=perm.permiso,
            vigente_desde=row.vigente_desde,
            vigente_hasta=row.vigente_hasta,
        )
        for row, perm in pairs
    ]


@router.post(
    "/{uuid}/permisos/{permiso_uuid}",
    response_model=AdminPermisoUsuarioRead,
    status_code=status.HTTP_201_CREATED,
    summary=(
        "Open a new permission grant (admin-only). 409 if the user already "
        "holds the permission; 404 if the permission uuid is unknown."
    ),
)
async def asignar_permiso(
    uuid: uuid_lib.UUID,
    permiso_uuid: uuid_lib.UUID,
    claims: AdminClaims,  # type: ignore[assignment]
    session: DbSession,  # type: ignore[assignment]
) -> AdminPermisoUsuarioRead:
    actor_uuid = _actor_uuid_from_claims(claims)
    await _require_usuario_in_scope(session, claims, uuid)
    try:
        new_row = await admin_repo.asignar_permiso(
            session,
            actor_uuid=actor_uuid,
            usuario_uuid=uuid,
            permiso_uuid=permiso_uuid,
        )
    except admin_repo.PermisoYaAsignadoError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except admin_repo.PermisoNoEncontradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except admin_repo.UsuarioNoEncontradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # Re-resolve the permission code for the response payload (the
    # join would otherwise need another round trip).
    from ...models.V.permisos import Permisos as _Permisos

    perm_row = (
        await session.execute(
            select(_Permisos).where(_Permisos.uuid == permiso_uuid)
        )
    ).scalar_one()
    await session.commit()
    await session.refresh(new_row)
    logger.info(
        "admin_usuarios.asignar_permiso",
        extra={
            "actor": str(actor_uuid),
            "user_uuid": str(uuid),
            "permiso_uuid": str(permiso_uuid),
        },
    )
    return AdminPermisoUsuarioRead(
        uuid=new_row.uuid,
        uuid_usuario=new_row.uuid_usuario,
        uuid_permiso=new_row.uuid_permiso,
        codigo=perm_row.permiso,
        vigente_desde=new_row.vigente_desde,
        vigente_hasta=new_row.vigente_hasta,
    )


@router.get(
    "/{uuid}/sesiones",
    response_model=list[AdminSesionRead],
    summary="List the user's currently-open cash sessions (admin-only).",
)
async def list_sesiones_usuario(
    uuid: uuid_lib.UUID,
    claims: AdminClaims,  # type: ignore[assignment]
    session: DbSession,  # type: ignore[assignment]
) -> list[AdminSesionRead]:
    """Return ``prod.sesion`` rows for one user where ``timestamp_cierre IS NULL``.

    The frontend's :class:`AdminSesionRead` carries ``ip_origen`` /
    ``user_agent`` fields that ``prod.sesion`` does NOT have today.
    They live on ``prod.login``. We return ``None`` for those fields
    rather than fabricating values -- the wire contract stays honest,
    and a future migration that adds the columns to ``prod.sesion``
    flips the response without a caller change.
    """
    from sqlalchemy import select as _select

    await _require_usuario_in_scope(session, claims, uuid)
    # Local import to avoid a cycle on models.base
    from ...models.L_S.sesion import Sesion as _Sesion
    from ...schemas.admin import AdminSesionRead as _Schema

    stmt = (
        _select(_Sesion)
        .where(
            _Sesion.uuid_usuario == uuid,
            _Sesion.timestamp_cierre.is_(None),
        )
        .order_by(
            _Sesion.timestamp_apertura.desc().nulls_last(),
            _Sesion.uuid.asc(),
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    # The frontend schema expects ``creado_en`` (timestamp_apertura) and
    # ``ultimo_activity`` (timestamp_evento on login would be ideal,
    # but ``prod.sesion`` carries neither). We expose the values the
    # table does have; the rest is ``None``.
    return [
        _Schema(
            uuid=r.uuid,
            uuid_usuario=r.uuid_usuario,
            ip_origen=None,
            user_agent=None,
            creado_en=r.timestamp_apertura,
            ultimo_activity=r.timestamp_apertura,
            timestamp_cierre=r.timestamp_cierre,
            estado=r.estado,
        )
        for r in rows
    ]


@router.post(
    "/{uuid}/sesiones/{login_uuid}/cerrar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=(
        "Close one open login attempt (admin-only). Maps to the "
        "``session_cycle.close_login_with_log`` repo helper, which "
        "writes the audit row FIRST (the DB-layer session guard trigger "
        "rejects the UPDATE otherwise) then UPDATE ``timestamp_cierre`` "
        "and stamps ``estado='cerrado'``. 404 if the login uuid is "
        "unknown or already closed."
    ),
)
async def cerrar_sesion(
    uuid: uuid_lib.UUID,
    login_uuid: uuid_lib.UUID,
    claims: AdminClaims,  # type: ignore[assignment]
    session: DbSession,  # type: ignore[assignment]
) -> Response:
    actor_uuid = _actor_uuid_from_claims(claims)
    await _require_usuario_in_scope(session, claims, uuid)
    # The login must belong to the user in the path: otherwise a scoped
    # admin could close any user's login by pairing it with a visible uuid.
    from ...models.L_S.login import Login as _LoginRow

    owner = (
        await session.execute(
            select(_LoginRow.uuid_usuario).where(_LoginRow.uuid == login_uuid)
        )
    ).first()
    if owner is not None and owner[0] != uuid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no open login {login_uuid} for user={uuid}",
        )
    # The repo lives in :mod:`session_cycle`; import lazily so the
    # admin module does not pull it at import time.
    from ...repo.session_cycle import close_login_with_log

    try:
        await close_login_with_log(
            session, login_uuid=login_uuid, actor_uuid=actor_uuid
        )
    except Exception as exc:
        # ``close_login_with_log`` raises ``SessionGuardError`` on
        # unknown login_uuid AND on session-guard trigger failures
        # (missing log row). Both map to 404 from the admin's view.
        from ...repo.session_cycle import SessionGuardError
        if isinstance(exc, SessionGuardError):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        raise
    await session.commit()
    logger.info(
        "admin_usuarios.cerrar_sesion",
        extra={
            "actor": str(actor_uuid),
            "user_uuid": str(uuid),
            "login_uuid": str(login_uuid),
        },
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{uuid}/login-historico",
    response_model=list[LoginIntentoItem],
    summary=(
        "Latest login attempts for the user (admin-only). Same shape as "
        "``GET /usuarios/{uuid}/login`` (HU-F1.15); this route is the "
        "admin-namespaced alias the web_admin frontend calls."
    ),
)
async def login_historico(
    uuid: uuid_lib.UUID,
    claims: AdminClaims,  # type: ignore[assignment]
    session: DbSession,  # type: ignore[assignment]
) -> list[LoginIntentoItem]:
    await _require_usuario_in_scope(session, claims, uuid)
    from sqlalchemy import select as _select
    from ...models.L_S.login import Login as _Login

    stmt = (
        _select(_Login)
        .where(_Login.uuid_usuario == uuid)
        .order_by(
            _Login.timestamp_evento.desc().nulls_last(),
            _Login.uuid.asc(),
        )
        .limit(50)  # cap matches :func:`usuarios_login::list_login_attempts`
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [LoginIntentoItem.model_validate(r) for r in rows]


@router.post(
    "/{uuid}/reset-password",
    response_model=dict,  # noqa: PGH003 -- temporary until a typed schema lands
    summary=(
        "Generate a temporary password and write it (bcrypt-hashed) to the "
        "user (admin-only). Returns the plaintext ONCE -- the handler "
        "surfaces it in the response so the admin can read it to the "
        "operator. The plaintext is never persisted; only its hash is. "
        "If ``new_password`` is supplied in the request body it is "
        "used instead of the generated one (future-facing; the form "
        "does not expose it today)."
    ),
)
async def reset_password(
    uuid: uuid_lib.UUID,
    claims: AdminClaims,  # type: ignore[assignment]
    session: DbSession,  # type: ignore[assignment]
) -> dict[str, object]:
    """No body required -- the admin issues a reset, the handler
    generates the password. The ``AdminResetPasswordRequest`` schema
    is reserved for the future ``new_password`` override path; we
    intentionally do NOT require it here so the form (which POSTs
    with no body) round-trips cleanly. ``None`` is the default."""
    payload = AdminResetPasswordRequest()
    actor_uuid = _actor_uuid_from_claims(claims)
    await _require_usuario_in_scope(session, claims, uuid)
    try:
        plaintext, user_uuid = await admin_repo.reset_admin_password(
            session,
            actor_uuid=actor_uuid,
            usuario_uuid=uuid,
            new_password=payload.new_password,
        )
    except admin_repo.UsuarioNoEncontradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    await session.commit()
    logger.info(
        "admin_usuarios.reset_password",
        extra={
            "actor": str(actor_uuid),
            "user_uuid": str(user_uuid),
        },
    )
    # The response shape is intentionally minimal -- the admin reads
    # the plaintext and types it into the operator's terminal. The
    # response is also logged at info level so the audit trail includes
    # WHO issued the reset, even though the plaintext itself is NOT
    # logged (that would be a security regression).
    return {
        "uuid_usuario": str(user_uuid),
        "temporary_password": plaintext,
        "message": (
            "Password reset. Provide the temporary password to the "
            "operator out-of-band; they must change it on next login."
        ),
    }
