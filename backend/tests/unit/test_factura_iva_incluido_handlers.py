"""Rotacion / salida / servicio invoices persist an IVA-INCLUDED breakdown.

The tariff price is what the customer pays (``total``); the IVA is a breakdown
inside it. ``factura_impuestos`` must therefore hold
``base = ROUND(total / (1 + p), 2)`` and ``valor = total - base`` (so
``base * p == valor`` within a cent and ``base + valor == total``) and
``facturas.subtotal`` must be that same base. Before this change the handlers
stored ``base = total`` and ``valor = ROUND(total * p, 2)`` (200 -> IVA 38, base
200), which printed an arithmetically wrong breakdown on a DIAN document.
The TOTAL charged never changes.
"""
from __future__ import annotations

import uuid as uuid_lib
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.api.v1 import facturacion as handlers
from parkos_core.repo.fe_emision import FeEmisionResultado
from parkos_core.schemas.facturacion import (
    FacturaCreate,
    FacturaItemCreate,
    FacturaServicioCreate,
)

IVA = Decimal("0.19")
TOTAL = Decimal("200.00")
BASE_ESPERADA = Decimal("168.07")  # ROUND(200 / 1.19, 2)
IVA_ESPERADO = Decimal("31.93")  # 200 - 168.07


def _items() -> list[FacturaItemCreate]:
    return [
        FacturaItemCreate(
            tipo="servicio",
            concepto="Parqueo",
            cantidad=1,
            valor_unitario=TOTAL,
            uuid_tarifa_sucursal=None,
        )
    ]


def _wire(monkeypatch: pytest.MonkeyPatch, sucursal: uuid_lib.UUID) -> dict[str, dict]:
    """Patch the repo seams and capture what the handler persists."""
    captured: dict[str, dict] = {"factura": {}, "impuesto": {}}
    p = "parkos_core.api.v1.facturacion."

    async def _iva(*_a: object, **_k: object) -> Decimal:
        return IVA

    async def _evento(*_a: object, **kw: object) -> MagicMock:
        captured["factura"] = dict(kw["new_attrs"])  # type: ignore[arg-type]
        f = MagicMock()
        f.uuid = uuid_lib.uuid4()
        f.uuid_sucursal = sucursal
        return f

    async def _detalle(*_a: object, **_k: object) -> list:
        return [MagicMock()]

    async def _impuesto(*_a: object, **kw: object) -> MagicMock:
        captured["impuesto"] = dict(kw)
        return MagicMock()

    async def _noop(*_a: object, **_k: object) -> MagicMock:
        return MagicMock()

    async def _display(*_a: object, **_k: object) -> MagicMock:
        return MagicMock()

    monkeypatch.setattr(p + "obtener_iva_vigente", _iva)
    monkeypatch.setattr(p + "repo_factura.validar_items", lambda items: items)
    monkeypatch.setattr(p + "repo_factura.lock_tarifas_sucursal_para_items", _noop)
    monkeypatch.setattr(p + "repo_factura.crear_factura_evento", _evento)
    monkeypatch.setattr(p + "crear_factura_detalle_bulk", _detalle)
    monkeypatch.setattr(p + "repo_factura.crear_factura_impuesto_iva", _impuesto)
    monkeypatch.setattr(p + "repo_factura.crear_factura_pago", _noop)
    monkeypatch.setattr(p + "resolver_sesion_de_pago", AsyncMock(return_value=None))
    monkeypatch.setattr(p + "build_display_factura", _display)
    monkeypatch.setattr(
        p + "emitir_fe_para_pago",
        AsyncMock(return_value=FeEmisionResultado(uuid_factura_electronica=uuid_lib.uuid4())),
    )
    return captured


def _ctx(sucursal: uuid_lib.UUID) -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.sucursal_uuid = sucursal
    ctx.issuer_prefix = "operador-"
    ctx.uuid_sesion = None
    return ctx


def _assert_desglose(captured: dict[str, dict]) -> None:
    imp = captured["impuesto"]
    assert imp["base"] == BASE_ESPERADA
    assert imp["iva_monto"] == IVA_ESPERADO
    assert imp["iva"] == IVA
    assert imp["base"] + imp["iva_monto"] == TOTAL  # nothing charged on top
    assert abs(imp["base"] * IVA - imp["iva_monto"]) <= Decimal("0.01")
    fac = captured["factura"]
    assert fac["subtotal"] == BASE_ESPERADA  # header agrees with the tax base
    assert fac["total"] == TOTAL  # the TOTAL charged never changes


