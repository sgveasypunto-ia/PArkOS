"""Pydantic schemas for the Empresa + Sucursal domain (PR4).

Covers 6 ``[V]`` tables in ``prod``:

- :class:`Empresa` — tax identity of the operator (UK on ``nit``).
- :class:`Sucursal` — branch master (UK on ``prefijo_nombre``).
- :class:`Documentos` — administrative files inlined as base64
  (1MB cap enforced here — REQ-OP-05).
- :class:`ResolucionFacturacion` — DIAN billing resolution per branch
  (cloud-only writes; :class:`ResolucionFacturacionCreate` server-assigns
  ``prefijo`` + ``rango_desde``/``rango_hasta`` — REQ-X3 boundary).
- :class:`TarifasSucursal` — per-branch rate by vehicle type + tariff mode.
- :class:`CantidadVehiculosSucursal` — branch capacity by vehicle type.

All schemas inherit :class:`_Base` from :mod:`.common`, which provides
``extra='forbid'`` (so clients cannot smuggle versioning columns) and
``from_attributes=True`` (so :func:`pydantic.BaseModel.model_validate` can
project an ORM row directly).
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field, StringConstraints

from .common import FilterBase, ReadListBase, _Base

# ---------------------------------------------------------------------------
# Empresa
# ---------------------------------------------------------------------------


class EmpresaRead(_Base):
    """Read-back for ``prod.empresa``. ``nit`` is the UK (with vigente_desde)."""

    uuid: uuid_lib.UUID
    nombre: str | None
    nit: str | None
    mensaje_bienvenida: str | None
    mensaje_salida: str | None
    regimen: str | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class EmpresaCreate(_Base):
    """REQ-03-V-INSERCION. Versioning columns excluded by ``extra='forbid'`` (C-6)."""

    nombre: str | None = None
    nit: str | None = None
    mensaje_bienvenida: str | None = None
    mensaje_salida: str | None = None
    regimen: str | None = None


class EmpresaUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create."""

    nombre: str | None = None
    nit: str | None = None
    mensaje_bienvenida: str | None = None
    mensaje_salida: str | None = None
    regimen: str | None = None


class EmpresaFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None


class EmpresaReadList(ReadListBase[EmpresaRead]):
    pass


# ---------------------------------------------------------------------------
# Sucursal
# ---------------------------------------------------------------------------


class SucursalRead(_Base):
    """Read-back for ``prod.sucursal``. UK is ``prefijo_nombre`` + vigente_desde."""

    uuid: uuid_lib.UUID
    nombre: str | None
    direccion: str | None
    telefono: str | None
    prefijo_nombre: str | None
    ciudad: str | None
    horario: str | None
    uuid_tipo_sucursal: uuid_lib.UUID | None
    uuid_empresa: uuid_lib.UUID | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class SucursalCreate(_Base):
    """REQ-03-V-INSERCION. UUID FKs to ``tipo_sucursal`` and ``empresa`` are
    application-enforced (no SQL FK). Mirrors the ORM nullable shape."""

    nombre: str | None = None
    direccion: str | None = None
    telefono: str | None = None
    prefijo_nombre: str | None = None
    ciudad: str | None = None
    horario: str | None = None
    uuid_tipo_sucursal: uuid_lib.UUID | None = None
    uuid_empresa: uuid_lib.UUID | None = None


class SucursalUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create."""

    nombre: str | None = None
    direccion: str | None = None
    telefono: str | None = None
    prefijo_nombre: str | None = None
    ciudad: str | None = None
    horario: str | None = None
    uuid_tipo_sucursal: uuid_lib.UUID | None = None
    uuid_empresa: uuid_lib.UUID | None = None


class SucursalFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    uuid_empresa: uuid_lib.UUID | None = None
    uuid_tipo_sucursal: uuid_lib.UUID | None = None


class SucursalReadList(ReadListBase[SucursalRead]):
    pass


# ---------------------------------------------------------------------------
# Documentos (REQ-OP-05: 1MB cap on documento_b64)
# ---------------------------------------------------------------------------


class DocumentosRead(_Base):
    """Read-back for ``prod.documentos``."""

    uuid: uuid_lib.UUID
    uuid_sucursal: uuid_lib.UUID | None
    tipo: str | None
    formato: str | None
    documento_b64: str | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class DocumentosCreate(_Base):
    """REQ-OP-05: ``documento_b64`` is capped at 1_400_000 chars (~1MB base64).
    ``StringConstraints(max_length=1_400_000)`` returns 422 if exceeded — that
    is T-PR4-09's test."""

    uuid_sucursal: uuid_lib.UUID
    tipo: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    formato: Annotated[str, StringConstraints(max_length=32)] | None = None
    documento_b64: Annotated[str, StringConstraints(max_length=1_400_000)]


class DocumentosUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create."""

    uuid_sucursal: uuid_lib.UUID
    tipo: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    formato: Annotated[str, StringConstraints(max_length=32)] | None = None
    documento_b64: Annotated[str, StringConstraints(max_length=1_400_000)]


class DocumentosFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    uuid_sucursal: uuid_lib.UUID | None = None


class DocumentosReadList(ReadListBase[DocumentosRead]):
    pass


# ---------------------------------------------------------------------------
# ResolucionFacturacion (REQ-X3: DIAN root, server-assigned ranges)
# ---------------------------------------------------------------------------


class ResolucionFacturacionRead(_Base):
    """Read-back for ``prod.resolucion_facturacion``. Includes the server-assigned
    ``prefijo`` and ``rango_desde``/``rango_hasta`` — but those are NOT accepted
    on :class:`ResolucionFacturacionCreate`."""

    uuid: uuid_lib.UUID
    uuid_sucursal: uuid_lib.UUID | None
    numero_resolucion: str | None
    prefijo: str | None
    rango_desde: int | None
    rango_hasta: int | None
    fecha_resolucion: date | None
    fecha_inicio_vigencia: date | None
    fecha_fin_vigencia: date | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class ResolucionFacturacionCreate(_Base):
    """REQ-X3: server assigns ``prefijo``, ``rango_desde``, ``rango_hasta``.
    ``extra='forbid'`` (from :class:`_Base`) blocks client-supplied values
    for those fields — that's T-PR4-08's test."""

    uuid_sucursal: uuid_lib.UUID
    numero_resolucion: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    fecha_resolucion: date
    fecha_inicio_vigencia: date
    fecha_fin_vigencia: date


class ResolucionFacturacionUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create."""

    uuid_sucursal: uuid_lib.UUID
    numero_resolucion: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    fecha_resolucion: date
    fecha_inicio_vigencia: date
    fecha_fin_vigencia: date


class ResolucionFacturacionFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    uuid_sucursal: uuid_lib.UUID | None = None


class ResolucionFacturacionReadList(ReadListBase[ResolucionFacturacionRead]):
    pass


# ---------------------------------------------------------------------------
# TarifasSucursal
# ---------------------------------------------------------------------------


