"""Bug #2: anulacion de salida y factura son mutuamente excluyentes.

Sin DB (session falsa que despacha por el SQL). Cubre los dos sentidos:
- anular-no-pagada sobre una salida ya facturada -> ``SalidaYaPagada`` (409).
- facturar una salida con anulacion ``ejecutada`` -> ``SalidaAnuladaError`` (409).
Ambos toman el mismo advisory lock por salida para cerrar la carrera.
"""
from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from parkos_core.repo import factura as repo_factura
from parkos_core.repo import salida as repo_salida


def _fake_session(*, anulada: bool, facturada: bool, salida: object | None):
    calls: list[str] = []

    async def _execute(stmt, params=None, *a, **k):
        sql = str(stmt)
        result = MagicMock()
        if "pg_advisory_xact_lock" in sql:
            calls.append("lock")
            return result
        if "prod.anulaciones" in sql:
            calls.append("check_anulada")
            result.first.return_value = (1,) if anulada else None
            return result
        if "prod.facturas" in sql:
            calls.append("check_facturada")
            result.first.return_value = (1,) if facturada else None
            return result
        calls.append("select_salida")
        result.scalar_one_or_none.return_value = salida
        return result

    session = MagicMock()
    session.execute = AsyncMock(side_effect=_execute)
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session, calls


async def test_anular_rechaza_salida_ya_facturada() -> None:
    salida = MagicMock()
    session, calls = _fake_session(anulada=False, facturada=True, salida=salida)
    with pytest.raises(repo_salida.SalidaYaPagada):
        await repo_salida.anular_salida_no_pagada(
            session,
            uuid_salida=uuid_lib.uuid4(),
            motivo="cancelo el pago",
            actor_uuid=uuid_lib.uuid4(),
        )
    assert calls[0] == "lock"
    session.add.assert_not_called()


async def test_anular_sin_factura_inserta_anulacion() -> None:
    salida = MagicMock()
    session, calls = _fake_session(anulada=False, facturada=False, salida=salida)
    await repo_salida.anular_salida_no_pagada(
        session,
        uuid_salida=uuid_lib.uuid4(),
        motivo="cancelo el pago",
        actor_uuid=uuid_lib.uuid4(),
    )
    session.add.assert_called_once()
    assert "check_facturada" in calls


async def test_buscar_salida_facturable_rechaza_salida_anulada() -> None:
    salida = MagicMock()
    session, calls = _fake_session(anulada=True, facturada=False, salida=salida)
    with pytest.raises(repo_factura.SalidaAnuladaError):
        await repo_factura.buscar_salida_facturable(
            session, uuid_salida=uuid_lib.uuid4()
        )
    assert calls[0] == "lock"


async def test_buscar_salida_facturable_ok_toma_lock_y_devuelve_salida() -> None:
    salida = MagicMock()
    session, calls = _fake_session(anulada=False, facturada=False, salida=salida)
    got = await repo_factura.buscar_salida_facturable(
        session, uuid_salida=uuid_lib.uuid4()
    )
    assert got is salida
    assert calls[0] == "lock"


async def test_endpoint_anular_mapea_salida_ya_pagada_a_409(monkeypatch) -> None:
    from parkos_core.api.v1 import operacion as op

    sucursal = uuid_lib.uuid4()
    salida = MagicMock()
    salida.uuid_sucursal = sucursal
    scope = MagicMock()
    scope.scalar_one_or_none.return_value = salida
    session = MagicMock()
    session.execute = AsyncMock(return_value=scope)
    session.commit = AsyncMock()
    monkeypatch.setattr(
        op,
        "anular_salida_no_pagada",
        AsyncMock(side_effect=repo_salida.SalidaYaPagada("x")),
    )
    ctx = MagicMock()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = sucursal
    ctx.actor_uuid = uuid_lib.uuid4()
    payload = MagicMock()
    payload.motivo = "cliente no pago en el cajon"
    with pytest.raises(HTTPException) as exc:
        await op.anular_salida_no_pagada_endpoint(
            uuid_salida=uuid_lib.uuid4(),
            payload=payload,
            response=MagicMock(headers={}),
            session=session,
            ctx=ctx,
            _issuer=None,
            _perm=None,
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["error"] == "salida_ya_pagada"


async def test_endpoint_factura_mapea_salida_anulada_a_409(monkeypatch) -> None:
    from parkos_core.api.v1.facturacion import create_factura

    async def _boom(*_a, **_k):
        raise repo_factura.SalidaAnuladaError("x")

    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.buscar_salida_facturable",
        _boom,
    )
    payload = MagicMock()
    payload.uuid_salida = uuid_lib.uuid4()
    with pytest.raises(HTTPException) as exc:
        await create_factura(MagicMock(), payload, AsyncMock(), MagicMock(), None)
    assert exc.value.status_code == 409
    assert exc.value.detail["error"] == "salida_anulada"
