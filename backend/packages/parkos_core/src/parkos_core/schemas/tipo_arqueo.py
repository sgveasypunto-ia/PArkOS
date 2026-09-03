"""Pydantic schemas for ``prod.tipo_arqueo`` (PR3 catalog domain)."""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from typing import Annotated

from pydantic import StringConstraints

from .common import FilterBase, ReadListBase, _Base


class TipoArqueoRead(_Base):
    """Catalog read-back for ``prod.tipo_arqueo``."""

    uuid: uuid_lib.UUID
    codigo: str | None
    nombre: str | None
    descripcion: str | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class TipoArqueoCreate(_Base):
    """REQ-03-V-INSERCION. ``codigo`` is the business key (UK01 with vigente_desde).
    Versioning columns excluded by ``extra='forbid'`` (C-6 bi-temporal-crud).
    """

    codigo: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    nombre: Annotated[str, StringConstraints(max_length=255)] | None = None
    descripcion: str | None = None


class TipoArqueoUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create."""

    codigo: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    nombre: Annotated[str, StringConstraints(max_length=255)] | None = None
    descripcion: str | None = None


class TipoArqueoFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    codigo: str | None = None


class TipoArqueoReadList(ReadListBase[TipoArqueoRead]):
    pass


__all__ = [
    "TipoArqueoCreate",
    "TipoArqueoFilter",
    "TipoArqueoRead",
    "TipoArqueoReadList",
    "TipoArqueoUpdate",
]