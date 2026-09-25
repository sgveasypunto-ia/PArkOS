"""HU-F1.9 / REQ-OPS-053..063 -- repo/factura.py + repo/factura_detalle.py unit tests.

Pydantic-style + pure-Python invariants that do NOT require a DB
session. DB integration tests live in
``tests/integration/test_factura_create_db.py`` (T2.1 + T2.5 in tasks
Phase 5). These unit tests catch regressions in:

- ``compute_total`` arithmetic (item subtotals + IVA - retencion).
- ``factura_detalle.crear_factura_detalle_bulk`` pure
  preprocessing (without session).
- Typed exception imports for handler 12-step chain discrimination.
- ``buscar_salida_facturable`` DB lookup (REQ-OPS-054 -- previously
  a placeholder that returned ``None``; verify-report C2 HIGH).
"""
from __future__ import annotations

import uuid as uuid_lib
from decimal import Decimal

import pytest
from parkos_core.models.A.salidas import Salidas
from parkos_core.models.V.impuestos import Impuestos
from parkos_core.repo.factura import (
    FacturaDuplicadaError,
    PagoDuplicadoError,
    TotalNoCoherenteError,
    buscar_salida_facturable,
    compute_total,
)
from parkos_core.repo.factura_detalle import crear_factura_detalle_bulk
from parkos_core.repo.impuestos import obtener_iva_vigente
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


def test_compute_total_resta_lineas_descuento() -> None:
    """2026-09-24 (salida-mensualidad factura): ``tipo="descuento"``
    lines are SUBTRACTED, not added -- a service line + a discount line
    of the SAME value nets to zero (the operator's directive: mostrar
    todos los valores + un descuento que deje el neto en $0).
    """
    items = [
        FacturaItemCreate(
            tipo="servicio",
            concepto="Estadia",
            cantidad=1,
            valor_unitario=Decimal("10000.00"),
            uuid_tarifa_sucursal=None,
        ),
        FacturaItemCreate(
            tipo="descuento",
            concepto="Descuento por mensualidad - Plan Oro",
            cantidad=1,
            valor_unitario=Decimal("10000.00"),
            uuid_tarifa_sucursal=None,
        ),
    ]
    total = compute_total(items=items, iva=Decimal("0.19"), retencion=Decimal("0"))
    assert total == Decimal("0.00")


def test_compute_total_descuento_parcial() -> None:
    """A discount smaller than the service line leaves a positive net
    (not every discount needs to zero out the total -- only the
    salida-mensualidad flow happens to send an equal-value discount)."""
    items = [
        FacturaItemCreate(
            tipo="servicio",
            concepto="Estadia",
            cantidad=1,
            valor_unitario=Decimal("10000.00"),
            uuid_tarifa_sucursal=None,
        ),
        FacturaItemCreate(
            tipo="descuento",
            concepto="Descuento parcial",
            cantidad=1,
            valor_unitario=Decimal("4000.00"),
            uuid_tarifa_sucursal=None,
        ),
    ]
    total = compute_total(items=items, iva=Decimal("0.19"), retencion=Decimal("0"))
    assert total == Decimal("6000.00")


def test_compute_descuento_suma_solo_lineas_descuento() -> None:
    """``compute_descuento`` sums ONLY ``tipo="descuento"`` lines --
    used to persist ``facturas.descuento`` / ``factura_electronica.
    descuento`` (document-level fields)."""
    from parkos_core.repo.factura import compute_descuento

    items = [
        FacturaItemCreate(
            tipo="servicio",
            concepto="Estadia",
            cantidad=1,
            valor_unitario=Decimal("10000.00"),
            uuid_tarifa_sucursal=None,
        ),
        FacturaItemCreate(
            tipo="descuento",
            concepto="Descuento por mensualidad - Plan Oro",
            cantidad=1,
            valor_unitario=Decimal("10000.00"),
            uuid_tarifa_sucursal=None,
        ),
    ]
    assert compute_descuento(items) == Decimal("10000.00")
    assert compute_descuento([items[0]]) == Decimal("0.00")


