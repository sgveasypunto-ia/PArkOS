"""D1: anular-no-pagada refresca ``prod.mv_ocupacion_diaria`` como ingreso/salida.

Sin DB (mocks). Tras la compensacion la placa vuelve a estar dentro: el
cupo del tablero debe reflejarlo en la misma respuesta. Un fallo del refresco
NO debe alterar la respuesta (la anulacion ya esta confirmada).
"""
from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.api.v1 import operacion as op

REFRESH_SQL = "SELECT prod.refresh_mv_ocupacion_diaria()"


def _session(*, refresh_error: Exception | None = None):
    sucursal = uuid_lib.uuid4()
    salida = MagicMock()
    salida.uuid_sucursal = sucursal
    scope = MagicMock()
    scope.scalar_one_or_none.return_value = salida
    calls: list[str] = []

    async def _execute(stmt, *a, **k):
        if str(stmt) == REFRESH_SQL:
            calls.append("refresh")
            if refresh_error is not None:
                raise refresh_error
            return MagicMock()
        return scope

    session = MagicMock()
    session.execute = AsyncMock(side_effect=_execute)

    async def _commit():
        calls.append("commit")

    async def _rollback():
        calls.append("rollback")

    session.commit = AsyncMock(side_effect=_commit)
    session.rollback = AsyncMock(side_effect=_rollback)
    session.refresh = AsyncMock()
    return session, sucursal, calls


async def _call(session, sucursal, monkeypatch):
    new_row = MagicMock()
    monkeypatch.setattr(op, "anular_salida_no_pagada", AsyncMock(return_value=new_row))
    sentinel = object()
    monkeypatch.setattr(op.AnulacionesRead, "model_validate", lambda row: sentinel)
    ctx = MagicMock()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = sucursal
    ctx.actor_uuid = uuid_lib.uuid4()
    response = MagicMock()
    response.headers = {}
    payload = MagicMock()
    payload.motivo = "cliente no pago en el cajon"
    result = await op.anular_salida_no_pagada_endpoint(
        uuid_salida=uuid_lib.uuid4(),
        payload=payload,
        response=response,
        session=session,
        ctx=ctx,
        _issuer=None,
        _perm=None,
    )
    return result, sentinel


async def test_anular_no_pagada_refresca_la_mv_despues_del_commit(monkeypatch):
    session, sucursal, calls = _session()
    result, sentinel = await _call(session, sucursal, monkeypatch)
    assert result is sentinel
    # commit de la anulacion primero, luego refresco, luego commit del refresco
    assert calls == ["commit", "refresh", "commit"]


async def test_fallo_del_refresco_no_altera_la_respuesta(monkeypatch):
    session, sucursal, calls = _session(refresh_error=RuntimeError("boom"))
    result, sentinel = await _call(session, sucursal, monkeypatch)
    assert result is sentinel
    assert calls == ["commit", "refresh", "rollback"]
