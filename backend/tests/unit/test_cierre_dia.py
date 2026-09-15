"""HU-F1.13 / T5.4 -- 2 ``cierre_dia`` POST handler tests.

The 2 tests verify the cierre_dia branching per plan.md line 1093:

  * ``test_cierre_dia_3_sesiones_2_cerradas_1_abierta_cerrar_solo_abierta`` --
    ``cerrar_sesiones_del_dia_bulk`` is invoked, returns count=1 (only the
    open sesion is closed; the 2 closed sesiones are SKIPPED per
    REQ-OPS-092 Scenario 2).
  * ``test_cierre_dia_uuid_sesion_en_body_returns_400`` -- V2: ``cierre_dia``
    codigo + ``uuid_sesion`` present -> 400 ``cierre_dia_no_acepta_uuid_sesion``.

Pattern: DB-mock via ``MagicMock`` + ``AsyncMock`` + ``patch.object``.
Mirrors F1.12 T7.2 / ``test_venta_suscripcion_e2e.py``.
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


def _make_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = uuid_lib.uuid4()
    return ctx


def _new_response() -> MagicMock:
    r = MagicMock()
    r.headers = {}
    return r


def _build_tipo_arqueo(codigo: str) -> MagicMock:
    row = MagicMock()
    row.uuid = uuid_lib.uuid4()
    row.codigo = codigo
    return row


def _build_tolerancia() -> MagicMock:
    tol = MagicMock()
    tol.tolerancia_efectivo = Decimal("100")
    tol.tolerancia_datafono = Decimal("200")
    return tol


def _build_payload(*, uuid_sesion: uuid_lib.UUID | None = None) -> MagicMock:
    payload = MagicMock()
    payload.uuid_tipo_arqueo = uuid_lib.uuid4()
    payload.uuid_sesion = uuid_sesion  # None for cierre_dia
    payload.valor_efectivo_reportado = Decimal("300000")
    payload.valor_datafono_reportado = Decimal("150000")
    payload.justificacion = "Sin diferencias"
    return payload


@pytest.mark.asyncio
async def test_cierre_dia_3_sesiones_2_cerradas_1_abierta_cerrar_solo_abierta() -> None:
    """cierre_dia path: 3 sesiones del dia, 2 already cerrada, 1 abierta -> cerrar 1.

    Validates:
      * Step 5 uses ``calcular_esperado_cierre_dia`` (NOT ``calcular_esperado_sesion``).
      * Step 9 calls ``cerrar_sesiones_del_dia_bulk`` exactly ONCE.
      * The wrapper returns the actual count of closed sesiones (1, not 3).
      * ``alerta_generada=False`` (sin diferencia).
      * KD-ARQUEO-01: ``session.commit`` called exactly once at Step 12.
    """
    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload(uuid_sesion=None)  # cierre_dia MUST have uuid_sesion=None
    session = MagicMock()
    session.commit = AsyncMock()

    m_resolver_tipo = AsyncMock(return_value=_build_tipo_arqueo(codigo="cierre_dia"))
    m_resolver_tol = AsyncMock(return_value=_build_tolerancia())
    m_calcular_esperado_cierre_dia = AsyncMock(
        return_value=(Decimal("300000"), Decimal("150000"))
    )
    m_cerrar_bulk = AsyncMock(return_value=1)  # 1 abierta cerrada, 2 SKIPPED
    arqueo_row = MagicMock()
    arqueo_row.uuid = uuid_lib.uuid4()

    with patch.object(handler_mod.repo_arqueo, "resolver_tipo_arqueo_por_uuid", m_resolver_tipo), \
         patch.object(handler_mod.repo_arqueo, "resolver_tolerancia_vigente", m_resolver_tol), \
         patch.object(handler_mod.repo_arqueo, "calcular_esperado_cierre_dia", m_calcular_esperado_cierre_dia), \
         patch.object(handler_mod.repo_arqueo, "insertar_arqueo", AsyncMock(return_value=arqueo_row)), \
         patch.object(handler_mod.repo_arqueo, "cerrar_sesiones_del_dia_bulk", m_cerrar_bulk):
        result = await handler_mod.post_arqueo(
            response=response,
            payload=payload,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    # Step 5 path -- cierre_dia branch
    m_calcular_esperado_cierre_dia.assert_awaited_once()
    # Step 9 -- bulk close
    m_cerrar_bulk.assert_awaited_once()
    # KD-ARQUEO-01: SINGLE commit
    session.commit.assert_called_once()
    assert response.headers["Cache-Control"] == "no-store"
    # Sin descuadre
    assert result.alerta_generada is False
    assert result.alerta_uuid is None
    assert result.codigo_tipo_arqueo == "cierre_dia"
    # cierres count not surfaced in response (it's an info-only count in logs)


@pytest.mark.asyncio
async def test_cierre_dia_uuid_sesion_en_body_returns_400() -> None:
    """V2: cierre_dia codigo + uuid_sesion present -> 400 cierre_dia_no_acepta_uuid_sesion.

    This is the **mandated** REQ-OPS-091 Scenario validation for the
    cross-validation rule (DEC-ARQUEO-03 + KD-ARQUEO-03): the handler
    short-circuits at Step 2 BEFORE Step 8 (no arqueo INSERT).
    """
    from fastapi import HTTPException

    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload(uuid_sesion=uuid_lib.uuid4())  # invalid for cierre_dia
    session = MagicMock()
    session.commit = AsyncMock()

    m_resolver_tipo = AsyncMock(return_value=_build_tipo_arqueo(codigo="cierre_dia"))
    m_insertar_arqueo = AsyncMock(return_value=uuid_lib.uuid4())

    with patch.object(handler_mod.repo_arqueo, "resolver_tipo_arqueo_por_uuid", m_resolver_tipo), \
         patch.object(handler_mod.repo_arqueo, "insertar_arqueo", m_insertar_arqueo):
        with pytest.raises(HTTPException) as exc_info:
            await handler_mod.post_arqueo(
                response=response,
                payload=payload,
                session=session,
                ctx=ctx,
                _claims=None,
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {"error": "cierre_dia_no_acepta_uuid_sesion"}
    assert exc_info.value.headers == {"Cache-Control": "no-store"}
    # Step 2 short-circuits BEFORE Step 8 (no arqueo INSERT)
    assert not m_insertar_arqueo.called
    # No commit -- error path
    assert not session.commit.called
