"""Pydantic schemas for ``prod.impuestos`` (PR3 catalog domain)."""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import StringConstraints

from .common import FilterBase, ReadListBase, _Base


class ImpuestosRead(_Base):
    """Catalog read-back for ``prod.impuestos``."""

    uuid: uuid_lib.UUID
    nombre: str | None
    codigo: str | None
    porcentaje: Decimal | None
    tipo_calculo: str | None
    base_calculo: str | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class ImpuestosCreate(_Base):
    """REQ-03-V-INSERCION. ``codigo`` is the business key (UK01 with vigente_desde).
    Versioning columns excluded by ``extra='forbid'`` (C-6 bi-temporal-crud).
    """

    nombre: Annotated[str, StringConstraints(max_length=255)] | None = None
    codigo: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    porcentaje: Decimal | None = None
    tipo_calculo: Annotated[str, StringConstraints(max_length=32)] | None = None
    base_calculo: Annotated[str, StringConstraints(max_length=32)] | None = None


class ImpuestosUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create."""

    nombre: Annotated[str, StringConstraints(max_length=255)] | None = None
    codigo: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    porcentaje: Decimal | None = None
    tipo_calculo: Annotated[str, StringConstraints(max_length=32)] | None = None
    base_calculo: Annotated[str, StringConstraints(max_length=32)] | None = None


class ImpuestosFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    codigo: str | None = None
    tipo_calculo: str | None = None


class ImpuestosReadList(ReadListBase[ImpuestosRead]):
    pass


__all__ = [
    "ImpuestosCreate",
    "ImpuestosFilter",
    "ImpuestosRead",
    "ImpuestosReadList",
    "ImpuestosUpdate",
]
