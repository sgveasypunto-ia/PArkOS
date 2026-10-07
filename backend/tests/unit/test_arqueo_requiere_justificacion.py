"""HU-F10.2 follow-up -- GET ``/arqueo/requiere-justificacion`` handler tests.

Bugfix (2026-10-01, cierre de turno): the FE's own diferencia guess
(against ``sesion.valor_inicial_*``) gave a false negative whenever the
session had any transactions -- the real esperado is server-side only
(``inicial + SUM(factura_pagos)``). This endpoint runs the same Step 5/6
diferencia check as ``post_arqueo`` and returns ONLY the boolean verdict
-- never the esperado amounts or the signed diferencia (conteo ciego,
plan.md HU-F10.2).

Pattern (mirrors ``test_arqueo_resumen.py``): DB-mock via ``MagicMock``
+ ``AsyncMock`` + ``patch.object``; the handler resolves
``params: RequiereJustificacionQueryParams = Depends()`` -- build a real
Pydantic instance with the required fields.
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
from parkos_core.schemas.caja import RequiereJustificacionQueryParams  # noqa: E402


def _make_ctx(*, sucursal_uuid: uuid_lib.UUID | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = sucursal_uuid or uuid_lib.uuid4()
    return ctx


def _new_response() -> MagicMock:
    r = MagicMock()
    r.headers = {}
    return r


@pytest.mark.asyncio
async def test_sin_diferencia_requiere_justificacion_false() -> None:
    """Reportado == esperado real (inicial + transacciones) -> False."""
    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    params = RequiereJustificacionQueryParams(
        uuid_sesion=uuid_lib.uuid4(),
        valor_efectivo_reportado=Decimal("150000"),
        valor_datafono_reportado=Decimal("30000"),
    )
    session = MagicMock()

    m_validar = AsyncMock(return_value=MagicMock())
    m_calcular_esperado = AsyncMock(return_value=Decimal("150000"))

    with (
        patch.object(handler_mod.repo_arqueo, "validar_sesion_abierta_para_arqueo", m_validar),
        patch.object(handler_mod.repo_arqueo, "calcular_esperado_sesion", m_calcular_esperado),
    ):
        result = await handler_mod.get_arqueo_requiere_justificacion(
            response=response,
            params=params,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    assert result.requiere_justificacion is False
    assert response.headers["Cache-Control"] == "no-store"
    # Conteo ciego: the response NEVER carries the esperado amounts.
    assert not hasattr(result, "esperado_efectivo")
    assert not hasattr(result, "valor_efectivo_esperado")


@pytest.mark.asyncio
async def test_con_diferencia_requiere_justificacion_true() -> None:
    """Reportado != esperado real (operador contó el fondo inicial, no el
    esperado real -- exactamente el bug real) -> True."""
    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    params = RequiereJustificacionQueryParams(
        uuid_sesion=uuid_lib.uuid4(),
        valor_efectivo_reportado=Decimal("100000"),  # inicial, NOT esperado real
        valor_datafono_reportado=Decimal("0"),
    )
    session = MagicMock()

    m_validar = AsyncMock(return_value=MagicMock())
    # esperado real = inicial (100000) + transacciones del turno (50000).
    m_calcular_esperado = AsyncMock(return_value=Decimal("150000"))

    with (
        patch.object(handler_mod.repo_arqueo, "validar_sesion_abierta_para_arqueo", m_validar),
        patch.object(handler_mod.repo_arqueo, "calcular_esperado_sesion", m_calcular_esperado),
    ):
        result = await handler_mod.get_arqueo_requiere_justificacion(
            response=response,
            params=params,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    assert result.requiere_justificacion is True


@pytest.mark.asyncio
async def test_sesion_no_encontrada_404() -> None:
    """Sesion inexistente (o de otra sucursal -- mismo filtro V4) -> 404."""
    from fastapi import HTTPException
    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    uuid_sesion = uuid_lib.uuid4()
    params = RequiereJustificacionQueryParams(
        uuid_sesion=uuid_sesion,
        valor_efectivo_reportado=Decimal("0"),
        valor_datafono_reportado=Decimal("0"),
    )
    session = MagicMock()

    m_validar = AsyncMock(
        side_effect=handler_mod.repo_arqueo.SesionNoEncontradaError(uuid_sesion=uuid_sesion)
    )

    with (
        patch.object(handler_mod.repo_arqueo, "validar_sesion_abierta_para_arqueo", m_validar),
        pytest.raises(HTTPException) as exc_info,
    ):
        await handler_mod.get_arqueo_requiere_justificacion(
            response=response,
            params=params,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "sesion_no_encontrada"


@pytest.mark.asyncio
async def test_sesion_ya_cerrada_409() -> None:
    """Sesion ya cerrada -> 409 (mismo mapeo que post_arqueo Step 4)."""
    from fastapi import HTTPException
    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    uuid_sesion = uuid_lib.uuid4()
    params = RequiereJustificacionQueryParams(
        uuid_sesion=uuid_sesion,
        valor_efectivo_reportado=Decimal("0"),
        valor_datafono_reportado=Decimal("0"),
    )
    session = MagicMock()

    m_validar = AsyncMock(
        side_effect=handler_mod.repo_arqueo.SesionYaCerradaError(uuid_sesion=uuid_sesion)
    )

    with (
        patch.object(handler_mod.repo_arqueo, "validar_sesion_abierta_para_arqueo", m_validar),
        pytest.raises(HTTPException) as exc_info,
    ):
        await handler_mod.get_arqueo_requiere_justificacion(
            response=response,
            params=params,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "sesion_ya_cerrada"