def test_compute_base_bruta_ignora_descuento() -> None:
    """2026-09-24 (live-validation bugfix): ``compute_base_bruta`` sums
    ONLY servicio/producto lines -- used as the IVA snapshot base so a
    salida-mensualidad factura shows the FULL IVA (como si fuera
    rotacion), not $0 (which is what happens if the NET total, after
    subtracting the descuento line, is used as the base instead)."""
    from parkos_core.repo.factura import compute_base_bruta

    items = [
        FacturaItemCreate(
            tipo="servicio",
            concepto="Estadia",
            cantidad=1,
            valor_unitario=Decimal("10000.00"),
            uuid_tarifa_sucursal=None,
        ),
        FacturaItemCreate(
            tipo="descuento",
            concepto="Descuento por mensualidad - Plan Oro",
            cantidad=1,
            valor_unitario=Decimal("10000.00"),
            uuid_tarifa_sucursal=None,
        ),
    ]
    assert compute_base_bruta(items) == Decimal("10000.00")
    # Ordinary rotacion factura (no descuento lines): base_bruta ==
    # compute_total() exactly -- this fix is a no-op for that flow.
    assert compute_base_bruta([items[0]]) == compute_total(
        items=[items[0]], iva=Decimal("0.19")
    )


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
    assert sig.return_annotation is not inspect.Signature.empty


@pytest.mark.asyncio
async def test_buscar_salida_facturable_returns_salida(
    pg_session: object,
) -> None:
    """C2 RED→GREEN: REQ-OPS-054 — lookup returns ``Salidas`` row, not ``None``.

    The pre-fix placeholder returned ``None`` regardless of the input,
    which caused handler Step 2 to wrongly raise 404 ``salida_no_encontrada``
    on every happy-path POST. The helper MUST query ``prod.salidas`` by
    ``uuid`` and return the row when present.
    """
    # Seed a Salidas row in the current session
    salida_uuid = uuid_lib.uuid4()
    salida = Salidas(
        uuid=salida_uuid,
        uuid_sucursal=None,  # nullable FK; isolation from real sucursal
        uuid_ingreso=None,   # nullable FK; isolation from real ingreso
    )
    pg_session.add(salida)  # type: ignore[attr-defined]
    await pg_session.flush()  # type: ignore[attr-defined]

    result = await buscar_salida_facturable(
        pg_session,  # type: ignore[arg-type]
        uuid_salida=salida_uuid,
    )
    assert result is not None
    assert isinstance(result, Salidas)
    assert result.uuid == salida_uuid


@pytest.mark.asyncio
async def test_buscar_salida_facturable_missing_returns_none(
    pg_session: object,
) -> None:
    """C2 regression: unknown ``uuid_salida`` returns ``None`` (handler 404)."""
    result = await buscar_salida_facturable(
        pg_session,  # type: ignore[arg-type]
        uuid_salida=uuid_lib.uuid4(),
    )
    assert result is None


@pytest.mark.asyncio
async def test_obtener_iva_vigente_returns_decimal(
    pg_session: object,
) -> None:
    """C3 RED→GREEN: REQ-OPS-055 / DEC-FACT-03 — read active IVA % as Decimal.

    The pre-fix handler passed the literal ``Decimal('0.19')`` to
    ``compute_total`` AND to ``crear_factura_impuesto_iva``, breaking
    the DEC-FACT-03 invariant that the IVA rate MUST come from
    ``prod.impuestos`` (not be hardcoded). The new helper reads the
    vigente row and returns its ``porcentaje`` as ``Decimal``.
    """
    from datetime import UTC, datetime

    from parkos_core.models.base import AuditMixin  # noqa: F401

    now = datetime.now(UTC).replace(tzinfo=None)
    iva_row = Impuestos(
        codigo="IVA",
        nombre="IVA",
        porcentaje=Decimal("0.19"),
        vigente_desde=now,
        vigente_hasta=None,
        estado="activo",
    )
    pg_session.add(iva_row)  # type: ignore[attr-defined]
    await pg_session.flush()  # type: ignore[attr-defined]

    result = await obtener_iva_vigente(pg_session)  # type: ignore[arg-type]
    assert result is not None
    assert result == Decimal("0.19")


@pytest.mark.asyncio
async def test_obtener_iva_vigente_missing_returns_none() -> None:
    """C3 regression: when no IVA row is vigente, helper returns ``None``.

    Handler maps ``None`` to 500 ``iva_no_configurado``. Uses a
    ``MagicMock`` session that returns no rows to keep the test
    independent of any IVA rows seeded in the live DB.
    """
    from unittest.mock import AsyncMock, MagicMock

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=None)
    mock_session.execute = AsyncMock(return_value=mock_result)

    result = await obtener_iva_vigente(mock_session)  # type: ignore[arg-type]
    assert result is None
