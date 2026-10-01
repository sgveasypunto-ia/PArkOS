"""Pydantic schemas for the per-branch configuration domain (PR4, HU-F13.3).

Covers 3 ``[V]`` tables in ``prod``:

- :class:`ConfiguracionTolerancias` — cash-counting tolerances (``uuid_sucursal``
  NULL = global default; per-branch rows override it).
- :class:`ConfiguracionSeguridad` — access policy (``uuid_sucursal`` NULL =
  global default; per-branch rows override it).
- :class:`ConfiguracionCaja` — cash-box config (base inicial sugerida,
  redondeo, denominaciones permitidas); same override shape (HU-F13.3,
  DEC-ADM-12).

Override resolution pattern (REQ-OP-12 + SC-OP-06): the
``GET /configuracion-seguridad/efectiva?uuid_sucursal=<uuid>`` route in
T-PR4-04 picks the per-branch row if present, otherwise falls back to the
global default (``uuid_sucursal IS NULL``).
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from decimal import Decimal
from typing import Literal

from .common import FilterBase, ReadListBase, _Base

# ---------------------------------------------------------------------------
# ConfiguracionTolerancias
# ---------------------------------------------------------------------------


class ConfiguracionToleranciasRead(_Base):
    """Read-back for ``prod.configuracion_tolerancias``. ``uuid_sucursal``
    NULL marks the global default row."""

    uuid: uuid_lib.UUID
    uuid_sucursal: uuid_lib.UUID | None
    tolerancia_efectivo: Decimal | None
    tolerancia_datafono: Decimal | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class ConfiguracionToleranciasCreate(_Base):
    """REQ-03-V-INSERCION. ``uuid_sucursal`` is optional: NULL writes the
    global default, a non-null value writes the per-branch override (REQ-OP-12)."""

    uuid_sucursal: uuid_lib.UUID | None = None
    tolerancia_efectivo: Decimal | None = None
    tolerancia_datafono: Decimal | None = None


class ConfiguracionToleranciasUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create."""

    uuid_sucursal: uuid_lib.UUID | None = None
    tolerancia_efectivo: Decimal | None = None
    tolerancia_datafono: Decimal | None = None


class ConfiguracionToleranciasFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    uuid_sucursal: uuid_lib.UUID | None = None


class ConfiguracionToleranciasReadList(ReadListBase[ConfiguracionToleranciasRead]):
    pass


# ---------------------------------------------------------------------------
# ConfiguracionSeguridad
# ---------------------------------------------------------------------------


class ConfiguracionSeguridadRead(_Base):
    """Read-back for ``prod.configuracion_seguridad``. ``uuid_sucursal``
    NULL marks the global default row."""

    uuid: uuid_lib.UUID
    uuid_sucursal: uuid_lib.UUID | None
    dias_expiracion_password: int | None
    max_intentos_login: int | None
    minutos_bloqueo_login: int | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class ConfiguracionSeguridadCreate(_Base):
    """REQ-03-V-INSERCION. ``uuid_sucursal`` is optional: NULL writes the
    global default, a non-null value writes the per-branch override (REQ-OP-12)."""

    uuid_sucursal: uuid_lib.UUID | None = None
    dias_expiracion_password: int | None = None
    max_intentos_login: int | None = None
    minutos_bloqueo_login: int | None = None


class ConfiguracionSeguridadUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create."""

    uuid_sucursal: uuid_lib.UUID | None = None
    dias_expiracion_password: int | None = None
    max_intentos_login: int | None = None
    minutos_bloqueo_login: int | None = None


class ConfiguracionSeguridadFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    uuid_sucursal: uuid_lib.UUID | None = None


class ConfiguracionSeguridadReadList(ReadListBase[ConfiguracionSeguridadRead]):
    pass


# ---------------------------------------------------------------------------
# ConfiguracionCaja (HU-F13.3)
# ---------------------------------------------------------------------------

Redondeo = Literal["ninguno", "100", "500", "1000"]


class ConfiguracionCajaRead(_Base):
    """Read-back for ``prod.configuracion_caja``. ``uuid_sucursal``
    NULL marks the global default row."""

    uuid: uuid_lib.UUID
    uuid_sucursal: uuid_lib.UUID | None
    base_inicial_sugerida: Decimal | None
    redondeo: Redondeo | None
    denominaciones_permitidas: list[int] | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class ConfiguracionCajaCreate(_Base):
    """REQ-03-V-INSERCION. ``uuid_sucursal`` is optional: NULL writes the
    global default, a non-null value writes the per-branch override (REQ-OP-12)."""

    uuid_sucursal: uuid_lib.UUID | None = None
    base_inicial_sugerida: Decimal | None = None
    redondeo: Redondeo | None = None
    denominaciones_permitidas: list[int] | None = None


class ConfiguracionCajaUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create."""

    uuid_sucursal: uuid_lib.UUID | None = None
    base_inicial_sugerida: Decimal | None = None
    redondeo: Redondeo | None = None
    denominaciones_permitidas: list[int] | None = None


class ConfiguracionCajaFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    uuid_sucursal: uuid_lib.UUID | None = None


class ConfiguracionCajaReadList(ReadListBase[ConfiguracionCajaRead]):
    pass


__all__ = [
    "ConfiguracionCajaCreate",
    "ConfiguracionCajaFilter",
    "ConfiguracionCajaRead",
    "ConfiguracionCajaReadList",
    "ConfiguracionCajaUpdate",
    "ConfiguracionSeguridadCreate",
    "ConfiguracionSeguridadFilter",
    "ConfiguracionSeguridadRead",
    "ConfiguracionSeguridadReadList",
    "ConfiguracionSeguridadUpdate",
    "ConfiguracionToleranciasCreate",
    "ConfiguracionToleranciasFilter",
    "ConfiguracionToleranciasRead",
    "ConfiguracionToleranciasReadList",
    "ConfiguracionToleranciasUpdate",
]
