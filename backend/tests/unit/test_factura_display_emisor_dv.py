"""FB3c: the invoice display header must carry the emisor NIT and the customer DV.

Live defect: ``datos_sucursal.nit`` printed as "NIT —" because the branch's
``sucursal.uuid_empresa`` is NULL and the LEFT JOIN to ``empresa`` yielded no
row. The display now falls back to the open empresa; and the persona jurídica
customer NIT carries its módulo-11 DV (it is not persisted on ``clientes``).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from parkos_core.api.v1._factura_display import (
    _dv_cliente_para_display,
    _empresa_de_sucursal,
)
from parkos_core.repo.nit_modulo11 import dv_esperado


class TestDvCliente:
    def test_nit_without_dv_gets_modulo11_dv(self) -> None:
        assert _dv_cliente_para_display("NIT", "900123456") == str(dv_esperado("900123456"))

    def test_nit_with_dots_is_normalised(self) -> None:
        assert _dv_cliente_para_display("NIT", "900.123.456") == str(dv_esperado("900123456"))

    def test_nit_already_carrying_dv_is_not_recomputed(self) -> None:
        assert _dv_cliente_para_display("NIT", "900123456-8") is None

    @pytest.mark.parametrize("tipo", ["CC", "CE", "pasaporte", None])
    def test_other_documents_have_no_dv(self, tipo: str | None) -> None:
        assert _dv_cliente_para_display(tipo, "12345678") is None

    @pytest.mark.parametrize("numero", [None, "", "abc", "123"])
    def test_unusable_numbers_yield_none(self, numero: str | None) -> None:
        assert _dv_cliente_para_display("NIT", numero) is None


def _session_returning(row: object | None) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.first.return_value = row
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


class TestEmpresaDeSucursal:
    @pytest.mark.asyncio
    async def test_keeps_the_joined_empresa(self) -> None:
        emp = SimpleNamespace(nit="900000000-5")
        session = _session_returning(SimpleNamespace(nit="otra"))
        assert await _empresa_de_sucursal(session, emp) is emp
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_the_open_empresa_when_sucursal_has_none(self) -> None:
        abierta = SimpleNamespace(nit="900000000-5", regimen="comun")
        session = _session_returning(abierta)
        assert await _empresa_de_sucursal(session, None) is abierta

    @pytest.mark.asyncio
    async def test_none_when_no_empresa_exists(self) -> None:
        assert await _empresa_de_sucursal(_session_returning(None), None) is None
