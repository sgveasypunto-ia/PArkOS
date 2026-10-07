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

# ---------------------------------------------------------------------------
# empresa singleton (0078 ``empresa_singleton_uk``)
# ---------------------------------------------------------------------------
# ``prod.empresa`` allows AT MOST ONE open (``vigente_hasta IS NULL``) row, and
# migrations seed one. Many integration modules seed their own ``Empresa`` as
# the FK parent of their ``sucursal`` rows, which used to be free to do and now
# violates the singleton. ``empresa_slot_libre`` frees the slot for the duration
# of a test and puts the seeded row back afterwards, so modules that insert
# their own empresa keep working and modules that read the seeded one are
# untouched (the fixture is only attached to modules that insert an ``Empresa``).


@pytest.fixture
def empresa_slot_libre(pg_dsn: str, alembic_upgrade):
    """Close the open empresa for the test, restore it afterwards."""
    import psycopg

    close_sql = (
        "UPDATE prod.empresa SET vigente_hasta = NOW(), estado = 'inactivo' "
        "WHERE vigente_hasta IS NULL"
    )
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT uuid FROM prod.empresa WHERE vigente_hasta IS NULL")
        originals = [row[0] for row in cur.fetchall()]
        cur.execute(close_sql)
        conn.commit()
    try:
        yield
    finally:
        with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
            cur.execute(close_sql)
            if originals:
                cur.execute(
                    "UPDATE prod.empresa SET vigente_hasta = NULL, estado = 'activo' "
                    "WHERE uuid = ANY(%s)",
                    (originals,),
                )
            conn.commit()


_EMPRESA_SEEDING_MODULES: dict[str, bool] = {}


def pytest_collection_modifyitems(config, items):
    """Attach ``empresa_slot_libre`` to every module that inserts an ``Empresa``."""
    for item in items:
        path = str(item.fspath)
        if "integration" not in path:
            continue
        seeds = _EMPRESA_SEEDING_MODULES.get(path)
        if seeds is None:
            try:
                with open(path, encoding="utf-8") as fh:
                    seeds = "Empresa(" in fh.read()
            except OSError:
                seeds = False
            _EMPRESA_SEEDING_MODULES[path] = seeds
        if seeds:
            item.add_marker(pytest.mark.usefixtures("empresa_slot_libre"))


@pytest.fixture(autouse=True)
def _empresa_extra_rows_as_closed_history():
    """A second OPEN ``empresa`` in the same test is stored as closed history.

    Several modules seed one ``Empresa`` per branch (``_seed_two_branches``...)
    purely as the FK parent of their ``sucursal`` rows. With the singleton
    index only one open row can exist, so any further ``Empresa`` flushed while
    another open one exists (in the DB or earlier in the same flush) is
    inserted already closed: it still satisfies the FK, and it cannot trip
    ``empresa_singleton_uk``. Tests that need THEIR empresa to be the open one
    get it for free: ``empresa_slot_libre`` frees the slot, so the first
    ``Empresa`` a test inserts is the open one.
    """
    from datetime import timedelta

    from parkos_core.models.V.empresa import Empresa
    from sqlalchemy import event, select
    from sqlalchemy.orm import Session

    def _before_flush(session, flush_context, instances):  # noqa: ARG001
        new_open = [
            obj for obj in session.new if isinstance(obj, Empresa) and obj.vigente_hasta is None
        ]
        if not new_open:
            return
        with session.no_autoflush:
            slot_taken = (
                session.execute(select(Empresa.uuid).where(Empresa.vigente_hasta.is_(None)))
                .scalars()
                .first()
                is not None
            )
        for obj in new_open:
            if slot_taken:
                obj.vigente_hasta = obj.vigente_desde + timedelta(seconds=1)
                obj.estado = "inactivo"
            else:
                slot_taken = True

    event.listen(Session, "before_flush", _before_flush)
    try:
        yield
    finally:
        event.remove(Session, "before_flush", _before_flush)
