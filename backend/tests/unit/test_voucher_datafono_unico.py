"""Caja bug 3: un voucher de datafono no puede repetirse en la misma sucursal y dia.

Regla (conservadora): entre pagos ``tipo_movimiento='pago'`` con
``medio_pago='datafono'`` de la misma sucursal y el mismo dia operativo
(Bogota), la ``referencia`` normalizada (trim + mayuscula) es unica, salvo que
el pago previo ya tenga un reverso. El reintento del mismo pago (misma
``uuid_factura``) no cuenta como duplicado.
"""

from __future__ import annotations

import uuid as uuid_lib
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from parkos_core.api.v1._helpers import voucher_duplicado_http
from parkos_core.repo.factura import (
    VoucherDatafonoDuplicadoError,
    crear_factura_pago,
    normalizar_voucher,
)
from sqlalchemy.dialects import postgresql

FACTURA = uuid_lib.UUID("00000000-0000-0000-0000-000000000cc1")
SUCURSAL = uuid_lib.UUID("00000000-0000-0000-0000-000000000bb1")


def _session(existing: object | None) -> AsyncMock:
    """Session cuyo SELECT de duplicados devuelve ``existing`` (None = libre)."""
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.first.return_value = existing
    session.execute.return_value = result
    return session


async def _pagar(session: AsyncMock, medio: str, ref: str | None, factura=FACTURA):
    return await crear_factura_pago(
        session,
        uuid_factura=factura,
        uuid_sucursal=SUCURSAL,
        medio_pago=medio,  # type: ignore[arg-type]
        valor=Decimal("1000"),
        referencia=ref,
    )


def test_normalizar_voucher_trim_y_mayuscula() -> None:
    assert normalizar_voucher("  test999 ") == "TEST999"
    assert normalizar_voucher("TeSt-9") == "TEST-9"
    assert normalizar_voucher("   ") is None
    assert normalizar_voucher(None) is None


@pytest.mark.asyncio
async def test_segundo_pago_con_mismo_voucher_es_rechazado() -> None:
    session = _session(existing=(uuid_lib.uuid4(),))
    with pytest.raises(VoucherDatafonoDuplicadoError) as exc:
        await _pagar(session, "datafono", "TEST999")
    assert exc.value.referencia == "TEST999"
    session.add.assert_not_called()  # nada se inserta


@pytest.mark.asyncio
async def test_voucher_distinto_es_aceptado() -> None:
    session = _session(existing=None)
    row = await _pagar(session, "datafono", "TEST1000")
    session.add.assert_called_once_with(row)
    assert row.referencia == "TEST1000"


@pytest.mark.asyncio
async def test_efectivo_sin_referencia_no_consulta_duplicados() -> None:
    session = _session(existing=(uuid_lib.uuid4(),))  # si consultara, rechazaria
    row = await _pagar(session, "efectivo", None)
    session.add.assert_called_once_with(row)
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_otros_medios_con_referencia_no_se_validan() -> None:
    session = _session(existing=(uuid_lib.uuid4(),))
    await _pagar(session, "transferencia", "ABC")
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_la_referencia_se_guarda_tal_cual_y_se_compara_normalizada() -> None:
    session = _session(existing=None)
    row = await _pagar(session, "datafono", " test999 ")
    assert row.referencia == " test999 "  # el dato original no se muta
    stmt = session.execute.await_args_list[-1].args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "upper(btrim(prod.factura_pagos.referencia))" in sql.lower()
    assert "'TEST999'" in sql


@pytest.mark.asyncio
async def test_consulta_excluye_misma_factura_y_pagos_revertidos() -> None:
    """El reintento del mismo pago no es duplicado y un reverso libera el voucher."""
    session = _session(existing=None)
    await _pagar(session, "datafono", "TEST999")
    stmt = session.execute.await_args_list[-1].args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).lower()
    assert "uuid_factura !=" in sql or "uuid_factura <>" in sql
    assert "not (exists" in sql
    assert "uuid_pago_revertido" in sql
    assert "tipo_movimiento = 'pago'" in sql
    assert "medio_pago = 'datafono'" in sql
    assert str(SUCURSAL) in sql


@pytest.mark.asyncio
async def test_toma_lock_advisory_antes_de_consultar() -> None:
    """Dos cobros simultaneos con el mismo voucher se serializan."""
    session = _session(existing=None)
    await _pagar(session, "datafono", "TEST999")
    first = str(session.execute.await_args_list[0].args[0]).lower()
    assert "pg_advisory_xact_lock" in first


def test_http_422_con_contrato_estandar() -> None:
    exc = voucher_duplicado_http(VoucherDatafonoDuplicadoError(referencia="TEST999"))
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 422
    assert exc.detail["error"] == "voucher_datafono_duplicado"
    assert exc.detail["referencia"] == "TEST999"
    assert "TEST999" in exc.detail["message"]
    assert exc.headers == {"Cache-Control": "no-store"}


@pytest.mark.asyncio
async def test_endpoint_factura_pagos_devuelve_422_sin_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from parkos_core.api.v1.facturacion import create_factura_pago
    from parkos_core.schemas.facturacion import FacturaPagoAdicionalCreate

    payload = FacturaPagoAdicionalCreate(
        uuid_factura=uuid_lib.uuid4(),
        medio_pago="datafono",
        valor=Decimal("1000.00"),
        referencia="TEST999",
        uuid_sesion=None,
    )
    session = AsyncMock()
    ctx = MagicMock()
    ctx.uuid_sesion = None

    async def _crear(*_a: object, **_k: object) -> None:
        raise VoucherDatafonoDuplicadoError(referencia="TEST999")

    monkeypatch.setattr("parkos_core.api.v1.facturacion.repo_factura.crear_factura_pago", _crear)

    with pytest.raises(HTTPException) as exc:
        await create_factura_pago(MagicMock(), payload, session, ctx, None)

    assert exc.value.status_code == 422
    assert exc.value.detail["error"] == "voucher_datafono_duplicado"
    session.commit.assert_not_called()
