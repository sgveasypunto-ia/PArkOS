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
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from ..repo.nit_modulo11 import dv_esperado, validar_nit_modulo11
from .common import FilterBase, ReadListBase, _Base
from .facturacion import FacturaRead

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
            and not validar_nit_modulo11(self.numero_identificacion, self.dv)
        ):
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
            and not validar_nit_modulo11(self.numero_identificacion, self.dv)
        ):
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


# ---------------------------------------------------------------------------
# HU-F1.12 — Venta atómica de suscripción (REQ-OPS-083..090 + XR5)
# ---------------------------------------------------------------------------


class VentaSuscripcionCreate(_Base):
    """HU-F1.12: POST /api/v1/clientes/venta-suscripcion payload.

    cliente OR uuid_cliente (discriminated XOR): exactly one is required.
    For embedded ``cliente``, ``dv`` is validated by Pydantic
    (DEC-VENTA-07) but NOT persisted -- ``prod.clientes`` has no ``dv``
    column.

    ``extra='forbid'`` (inherited from ``_Base``) blocks client
    smuggling of ``uuid_sucursal``, ``vigente_desde``, ``estado``,
    ``created_at``, ``created_by``, ``monto_prorrateado``, ``valor_dia``,
    ``dias_restantes_mes``.

    ``placas`` is bounded 1-2 by ``Field(min_length=1, max_length=2)``
    (the per-placa + cross-placa validation runs in the handler /
    repo layer; this is the request-shape guard only).
    """

    cliente: ClientesCreate | None = None
    uuid_cliente: uuid_lib.UUID | None = None
    placas: Annotated[list[str], Field(min_length=1, max_length=2)]
    uuid_tipo_subscripcion: uuid_lib.UUID
    fecha_inicio_cobertura: date
    cobrar_ahora: bool = False
    emitir_factura_electronica: bool = False
    medio_pago: Literal["efectivo", "tarjeta", "datafono", "transferencia"] = (
        "efectivo"
    )
    referencia: str | None = None

    @model_validator(mode="after")
    def _check_cliente_xor_uuid(self) -> Self:
        """T2.2: exactly-one-of (``cliente`` XOR ``uuid_cliente``).

        Raises ``ValueError`` (Pydantic maps to 422) when both are
        populated (would over-write existing cliente) or both are
        absent (no way to identify the buyer).
        """
        if (self.cliente is None) == (self.uuid_cliente is None):
            raise ValueError(
                "exactly one of cliente or uuid_cliente is required"
            )
        return self


class VentaSuscripcionResponse(_Base):
    """HU-F1.12: POST /api/v1/clientes/venta-suscripcion response.

    Returns the full set of created UUIDs (cliente, subscripcion,
    vehiculos) + dates + amounts.

    DEC-VENTA-03: ``monto_prorrateado`` is ``None`` when
    ``cobrar_ahora=False`` (V7 prorrateo not persisted -- V8 cobro
    sub-chain runs only when ``cobrar_ahora=True``). Optional cobro
    artifacts (``uuid_factura``, ``uuid_factura_electronica``,
    ``uuid_envio_dian``) are ``None`` when not requested.
    """

    uuid_cliente: uuid_lib.UUID
    uuid_subscripcion: uuid_lib.UUID
    uuid_vehiculos: list[uuid_lib.UUID]
    uuid_sucursal: uuid_lib.UUID
    fecha_inicio_cobertura: date
    fecha_vencimiento: date
    valor_total_plan: Decimal
    monto_prorrateado: Decimal | None = None
    uuid_factura: uuid_lib.UUID | None = None
    uuid_factura_electronica: uuid_lib.UUID | None = None
    uuid_envio_dian: uuid_lib.UUID | None = None
    # HU-F9.1 bugfix (2026-09-25): the enriched display projection, same
    # shape ``POST /facturacion/factura`` returns, so `<Venta />` can
    # render `<FacturaDisplayModal />` + fire the recibo print envelope
    # right after a subscription sale with `cobrar_ahora=true` — mirrors
    # the ingreso/salida cobro flow (HU-F8.4) instead of leaving the
    # operator without a ticket. ``None`` when `cobrar_ahora=false`.
    factura: FacturaRead | None = None


# ---------------------------------------------------------------------------
# HU-F9.2 realineada — gestión de cupos de suscripción (sucursal, Sheet)
# ---------------------------------------------------------------------------


class ClienteResumen(_Base):
    """Datos mínimos del cliente para mostrar en el listado/detalle de cupos."""

    uuid: uuid_lib.UUID
    nombre: str | None
    apellido: str | None
    numero_identificacion: str | None


class PlanResumen(_Base):
    """Datos mínimos del plan (``tipo_subscripciones``) para el listado/detalle."""

    uuid: uuid_lib.UUID
    tipo: str | None
    valor: Decimal | None
    cantidad_maxima_vehiculos: int | None
    mismo_tipo_vehiculo: bool | None


class VehiculoInscrito(_Base):
    """Un vehículo inscrito vigente en una suscripción.

    ``uuid`` es el uuid de la fila ``subscripcion_vehiculos`` (lo que se
    necesita para "quitar" ese vehículo puntual); ``uuid_vehiculo`` es el
    FK al catálogo de vehículos.
    """

    uuid: uuid_lib.UUID
    uuid_vehiculo: uuid_lib.UUID
    placa: str | None


class SubscripcionActivaItem(_Base):
    """Una fila del listado de suscripciones activas (paso 1 del Sheet)."""

    uuid: uuid_lib.UUID
    cliente: ClienteResumen
    plan: PlanResumen
    fecha_inicio_cobertura: date | None
    fecha_vencimiento: date | None
    cupo_maximo: int | None
    vehiculos_inscritos: int


class SubscripcionesActivasResponse(_Base):
    """``GET /clientes/subscripciones-activas`` response."""

    items: list[SubscripcionActivaItem]


class SubscripcionCupoDetalle(_Base):
    """Detalle de una suscripción para el paso de gestión de cupos.

    Devuelto tanto por la búsqueda por identificación como por
    agregar/quitar un vehículo (para que el frontend refresque el estado
    sin un segundo round-trip).
    """

    uuid: uuid_lib.UUID
    cliente: ClienteResumen
    plan: PlanResumen
    fecha_inicio_cobertura: date | None
    fecha_vencimiento: date | None
    cupo_maximo: int | None
    cupo_disponible: int | None
    vehiculos: list[VehiculoInscrito]


class AgregarVehiculoCupoRequest(_Base):
    """``POST /clientes/subscripcion-vehiculos/agregar`` payload."""

    uuid_subscripcion_cliente: uuid_lib.UUID
    placa: Annotated[str, StringConstraints(min_length=1, max_length=16)]


__all__ = [
    "AgregarVehiculoCupoRequest",
    "ClienteResumen",
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
    "PlanResumen",
    "SubscripcionActivaItem",
    "SubscripcionCupoDetalle",
    "SubscripcionVehiculosCreate",
    "SubscripcionVehiculosFilter",
    "SubscripcionVehiculosRead",
    "SubscripcionVehiculosReadList",
    "SubscripcionVehiculosUpdate",
    "SubscripcionesActivasResponse",
    "SubscripcionesClienteCreate",
    "SubscripcionesClienteFilter",
    "SubscripcionesClienteRead",
    "SubscripcionesClienteReadList",
    "SubscripcionesClienteUpdate",
    "VehiculoInscrito",
    "VehiculosCreate",
    "VehiculosFilter",
    "VehiculosRead",
    "VehiculosReadList",
    "VehiculosUpdate",
    "VentaSuscripcionCreate",
    "VentaSuscripcionResponse",
]