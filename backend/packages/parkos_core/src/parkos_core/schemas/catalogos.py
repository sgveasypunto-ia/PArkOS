"""Catalog-domain Pydantic schemas (PR1b smoke mount + PR3 full).

PR1b ships only ``TipoPersonaRead/Create/Update/Filter/ReadList`` for the
``api/v1/catalogos.py`` smoke mount. PR3 extends this file with the other
8 catalog tables (tipos_vehiculo, tipo_subscripciones, tipo_tarifa,
tipo_sucursal, tipo_arqueo, impuestos, otros_cobros, costos_servicios).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

from pydantic import StringConstraints
from typing_extensions import Annotated

from .common import FilterBase, ReadListBase, _Base


class TipoPersonaRead(_Base):
    """Catalog read-back for ``prod.tipo_persona``."""

    uuid: uuid_lib.UUID
    tipo: str | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class TipoPersonaCreate(_Base):
    """REQ-03-V-INSERCION. ``tipo`` is the business key; versioning columns
    excluded (C-6 bi-temporal-crud).
    """

    tipo: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class TipoPersonaUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create."""

    tipo: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class TipoPersonaFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None


class TipoPersonaReadList(ReadListBase[TipoPersonaRead]):
    pass


__all__ = [
    "TipoPersonaRead",
    "TipoPersonaCreate",
    "TipoPersonaUpdate",
    "TipoPersonaFilter",
    "TipoPersonaReadList",
]