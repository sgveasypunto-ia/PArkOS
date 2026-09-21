"""tests/integration/conftest.py — fixtures for HU integration tests.

Pytest auto-loads this conftest before any test file under
``tests/integration/``. Currently exports one factory fixture used by
the F12.1 mi-turno endpoint tests:

  - ``sesion_with_ingresos_y_pagos`` — seeds (in-memory mocks) one
    ``Sesion`` row + two ``Ingreso`` rows + one ``Salida`` row +
    three ``FacturaPagos`` rows. Mirrors the F1.13 / F12.1 spec:
    "1 Sesion + 2 ingreso + 1 salida + 3 factura_pagos".

The mock row shape mirrors the ORM fields the handler reads; the
fixture is consumed by ``test_mi_turno_endpoint.py`` (HU-F12.1).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest


def _now_naive() -> datetime:
    """Naive UTC ``datetime`` matching DB ``DateTime(timezone=False)`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def _build_sesion_mock(
    *,
    uuid_sesion: uuid_lib.UUID | None = None,
    uuid_sucursal: uuid_lib.UUID | None = None,
    timestamp_apertura: datetime | None = None,
    timestamp_cierre: datetime | None = None,
) -> Any:
    """Build a MagicMock that quacks like :class:`Sesion`.

    Only the fields the handler reads are populated — this is a fixture,
    not a full ORM mock.
    """
    from unittest.mock import MagicMock

    sesion = MagicMock()
    sesion.uuid = uuid_sesion or uuid_lib.uuid4()
    sesion.uuid_sucursal = uuid_sucursal or uuid_lib.uuid4()
    sesion.timestamp_apertura = timestamp_apertura or _now_naive()
    # ``MagicMock`` auto-creates child attributes as MagicMocks — which
    # breaks the SQL builder's ``is None`` check. Pin both timestamps
    # to real datetimes / None explicitly.
    sesion.timestamp_cierre = timestamp_cierre
    sesion.uuid_usuario = uuid_lib.uuid4()
    return sesion


def _build_ingreso_mock(
    *,
    uuid_sucursal: uuid_lib.UUID,
    fecha_ingreso: datetime | None = None,
) -> Any:
    from unittest.mock import MagicMock

    row = MagicMock()
    row.uuid = uuid_lib.uuid4()
    row.uuid_sucursal = uuid_sucursal
    row.fecha_ingreso = fecha_ingreso or _now_naive()
    return row


def _build_salida_mock(
    *,
    uuid_sucursal: uuid_lib.UUID,
    fecha_salida: datetime | None = None,
) -> Any:
    from unittest.mock import MagicMock

    row = MagicMock()
    row.uuid = uuid_lib.uuid4()
    row.uuid_sucursal = uuid_sucursal
    row.fecha_salida = fecha_salida or _now_naive()
    return row


def _build_factura_pago_mock(
    *,
    uuid_sesion: uuid_lib.UUID,
    medio_pago: str,
    valor: Decimal,
    tipo_movimiento: str = "pago",
) -> Any:
    from unittest.mock import MagicMock

    row = MagicMock()
    row.uuid = uuid_lib.uuid4()
    row.uuid_sesion = uuid_sesion
    row.uuid_sucursal = uuid_lib.uuid4()
    row.medio_pago = medio_pago
    row.valor = valor
    row.tipo_movimiento = tipo_movimiento
    return row


@pytest.fixture
def sesion_with_ingresos_y_pagos() -> dict[str, Any]:
    """HU-F12.1 factory fixture: 1 sesion + 2 ingresos + 1 salida + 3 pagos.

    Returned dict layout (consumed by ``test_mi_turno_endpoint.py``):

      sesion:        Sesion-shaped mock
      ingresos:      list[Ingreso-shaped mock]   (length 2)
      salidas:       list[Salida-shaped mock]    (length 1)
      pagos:         list[FacturaPagos-shaped mock] (length 3)
      uuid_sesion:   uuid.UUID  (== sesion.uuid, for convenience)
      uuid_sucursal: uuid.UUID  (== sesion.uuid_sucursal, for tenant-pin tests)
      total_efectivo_cop: Decimal  (sum of efectivo pagos)
      total_datafono_cop: Decimal  (sum of tarjeta + datafono pagos)
    """
    sesion = _build_sesion_mock()
    ingresos = [
        _build_ingreso_mock(uuid_sucursal=sesion.uuid_sucursal),
        _build_ingreso_mock(uuid_sucursal=sesion.uuid_sucursal),
    ]
    salidas = [
        _build_salida_mock(uuid_sucursal=sesion.uuid_sucursal),
    ]
    # Per AD-3 / F1.13: efectivo = medio_pago='efectivo'; datafono =
    # medio_pago IN ('tarjeta', 'datafono'). Distribute values so both
    # buckets return non-zero totals (handler asserts these via SUM).
    pagos = [
        _build_factura_pago_mock(
            uuid_sesion=sesion.uuid, medio_pago="efectivo", valor=Decimal("50000"),
        ),
        _build_factura_pago_mock(
            uuid_sesion=sesion.uuid, medio_pago="tarjeta", valor=Decimal("20000"),
        ),
        _build_factura_pago_mock(
            uuid_sesion=sesion.uuid, medio_pago="datafono", valor=Decimal("10000"),
        ),
    ]

    return {
        "sesion": sesion,
        "ingresos": ingresos,
        "salidas": salidas,
        "pagos": pagos,
        "uuid_sesion": sesion.uuid,
        "uuid_sucursal": sesion.uuid_sucursal,
        "total_efectivo_cop": Decimal("50000"),
        "total_datafono_cop": Decimal("30000"),
    }


__all__ = [
    "sesion_with_ingresos_y_pagos",
]