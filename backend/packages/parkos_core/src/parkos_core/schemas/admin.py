"""Pydantic schemas for the admin user-management endpoints (IT-1.4,
IT-1.5 of ``openspec/_meta/iteration-plan.md``).

Why a separate module: ``schemas/auth.py`` already covers ``Login``,
``Register`` (HU-F1.2), and ``LoginHistorico`` (HU-F1.15). The admin
schemas are write-side (``POST /admin/usuarios``, ``POST /admin/usuarios/
{uuid}/sucursales``) and deliberately accept ``password`` as PLAINTEXT
at the edge so the handler can bcrypt it server-side. The existing
``UsuariosCreate`` in ``schemas/auth.py`` takes an already-hashed
``password_hash`` -- that's the right shape for ``close_and_insert``
re-use but the wrong shape for the HTTP edge.

Field policy
------------

- ``extra='forbid'`` (inherited from :class:`_Base`) -- clients cannot
  smuggle versioning columns (``vigente_desde``, ``vigente_hasta``,
  ``estado``, ``created_at``, ``created_by``, ``sync_status``); the
  handler writes those through ``close_and_insert`` which sets them
  server-side.
- ``password`` is ``min_length=8`` -- aligned with
  ``backend/.../schemas/auth.py::LoginRequest.password``.
- ``rol`` is one of ``{"admin", "operador"}`` -- matches the column
  comment in ``models/V/usuarios.py``.
- ``uuid_sucursal`` accepts a single UUID in the create-user call; the
  handler fans out to insert one ``usuarios_sucursal`` row per UUID in
  the list, and queues one ``sync_queue`` row per UUID so the existing
  apply-pending loop drips each branch.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints

from ._email import ParkosEmail
from .common import ReadListBase, _Base


class AdminUsuarioCreateRequest(_Base):
    """Edge schema for ``POST /api/v1/admin/usuarios``.

    Differs from ``schemas.auth.UsuariosCreate`` in one important way:
    ``password`` is plaintext. The handler bcrypts it before calling
    ``close_and_insert`` so the hash is what hits the ``[V]`` table.
    """

    nombre: Annotated[str | None, StringConstraints(max_length=255)] = None
    apellido: Annotated[str | None, StringConstraints(max_length=255)] = None
    cedula: Annotated[str | None, StringConstraints(max_length=64)] = None
    email: ParkosEmail
    password: Annotated[str, StringConstraints(min_length=8, max_length=128)]
    rol: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    # Initial branch assignments. Empty list = create the user without
    # branch assignment; the admin can attach branches later via
    # ``POST /admin/usuarios/{uuid}/sucursales``.
    sucursales_asignadas: list[uuid_lib.UUID] = Field(default_factory=list)


class SucursalAsignadaResumen(_Base):
    """Lightweight per-branch payload embedded in :class:`AdminUsuarioRead`.

    Returned by ``GET /admin/usuarios`` (list + single) so the admin
    users table can render a Sucursales column without a second round
    trip per row. Distinct from :class:`AdminSucursalAsignadaRead`,
    which carries the full bi-temporal lifecycle fields for the
    dedicated ``GET /admin/usuarios/{uuid}/sucursales`` endpoint.

    Only currently-open assignments (``vigente_hasta IS NULL``) are
    surfaced. The branch-side join also requires the joined
    ``prod.sucursal`` row to be the currently-open version -- an
    assignment to a long-since-closed branch still appears here but
    with ``nombre=None``/``prefijo_nombre=None`` to signal "the
    assignment is real but the branch as a unit is gone". We keep the
    row rather than silently dropping it: it is auditable evidence
    that this user once had access to that branch.
    """

    uuid_sucursal: uuid_lib.UUID
    nombre: str | None
    prefijo_nombre: str | None
    vigente_desde: datetime


class AdminUsuarioRead(_Base):
    """Read-back shape for ``GET /admin/usuarios`` (single + list).

    Deliberately OMITS ``password_hash`` -- never leak the hash at the
    HTTP edge. The ``__init__.py`` model_config's ``extra='forbid'``
    will reject any client that sends ``password_hash`` back.

    The ``sucursales`` field carries the user's currently-open branch
    assignments (one entry per active assignment). It is populated by
    the handler from :func:`repo.admin_usuarios.
    list_branch_assignments_for_users`, which runs a single
    ``WHERE uuid_usuario IN (...) AND vigente_hasta IS NULL`` query
    so listing N users costs exactly ONE extra round trip -- no N+1.
    Default ``[]`` so a malformed payload still validates against the
    schema.
    """

    uuid: uuid_lib.UUID
    nombre: str | None
    apellido: str | None
    cedula: str | None
    email: str | None
    rol: str | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sucursales: list[SucursalAsignadaResumen] = Field(default_factory=list)


class AdminUsuarioReadList(ReadListBase[AdminUsuarioRead]):
    pass


class AdminAsignarSucursalRequest(_Base):
    """Edge schema for ``POST /admin/usuarios/{uuid}/sucursales``.

    One assignment per request -- the close+insert pattern opens a new
    ``vigente_desde`` window for the user-branch pair; a second
    assignment while the previous is still open is a 409 (the unique
    constraint on ``(uuid_sucursal, uuid_usuario, vigente_desde)``
    rejects it).
    """

    uuid_sucursal: uuid_lib.UUID


class AdminSucursalAsignadaRead(_Base):
    """One row in ``GET /admin/usuarios/{uuid}/sucursales``.

    Returns the currently-open (``vigente_hasta IS NULL``) branch
    assignments for the user.

    ``uuid_usuario`` is required here because the frontend's
    ``sucursalUsuarioSchema`` (Zod) requires it too -- without this
    field the wire payload fails that Zod parse for EVERY user with
    at least one assignment, and ``SucursalesAsignadas.tsx`` swallows
    the resulting SWR error silently (no error branch), rendering
    "No hay sucursales asignadas" even when assignments exist. Found
    live via qa/batch-usuarios (2026-10-02): the detail page's
    Sucursales tab never worked for ANY user before this fix.
    """

    uuid: uuid_lib.UUID
    uuid_usuario: uuid_lib.UUID
    uuid_sucursal: uuid_lib.UUID
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str


# ---------------------------------------------------------------------------
# HU-F16 -- remaining read/write endpoints
# ---------------------------------------------------------------------------


class AdminUsuarioUpdateRequest(_Base):
    """Edge schema for ``PUT /api/v1/admin/usuarios/{uuid}``.

    Bi-temporal close+insert: every field is optional + nullable so the
    caller can patch a single field without sending the whole user.
    The handler maps ``None`` to "do not touch" and the absence of a
    key to "do not touch" too -- both mean "leave the existing value
    alone". A field present with ``null`` ALSO means "do not touch"
    (it is typed ``Optional[...]``); clearing a value would need a
    different endpoint, not in scope here.

    Re-using the read model types (every field Optional + ``str``) keeps
    the round-trip lossy-free: the edit form can pre-fill straight
    from ``GET /admin/usuarios/{uuid}`` without casting. Mirrors the
    Zod ``usuarioUpdateSchema`` on the frontend side
    (``apps/web_admin/src/features/usuarios/api/usuariosSchema.ts:43``).
    """

    nombre: Annotated[str | None, StringConstraints(max_length=255)] = None
    apellido: Annotated[str | None, StringConstraints(max_length=255)] = None
    cedula: Annotated[str | None, StringConstraints(max_length=64)] = None
    email: ParkosEmail | None = None
    rol: Annotated[str | None, StringConstraints(max_length=32)] = None


class AdminPermisoRead(_Base):
    """One row in ``GET /api/v1/admin/permisos``.

    The catalog table (``prod.permisos``) carries only the ``permiso``
    code column; the schema exposes it as ``codigo`` because
    ``permiso`` is reserved at the Python ORM level for the column
    accessor (same pattern as ``schemas/auth.py::TokenPair.token_type``).
    ``descripcion`` is reserved for a future catalog enrichment; the
    underlying column does NOT exist yet, so the handler returns
    ``None`` until then -- matches the Zod ``permisoSchema``.
    """

    uuid: uuid_lib.UUID
    codigo: str | None
    descripcion: str | None = None


class AdminPermisoUsuarioRead(_Base):
    """One row in ``GET /admin/usuarios/{uuid}/permisos``.

    Mirrors ``prod.permisos_usuario`` joined with ``prod.permisos`` for
    the human-readable code. Only currently-open grants
    (``vigente_hasta IS NULL``) are returned.
    """

    uuid: uuid_lib.UUID
    uuid_usuario: uuid_lib.UUID
    uuid_permiso: uuid_lib.UUID
    codigo: str | None
    vigente_desde: datetime
    vigente_hasta: datetime | None


class AdminAsignarPermisoRequest(_Base):
    """Edge schema for ``POST /admin/usuarios/{uuid}/permisos/{permiso_uuid}``.

    Empty body -- the permission uuid is in the path. The handler's
    only job is to open the bi-temporal junction row. Returns 409
    if the user already holds that permission (the UK on
    ``(uuid_usuario, uuid_permiso, vigente_desde)`` rejects it).
    """


class AdminSesionRead(_Base):
    """One row in ``GET /admin/usuarios/{uuid}/sesiones?activas=true``.

    The underlying table (``prod.sesion``, [L-S]) has columns the
    frontend never set -- ``ip_origen`` and ``user_agent`` are NOT
    columns on ``prod.sesion`` today; they exist only on
    ``prod.login``. To keep the wire contract honest, the handler
    returns ``None`` for the fields the table does not carry rather
    than fabricate values; if a future PR adds the columns this
    schema flips to real values with no caller change.
    """

    uuid: uuid_lib.UUID
    uuid_usuario: uuid_lib.UUID
    ip_origen: str | None = None
    user_agent: str | None = None
    creado_en: datetime
    ultimo_activity: datetime | None = None
    timestamp_cierre: datetime | None = None
    estado: str | None = None


class AdminResetPasswordRequest(_Base):
    """Edge schema for ``POST /admin/usuarios/{uuid}/reset-password``.

    The handler generates a 12-char temporary password server-side
    (with mixed charset per IT-1.7 spec); ``new_password`` is reserved
    for an admin-supplied override -- not exposed in the form yet,
    so this schema is currently empty. Documented here so the route
    can grow the field without a wire-shape break later.
    """

    new_password: (
        Annotated[str, StringConstraints(min_length=8, max_length=128)] | None
    ) = None
