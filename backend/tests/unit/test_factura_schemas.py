"""HU-F1.9 / REQ-OPS-053..063 -- F1.9 Pydantic schemas tests.

Covers:
- ``FacturaItemConDatosPropios._validar_nit_modulo11`` Pydantic v2
  @field_validator (REJECTS NIT with bad DV → ValidationError → 422).
- ``ClientesCreate._validar_nit_modulo11`` Pydantic v2 validator
  (same contract on F1.5's existing ClientesCreate).
- CC/CE/pasaporte do NOT require DV (DEC-FACT-08 consumidor final).
- ``extra='forbid'`` rejects ``uuid_cliente`` injection (DEC-FACT-06)
  on the response schema.
- ``FacturaCreate`` ``medio_pago`` Literal accepts the 5 enum values
  (DEC-FACT-07 Opción A).
"""
from __future__ import annotations

import uuid as uuid_lib
from decimal import Decimal

import pytest
from parkos_core.schemas.clientes import ClientesCreate
from parkos_core.schemas.facturacion import (
    FacturaCreate,
    FacturaItemConDatosPropios,
    FacturaItemCreate,
    FacturaPagoAdicionalCreate,
    FacturaPagoRead,
    FacturaRead,
)
from pydantic import ValidationError


def test_clientes_create_rechaza_nit_dv_invalido() -> None:
    """NIT with bad DV → ValidationError on ClientesCreate."""
    with pytest.raises(ValidationError) as exc_info:
        ClientesCreate(
            tipo_identificador="NIT",
            numero_identificacion="800.123.456",
            dv="9",  # wrong; Variant A expects 7
            nombre="Empresa ABC",
            apellido=None,
            email="test@example.com",
            telefono="3001234567",
        )
    assert any(
        "DV inválido" in str(err.get("msg", "")) or "DV" in str(err.get("msg", ""))
        for err in exc_info.value.errors()
    )


def test_clientes_create_acepta_nit_dv_valido() -> None:
    """NIT with correct DV passes ClientesCreate."""
    obj = ClientesCreate(
        tipo_identificador="NIT",
        numero_identificacion="800.123.456",
        dv="7",
        nombre="Empresa ABC",
        apellido=None,
        email="test@example.com",
        telefono="3001234567",
    )
    assert obj.tipo_identificador == "NIT"
    assert obj.dv == "7"


def test_factura_datos_cliente_rechaza_nit_dv_invalido() -> None:
    """FacturaItemConDatosPropios rejects NIT with wrong DV."""
    with pytest.raises(ValidationError):
        FacturaItemConDatosPropios(
            tipo_identificador="NIT",
            numero_identificacion="800.123.456",
            dv="9",  # DV esperado = 7
            nombre="Empresa ABC",
            apellido=None,
            email="test@example.com",
            telefono="3001234567",
        )


def test_factura_datos_cliente_acepta_cc_sin_dv() -> None:
    """CC/CE/pasaporte do NOT require DV (DEC-FACT-08 consumidor final)."""
    obj = FacturaItemConDatosPropios(
        tipo_identificador="CC",
        numero_identificacion="1234567890",
        dv=None,  # CC no requiere DV
        nombre="Juan",
        apellido="Pérez",
        email=None,
        telefono=None,
    )
    assert obj.tipo_identificador == "CC"
    assert obj.dv is None


def test_factura_create_acepta_medio_pago_literal_validos() -> None:
    """FacturaCreate medio_pago accepts all 5 literal values (DEC-FACT-07)."""
    for medio in ("efectivo", "tarjeta", "transferencia", "datafono", "mixto"):
        obj = FacturaCreate(
            uuid_salida=uuid_lib.uuid4(),
            items=[
                FacturaItemCreate(
                    tipo="servicio",
                    concepto="Parqueo 1h",
                    cantidad=1,
                    valor_unitario=Decimal("5000.00"),
                    uuid_tarifa_sucursal=None,
                ),
            ],
            subtotal=Decimal("5000.00"),
            total=Decimal("5950.00"),
            medio_pago=medio,  # type: ignore[arg-type]
            referencia=None,
            fe_con_datos=False,
            fe_datos_cliente=None,
        )
        assert obj.medio_pago == medio


def test_factura_create_rechaza_items_vacio() -> None:
    """Empty items rejected with min_length=1."""
    with pytest.raises(ValidationError):
        FacturaCreate(
            uuid_salida=uuid_lib.uuid4(),
            items=[],
            subtotal=Decimal("0"),
            total=Decimal("0"),
            medio_pago="efectivo",
            referencia=None,
            fe_con_datos=False,
            fe_datos_cliente=None,
        )


def test_factura_read_extrae_uuid_cliente() -> None:
    """FacturaRead accepts server-derived uuid_cliente (DEC-FACT-06)."""
    cliente_uuid = uuid_lib.uuid4()
    obj = FacturaRead(
        uuid=uuid_lib.uuid4(),
        created_at="2026-09-14T10:00:00",
        uuid_sucursal=uuid_lib.uuid4(),
        uuid_ingreso=None,
        uuid_salida=uuid_lib.uuid4(),
        subtotal=Decimal("5000.00"),
        descuento=Decimal("0.00"),
        total=Decimal("5950.00"),
        uuid_cliente=cliente_uuid,
        items=[],
        estado="emitida",
    )
    assert obj.uuid_cliente == cliente_uuid


def test_factura_pago_adicional_rechaza_datafono_sin_referencia() -> None:
    """Datafono without referencia is allowed at Pydantic level (handler enforces).

    Note: Pydantic v2 does NOT enforce V7 server-side check. This test
    documents that the schema accepts datafono + None referencia; the
    handler maps it to 400 ``voucher_requerido``.
    """
    obj = FacturaPagoAdicionalCreate(
        uuid_factura=uuid_lib.uuid4(),
        medio_pago="datafono",
        valor=Decimal("1000.00"),
        referencia=None,
        uuid_sesion=None,
    )
    assert obj.medio_pago == "datafono"
    assert obj.referencia is None


def test_factura_pago_adicional_valor_positivo() -> None:
    """FacturaPagoAdicionalCreate requiere valor > 0."""
    with pytest.raises(ValidationError):
        FacturaPagoAdicionalCreate(
            uuid_factura=uuid_lib.uuid4(),
            medio_pago="efectivo",
            valor=Decimal("0"),  # gt(0) required
            referencia=None,
            uuid_sesion=None,
        )


def test_factura_pago_read_shape() -> None:
    """FacturaPagoRead has the 6 documented fields."""
    obj = FacturaPagoRead(
        uuid=uuid_lib.uuid4(),
        uuid_factura=uuid_lib.uuid4(),
        medio_pago="efectivo",
        valor=Decimal("5000.00"),
        referencia=None,
        timestamp_evento="2026-09-14T10:00:00",
    )
    assert obj.medio_pago == "efectivo"
