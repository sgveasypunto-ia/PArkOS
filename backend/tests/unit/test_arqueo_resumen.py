"""HU-F1.13 / T5.4 -- 3 GET ``/arqueo/resumen`` handler tests.

The 3 tests cover the 6-step read chain (REQ-OPS-097):

  * ``test_resumen_3_sesiones_con_cierre_dia_returns_combined`` --
    3 sesiones + 1 cierre_dia arqueo -> ArqueoResumenRead with both lists.
  * ``test_resumen_sin_cierre_dia_returns_cierre_dia_none`` --
    0 cierre_dia arqueo -> ``cierre_dia=None``.
  * ``test_resumen_dia_vacio_returns_sesiones_empty`` --
    0 sesiones + 0 cierre_dia -> ``sesiones=[]``, ``cierre_dia=None`` (Scenario 3).

Pattern: DB-mock via ``MagicMock`` + ``AsyncMock`` + ``patch.object``.
The handler resolves ``params: CierreDiarioQueryParams = Depends()`` --
we build a real Pydantic instance with the required fields.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import date as date_cls
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402

from parkos_core.schemas.caja import CierreDiarioQueryParams  # noqa: E402


def _make_ctx(*, sucursal_uuid: uuid_lib.UUID | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.issuer_prefix = "admin-"  # admin bypasses cross-branch tenant check
    ctx.sucursal_uuid = sucursal_uuid or uuid_lib.uuid4()
    return ctx


def _new_response() -> MagicMock:
    r = MagicMock()
    r.headers = {}
    return r


def _build_sesion_row(*, uuid_sesion: uuid_lib.UUID | None = None) -> MagicMock:
    row = MagicMock()
    row.uuid = uuid_sesion or uuid_lib.uuid4()
    row.uuid_usuario = uuid_lib.uuid4()
    row.timestamp_apertura = MagicMock()
    row.timestamp_cierre = MagicMock()
    row.estado = "cerrada"
    return row


def _resumen_dict_for(sesion_uuid: uuid_lib.UUID | None = None) -> dict:
    return {
        "uuid_sesion": sesion_uuid,
        "uuid_usuario": uuid_lib.uuid4(),
        "timestamp_apertura": "2026-09-15T08:00:00",
        "timestamp_cierre": "2026-09-15T20:00:00",
        "estado": "cerrada",
        "valor_efectivo_esperado": Decimal("100000"),
        "valor_datafono_esperado": Decimal("50000"),
        "valor_efectivo_reportado": Decimal("100000"),
        "valor_datafono_reportado": Decimal("50000"),
        "uuid_arqueo": uuid_lib.uuid4(),
    }


@pytest.mark.asyncio
async def test_resumen_3_sesiones_con_cierre_dia_returns_combined() -> None:
    """3 sesiones + 1 cierre_dia arqueo -> ArqueoResumenRead with both populated."""
    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    sucursal = ctx.sucursal_uuid
    params = CierreDiarioQueryParams(uuid_sucursal=sucursal, fecha=date_cls(2026, 9, 15))
    session = MagicMock()
    session.commit = AsyncMock()

    sesiones = [_build_sesion_row() for _ in range(3)]
    cierre_dia_dict = _resumen_dict_for(sesion_uuid=None)  # cierre_dia has uuid_sesion=None

    m_listar = AsyncMock(return_value=sesiones)
    m_construir = AsyncMock(side_effect=[_resumen_dict_for(s.uuid) for s in sesiones])
    m_obtener = AsyncMock(return_value=cierre_dia_dict)

    with patch.object(handler_mod.repo_arqueo, "listar_sesiones_del_dia", m_listar), \
         patch.object(handler_mod.repo_arqueo, "construir_resumen_sesion", m_construir), \
         patch.object(handler_mod.repo_arqueo, "obtener_cierre_dia_del_dia", m_obtener):
        result = await handler_mod.get_arqueo_resumen(
            response=response,
            params=params,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    m_listar.assert_awaited_once()
    assert m_construir.await_count == 3
    m_obtener.assert_awaited_once()
    # DEC-ARQUEO-06: no-store
    assert response.headers["Cache-Control"] == "no-store"
    # Combined: 3 sesiones + 1 cierre_dia
    assert len(result.sesiones) == 3
    assert result.cierre_dia is not None
    assert result.cierre_dia.uuid_sesion is None  # DEC-ARQUEO-03
    assert result.fecha == date_cls(2026, 9, 15)
    assert result.uuid_sucursal == sucursal


@pytest.mark.asyncio
async def test_resumen_sin_cierre_dia_returns_cierre_dia_none() -> None:
    """0 cierre_dia arqueo -> ``cierre_dia=None``, sesiones still populated."""
    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    sucursal = ctx.sucursal_uuid
    params = CierreDiarioQueryParams(uuid_sucursal=sucursal, fecha=date_cls(2026, 9, 15))
    session = MagicMock()
    session.commit = AsyncMock()

    sesiones = [_build_sesion_row() for _ in range(2)]

    m_listar = AsyncMock(return_value=sesiones)
    m_construir = AsyncMock(side_effect=[_resumen_dict_for(s.uuid) for s in sesiones])
    m_obtener = AsyncMock(return_value=None)  # NO cierre_dia for date

    with patch.object(handler_mod.repo_arqueo, "listar_sesiones_del_dia", m_listar), \
         patch.object(handler_mod.repo_arqueo, "construir_resumen_sesion", m_construir), \
         patch.object(handler_mod.repo_arqueo, "obtener_cierre_dia_del_dia", m_obtener):
        result = await handler_mod.get_arqueo_resumen(
            response=response,
            params=params,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    assert len(result.sesiones) == 2
    assert result.cierre_dia is None


@pytest.mark.asyncio
async def test_resumen_dia_vacio_returns_sesiones_empty() -> None:
    """0 sesiones + 0 cierre_dia -> sesiones=[], cierre_dia=None (REQ-OPS-097 Scenario 3)."""
    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    sucursal = ctx.sucursal_uuid
    params = CierreDiarioQueryParams(uuid_sucursal=sucursal, fecha=date_cls(2026, 9, 15))
    session = MagicMock()
    session.commit = AsyncMock()

    m_listar = AsyncMock(return_value=[])
    m_obtener = AsyncMock(return_value=None)

    with patch.object(handler_mod.repo_arqueo, "listar_sesiones_del_dia", m_listar), \
         patch.object(handler_mod.repo_arqueo, "obtener_cierre_dia_del_dia", m_obtener):
        result = await handler_mod.get_arqueo_resumen(
            response=response,
            params=params,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    assert result.sesiones == []
    assert result.cierre_dia is None
    assert result.fecha == date_cls(2026, 9, 15)
    assert response.headers["Cache-Control"] == "no-store"
    # No m_construir called (no sesiones to iterate over)
