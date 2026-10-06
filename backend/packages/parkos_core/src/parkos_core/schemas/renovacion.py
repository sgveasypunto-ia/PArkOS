"""Schemas for subscription renewal (PT-3) + the computed read-model fields.

* :class:`ConRenovacion` -- base for every subscription READ schema that the
  frontend uses to decide whether to show "Renovar". It adds the computed
  ``dias_restantes`` / ``puede_renovar`` fields (derived from
  ``fecha_vencimiento`` and Bogota's today), so the UI never recalculates
  dates. The rules live in :mod:`parkos_core.runtime.renovacion`.
* :class:`RenovarSuscripcionRequest` / :class:`RenovarSuscripcionResponse` --
  ``POST /clientes/subscripciones/{uuid}/renovar``.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import computed_field

from ..runtime.renovacion import (
    RENOVACION_VENTANA_DIAS,
    dias_restantes,
    renovacion_permitida,
)
from .common import _Base
from .facturacion import FacturaRead

__all__ = [
    "ConRenovacion",
    "ProximaVencerItem",
    "RenovarSuscripcionRequest",
    "RenovarSuscripcionResponse",
]


class ConRenovacion(_Base):
    """Adds ``dias_restantes`` and ``puede_renovar`` to a read schema.

    Subclasses MUST declare ``fecha_vencimiento: date | None``.
    ``puede_renovar`` is a date-only hint; the POST endpoint stays the
    authority (it can still answer 409 ``suscripcion_no_renovable``).
    """

    fecha_vencimiento: date | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dias_restantes(self) -> int | None:
        return dias_restantes(self.fecha_vencimiento)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def puede_renovar(self) -> bool:
        return renovacion_permitida(dias_restantes(self.fecha_vencimiento))


class RenovarSuscripcionRequest(_Base):
    """Payment data only: plates, plan and amount come from the subscription."""

    medio_pago: Literal["efectivo", "tarjeta", "datafono", "transferencia"] = "efectivo"
    referencia: str | None = None


class RenovarSuscripcionResponse(_Base):
    """Result of a renewal: the NEW subscription row + invoice/payment/FE."""

    uuid_subscripcion_anterior: uuid_lib.UUID
    uuid_subscripcion: uuid_lib.UUID
    uuid_cliente: uuid_lib.UUID | None
    uuid_sucursal: uuid_lib.UUID
    uuid_tipo_subscripcion: uuid_lib.UUID
    uuid_vehiculos: list[uuid_lib.UUID]
    placas: list[str]
    fecha_inicio_cobertura: date
    fecha_vencimiento: date
    dias_restantes: int
    renovacion_anticipada: bool
    ventana_renovacion_dias: int = RENOVACION_VENTANA_DIAS
    valor_total_plan: Decimal
    total_con_iva: Decimal
    uuid_factura: uuid_lib.UUID
    uuid_factura_electronica: uuid_lib.UUID | None = None
    # Same codes as the venta flow (``missing_sucursal_context``,
    # ``resolucion_facturacion_no_encontrada``, ``numeracion_agotada``,
    # ``resolucion_sin_prefijo``). Non-null = the renewal and the payment
    # succeeded and only the electronic invoice must be retried.
    factura_electronica_error: str | None = None
    # True when the failed FE was queued for the automatic retry.
    factura_electronica_pendiente: bool = False
    factura: FacturaRead | None = None


class ProximaVencerItem(_Base):
    """One row of the expiry-warning feed (banner)."""

    uuid: uuid_lib.UUID
    cliente_nombre: str
    plan_nombre: str
    placas: list[str]
    fecha_vencimiento: date
    dias_restantes: int
    dias_alerta_pre_vencimiento: int
    puede_renovar: bool
