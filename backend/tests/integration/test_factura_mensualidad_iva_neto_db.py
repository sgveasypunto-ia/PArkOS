"""AUD2 -- salida-mensualidad invoice: IVA on the NET taxable amount, DB-backed.

``POST /api/v1/facturacion/facturas`` with a servicio line (IVA-included tariff
1500) + a ``descuento`` line must persist ``factura_impuestos`` on
``total - descuento``: a fully covered exit (total 0) carries base 0 / IVA 0, a
partial discount taxes only what is charged. The header keeps the gross base
(subtotal 1260.50) and the discount; the display derives the discount-in-base.
"""
from __future__ import annotations

import uuid as uuid_lib
from decimal import Decimal

from parkos_core.models.A.factura_impuestos import FacturaImpuestos
from parkos_core.models.L_E.facturas import Facturas
from parkos_core.models.V.usuarios import Usuarios
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.conftest import VFixtureFactory
from tests.integration.test_calcular_cotizacion_db import (
    _seed_minimal_happy_path,
    _truncate_tables,
)
from tests.integration.test_calcular_cotizacion_salida_anulada_db import _insert_salida

URL = "/api/v1/facturacion/factura"


async def _mundo(pg_engine, pg_dsn):
    await _truncate_tables(pg_dsn)
    sucursal = uuid_lib.uuid4()
    ingreso = await _seed_minimal_happy_path(
        pg_engine,
        uuid_sucursal=sucursal,
        uuid_tipo_vehiculo=uuid_lib.uuid4(),
        uuid_tipo_tarifa=uuid_lib.uuid4(),
        minutos_en_estacionamiento=30,
    )
    salida = _insert_salida(pg_dsn, sucursal, ingreso)
    actor = uuid_lib.uuid4()
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as s:
        s.add(
            VFixtureFactory.build(
                Usuarios, uuid=actor, email=f"{actor}@example.com",
                password_hash="x", rol="operador",
            )
        )
        await s.commit()
    return sucursal, salida, actor


def _body(salida, descuento: str, total: str) -> dict:
    return {
        "uuid_salida": str(salida),
        "items": [
            {"tipo": "servicio", "concepto": "Parqueo", "cantidad": 1,
             "valor_unitario": "1500.00"},
            {"tipo": "descuento", "concepto": "Descuento por mensualidad - Plan",
             "cantidad": 1, "valor_unitario": descuento},
        ],
        "subtotal": "1260.50",
        "total": total,
        "medio_pago": "suscripcion",
        "fe_con_datos": False,
    }


async def _persistido(pg_engine, factura_uuid):
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as s:
        fac = (await s.execute(select(Facturas).where(Facturas.uuid == factura_uuid))).scalar_one()
        imp = (
            await s.execute(
                select(FacturaImpuestos).where(FacturaImpuestos.uuid_factura == factura_uuid)
            )
        ).scalar_one()
    return fac, imp


async def test_salida_mensualidad_total_cero_no_causa_iva(
    client, pg_engine, pg_dsn, alembic_upgrade, mint_operador_jwt
) -> None:
    sucursal, salida, actor = await _mundo(pg_engine, pg_dsn)
    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=sucursal)
    r = await client.post(
        URL, json=_body(salida, "1500.00", "0.00"),
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"k-{uuid_lib.uuid4()}"},
    )
    assert r.status_code == 201, r.text
    fac, imp = await _persistido(pg_engine, uuid_lib.UUID(r.json()["uuid"]))
    assert Decimal(fac.total) == Decimal("0.00")
    assert Decimal(fac.subtotal) == Decimal("1260.50")
    assert Decimal(fac.descuento) == Decimal("1500.00")
    assert Decimal(imp.base_calculo) == Decimal("0")
    assert Decimal(imp.valor) == Decimal("0")


async def test_salida_mensualidad_descuento_parcial_grava_el_neto(
    client, pg_engine, pg_dsn, alembic_upgrade, mint_operador_jwt
) -> None:
    sucursal, salida, actor = await _mundo(pg_engine, pg_dsn)
    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=sucursal)
    r = await client.post(
        URL, json=_body(salida, "500.00", "1000.00"),
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"k-{uuid_lib.uuid4()}"},
    )
    assert r.status_code == 201, r.text
    fac, imp = await _persistido(pg_engine, uuid_lib.UUID(r.json()["uuid"]))
    assert Decimal(imp.base_calculo) == Decimal("840.34")
    assert Decimal(imp.valor) == Decimal("159.66")
    assert Decimal(imp.base_calculo) + Decimal(imp.valor) == Decimal(fac.total)
