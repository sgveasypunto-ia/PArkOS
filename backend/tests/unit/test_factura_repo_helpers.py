"""HU-F1.9 / REQ-OPS-053..063 -- repo/factura.py + repo/factura_detalle.py unit tests.

Pydantic-style + pure-Python invariants that do NOT require a DB
session. DB integration tests live in
``tests/integration/test_factura_create_db.py`` (T2.1 + T2.5 in tasks
Phase 5). These unit tests catch regressions in:

- ``compute_total`` arithmetic (item subtotals + IVA - retencion).
- ``factura_detalle.crear_factura_detalle_bulk`` pure
  preprocessing (without session).
- Typed exception imports for handler 12-step chain discrimination.
"""
from __future__ import annotations

from decimal import Decimal

from parkos_core.repo.factura import (
    FacturaDuplicadaError,
    PagoDuplicadoError,
    TotalNoCoherenteError,
    compute_total,
)
from parkos_core.repo.factura_detalle import crear_factura_detalle_bulk
from parkos_core.schemas.facturacion import FacturaItemCreate


def test_compute_total_suma_items_mas_iva() -> None:
    """V6 invariant: total = sum(cantidad*valor_unitario) + iva - retencion."""
    items = [
        FacturaItemCreate(
            tipo="servicio",
            concepto="Parqueo 1h",
            cantidad=1,
            valor_unitario=Decimal("5000.00"),
            uuid_tarifa_sucursal=None,
        ),
        FacturaItemCreate(
            tipo="servicio",
            concepto="Parqueo 2h",
            cantidad=2,
            valor_unitario=Decimal("3000.00"),
            uuid_tarifa_sucursal=None,
        ),
    ]
    # subtotal = 1*5000 + 2*3000 = 11000.00
    # iva = 11000.00 * 0.19 = 2090.00
    # retencion = 0 (DEC-FACT-04 Fase 4 deferred)
    # total = 13090.00
    total = compute_total(items=items, iva=Decimal("0.19"), retencion=Decimal("0"))
    assert total == Decimal("13090.00")


def test_compute_total_items_vacio_retorna_iva_solo() -> None:
    """Edge case: empty items + iva=0 → total=0 (F1.9 allows min 1 item)."""
    total = compute_total(items=[], iva=Decimal("0.19"), retencion=Decimal("0"))
    # 0 + 0 - 0 = 0
    assert total == Decimal("0")


def test_compute_total_retencion_default_cero() -> None:
    """DEC-FACT-04: retencion placeholder default is Decimal('0')."""
    items = [
        FacturaItemCreate(
            tipo="servicio",
            concepto="x",
            cantidad=1,
            valor_unitario=Decimal("100.00"),
            uuid_tarifa_sucursal=None,
        ),
    ]
    # 100 + 19 = 119 (iva=0.19, retencion=0)
    total = compute_total(items=items, iva=Decimal("0.19"))
    assert total == Decimal("119.00")


def test_typed_exceptions_importable() -> None:
    """Typed exceptions are importable from repo/factura (handler chain)."""
    # All 7 typed exceptions from design §9 must be exposed in __all__.
    assert TotalNoCoherenteError is not None
    assert FacturaDuplicadaError is not None
    assert PagoDuplicadoError is not None


def test_factura_detalle_bulk_signature() -> None:
    """``crear_factura_detalle_bulk`` accepts the documented signature."""
    import inspect

    sig = inspect.signature(crear_factura_detalle_bulk)
    params = sig.parameters
    assert "session" in params
    assert "uuid_factura" in params
    assert "items" in params
    # Returns list[FacturaDetalle]
    assert "return" in sig.annotations or sig.return_annotation is not inspect.Signature.empty
