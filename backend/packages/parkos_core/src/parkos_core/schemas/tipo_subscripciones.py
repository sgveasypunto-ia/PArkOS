"""Pydantic schemas for ``prod.tipo_subscripciones`` (PR3 catalog domain)."""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import StringConstraints

from .common import FilterBase, ReadListBase, _Base


class TipoSubscripcionesRead(_Base):
    """Catalog read-back for ``prod.tipo_subscripciones``."""

    uuid: uuid_lib.UUID
    tipo: str | None
    valor: Decimal | None
    duracion_dias: int | None
    cantidad_maxima_vehiculos: int | None
    mismo_tipo_vehiculo: bool | None
    tipo_cliente_permitido: str | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class TipoSubscripcionesCreate(_Base):
    """REQ-03-V-INSERCION. Versioning columns excluded by ``extra='forbid'`` (C-6)."""

    tipo: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    valor: Decimal | None = None
    duracion_dias: int | None = None
    cantidad_maxima_vehiculos: int | None = None
    mismo_tipo_vehiculo: bool | None = None
    tipo_cliente_permitido: Annotated[str, StringConstraints(max_length=64)] | None = None


class TipoSubscripcionesUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create."""

    tipo: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    valor: Decimal | None = None
    duracion_dias: int | None = None
    cantidad_maxima_vehiculos: int | None = None
    mismo_tipo_vehiculo: bool | None = None
    tipo_cliente_permitido: Annotated[str, StringConstraints(max_length=64)] | None = None


class TipoSubscripcionesFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    duracion_dias__gte: int | None = None
    duracion_dias__lte: int | None = None


class TipoSubscripcionesReadList(ReadListBase[TipoSubscripcionesRead]):
    pass


__all__ = [
    "TipoSubscripcionesCreate",
    "TipoSubscripcionesFilter",
    "TipoSubscripcionesRead",
    "TipoSubscripcionesReadList",
    "TipoSubscripcionesUpdate",
]
