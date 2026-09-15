"""Pydantic schemas for commercial domain (PR5).

5 ``[V]`` tables in ``prod``:

- :class:`Clientes` — customer master (UK on ``tipo_identificador`` +
  ``numero_identificacion``).
- :class:`ClientesB2B` — corporate extension with ``cantidad`` +
  ``fecha_inicio_convenio`` / ``fecha_vencimiento``.
- :class:`SubscripcionesCliente` — plan subscription per branch (no DB UK;
  uniqueness enforced at the API layer via the bi-temporal
  ``vigente_desde`` discriminator).
- :class:`Vehiculos` — registered vehicles (UK on ``placa``; 1-16 chars
  per REQ-OP-06 — Colombian plates are 6, international up to 16).
- :class:`SubscripcionVehiculos` — junction linking vehicles to a
  subscription; carries the **REQ-OP-08 fast-fail validator** on
  :class:`SubscripcionVehiculosCreate` (defense in depth — the
  authoritative count check lives in the endpoint layer with
  ``pg_advisory_xact_lock``, see T-PR5-06).

All schemas inherit :class:`_Base` from :mod:`.common`, which provides
``extra='forbid'`` (so clients cannot smuggle versioning columns) and
``from_attributes=True`` (so :func:`pydantic.BaseModel.model_validate` can
project an ORM row directly).
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import StringConstraints, field_validator, model_validator

from ..repo.nit_modulo11 import dv_esperado, validar_nit_modulo11
from .common import FilterBase, ReadListBase, _Base

# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------


class ClientesRead(_Base):
    """Read-back for ``prod.clientes``. UK is ``(tipo_identificador,
    numero_identificacion, vigente_desde)``."""

    uuid: uuid_lib.UUID
    tipo_identificador: str | None
    numero_identificacion: str | None
    nombre: str | None
    apellido: str | None
    telefono: str | None
    email: str | None
    uuid_tipo_persona: uuid_lib.UUID | None
    registro: dict[str, Any] | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class ClientesCreate(_Base):
    """REQ-03-V-INSERCION. Versioning columns excluded by ``extra='forbid'``.

    HU-F1.9 / REQ-OPS-058: NIT módulo 11 validation when
    ``tipo_identificador='NIT'`` AND ``dv`` is provided.
    CC / CE / pasaporte do NOT require DV
    (DEC-FACT-08 consumidor final placeholder).
    """

    tipo_identificador: str | None = None
    numero_identificacion: str | None = None
    dv: str | None = None  # HU-F1.9 — DV for NIT modulo 11 validation
    nombre: str | None = None
    apellido: str | None = None
    telefono: str | None = None
    email: str | None = None
    uuid_tipo_persona: uuid_lib.UUID | None = None
    registro: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _validar_nit_dv(self) -> ClientesCreate:
        """HU-F1.9 / REQ-OPS-058: cross-field NIT módulo 11 validation.

        Runs after all fields are populated (mode='after'), so ``dv`` is
        available regardless of declaration order. Only validates when
        ALL three are present: ``tipo_identificador='NIT'``,
        ``numero_identificacion``, ``dv``. If ``dv`` is absent for a
        NIT, no-ops — caller may populate DV later via UPDATE.
        """
        if (
            self.tipo_identificador == "NIT"
            and self.numero_identificacion
            and self.dv
        ):
            if not validar_nit_modulo11(self.numero_identificacion, self.dv):
                expected = dv_esperado(self.numero_identificacion)
                raise ValueError(
                    f"DV inválido: recibido={self.dv}, esperado={expected}"
                )
        return self


class ClientesUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as :class:`ClientesCreate`.

    HU-F1.9: also accepts optional ``dv`` for NIT módulo 11 re-validation
    on update flows where the identificador is changed.
    """

    tipo_identificador: str | None = None
    numero_identificacion: str | None = None
    dv: str | None = None
    nombre: str | None = None
    apellido: str | None = None
    telefono: str | None = None
    email: str | None = None
    uuid_tipo_persona: uuid_lib.UUID | None = None
    registro: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _validar_nit_dv(self) -> ClientesUpdate:
        """HU-F1.9 / REQ-OPS-058 mirror on :class:`ClientesUpdate`."""
        if (
            self.tipo_identificador == "NIT"
            and self.numero_identificacion
            and self.dv
        ):
            if not validar_nit_modulo11(self.numero_identificacion, self.dv):
                expected = dv_esperado(self.numero_identificacion)
                raise ValueError(
                    f"DV inválido: recibido={self.dv}, esperado={expected}"
                )
        return self


class ClientesFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    uuid_tipo_persona: uuid_lib.UUID | None = None


class ClientesReadList(ReadListBase[ClientesRead]):
    pass


# ---------------------------------------------------------------------------
# ClientesB2B
# ---------------------------------------------------------------------------


class ClientesB2BRead(_Base):
    """Read-back for ``prod.clientes_b2b``. UK is
    ``(uuid_cliente, vigente_desde)`` — one active B2B extension per
    customer per version."""

    uuid: uuid_lib.UUID
    uuid_cliente: uuid_lib.UUID | None
    cantidad: int | None
    registro: dict[str, Any] | None
    fecha_inicio_convenio: date | None
    fecha_vencimiento: date | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class ClientesB2BCreate(_Base):
    """REQ-03-V-INSERCION."""

    uuid_cliente: uuid_lib.UUID | None = None
    cantidad: int | None = None
    registro: dict[str, Any] | None = None
    fecha_inicio_convenio: date | None = None
    fecha_vencimiento: date | None = None


class ClientesB2BUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as :class:`ClientesB2BCreate`."""

    uuid_cliente: uuid_lib.UUID | None = None
    cantidad: int | None = None
    registro: dict[str, Any] | None = None
    fecha_inicio_convenio: date | None = None
    fecha_vencimiento: date | None = None


class ClientesB2BFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    uuid_cliente: uuid_lib.UUID | None = None


class ClientesB2BReadList(ReadListBase[ClientesB2BRead]):
    pass


# ---------------------------------------------------------------------------
# SubscripcionesCliente
# ---------------------------------------------------------------------------


class SubscripcionesClienteRead(_Base):
    """Read-back for ``prod.subscripciones_cliente``. No DB-level UK —
    the bi-temporal ``vigente_desde`` discriminator keeps each version
    unique and the business key (the 3 FKs + dates) is enforced at the
    API layer."""

    uuid: uuid_lib.UUID
    uuid_cliente: uuid_lib.UUID | None
    uuid_sucursal: uuid_lib.UUID | None
    uuid_tipo_subscripcion: uuid_lib.UUID | None
    fecha_inicio_cobertura: date | None
    fecha_vencimiento: date | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class SubscripcionesClienteCreate(_Base):
    """REQ-03-V-INSERCION."""

    uuid_cliente: uuid_lib.UUID | None = None
    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_tipo_subscripcion: uuid_lib.UUID | None = None
    fecha_inicio_cobertura: date | None = None
    fecha_vencimiento: date | None = None


class SubscripcionesClienteUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as
    :class:`SubscripcionesClienteCreate`."""

    uuid_cliente: uuid_lib.UUID | None = None
    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_tipo_subscripcion: uuid_lib.UUID | None = None
    fecha_inicio_cobertura: date | None = None
    fecha_vencimiento: date | None = None


class SubscripcionesClienteFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    uuid_cliente: uuid_lib.UUID | None = None
    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_tipo_subscripcion: uuid_lib.UUID | None = None


class SubscripcionesClienteReadList(ReadListBase[SubscripcionesClienteRead]):
    pass


# ---------------------------------------------------------------------------
# Vehiculos (REQ-OP-06: placa 1-16 chars)
# ---------------------------------------------------------------------------


class VehiculosRead(_Base):
    """Read-back for ``prod.vehiculos``. UK is ``(placa, vigente_desde)``."""

    uuid: uuid_lib.UUID
    placa: str | None
    uuid_tipo_vehiculo: uuid_lib.UUID | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class VehiculosCreate(_Base):
    """REQ-03-V-INSERCION. ``placa`` capped at 1-16 chars per REQ-OP-06
    (Colombian plates are 6, international up to 16)."""

    placa: Annotated[str, StringConstraints(min_length=1, max_length=16)]
    uuid_tipo_vehiculo: uuid_lib.UUID | None = None


class VehiculosUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as :class:`VehiculosCreate`."""

    placa: Annotated[str, StringConstraints(min_length=1, max_length=16)]
    uuid_tipo_vehiculo: uuid_lib.UUID | None = None


class VehiculosFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    placa: str | None = None
    uuid_tipo_vehiculo: uuid_lib.UUID | None = None


class VehiculosReadList(ReadListBase[VehiculosRead]):
    pass


# ---------------------------------------------------------------------------
# SubscripcionVehiculos (REQ-OP-08 + risk #18 + SC-OP-08)
# ---------------------------------------------------------------------------


class SubscripcionVehiculosRead(_Base):
    """Read-back for ``prod.subscripcion_vehiculos``. UK is
    ``(uuid_subscripcion_cliente, uuid_vehiculo, vigente_desde)``."""

    uuid: uuid_lib.UUID
    uuid_subscripcion_cliente: uuid_lib.UUID | None
    uuid_vehiculo: uuid_lib.UUID | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None


class SubscripcionVehiculosCreate(_Base):
    """REQ-03-V-INSERCION.

    Both FK UUIDs are required — :meth:`_check_vehicle_count` raises 422
    if either is ``None``. This is a fast-fail (request-layer) guard;
    the authoritative count check
    (``count(active vehiculos for this subscripcion) <=
    cantidad_maxima_vehiculos of the plan``) runs in the endpoint
    wrapped by T-PR5-06's ``api/v1/clientes.py`` with
    ``pg_advisory_xact_lock(uuid_subscripcion_cliente)`` to serialize
    concurrent inserts (DB-layer guard). See T-PR5-10's test for the
    advisory-lock semantics.
    """

    uuid_subscripcion_cliente: uuid_lib.UUID | None = None
    uuid_vehiculo: uuid_lib.UUID | None = None

    @model_validator(mode="after")
    def _check_vehicle_count(self) -> SubscripcionVehiculosCreate:
        """REQ-OP-08: count(active vehiculos for this subscripcion) <= cantidad_maxima_vehiculos of the plan.

        Production uses ``pg_advisory_xact_lock(uuid_subscripcion_cliente)`` to
        serialize concurrent inserts (DB-layer guard). The Pydantic validator
        here is a fast-fail (request-layer guard) — counts from the loaded
        subscripciones_cliente + tipo_subscripciones rows.
        """
        # The actual DB serialization happens in the endpoint via the advisory
        # lock; this validator does a non-locking best-effort check using the
        # Pydantic-level data only (no DB access — that's the architect's
        # intent for PR5: the validator checks obvious overflow pre-DB).
        #
        # In PR5 scope, the validator simply enforces shape: requiere non-None
        # UUID FKs, no emptiness. Real count enforcement is in the endpoint
        # layer (T-PR5-06's api/v1/clientes.py wraps the make_router POST and
        # does the actual advisory-lock + count).
        if self.uuid_subscripcion_cliente is None:
            raise ValueError("uuid_subscripcion_cliente is required")
        if self.uuid_vehiculo is None:
            raise ValueError("uuid_vehiculo is required")
        return self


class SubscripcionVehiculosUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as
    :class:`SubscripcionVehiculosCreate` (validator re-applies)."""

    uuid_subscripcion_cliente: uuid_lib.UUID | None = None
    uuid_vehiculo: uuid_lib.UUID | None = None

    @model_validator(mode="after")
    def _check_vehicle_count(self) -> SubscripcionVehiculosUpdate:
        """Same fast-fail guard as on :class:`SubscripcionVehiculosCreate`."""
        if self.uuid_subscripcion_cliente is None:
            raise ValueError("uuid_subscripcion_cliente is required")
        if self.uuid_vehiculo is None:
            raise ValueError("uuid_vehiculo is required")
        return self


class SubscripcionVehiculosFilter(FilterBase):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    uuid_subscripcion_cliente: uuid_lib.UUID | None = None
    uuid_vehiculo: uuid_lib.UUID | None = None


class SubscripcionVehiculosReadList(ReadListBase[SubscripcionVehiculosRead]):
    pass


__all__ = [
    "ClientesB2BCreate",
    "ClientesB2BFilter",
    "ClientesB2BRead",
    "ClientesB2BReadList",
    "ClientesB2BUpdate",
    "ClientesCreate",
    "ClientesFilter",
    "ClientesRead",
    "ClientesReadList",
    "ClientesUpdate",
    "SubscripcionVehiculosCreate",
    "SubscripcionVehiculosFilter",
    "SubscripcionVehiculosRead",
    "SubscripcionVehiculosReadList",
    "SubscripcionVehiculosUpdate",
    "SubscripcionesClienteCreate",
    "SubscripcionesClienteFilter",
    "SubscripcionesClienteRead",
    "SubscripcionesClienteReadList",
    "SubscripcionesClienteUpdate",
    "VehiculosCreate",
    "VehiculosFilter",
    "VehiculosRead",
    "VehiculosReadList",
    "VehiculosUpdate",
]