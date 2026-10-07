"""IVA-inclusive breakdown helper for the subscription price (plan valor = total)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from parkos_core.repo.impuestos import desglosar_iva_incluido


def test_plan_120000_al_19_por_ciento() -> None:
    base, iva, total = desglosar_iva_incluido(Decimal("120000"), Decimal("0.19"))
    assert base == Decimal("100840.34")
    assert iva == Decimal("19159.66")
    assert total == Decimal("120000.00")


@pytest.mark.parametrize(
    "total", ["0", "0.01", "1", "999.99", "30000", "119000", "35700.50", "1234567.89"]
)
@pytest.mark.parametrize("pct", ["0", "0.05", "0.19"])
def test_base_mas_iva_es_exactamente_total(total: str, pct: str) -> None:
    base, iva, tot = desglosar_iva_incluido(Decimal(total), Decimal(pct))
    assert base + iva == tot == Decimal(total).quantize(Decimal("0.01"))
    assert base.as_tuple().exponent == -2 and iva.as_tuple().exponent == -2


def test_iva_cero_no_grava() -> None:
    base, iva, total = desglosar_iva_incluido(Decimal("50000"), Decimal("0"))
    assert (base, iva, total) == (Decimal("50000.00"), Decimal("0.00"), Decimal("50000.00"))


def test_redondeo_half_up() -> None:
    # 1.00 / 1.19 = 0.840336... -> 0.84 ; iva = 0.16
    assert desglosar_iva_incluido(Decimal("1"), Decimal("0.19"))[:2] == (
        Decimal("0.84"),
        Decimal("0.16"),
    )
