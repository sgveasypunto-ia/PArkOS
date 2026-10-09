"""Producido del turno = efectivo en caja al cierre - base de caja (efectivo only)."""

from __future__ import annotations

from decimal import Decimal

from parkos_core.repo.mi_turno import producido_de
from parkos_core.schemas.operacion import ResumenCierreTurnoRead


def test_producido_is_the_cash_that_exceeds_the_base() -> None:
    assert producido_de(Decimal("350000"), Decimal("100000")) == Decimal("250000")


def test_producido_is_zero_when_the_count_equals_the_base() -> None:
    assert producido_de(Decimal("100000"), Decimal("100000")) == Decimal("0")


def test_a_shortage_is_reported_as_negative_not_clamped() -> None:
    assert producido_de(Decimal("90000"), Decimal("100000")) == Decimal("-10000")


def test_resumen_cierre_new_fields_are_optional_for_older_payloads() -> None:
    from datetime import datetime
    from uuid import uuid4

    resumen = ResumenCierreTurnoRead(
        uuid_sesion=uuid4(), uuid_sucursal=uuid4(), timestamp_calculo=datetime(2026, 1, 1)
    )

    assert resumen.base_entregada is None
    assert resumen.efectivo_reportado is None
    assert resumen.producido is None
