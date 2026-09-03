"""Pydantic schemas for ``prod.tipo_sucursal`` (PR3 catalog domain)."""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from typing import Annotated, Any

from pydantic import StringConstraints

from .common import FilterBase, ReadListBase, _Base


class TipoSucursalRead(_Base):
    """Catalog read-back for ``prod.tipo_sucursal``."""

    uuid: uuid_lib.UUID
    codigo: str | None
    nombre: str | None
    descripcion: str | None
    caracteristicas: dict[str, Any] | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class TipoSucursalCreate(_Base):
    """REQ-03-V-INSERCION. ``codigo`` is the business key (UK01 with vigente_desde).
    Versioning columns excluded by ``extra='forbid'`` (C-6 bi-temporal-crud).
    """

    codigo: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    nombre: Annotated[str, StringConstraints(max_length=255)] | None = None
    descripcion: str | None = None
    caracteristicas: dict[str, Any] | None = None


class TipoSucursalUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create."""

    codigo: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    nombre: Annotated[str, StringConstraints(max_length=255)] | None = None
    descripcion: str | None = None
    caracteristicas: dict[str, Any] | None = None


class TipoSucursalFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    codigo: str | None = None


class TipoSucursalReadList(ReadListBase[TipoSucursalRead]):
    pass


__all__ = [
    "TipoSucursalCreate",
    "TipoSucursalFilter",
    "TipoSucursalRead",
    "TipoSucursalReadList",
    "TipoSucursalUpdate",
]
