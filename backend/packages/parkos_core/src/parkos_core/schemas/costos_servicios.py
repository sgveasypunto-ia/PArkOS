"""Pydantic schemas for ``prod.costos_servicios`` (PR3 catalog domain)."""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import StringConstraints

from .common import FilterBase, ReadListBase, _Base


class CostosServiciosRead(_Base):
    """Catalog read-back for ``prod.costos_servicios``."""

    uuid: uuid_lib.UUID
    concepto: str | None
    costo: Decimal | None
    tipo_calculo: str | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class CostosServiciosCreate(_Base):
    """REQ-03-V-INSERCION. ``concepto`` is the business key (UK01 with vigente_desde).
    Versioning columns excluded by ``extra='forbid'`` (C-6 bi-temporal-crud).
    """

    concepto: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    costo: Decimal | None = None
    tipo_calculo: Annotated[str, StringConstraints(max_length=32)] | None = None


class CostosServiciosUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create."""

    concepto: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    costo: Decimal | None = None
    tipo_calculo: Annotated[str, StringConstraints(max_length=32)] | None = None


class CostosServiciosFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    concepto: str | None = None
    tipo_calculo: str | None = None


class CostosServiciosReadList(ReadListBase[CostosServiciosRead]):
    pass


__all__ = [
    "CostosServiciosCreate",
    "CostosServiciosFilter",
    "CostosServiciosRead",
    "CostosServiciosReadList",
    "CostosServiciosUpdate",
]
