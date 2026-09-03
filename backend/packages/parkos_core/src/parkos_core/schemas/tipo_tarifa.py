"""Pydantic schemas for ``prod.tipo_tarifa`` (PR3 catalog domain)."""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from typing import Annotated

from pydantic import StringConstraints

from .common import FilterBase, ReadListBase, _Base


class TipoTarifaRead(_Base):
    """Catalog read-back for ``prod.tipo_tarifa``."""

    uuid: uuid_lib.UUID
    tipo: str | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class TipoTarifaCreate(_Base):
    """REQ-03-V-INSERCION. ``tipo`` is the business key; versioning columns
    excluded by ``extra='forbid'`` (C-6 bi-temporal-crud).
    """

    tipo: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class TipoTarifaUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create."""

    tipo: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class TipoTarifaFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None


class TipoTarifaReadList(ReadListBase[TipoTarifaRead]):
    pass


__all__ = [
    "TipoTarifaCreate",
    "TipoTarifaFilter",
    "TipoTarifaRead",
    "TipoTarifaReadList",
    "TipoTarifaUpdate",
]
