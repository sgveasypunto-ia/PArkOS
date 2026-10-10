"""The 201 display must reflect the init ``factura_pagos`` row.

Live defect (venta de suscripcion, datafono + VOUCHER001): the row was
persisted with its ``referencia`` but the response carried
``voucher=null`` and ``pagos=[]`` because the projection hardcoded both.
"""
from __future__ import annotations

import uuid as uuid_lib
from decimal import Decimal
from types import SimpleNamespace

from parkos_core.api.v1._factura_display import _proyectar_pago_display


def _pago(medio: str | None, referencia: str | None, valor: float = 220000.0):
    return SimpleNamespace(
        uuid=uuid_lib.uuid4(), medio_pago=medio, valor=valor, referencia=referencia
    )


def test_datafono_exposes_voucher_and_the_pago() -> None:
    row = _pago("datafono", "VOUCHER001")
    voucher, pagos = _proyectar_pago_display(row)
    assert voucher == "VOUCHER001"
    assert len(pagos) == 1
    assert pagos[0].uuid == row.uuid
    assert pagos[0].medio_pago == "datafono"
    assert pagos[0].referencia == "VOUCHER001"
    assert pagos[0].valor == Decimal("220000.0")


def test_efectivo_has_no_voucher_but_still_lists_the_pago() -> None:
    voucher, pagos = _proyectar_pago_display(_pago("efectivo", None))
    assert voucher is None
    assert [p.medio_pago for p in pagos] == ["efectivo"]


def test_non_datafono_reference_is_not_surfaced_as_voucher() -> None:
    voucher, pagos = _proyectar_pago_display(_pago("transferencia", "TRX-9"))
    assert voucher is None
    assert pagos[0].referencia == "TRX-9"


def test_no_pago_row_yields_empty_projection() -> None:
    assert _proyectar_pago_display(None) == (None, [])
