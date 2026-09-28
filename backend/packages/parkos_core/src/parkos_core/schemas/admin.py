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


class AdminUsuarioRead(_Base):
    """Read-back shape for ``GET /admin/usuarios`` (single + list).

    Deliberately OMITS ``password_hash`` -- never leak the hash at the
    HTTP edge. The ``__init__.py`` model_config's ``extra='forbid'``
    will reject any client that sends ``password_hash`` back.
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
    sync_status: str | None


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
    """

    uuid: uuid_lib.UUID
    uuid_sucursal: uuid_lib.UUID
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
