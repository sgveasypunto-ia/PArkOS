"""D4 follow-up: ``calcular_esperado_cierre_dia`` must include the opening
cash (``valor_inicial_efectivo``) of the day's sesiones, exactly like
``calcular_esperado_sesion`` does per session (REQ-OPS-194:
``valor_inicial_efectivo + SUM(pagos efectivo)`` aggregated for the day).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from parkos_core.repo import arqueo as repo_arqueo


@pytest.mark.asyncio
async def test_esperado_cierre_dia_suma_base_de_las_sesiones_mas_pagos_efectivo() -> None:
    session = MagicMock()
    result = MagicMock()
    result.scalar_one.return_value = Decimal("150000")  # SUM(valor_inicial_efectivo)
    session.execute = AsyncMock(return_value=result)

    with patch.object(
        repo_arqueo,
        "_sum_factura_pagos_by_medio_pago",
        new=AsyncMock(return_value=Decimal("1500")),
    ):
        esperado = await repo_arqueo.calcular_esperado_cierre_dia(
            session, uuid_sucursal=uuid_lib.uuid4(), fecha=date(2026, 10, 7)
        )

    assert esperado == Decimal("151500")
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_esperado_cierre_dia_sin_sesiones_es_cero() -> None:
    session = MagicMock()
    result = MagicMock()
    result.scalar_one.return_value = 0
    session.execute = AsyncMock(return_value=result)
    with patch.object(
        repo_arqueo, "_sum_factura_pagos_by_medio_pago", new=AsyncMock(return_value=Decimal("0"))
    ):
        esperado = await repo_arqueo.calcular_esperado_cierre_dia(
            session, uuid_sucursal=uuid_lib.uuid4(), fecha=date(2026, 10, 7)
        )
    assert esperado == Decimal("0")
