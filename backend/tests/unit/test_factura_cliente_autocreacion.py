"""H2 regression: facturar con datos propios crea la persona natural si falta.

Pre-fix, ``buscar_o_crear_cliente_por_nit`` solo buscaba y los handlers
devolvian 404 ``cliente_no_encontrado`` cuando la persona natural no estaba
en ``prod.clientes`` (mock-everything, sin DB).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_PARKOS_CORE_SRC = Path(__file__).resolve().parents[2] / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402


def _session_with_lookup(row: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _datos() -> MagicMock:
    datos = MagicMock()
    datos.model_dump.return_value = {
        "tipo_identificador": "CC",
        "numero_identificacion": "1234567890",
        "dv": None,
        "nombre": "Juan",
        "apellido": "Perez",
        "email": None,
        "telefono": None,
    }
    return datos


@pytest.mark.asyncio
async def test_crea_cliente_cuando_no_existe() -> None:
    from parkos_core.repo import factura as repo_factura
    from parkos_core.repo import venta_suscripcion as repo_venta

    nuevo = MagicMock()
    actor = uuid_lib.uuid4()
    session = _session_with_lookup(None)

    with patch.object(
        repo_venta,
        "buscar_cliente_por_uuid_o_crear_nuevo",
        new=AsyncMock(return_value=nuevo),
    ) as mock_crear:
        result = await repo_factura.buscar_o_crear_cliente_por_nit(
            session,
            tipo_identificador="CC",
            numero_identificacion="1234567890",
            datos=_datos(),
            actor_uuid=actor,
        )

    assert result is nuevo
    mock_crear.assert_awaited_once()
    kwargs = mock_crear.call_args.kwargs
    assert kwargs["actor_uuid"] == actor
    assert kwargs["datos_cliente"]["numero_identificacion"] == "1234567890"
    assert kwargs["datos_cliente"]["nombre"] == "Juan"


@pytest.mark.asyncio
async def test_reutiliza_cliente_existente_sin_crear() -> None:
    from parkos_core.repo import factura as repo_factura
    from parkos_core.repo import venta_suscripcion as repo_venta

    existente = MagicMock()
    session = _session_with_lookup(existente)

    with patch.object(
        repo_venta, "buscar_cliente_por_uuid_o_crear_nuevo", new=AsyncMock()
    ) as mock_crear:
        result = await repo_factura.buscar_o_crear_cliente_por_nit(
            session,
            tipo_identificador="CC",
            numero_identificacion="1234567890",
            datos=_datos(),
            actor_uuid=uuid_lib.uuid4(),
        )

    assert result is existente
    mock_crear.assert_not_awaited()


@pytest.mark.asyncio
async def test_sin_datos_y_sin_fila_devuelve_none() -> None:
    from parkos_core.repo import factura as repo_factura

    result = await repo_factura.buscar_o_crear_cliente_por_nit(
        _session_with_lookup(None),
        tipo_identificador="CC",
        numero_identificacion="1234567890",
        datos=None,
        actor_uuid=uuid_lib.uuid4(),
    )
    assert result is None
