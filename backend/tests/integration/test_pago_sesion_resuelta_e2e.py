"""CS1 -- every cash payment is tied to the operator's OPEN sesion.

The JWT ``sesion`` claim is absent when the operator opens the turno AFTER
logging in; the payment must still be linked (resolved from DB) so that
'efectivo esperado' counts it.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from parkos_core.models.A.factura_pagos import FacturaPagos
from parkos_core.models.L_S.sesion import Sesion
from parkos_core.repo import arqueo as repo_arqueo
from parkos_core.runtime.tiempo import hoy_bogota
from tests.integration.test_renovacion_e2e import (
    _headers,
    _sembrar_base,
    _sembrar_suscripcion,
    _url,
)

BASE = "/api/v1/clientes"


async def _abrir_sesion(pg_engine, m, *, inicial: str = "4500") -> uuid_lib.UUID:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        row = Sesion(
            uuid_sucursal=m.sucursal,
            uuid_usuario=m.actor,
            timestamp_apertura=datetime.utcnow(),
            timestamp_cierre=None,
            valor_inicial_efectivo=Decimal(inicial),
            valor_inicial_datafono=0,
            created_at=datetime.utcnow(),
            created_by=m.actor,
            sync_status="pendiente",
        )
        s.add(row)
        await s.commit()
        return row.uuid


async def _pagos(pg_engine, uuid_factura: str) -> list[FacturaPagos]:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        return list(
            (
                await s.execute(
                    select(FacturaPagos).where(FacturaPagos.uuid_factura == uuid_lib.UUID(uuid_factura))
                )
            ).scalars()
        )


async def test_renovacion_sin_claim_se_liga_a_la_sesion_abierta_y_cuenta_en_esperado(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    m = await _sembrar_base(pg_engine, con_resolucion=True, valor="100000")
    sub = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy_bogota() + timedelta(days=5))
    sesion = await _abrir_sesion(pg_engine, m)

    r = await client.post(
        _url(sub), json={"medio_pago": "efectivo"},
        headers=_headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}"),
    )
    assert r.status_code == 201, r.text

    pagos = await _pagos(pg_engine, r.json()["uuid_factura"])
    assert [p.uuid_sesion for p in pagos] == [sesion]
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        esperado = await repo_arqueo.calcular_esperado_sesion(s, uuid_sesion=sesion)
    assert esperado == Decimal("4500") + Decimal("119000")


async def test_venta_suscripcion_sin_claim_se_liga_a_la_sesion_abierta(
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

    pagos = await _pagos(pg_engine, r.json()["uuid_factura"])
    assert len(pagos) == 1
    assert pagos[0].uuid_sesion == sesion


async def test_renovacion_sin_sesion_abierta_conserva_regla_existente_sesion_nula(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    m = await _sembrar_base(pg_engine, con_resolucion=True, valor="100000")
    sub = await _sembrar_suscripcion(pg_engine, m, vencimiento=hoy_bogota() + timedelta(days=5))
    r = await client.post(
        _url(sub), json={"medio_pago": "efectivo"},
        headers=_headers(mint_operador_jwt, m, key=f"k-{uuid_lib.uuid4()}"),
    )
    assert r.status_code == 201, r.text
    pagos = await _pagos(pg_engine, r.json()["uuid_factura"])
    assert [p.uuid_sesion for p in pagos] == [None]
