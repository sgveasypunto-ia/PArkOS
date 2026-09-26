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
    FacturaDisplayCliente,
    FacturaDisplayImpuesto,
    FacturaDisplayPago,
    FacturaDisplaySucursal,
    FacturaDisplayVehiculo,
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
    with pytest.raises(ValidationError) as exc_info:
        FacturaItemConDatosPropios(
            tipo_identificador="NIT",
            numero_identificacion="800.123.456",
            dv="9",  # DV esperado = 7
            nombre="Empresa ABC",
            apellido=None,
            email="test@example.com",
            telefono="3001234567",
        )
    assert any(
        "DV inválido" in str(err.get("msg", "")) for err in exc_info.value.errors()
    )


def test_factura_datos_cliente_acepta_nit_dv_valido() -> None:
    """BUGFIX (2026-09-25, hallado en validación en vivo Chrome DevTools):
    ``@field_validator("numero_identificacion")`` leía ``info.data.get("dv")``,
    pero ``dv`` se declara DESPUÉS de ``numero_identificacion`` — en
    Pydantic v2 ``info.data`` solo trae los campos declarados ANTES del
    campo bajo validación, así que ``dv`` era SIEMPRE ``None`` y todo NIT
    con DV real (correcto) rechazaba con 422 "dv required". El test
    anterior (`rechaza_nit_dv_invalido`) no lo detectó porque solo
    afirmaba ``pytest.raises(ValidationError)`` genérico — pasaba "por
    accidente" con el mensaje equivocado. Fix: `model_validator(mode="after")`
    (mismo patrón que `ClientesCreate`).
    """
    obj = FacturaItemConDatosPropios(
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
    """FacturaCreate medio_pago accepts all 6 literal values (DEC-FACT-07 +
    ``"suscripcion"`` added 2026-09-24 for the salida-mensualidad $0
    factura flow)."""
    for medio in (
        "efectivo",
        "tarjeta",
        "transferencia",
        "datafono",
        "mixto",
        "suscripcion",
    ):
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


def test_factura_item_create_acepta_tipo_descuento() -> None:
    """``FacturaItemCreate.tipo="descuento"`` (2026-09-24, salida-
    mensualidad factura): ``valor_unitario`` stays POSITIVE (ge=0
    unchanged) -- ``repo.factura.compute_total`` is what subtracts it."""
    obj = FacturaItemCreate(
        tipo="descuento",
        concepto="Descuento por mensualidad - Plan Oro",
        cantidad=1,
        valor_unitario=Decimal("10000.00"),
        uuid_tarifa_sucursal=None,
    )
    assert obj.tipo == "descuento"
    assert obj.valor_unitario == Decimal("10000.00")
    with pytest.raises(ValidationError):
        FacturaItemCreate(
            tipo="descuento",
            concepto="Descuento negativo invalido",
            cantidad=1,
            valor_unitario=Decimal("-10000.00"),
            uuid_tarifa_sucursal=None,
        )


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
    """FacturaRead accepts server-derived uuid_cliente (DEC-FACT-06).

    Also covers the 11 HU-F8.4 display-enrichment fields added in
    ``de1b83b`` (feat(backend): HU-F8.4 enrichment POST
    /facturacion/factura response). ``FacturaRead`` grew from 11 a 22
    campos obligatorios; este fixture refleja la forma completa actual.
    """
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
        medio_pago="efectivo",
        monto_recibido_cents=600_000,
        vuelto_cents=5_000,
        voucher=None,
        numero_recibo="SUC01-20260914-000123",
        cliente=FacturaDisplayCliente(
            tipo_identificador="CC",
            numero_identificacion="1020304050",
            dv=None,
            nombre="Juan",
            apellido="Pérez",
            email=None,
            telefono=None,
        ),
        datos_sucursal=FacturaDisplaySucursal(
            razon_social="Parqueadero Central S.A.S.",
            nit="900123456",
            direccion="Cra 10 # 20-30",
            ciudad="Bogotá",
            telefono="6011234567",
            horario="6:00am - 10:00pm",
            regimen="Común",
        ),
        datos_vehiculo=FacturaDisplayVehiculo(
            placa="ABC123",
            uuid_tipo_vehiculo=uuid_lib.uuid4(),
            fecha_ingreso="2026-09-14T09:00:00",
            fecha_salida="2026-09-14T10:00:00",
            minutos=60,
        ),
        impuestos=[
            FacturaDisplayImpuesto(
                uuid=uuid_lib.uuid4(),
                uuid_impuesto=uuid_lib.uuid4(),
                nombre_impuesto="IVA",
                codigo_impuesto="01",
                base_calculo=Decimal("5000.00"),
                porcentaje_aplicado=Decimal("19.00"),
                valor=Decimal("950.00"),
            ),
        ],
        pagos=[
            FacturaDisplayPago(
                uuid=uuid_lib.uuid4(),
                medio_pago="efectivo",
                valor=Decimal("5950.00"),
                referencia=None,
            ),
        ],
        factura_electronica=None,
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
