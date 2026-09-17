"""Pydantic schemas for the auth-domain tables (PR1b).

Tables covered:
- ``usuarios`` ([V])
- ``permisos`` ([V])
- ``permisos_usuario`` ([V] junction)
- ``usuarios_sucursal`` ([V] junction)
- ``login`` ([L-S])

Field names mirror ORM column names 1:1 (no aliases — C-3 bi-temporal-crud).
For [V] tables the bi-temporal columns (``vigente_desde``, ``vigente_hasta``,
``estado``) are excluded from ``Create`` and ``Update``: the server-side
``repo.versioned.close_and_insert`` is the sole writer of those columns.
``Update`` mirrors ``Create`` — both produce the new version's payload;
the close+insert pattern handles the temporal swap in one TX.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints

from ._email import ParkosEmail
from .common import FilterBase, ReadListBase, _Base

# ---------------------------------------------------------------------------
# usuarios ([V])
# ---------------------------------------------------------------------------


class UsuariosRead(_Base):
    """Full row read-back for ``prod.usuarios``."""

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


class UsuariosCreate(_Base):
    """REQ-01/03-V-INSERCION. Clients MUST NOT supply versioning columns
    (C-6 in bi-temporal-crud.md). ``extra='forbid'`` from :class:`_Base`
    rejects them with 422.
    """

    nombre: Annotated[str | None, StringConstraints(max_length=255)] = None
    apellido: Annotated[str | None, StringConstraints(max_length=255)] = None
    cedula: Annotated[str | None, StringConstraints(max_length=64)] = None
    email: ParkosEmail | None = None
    password_hash: Annotated[str, StringConstraints(min_length=1)] = Field(
        ..., description="Already-hashed bcrypt; never accept plaintext here."
    )
    fecha_cambio_password: datetime | None = None
    rol: Annotated[str, StringConstraints(min_length=1, max_length=32)] = Field(
        ..., description="'admin' | 'operador'"
    )


class UsuariosUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. The new version's payload — close+insert happens
    in ``repo.versioned.close_and_insert``.
    """

    nombre: Annotated[str | None, StringConstraints(max_length=255)] = None
    apellido: Annotated[str | None, StringConstraints(max_length=255)] = None
    cedula: Annotated[str | None, StringConstraints(max_length=64)] = None
    email: ParkosEmail | None = None
    password_hash: Annotated[str | None, StringConstraints(min_length=1)] = None
    fecha_cambio_password: datetime | None = None
    rol: Annotated[str | None, StringConstraints(max_length=32)] = None


class UsuariosFilter(FilterBase):
    estado: str | None = None
    rol: str | None = None
    cedula: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None


class UsuariosReadList(ReadListBase[UsuariosRead]):
    pass


# ---------------------------------------------------------------------------
# permisos ([V])
# ---------------------------------------------------------------------------


class PermisosRead(_Base):
    uuid: uuid_lib.UUID
    permiso: str | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class PermisosCreate(_Base):
    permiso: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class PermisosUpdate(_Base):
    permiso: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class PermisosFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None


class PermisosReadList(ReadListBase[PermisosRead]):
    pass


# ---------------------------------------------------------------------------
# permisos_usuario ([V] junction)
# ---------------------------------------------------------------------------


class PermisosUsuarioRead(_Base):
    uuid: uuid_lib.UUID
    uuid_usuario: uuid_lib.UUID | None
    uuid_permiso: uuid_lib.UUID | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class PermisosUsuarioCreate(_Base):
    uuid_usuario: uuid_lib.UUID
    uuid_permiso: uuid_lib.UUID


class PermisosUsuarioUpdate(_Base):
    uuid_usuario: uuid_lib.UUID
    uuid_permiso: uuid_lib.UUID


class PermisosUsuarioFilter(FilterBase):
    uuid_usuario: uuid_lib.UUID | None = None
    uuid_permiso: uuid_lib.UUID | None = None
    estado: str | None = None


class PermisosUsuarioReadList(ReadListBase[PermisosUsuarioRead]):
    pass


# ---------------------------------------------------------------------------
# usuarios_sucursal ([V] junction)
# ---------------------------------------------------------------------------


class UsuariosSucursalRead(_Base):
    uuid: uuid_lib.UUID
    uuid_sucursal: uuid_lib.UUID | None
    uuid_usuario: uuid_lib.UUID | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class UsuariosSucursalCreate(_Base):
    uuid_sucursal: uuid_lib.UUID
    uuid_usuario: uuid_lib.UUID


class UsuariosSucursalUpdate(_Base):
    uuid_sucursal: uuid_lib.UUID
    uuid_usuario: uuid_lib.UUID


