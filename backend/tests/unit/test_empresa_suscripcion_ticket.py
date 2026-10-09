"""Ticket de salida: razon social de la empresa dueña de la suscripcion.

Cuando la placa que sale pertenece a una suscripcion vigente de un cliente
empresa (NIT / persona juridica) el display de la factura expone SOLO su razon
social. Persona natural, placa sin suscripcion o suscripcion vencida: None.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.repo import subscripcion_activa as repo
from parkos_core.repo.subscripcion_activa import (
    SubscriptionLookupResult,
    resolver_empresa_suscripcion,
)
from parkos_core.schemas.facturacion import FacturaDisplayVehiculo

SUC = uuid_lib.uuid4()


def _session(*rows: object) -> AsyncMock:
    """Session cuyos execute() devuelven, en orden, un scalar por consulta."""
    results = []
    for row in rows:
        res = MagicMock()
        res.scalars.return_value.first.return_value = row
        res.scalar_one_or_none.return_value = row
        results.append(res)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=results)
    return session


def _sub(estado: str = "activo") -> SimpleNamespace:
    return SimpleNamespace(uuid=uuid_lib.uuid4(), uuid_cliente=uuid_lib.uuid4(), estado=estado)


def _cliente(tipo: str, nombre: str | None, numero: str = "900123456") -> SimpleNamespace:
    return SimpleNamespace(
        tipo_identificador=tipo, numero_identificacion=numero, nombre=nombre
    )


def _lookup(monkeypatch: pytest.MonkeyPatch, result: SubscriptionLookupResult) -> None:
    monkeypatch.setattr(
        repo, "resolve_active_subscription_for_exit", AsyncMock(return_value=result)
    )


async def test_empresa_con_suscripcion_vigente_devuelve_razon_social(monkeypatch) -> None:
    _lookup(monkeypatch, SubscriptionLookupResult(found=True, subscripcion=_sub()))
    # 1) cliente referenciado por la suscripcion, 2) version vigente por llave natural
    session = _session(_cliente("NIT", "Acme Viejo SAS"), _cliente("NIT", "Acme SAS"))
    got = await resolver_empresa_suscripcion(
        session, placa="ABC123", uuid_sucursal=SUC, as_of=date(2026, 10, 9)
    )
    assert got == "Acme SAS"  # version vigente, no la historica referenciada


async def test_si_no_hay_version_vigente_usa_la_referenciada(monkeypatch) -> None:
    _lookup(monkeypatch, SubscriptionLookupResult(found=True, subscripcion=_sub()))
    session = _session(_cliente("NIT", "Acme SAS"), None)
    got = await resolver_empresa_suscripcion(
        session, placa="ABC123", uuid_sucursal=SUC, as_of=date(2026, 10, 9)
    )
    assert got == "Acme SAS"


async def test_persona_natural_no_muestra_empresa(monkeypatch) -> None:
    _lookup(monkeypatch, SubscriptionLookupResult(found=True, subscripcion=_sub()))
    session = _session(_cliente("CC", "Ana"))
    assert (
        await resolver_empresa_suscripcion(
            session, placa="ABC123", uuid_sucursal=SUC, as_of=date(2026, 10, 9)
        )
        is None
    )


@pytest.mark.parametrize(
    "result",
    [
        SubscriptionLookupResult(found=False, message="no subscription at this branch"),
        SubscriptionLookupResult(found=False, subscripcion=_sub(), message="subscription expired"),
        SubscriptionLookupResult(found=True, subscripcion=_sub(estado="inactivo")),
    ],
)
async def test_sin_suscripcion_vencida_o_inactiva_no_muestra_empresa(
    monkeypatch, result
) -> None:
    _lookup(monkeypatch, result)
    session = _session()
    assert (
        await resolver_empresa_suscripcion(
            session, placa="ABC123", uuid_sucursal=SUC, as_of=date(2026, 10, 9)
        )
        is None
    )
    session.execute.assert_not_called()


async def test_placa_ausente_no_consulta(monkeypatch) -> None:
    _lookup(monkeypatch, SubscriptionLookupResult(found=False))
    session = _session()
    assert (
        await resolver_empresa_suscripcion(
            session, placa=None, uuid_sucursal=SUC, as_of=date(2026, 10, 9)
        )
        is None
    )


async def test_nombre_vacio_se_trata_como_ausente(monkeypatch) -> None:
    _lookup(monkeypatch, SubscriptionLookupResult(found=True, subscripcion=_sub()))
    session = _session(_cliente("NIT", "  "), None)
    assert (
        await resolver_empresa_suscripcion(
            session, placa="ABC123", uuid_sucursal=SUC, as_of=date(2026, 10, 9)
        )
        is None
    )


def test_el_campo_es_opcional_y_no_rompe_contratos() -> None:
    v = FacturaDisplayVehiculo(
        placa="ABC123", uuid_tipo_vehiculo=None, fecha_ingreso=None,
        fecha_salida=None, minutos=None,
    )
    assert v.empresa_suscripcion is None
    assert FacturaDisplayVehiculo(
        placa="ABC123", uuid_tipo_vehiculo=None, fecha_ingreso=None,
        fecha_salida=None, minutos=None, empresa_suscripcion="Acme SAS",
    ).empresa_suscripcion == "Acme SAS"
