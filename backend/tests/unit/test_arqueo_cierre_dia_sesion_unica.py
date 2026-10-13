"""b-cd-sesion -- cierre_dia solo procede con UNA unica sesion abierta, la propia.

Defensa en profundidad del handler POST /caja/arqueo (el FE ya deshabilita
el boton): 0 abiertas, 1 ajena o 2+ abiertas -> 409 sin tocar nada.
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
from fastapi import HTTPException  # noqa: E402


def _sesion(uuid_usuario: uuid_lib.UUID) -> MagicMock:
    s = MagicMock()
    s.uuid = uuid_lib.uuid4()
    s.uuid_usuario = uuid_usuario
    return s


async def _post(abiertas_factory):
    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = uuid_lib.uuid4()
    payload = MagicMock()
    payload.uuid_tipo_arqueo = uuid_lib.uuid4()
    payload.uuid_sesion = None
    payload.valor_efectivo_reportado = Decimal("100000")
    payload.justificacion = None
    session = MagicMock()
    session.commit = AsyncMock()
    tipo = MagicMock(uuid=uuid_lib.uuid4(), codigo="cierre_dia")
    arqueo = MagicMock(uuid=uuid_lib.uuid4())
    m_insertar = AsyncMock(return_value=arqueo)
    m_cerrar = AsyncMock(return_value=1)
    m_abiertas = AsyncMock(return_value=abiertas_factory(ctx.actor_uuid))
    with patch.object(handler_mod.repo_arqueo, "resolver_tipo_arqueo_por_uuid", AsyncMock(return_value=tipo)), \
         patch.object(handler_mod.repo_arqueo, "resolver_tolerancia_vigente", AsyncMock(return_value=MagicMock(tolerancia_efectivo=Decimal("100")))), \
         patch.object(handler_mod.repo_arqueo, "listar_sesiones_abiertas_del_dia", m_abiertas), \
         patch.object(handler_mod.repo_arqueo, "calcular_esperado_cierre_dia", AsyncMock(return_value=Decimal("100000"))), \
         patch.object(handler_mod.repo_arqueo, "insertar_arqueo", m_insertar), \
         patch.object(handler_mod.repo_arqueo, "cerrar_sesiones_del_dia_bulk", m_cerrar):
        try:
            await handler_mod.post_arqueo(
                response=MagicMock(headers={}),
                payload=payload,
                session=session,
                ctx=ctx,
                _claims=None,
            )
            exc = None
        except HTTPException as e:
            exc = e
    return exc, m_insertar, m_cerrar, session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("factory", "motivo", "n"),
    [
        (lambda me: [], "sin_sesion_abierta", 0),
        (lambda me: [_sesion(uuid_lib.uuid4())], "sesion_ajena", 1),
        (lambda me: [_sesion(me), _sesion(uuid_lib.uuid4())], "varias_sesiones_abiertas", 2),
        (lambda me: [_sesion(me), _sesion(me)], "varias_sesiones_abiertas", 2),
    ],
)
async def test_cierre_dia_rechazado_si_no_es_unica_sesion_propia(factory, motivo, n) -> None:
    exc, m_insertar, m_cerrar, session = await _post(factory)

    assert exc is not None
    assert exc.status_code == 409
    assert exc.detail["error"] == "cierre_dia_requiere_sesion_propia_unica"
    assert exc.detail["motivo"] == motivo
    assert exc.detail["abiertas"] == n
    m_insertar.assert_not_awaited()
    m_cerrar.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_cierre_dia_permitido_con_una_unica_sesion_propia() -> None:
    exc, m_insertar, m_cerrar, session = await _post(lambda me: [_sesion(me)])

    assert exc is None
    m_insertar.assert_awaited_once()
    m_cerrar.assert_awaited_once()
    session.commit.assert_awaited_once()
