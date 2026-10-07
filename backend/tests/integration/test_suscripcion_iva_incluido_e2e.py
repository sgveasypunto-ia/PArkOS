"""The subscription plan price is IVA-INCLUSIVE (plan valor == total paid).

Sale: a 100.000 plan charges exactly 100.000; the tax (19% seeded) is a
breakdown INSIDE it (base 84.033,61 + IVA 15.966,39) recorded in
``factura_impuestos``; the cash 'esperado' of the turno reflects the plan
price, not an extra on top.
"""
from __future__ import annotations

import uuid as uuid_lib
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from parkos_core.models.A.factura_detalle import FacturaDetalle
from parkos_core.models.A.factura_impuestos import FacturaImpuestos
from parkos_core.models.A.factura_pagos import FacturaPagos
from parkos_core.models.L_E.facturas import Facturas
from parkos_core.repo import arqueo as repo_arqueo
from parkos_core.runtime.tiempo import hoy_bogota
from tests.integration.test_pago_sesion_resuelta_e2e import _abrir_sesion
from tests.integration.test_renovacion_e2e import _headers, _sembrar_base

BASE = "/api/v1/clientes"


async def test_venta_suscripcion_cobra_el_valor_del_plan_con_iva_incluido(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    m = await _sembrar_base(pg_engine, con_resolucion=True, valor="100000")
    sesion = await _abrir_sesion(pg_engine, m)

    r = await client.post(
        f"{BASE}/venta-suscripcion",
        json={
            "uuid_cliente": str(m.cliente),
            "placas": ["ZZZ999"],
            "uuid_tipo_subscripcion": str(m.plan),
            "fecha_inicio_cobertura": hoy_bogota().isoformat(),
            "cobrar_ahora": True,
            "medio_pago": "efectivo",
        },
        headers=_headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}"),
    )
    assert r.status_code == 201, r.text
    uuid_factura = uuid_lib.UUID(r.json()["uuid_factura"])

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        factura = (
            await s.execute(select(Facturas).where(Facturas.uuid == uuid_factura))
        ).scalar_one()
        imp = (
            await s.execute(
                select(FacturaImpuestos).where(FacturaImpuestos.uuid_factura == uuid_factura)
            )
        ).scalar_one()
        pago = (
            await s.execute(select(FacturaPagos).where(FacturaPagos.uuid_factura == uuid_factura))
        ).scalar_one()
        det = (
            await s.execute(
                select(FacturaDetalle).where(FacturaDetalle.uuid_factura == uuid_factura)
            )
        ).scalar_one()
        esperado = await repo_arqueo.calcular_esperado_sesion(s, uuid_sesion=sesion)

    assert Decimal(factura.total) == Decimal("100000.00")
    assert Decimal(factura.subtotal) == Decimal("84033.61")
    assert Decimal(det.subtotal) == Decimal("84033.61")
    assert Decimal(imp.base_calculo) == Decimal("84033.61")
    assert Decimal(imp.valor) == Decimal("15966.39")
    assert Decimal(imp.base_calculo) + Decimal(imp.valor) == Decimal(factura.total)
    assert Decimal(pago.valor) == Decimal("100000.00")
    assert esperado == Decimal("4500") + Decimal("100000")
