"""Defecto 7.7 -- la busqueda por identificacion debe ignorar mayusculas/espacios.

``Clientes.numero_identificacion == :param`` era case-sensitive: un
documento alfanumerico (CE/pasaporte) guardado como ``AB123`` no se
encontraba al buscar ``ab123``. El helper ``repo.busqueda`` normaliza el
termino (trim + casefold) y compara contra ``lower(trim(columna))``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from parkos_core.models.V.clientes import Clientes
from parkos_core.repo import cupos_subscripcion
from parkos_core.repo.busqueda import coincide_ci, normalizar_termino


def _sql(expr) -> tuple[str, dict]:
    c = expr.compile(dialect=postgresql.dialect())
    return str(c), c.params


def test_normalizar_termino_trim_y_casefold() -> None:
    assert normalizar_termino("  Juan PEREZ ") == "juan perez"
    assert normalizar_termino("AB-123x") == "ab-123x"
    assert normalizar_termino(None) == ""
    assert normalizar_termino("   ") == ""


def test_coincide_ci_compara_lower_trim_de_la_columna() -> None:
    sql, params = _sql(coincide_ci(Clientes.numero_identificacion, "  AB123x "))
    assert "lower(trim(" in sql
    assert list(params.values()) == ["ab123x"]


@pytest.mark.asyncio
async def test_buscar_por_identificacion_normaliza_en_la_query() -> None:
    session = MagicMock()
    result = MagicMock()
    result.first.return_value = None
    session.execute = AsyncMock(return_value=result)

    out = await cupos_subscripcion.buscar_subscripcion_activa_por_identificacion(
        session, numero_identificacion="  ab123X "
    )

    assert out is None
    stmt = session.execute.await_args.args[0]
    sql, params = _sql(stmt)
    assert "lower(trim(clientes.numero_identificacion))" in sql.replace("prod.", "")
    assert "ab123x" in params.values()
    assert "  ab123X " not in params.values()
