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

from pydantic import EmailStr, Field, StringConstraints
from typing_extensions import Annotated

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
    email: EmailStr | None = None
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
    email: EmailStr | None = None
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

    email: EmailStr
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


__all__ = [
    "UsuariosRead",
    "UsuariosCreate",
    "UsuariosUpdate",
    "UsuariosFilter",
    "UsuariosReadList",
    "PermisosRead",
    "PermisosCreate",
    "PermisosUpdate",
    "PermisosFilter",
    "PermisosReadList",
    "PermisosUsuarioRead",
    "PermisosUsuarioCreate",
    "PermisosUsuarioUpdate",
    "PermisosUsuarioFilter",
    "PermisosUsuarioReadList",
    "UsuariosSucursalRead",
    "UsuariosSucursalCreate",
    "UsuariosSucursalUpdate",
    "UsuariosSucursalFilter",
    "UsuariosSucursalReadList",
    "LoginRead",
    "LoginCreate",
    "LoginFilter",
    "LoginReadList",
    "LoginRequest",
    "RefreshRequest",
    "TokenPair",
]