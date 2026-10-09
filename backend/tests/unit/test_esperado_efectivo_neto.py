"""Efectivo esperado del turno: base + cobros en efectivo - reversos en efectivo.

Caso del reporte: base 10.000, pagos en efectivo 5.000 y pagos con datafono
20.000 -> esperado en efectivo 15.000 (el datafono no entra, F12.1.1).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402

from parkos_core.repo import arqueo as repo_arqueo  # noqa: E402


async def _sql_de_la_suma(**kwargs) -> str:
    captured: dict[str, object] = {}

    async def _execute(stmt):  # noqa: ANN001
        captured["stmt"] = stmt
        r = MagicMock()
        r.scalar_one.return_value = Decimal("0")
        return r

    session = MagicMock()
    session.execute = AsyncMock(side_effect=_execute)
    await repo_arqueo._sum_factura_pagos_by_medio_pago(session, **kwargs)
    return str(
        captured["stmt"].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


@pytest.mark.asyncio
async def test_suma_resta_los_reversos_del_mismo_medio() -> None:
    sql = await _sql_de_la_suma(
        uuid_sesion=uuid_lib.uuid4(),
        uuid_sucursal=None,
        fecha=None,
        medios_pago=("efectivo",),
    )
    assert "'reverso'" in sql
    assert "CASE" in sql.upper()
    assert "-" in sql  # el reverso entra con signo negativo


@pytest.mark.asyncio
async def test_suma_cierre_dia_tambien_resta_reversos() -> None:
    from datetime import date

    sql = await _sql_de_la_suma(
        uuid_sesion=None,
        uuid_sucursal=uuid_lib.uuid4(),
        fecha=date(2026, 10, 9),
        medios_pago=("efectivo",),
    )
    assert "'reverso'" in sql


def test_el_esperado_solo_considera_efectivo() -> None:
    # Un solo punto de decision: sumar el datafono es cambiar esta tupla.
    assert repo_arqueo.MEDIOS_PAGO_EN_ESPERADO == ("efectivo",)


@pytest.mark.asyncio
async def test_esperado_sesion_base_mas_efectivo_sin_datafono() -> None:
    sesion = MagicMock()
    sesion.valor_inicial_efectivo = Decimal("10000")
    res = MagicMock()
    res.scalar_one_or_none.return_value = sesion
    session = MagicMock()
    session.execute = AsyncMock(return_value=res)
    suma = AsyncMock(return_value=Decimal("5000"))
    with patch.object(repo_arqueo, "_sum_factura_pagos_by_medio_pago", new=suma):
        esperado = await repo_arqueo.calcular_esperado_sesion(
            session, uuid_sesion=uuid_lib.uuid4()
        )
    assert esperado == Decimal("15000")
    assert suma.await_args.kwargs["medios_pago"] == ("efectivo",)


@pytest.mark.asyncio
async def test_esperado_sesion_sin_cobros_es_solo_la_base() -> None:
    sesion = MagicMock()
    sesion.valor_inicial_efectivo = Decimal("10000")
    res = MagicMock()
    res.scalar_one_or_none.return_value = sesion
    session = MagicMock()
    session.execute = AsyncMock(return_value=res)
    with patch.object(
        repo_arqueo,
        "_sum_factura_pagos_by_medio_pago",
        new=AsyncMock(return_value=Decimal("0")),
    ):
        esperado = await repo_arqueo.calcular_esperado_sesion(
            session, uuid_sesion=uuid_lib.uuid4()
        )
    assert esperado == Decimal("10000")


# --- GET /caja/arqueo/esperado-parcial -------------------------------------


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = uuid_lib.uuid4()
    return ctx


@pytest.mark.asyncio
async def test_endpoint_parcial_devuelve_el_mismo_esperado_que_el_post() -> None:
    from parkos_core.api.v1 import caja_arqueo as handler_mod
    from parkos_core.schemas.caja import EsperadoParcialQueryParams

    response = MagicMock()
    response.headers = {}
    params = EsperadoParcialQueryParams(uuid_sesion=uuid_lib.uuid4())
    with (
        patch.object(
            handler_mod.repo_arqueo,
            "validar_sesion_abierta_para_arqueo",
            AsyncMock(return_value=MagicMock()),
        ),
        patch.object(
            handler_mod.repo_arqueo,
            "calcular_esperado_sesion",
            AsyncMock(return_value=Decimal("15000")),
        ) as calc,
    ):
        out = await handler_mod.get_arqueo_esperado_parcial(
            response=response,
            params=params,
            session=MagicMock(),
            ctx=_ctx(),
            _claims=None,
        )
    assert out.valor_efectivo_esperado == Decimal("15000")
    calc.assert_awaited_once()
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_endpoint_parcial_404_y_409() -> None:
    from fastapi import HTTPException

    from parkos_core.api.v1 import caja_arqueo as handler_mod
    from parkos_core.schemas.caja import EsperadoParcialQueryParams

    u = uuid_lib.uuid4()
    params = EsperadoParcialQueryParams(uuid_sesion=u)
    for exc, code in (
        (handler_mod.repo_arqueo.SesionNoEncontradaError(uuid_sesion=u), 404),
        (handler_mod.repo_arqueo.SesionYaCerradaError(uuid_sesion=u), 409),
    ):
        with (
            patch.object(
                handler_mod.repo_arqueo,
                "validar_sesion_abierta_para_arqueo",
                AsyncMock(side_effect=exc),
            ),
            pytest.raises(HTTPException) as ei,
        ):
            await handler_mod.get_arqueo_esperado_parcial(
                response=MagicMock(),
                params=params,
                session=MagicMock(),
                ctx=_ctx(),
                _claims=None,
            )
        assert ei.value.status_code == code