@pytest.mark.asyncio
async def test_rotacion_salida_persists_iva_included_breakdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sucursal = uuid_lib.uuid4()
    captured = _wire(monkeypatch, sucursal)
    salida = MagicMock()
    salida.uuid = uuid_lib.uuid4()
    salida.uuid_sucursal = sucursal
    salida.uuid_ingreso = uuid_lib.uuid4()

    async def _buscar(*_a: object, **_k: object) -> MagicMock:
        return salida

    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.buscar_salida_facturable", _buscar
    )
    payload = FacturaCreate(
        uuid_salida=salida.uuid,
        items=_items(),
        # the client still sends the legacy split (total - total*p): ignored
        subtotal=Decimal("162.00"),
        total=TOTAL,
        medio_pago="efectivo",
        referencia=None,
        fe_con_datos=False,
        fe_datos_cliente=None,
    )

    await handlers.create_factura(MagicMock(), payload, AsyncMock(), _ctx(sucursal), None)

    _assert_desglose(captured)


@pytest.mark.asyncio
async def test_servicio_suelto_persists_iva_included_breakdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sucursal = uuid_lib.uuid4()
    captured = _wire(monkeypatch, sucursal)
    ingreso = MagicMock()
    ingreso.uuid_sucursal = sucursal
    session = AsyncMock()
    session.get = AsyncMock(return_value=ingreso)
    payload = FacturaServicioCreate(
        uuid_ingreso=uuid_lib.uuid4(),
        items=_items(),
        subtotal=Decimal("162.00"),
        total=TOTAL,
        medio_pago="efectivo",
        referencia=None,
        fe_con_datos=False,
        fe_datos_cliente=None,
    )

    await handlers.create_factura_servicio(
        MagicMock(), payload, session, _ctx(sucursal), None
    )

    _assert_desglose(captured)


@pytest.mark.asyncio
async def test_mensualidad_exit_zero_total_invoice_adds_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Salida-mensualidad: servicio 1500 (IVA incl.) + descuento 1500, total 0.

    The receipt must add up: base 1260.50 + IVA 239.50 - descuento 1500 == 0
    (before: subtotal 1215 / IVA 285 split on the total, IVA row not even
    visible, so "Subtotal 1.215, Descuento -1.500, TOTAL 0" did not reconcile).
    """
    sucursal = uuid_lib.uuid4()
    captured = _wire(monkeypatch, sucursal)
    # compute_total / compute_descuento are real: they net the discount line.
    salida = MagicMock()
    salida.uuid = uuid_lib.uuid4()
    salida.uuid_sucursal = sucursal
    salida.uuid_ingreso = uuid_lib.uuid4()

    async def _buscar(*_a: object, **_k: object) -> MagicMock:
        return salida

    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.buscar_salida_facturable", _buscar
    )
    payload = FacturaCreate(
        uuid_salida=salida.uuid,
        items=[
            FacturaItemCreate(
                tipo="servicio", concepto="Parqueo", cantidad=1,
                valor_unitario=Decimal("1500.00"), uuid_tarifa_sucursal=None,
            ),
            FacturaItemCreate(
                tipo="descuento", concepto="Descuento por mensualidad - Plan",
                cantidad=1, valor_unitario=Decimal("1500.00"), uuid_tarifa_sucursal=None,
            ),
        ],
        subtotal=Decimal("1215.00"),
        total=Decimal("0.00"),
        medio_pago="suscripcion",
        referencia=None,
        fe_con_datos=False,
        fe_datos_cliente=None,
    )

    await handlers.create_factura(MagicMock(), payload, AsyncMock(), _ctx(sucursal), None)

    imp, fac = captured["impuesto"], captured["factura"]
    assert imp["base"] == Decimal("1260.50")
    assert imp["iva_monto"] == Decimal("239.50")
    assert fac["subtotal"] == Decimal("1260.50")
    assert fac["descuento"] == Decimal("1500.00")
    assert fac["total"] == Decimal("0.00")
    assert fac["subtotal"] + imp["iva_monto"] - fac["descuento"] == fac["total"]
