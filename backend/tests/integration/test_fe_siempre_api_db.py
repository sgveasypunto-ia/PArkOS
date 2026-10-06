"""FE always emitted through the real API (``POST /facturacion/factura-servicio``).

DB + ASGI app, no mocks: payment commit, then FE with the standard customer;
failure keeps the payment, leaves the invoice pending and the automatic retry
emits it once the resolution exists. Uses its own random sucursal and never
truncates (run it against a DISPOSABLE migrated DB, see
``test_fe_emision_db.py``).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from parkos_core.constants import CLIENTE_ESTANDAR_UUID
from parkos_core.models.L_E.factura_electronica import FacturaElectronica
from parkos_core.models.L_E.facturas import Facturas
from parkos_core.models.L_E.ingreso import Ingreso
from parkos_core.models.L_W.alerta import Alerta
from parkos_core.models.V.empresa import Empresa
from parkos_core.models.V.resolucion_facturacion import ResolucionFacturacion
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from parkos_core.repo.fe_emision import FeRetryScheduler, reintentar_pendientes
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seed(Session, *, con_resolucion: bool):  # noqa: N803
    suc = uuid_lib.uuid4()
    ingreso = uuid_lib.uuid4()
    async with Session() as s:
        empresa = (
            await s.execute(select(Empresa.uuid).where(Empresa.vigente_hasta.is_(None)))
        ).scalars().first()
        tipo = (
            await s.execute(select(TiposVehiculo.uuid).where(TiposVehiculo.vigente_hasta.is_(None)))
        ).scalars().first()
        s.add(
            Sucursal(
                uuid=suc, uuid_empresa=empresa, uuid_tipo_sucursal=None,
                nombre=f"Suc API {suc.hex[:6]}", prefijo_nombre=f"AP{suc.hex[:4]}",
                ciudad="Ciudad", direccion="Calle 1", telefono="+57111", horario="24/7",
                vigente_desde=_now(), vigente_hasta=None, estado="activo",
                created_at=_now(), created_by=None, sync_status="sincronizado",
                sync_timestamp=None, sync_attempts=0,
            )
        )
        await s.flush()
        s.add(
            Ingreso(
                uuid=ingreso, uuid_sucursal=suc, uuid_tipo_vehiculo=tipo, placa="ZZZ999",
                uuid_subscripcion_cliente=None, fecha_ingreso=_now() - timedelta(hours=1),
                observaciones=None, created_at=_now(), created_by=None,
                sync_status="sincronizado", sync_timestamp=None, sync_attempts=0,
            )
        )
        if con_resolucion:
            await _resolucion(s, suc)
        await s.commit()
    return suc, ingreso


async def _resolucion(s, suc, desde=100):
    s.add(
        ResolucionFacturacion(
            uuid=uuid_lib.uuid4(), uuid_sucursal=suc,
            numero_resolucion=f"R-{uuid_lib.uuid4().hex[:10]}", prefijo="SETP",
            rango_desde=desde, rango_hasta=desde + 100, vigente_desde=_now(),
            vigente_hasta=None, estado="activo", created_at=_now(), created_by=None,
            sync_status="sincronizado", sync_attempts=0,
        )
    )


def _body(ingreso: uuid_lib.UUID) -> dict:
    subtotal = Decimal("1000")
    total = subtotal  # IVA is included in the unit value (compute_total)
    return {
        "uuid_ingreso": str(ingreso),
        "items": [
            {"tipo": "servicio", "concepto": "reimpresion", "cantidad": 1, "valor_unitario": "1000"}
        ],
        "subtotal": str(subtotal),
        "total": str(total),
        "medio_pago": "efectivo",
        # NOTE: no fe_con_datos / fe_datos_cliente -> standard customer
    }


async def _post(client, token, suc, ingreso):
    return await client.post(
        "/api/v1/facturacion/factura-servicio",
        json=_body(ingreso),
        headers={"Authorization": f"Bearer {token}", "X-Sucursal-Context": str(suc)},
    )


async def test_cobro_sin_pedir_fe_emite_con_cliente_estandar(
    pg_engine, mint_operador_jwt, client
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)  # noqa: N806
    suc, ingreso = await _seed(Session, con_resolucion=True)
    token = mint_operador_jwt(actor_uuid=uuid_lib.uuid4(), sucursal_uuid=suc)

    resp = await _post(client, token, suc, ingreso)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["factura_electronica"] is not None
    assert body["factura_electronica"]["consecutivo"] == 100
    assert body["factura_electronica"]["estado_dian"] == "pendiente"
    assert body["factura_electronica_error"] is None
    assert body["factura_electronica_pendiente"] is False
    async with Session() as s:
        fe = (
            await s.execute(select(FacturaElectronica).where(FacturaElectronica.uuid_sucursal == suc))
        ).scalar_one()
        assert fe.uuid_cliente == CLIENTE_ESTANDAR_UUID
        assert str(fe.uuid_factura) == body["uuid"]


async def test_fallo_de_fe_conserva_el_pago_y_el_reintento_lo_emite(
    pg_engine, mint_operador_jwt, client
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)  # noqa: N806
    suc, ingreso = await _seed(Session, con_resolucion=False)  # no resolution
    token = mint_operador_jwt(actor_uuid=uuid_lib.uuid4(), sucursal_uuid=suc)

    resp = await _post(client, token, suc, ingreso)

    assert resp.status_code == 201, resp.text  # the payment is NOT undone
    body = resp.json()
    assert body["factura_electronica"] is None
    assert body["factura_electronica_error"] == "resolucion_facturacion_no_encontrada"
    assert body["factura_electronica_pendiente"] is True
    async with Session() as s:
        assert (
            await s.execute(select(Facturas).where(Facturas.uuid == uuid_lib.UUID(body["uuid"])))
        ).scalar_one_or_none() is not None
        marcadores = (
            await s.execute(
                select(Alerta).where(
                    Alerta.uuid_sucursal == suc, Alerta.tipo_alerta == "fe_emision_pendiente"
                )
            )
        ).scalars().all()
        assert len(marcadores) == 1

        await _resolucion(s, suc, desde=900)  # administrator configures it
        await s.commit()
        cont = await reintentar_pendientes(s, uuid_sucursal=suc, scheduler=FeRetryScheduler())
        assert cont["emitidas"] == 1
        fe = (
            await s.execute(select(FacturaElectronica).where(FacturaElectronica.uuid_sucursal == suc))
        ).scalar_one()
        assert fe.consecutivo == 900
        assert fe.uuid_cliente == CLIENTE_ESTANDAR_UUID
        assert str(fe.uuid_factura) == body["uuid"]
