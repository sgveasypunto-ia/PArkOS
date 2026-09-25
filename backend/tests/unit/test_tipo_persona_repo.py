"""Ajuste identificación persona natural/empresa -- unit tests for
``repo.tipo_persona.resolve_uuid_tipo_persona``.

Mock-everything pattern (no live DB), mirrors
``test_venta_suscripcion_repo.py``.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402


def _session_returning(uuid_value: uuid_lib.UUID | None) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = uuid_value
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_resolve_uuid_tipo_persona_nit_queries_juridica() -> None:
    """``NIT`` maps to the ``juridica`` tipo_persona catalog row."""
    from parkos_core.repo.tipo_persona import resolve_uuid_tipo_persona

    expected = uuid_lib.uuid4()
    session = _session_returning(expected)

    result = await resolve_uuid_tipo_persona(session, tipo_identificador="NIT")

    assert result == expected
    stmt = session.execute.call_args[0][0]
    assert "tipo_persona" in str(stmt)
    assert "juridica" in str(stmt.compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.parametrize("tipo_identificador", ["CC", "CE", "pasaporte"])
@pytest.mark.asyncio
async def test_resolve_uuid_tipo_persona_documento_natural_queries_natural(
    tipo_identificador: str,
) -> None:
    """``CC``/``CE``/``pasaporte`` all map to the ``natural`` catalog row."""
    from parkos_core.repo.tipo_persona import resolve_uuid_tipo_persona

    expected = uuid_lib.uuid4()
    session = _session_returning(expected)

    result = await resolve_uuid_tipo_persona(
        session, tipo_identificador=tipo_identificador
    )

    assert result == expected
    stmt = session.execute.call_args[0][0]
    assert "natural" in str(stmt.compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.asyncio
async def test_resolve_uuid_tipo_persona_none_when_tipo_identificador_falsy() -> None:
    """``None``/empty ``tipo_identificador`` short-circuits without querying."""
    from parkos_core.repo.tipo_persona import resolve_uuid_tipo_persona

    session = MagicMock()
    session.execute = AsyncMock()

    result = await resolve_uuid_tipo_persona(session, tipo_identificador=None)

    assert result is None
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_uuid_tipo_persona_none_when_catalog_not_seeded() -> None:
    """No vigente/activo row for the resolved ``tipo`` -> ``None``, not an error."""
    from parkos_core.repo.tipo_persona import resolve_uuid_tipo_persona

    session = _session_returning(None)

    result = await resolve_uuid_tipo_persona(session, tipo_identificador="CC")

    assert result is None