class TarifasSucursalRead(_Base):
    """Read-back for ``prod.tarifas_sucursal``. UK01 is
    ``(uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa, vigente_desde)``."""

    uuid: uuid_lib.UUID
    uuid_sucursal: uuid_lib.UUID | None
    uuid_tipo_vehiculo: uuid_lib.UUID | None
    uuid_tipo_tarifa: uuid_lib.UUID | None
    valor: Decimal | None
    valor_plena: Decimal | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class TarifasSucursalCreate(_Base):
    """REQ-03-V-INSERCION. Versioning columns excluded by ``extra='forbid'`` (C-6).

    PR-C additions:

    * ``vigente_desde``: optional client-supplied valid-time. When omitted
      the factory defaults to ``clock_timestamp()`` (Carril B). When set
      in the future, the new version opens at that future instant — the
      operator schedules a rate change without a separate "scheduled
      change" feature. The handler validates the resulting window does
      not overlap any other open row for the same business key (409 if
      it does — see ``repo.overlap``).
    * ``valor > 0``, ``valor_plena >= 0``: enforced via Pydantic
      constraints so a malformed payload is rejected at the API edge
      instead of leaking through to the DB.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_tipo_vehiculo: uuid_lib.UUID | None = None
    uuid_tipo_tarifa: uuid_lib.UUID | None = None
    valor: Decimal | None = Field(default=None, gt=Decimal("0"))
    valor_plena: Decimal | None = Field(default=None, ge=Decimal("0"))
    vigente_desde: datetime | None = None


class TarifasSucursalUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create.

    PR-C: ``vigente_desde`` becomes the boundary of the close+insert
    Carril B — when set, the new version opens at that boundary AND
    the row being closed ends at the SAME boundary (no gap, no overlap
    with adjacent windows). The handler also enforces
    ``uuid_sucursal`` immutability (422 if the payload differs from
    the existing row).
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_tipo_vehiculo: uuid_lib.UUID | None = None
    uuid_tipo_tarifa: uuid_lib.UUID | None = None
    valor: Decimal | None = Field(default=None, gt=Decimal("0"))
    valor_plena: Decimal | None = Field(default=None, ge=Decimal("0"))
    vigente_desde: datetime | None = None


class TarifasSucursalFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_tipo_vehiculo: uuid_lib.UUID | None = None
    uuid_tipo_tarifa: uuid_lib.UUID | None = None
    # HU-F1.4 / REQ-OPS-021: point-in-time for the bi-temporal predicate.
    # Default ``None`` keeps the legacy factory / POST / PUT / GET-by-uuid
    # paths untouched — only the dedicated list handler reads this.
    vigente_en: datetime | None = None


class TarifasSucursalReadList(ReadListBase[TarifasSucursalRead]):
    pass


# ---------------------------------------------------------------------------
# CantidadVehiculosSucursal
# ---------------------------------------------------------------------------


class CantidadVehiculosSucursalRead(_Base):
    """Read-back for ``prod.cantidad_vehiculos_sucursal``.
    UK01 is ``(uuid_sucursal, uuid_tipo_vehiculo, vigente_desde)``."""

    uuid: uuid_lib.UUID
    uuid_sucursal: uuid_lib.UUID | None
    uuid_tipo_vehiculo: uuid_lib.UUID | None
    cantidad: int | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class CantidadVehiculosSucursalCreate(_Base):
    """REQ-03-V-INSERCION.

    PR-C additions:

    * ``vigente_desde``: optional client-supplied valid-time. Same
      Carril B semantics as :class:`TarifasSucursalCreate`. The handler
      validates the resulting window does not overlap any other open
      row for the same ``(uuid_sucursal, uuid_tipo_vehiculo)`` (409).
    * ``cantidad >= 0``: enforced at the API edge. ``cantidad == 0``
      is allowed (effectively disables the tipo at that branch until
      a later version restores capacity) and is the sanctioned
      alternative to DELETE (which the project canon forbids).
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_tipo_vehiculo: uuid_lib.UUID | None = None
    cantidad: int | None = Field(default=None, ge=0)
    vigente_desde: datetime | None = None


class CantidadVehiculosSucursalUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create.

    PR-C: in addition to the Carril B ``vigente_desde``, the handler
    rejects (422) PUTs whose payload ``cantidad`` is below the count of
    currently-active ``ingreso`` rows for the same
    ``(uuid_sucursal, uuid_tipo_vehiculo)``. Lowering capacity below
    active ingreso would silently leave the operator accepting ingreso
    the system then rejects at the close step. The operator must
    close / annul those ingreso first and then lower the capacity.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_tipo_vehiculo: uuid_lib.UUID | None = None
    cantidad: int | None = Field(default=None, ge=0)
    vigente_desde: datetime | None = None


class CantidadVehiculosSucursalFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_tipo_vehiculo: uuid_lib.UUID | None = None


class CantidadVehiculosSucursalReadList(ReadListBase[CantidadVehiculosSucursalRead]):
    pass


__all__ = [
    "CantidadVehiculosSucursalCreate",
    "CantidadVehiculosSucursalFilter",
    "CantidadVehiculosSucursalRead",
    "CantidadVehiculosSucursalReadList",
    "CantidadVehiculosSucursalUpdate",
    "DocumentosCreate",
    "DocumentosFilter",
    "DocumentosRead",
    "DocumentosReadList",
    "DocumentosUpdate",
    "EmpresaCreate",
    "EmpresaFilter",
    "EmpresaRead",
    "EmpresaReadList",
    "EmpresaUpdate",
    "ResolucionFacturacionCreate",
    "ResolucionFacturacionFilter",
    "ResolucionFacturacionRead",
    "ResolucionFacturacionReadList",
    "ResolucionFacturacionUpdate",
    "SucursalCreate",
    "SucursalFilter",
    "SucursalRead",
    "SucursalReadList",
    "SucursalUpdate",
    "TarifasSucursalCreate",
    "TarifasSucursalFilter",
    "TarifasSucursalRead",
    "TarifasSucursalReadList",
    "TarifasSucursalUpdate",
]
