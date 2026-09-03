"""Pydantic schemas for ``prod.otros_cobros`` (PR3 catalog domain)."""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import StringConstraints

from .common import FilterBase, ReadListBase, _Base


class OtrosCobrosRead(_Base):
    """Catalog read-back for ``prod.otros_cobros``."""

    uuid: uuid_lib.UUID
    nombre: str | None
    costo: Decimal | None
    tipo_calculo: str | None
    base_calculo: str | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class OtrosCobrosCreate(_Base):
    """REQ-03-V-INSERCION. ``nombre`` is the business key (UK01 with vigente_desde).
    Versioning columns excluded by ``extra='forbid'`` (C-6 bi-temporal-crud).
    """

    nombre: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    costo: Decimal | None = None
    tipo_calculo: Annotated[str, StringConstraints(max_length=32)] | None = None
    base_calculo: Annotated[str, StringConstraints(max_length=32)] | None = None


class OtrosCobrosUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create."""

    nombre: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    costo: Decimal | None = None
    tipo_calculo: Annotated[str, StringConstraints(max_length=32)] | None = None
    base_calculo: Annotated[str, StringConstraints(max_length=32)] | None = None


class OtrosCobrosFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    nombre: str | None = None
    tipo_calculo: str | None = None


class OtrosCobrosReadList(ReadListBase[OtrosCobrosRead]):
    pass


__all__ = [
    "OtrosCobrosCreate",
    "OtrosCobrosFilter",
    "OtrosCobrosRead",
    "OtrosCobrosReadList",
    "OtrosCobrosUpdate",
]