class UsuariosSucursalFilter(FilterBase):
    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_usuario: uuid_lib.UUID | None = None
    estado: str | None = None


class UsuariosSucursalReadList(ReadListBase[UsuariosSucursalRead]):
    pass


# ---------------------------------------------------------------------------
# login ([L-S])
# ---------------------------------------------------------------------------


class LoginRead(_Base):
    uuid: uuid_lib.UUID
    uuid_usuario: uuid_lib.UUID | None
    uuid_sucursal: uuid_lib.UUID | None
    timestamp_evento: datetime | None
    timestamp_cierre: datetime | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class LoginCreate(_Base):
    """REQ-42-S-LOGIN. Written by ``repo.session_cycle.record_login``."""

    uuid_usuario: uuid_lib.UUID
    uuid_sucursal: uuid_lib.UUID


class LoginFilter(FilterBase):
    uuid_usuario: uuid_lib.UUID | None = None
    uuid_sucursal: uuid_lib.UUID | None = None
    estado: str | None = None


class LoginReadList(ReadListBase[LoginRead]):
    pass


# ---------------------------------------------------------------------------
# Auth API payloads (auth.py router)
# ---------------------------------------------------------------------------


class LoginRequest(_Base):
    """POST /auth/login body."""

    email: ParkosEmail
    password: Annotated[str, StringConstraints(min_length=8, max_length=128)]


class RefreshRequest(_Base):
    """POST /auth/refresh body."""

    refresh_token: Annotated[str, StringConstraints(min_length=1)]


class TokenPair(_Base):
    """Successful login response (REQ-42)."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


# ---------------------------------------------------------------------------
# GET /auth/me — HU-F1.2 (R-F1.2-5..9)
# ---------------------------------------------------------------------------


class UserItem(_Base):
    """Identity block of ``AuthMeResponse``.

    Mirrors the columns the operator UI needs to render the avatar/name
    panel from the access token alone — no extra roundtrip to ``/usuarios``
    required.
    """

    uuid: uuid_lib.UUID
    email: str | None = None
    nombre: str | None = None
    apellido: str | None = None
    rol: str | None = None


class SucursalItem(_Base):
    """Branch block. Reused by both the singular ``sucursal`` (JWT claim)
    and the plural ``sucursales_permitidas`` (DB-driven list of every
    active assignment)."""

    uuid: uuid_lib.UUID
    nombre: str | None = None
    prefijo_nombre: str | None = None


class AuthMeResponse(_Base):
    """``GET /api/v1/auth/me`` response — operator session profile.

    Five populated blocks (R-F1.2-5..9):

    - ``user`` — identity (from ``prod.usuarios``).
    - ``sucursal`` — single branch pinned by the ``operador-`` JWT
      (the ``sucursal`` claim). Mirrors the JWT pinneado.
    - ``sucursales_permitidas`` — ALL active ``usuarios_sucursal`` for
      the actor, ordered by ``sucursal.nombre ASC``. Includes the
      singular ``sucursal`` above (subset relationship).
    - ``permisos`` — list of permission codes (``[]`` if none).
    - ``expires_at`` — ISO 8601 UTC derived from the JWT ``exp`` claim.

    ASIMETRÍA (KD-4 del design): ``sucursal`` es el pinneado del JWT
    (singular) y ``sucursales_permitidas`` es la lista completa de DB
    (plural). El subset relationship
    (``sucursal.uuid in {s.uuid for s in sucursales_permitidas}``)
    se mantiene por invariante y se valida en
    ``test_auth_me_multi_branch.py``.
    """

    user: UserItem
    sucursal: SucursalItem
    sucursales_permitidas: list[SucursalItem]
    permisos: list[str]
    expires_at: str  # ISO 8601 UTC, derivated from JWT exp claim


__all__ = [
    "AuthMeResponse",
    "LoginCreate",
    "LoginFilter",
    "LoginRead",
    "LoginReadList",
    "LoginRequest",
    "PermisosCreate",
    "PermisosFilter",
    "PermisosRead",
    "PermisosReadList",
    "PermisosUpdate",
    "PermisosUsuarioCreate",
    "PermisosUsuarioFilter",
    "PermisosUsuarioRead",
    "PermisosUsuarioReadList",
    "PermisosUsuarioUpdate",
    "RefreshRequest",
    "SucursalItem",
    "TokenPair",
    "UserItem",
    "UsuariosCreate",
    "UsuariosFilter",
    "UsuariosRead",
    "UsuariosReadList",
    "UsuariosSucursalCreate",
    "UsuariosSucursalFilter",
    "UsuariosSucursalRead",
    "UsuariosSucursalReadList",
    "UsuariosSucursalUpdate",
    "UsuariosUpdate",
]