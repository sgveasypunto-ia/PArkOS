"""HU-F1.13 / T5.4 -- 4 MANDATED POST handler unit tests + 4 extra asymmetry tests.

The 4 mandated tests per plan.md line 1093:

  * ``test_arqueo_sin_diferencia_201`` -- happy path, sin diferencia.
  * ``test_arqueo_diferencia_justificada_201`` -- diferencia + justificacion.
  * ``test_arqueo_descuadre_sobre_tolerancia_201_con_alerta`` -- descuadre critico.
  * ``test_arqueo_diferencia_sin_justificacion_400`` -- 400 justificacion_requerida.

Plus 4 extra tests for asymmetry / no-store header / cross-branch.

Pattern (F1.12 T7.2 / ``test_venta_suscripcion_e2e.py``): mock all repo
helpers + DB-mock session with ``AsyncMock`` for ``session.commit``.
DB-mock pattern is the F1.12 standard (Docker unavailable).
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


def _make_ctx(*, sucursal_uuid: uuid_lib.UUID | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = sucursal_uuid or uuid_lib.uuid4()
    ctx.actor_rol = "operador"
    return ctx


def _new_response() -> MagicMock:
    r = MagicMock()
    r.headers = {}
    return r


def _build_payload(
    *,
    codigo: str = "auditoria",
    uuid_sesion: uuid_lib.UUID | None = None,
    valor_efectivo: Decimal = Decimal("100000"),
    valor_datafono: Decimal = Decimal("50000"),
    justificacion: str | None = None,
) -> MagicMock:
    payload = MagicMock()
    payload.uuid_tipo_arqueo = uuid_lib.uuid4()
    payload.uuid_sesion = uuid_sesion or uuid_lib.uuid4()
    payload.valor_efectivo_reportado = valor_efectivo
    payload.valor_datafono_reportado = valor_datafono
    payload.justificacion = justificacion
    return payload


def _build_arqueo_row() -> MagicMock:
    """Mock Arqueo ORM row -- the handler reads ``.uuid`` from this."""
    row = MagicMock()
    row.uuid = uuid_lib.uuid4()
    return row


def _build_alerta_row() -> MagicMock:
    """Mock Alerta ORM row -- the handler reads ``.uuid`` from this."""
    row = MagicMock()
    row.uuid = uuid_lib.uuid4()
    return row


def _build_tipo_arqueo(*, codigo: str) -> MagicMock:
    row = MagicMock()
    row.uuid = uuid_lib.uuid4()
    row.codigo = codigo
    row.vigente_hasta = None
    row.estado = "activo"
    return row


def _build_tolerancia(
    *,
    tol_efectivo: Decimal = Decimal("100"),
    tol_datafono: Decimal = Decimal("200"),
) -> MagicMock:
    tol = MagicMock()
    tol.tolerancia_efectivo = tol_efectivo
    tol.tolerancia_datafono = tol_datafono
    return tol


# ---------------------------------------------------------------------------
# T5.4 -- 4 MANDATED handler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_arqueo_sin_diferencia_201() -> None:
    """MANDATED T5.4 T1 (plan.md line 1093): sin diferencia -> 201, sin alerta."""
    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload(
        codigo="auditoria",
        valor_efectivo=Decimal("148000"),
        valor_datafono=Decimal("320000"),
        justificacion=None,
    )
    session = MagicMock()
    session.commit = AsyncMock()

    m_resolver_tipo = AsyncMock(return_value=_build_tipo_arqueo(codigo="auditoria"))
    m_resolver_tol = AsyncMock(return_value=_build_tolerancia())
    m_validar_sesion = AsyncMock(return_value=MagicMock())
    m_calcular_esperado = AsyncMock(return_value=(Decimal("148000"), Decimal("320000")))
    m_insertar_arqueo = AsyncMock(return_value=_build_arqueo_row())
    m_cerrar_sesiones = AsyncMock(return_value=0)
    m_insertar_alerta = AsyncMock(return_value=_build_alerta_row())

    with patch.object(handler_mod.repo_arqueo, "resolver_tipo_arqueo_por_uuid", m_resolver_tipo), \
         patch.object(handler_mod.repo_arqueo, "resolver_tolerancia_vigente", m_resolver_tol), \
         patch.object(handler_mod.repo_arqueo, "validar_sesion_abierta_para_arqueo", m_validar_sesion), \
         patch.object(handler_mod.repo_arqueo, "calcular_esperado_sesion", m_calcular_esperado), \
         patch.object(handler_mod.repo_arqueo, "insertar_arqueo", m_insertar_arqueo), \
         patch.object(handler_mod.repo_arqueo, "cerrar_sesiones_del_dia_bulk", m_cerrar_sesiones), \
         patch.object(handler_mod.repo_arqueo, "insertar_alerta_descuadre_critico", m_insertar_alerta):
        result = await handler_mod.post_arqueo(
            response=response,
            payload=payload,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    # KD-ARQUEO-01: SINGLE COMMIT
    session.commit.assert_called_once()
    # DEC-ARQUEO-06: Cache-Control: no-store
    assert response.headers["Cache-Control"] == "no-store"
    # Sin diferencia -> alerta_generada=false, alerta_uuid=None
    assert result.alerta_generada is False
    assert result.alerta_uuid is None
    # Alerta helper NOT called (es_critico=False)
    assert not m_insertar_alerta.called
    # cierre_dia path NOT taken (codigo=auditoria)
    assert not m_cerrar_sesiones.called


@pytest.mark.asyncio
async def test_arqueo_diferencia_justificada_201() -> None:
    """MANDATED T5.4 T2: diferencia justificada (dentro tolerancia) -> 201, sin alerta."""
    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload(
        codigo="cierre_turno",
        valor_efectivo=Decimal("100050"),  # diferencia=50 dentro de tolerancia 100
        valor_datafono=Decimal("50000"),
        justificacion="Vueltos",
    )
    session = MagicMock()
    session.commit = AsyncMock()

    m_resolver_tipo = AsyncMock(return_value=_build_tipo_arqueo(codigo="cierre_turno"))
    m_resolver_tol = AsyncMock(return_value=_build_tolerancia())
    m_validar_sesion = AsyncMock(return_value=MagicMock())
    m_calcular_esperado = AsyncMock(return_value=(Decimal("100000"), Decimal("50000")))
    m_insertar_arqueo = AsyncMock(return_value=_build_arqueo_row())
    m_cerrar_sesiones = AsyncMock(return_value=0)
    m_insertar_alerta = AsyncMock(return_value=_build_alerta_row())

    with patch.object(handler_mod.repo_arqueo, "resolver_tipo_arqueo_por_uuid", m_resolver_tipo), \
         patch.object(handler_mod.repo_arqueo, "resolver_tolerancia_vigente", m_resolver_tol), \
         patch.object(handler_mod.repo_arqueo, "validar_sesion_abierta_para_arqueo", m_validar_sesion), \
         patch.object(handler_mod.repo_arqueo, "calcular_esperado_sesion", m_calcular_esperado), \
         patch.object(handler_mod.repo_arqueo, "insertar_arqueo", m_insertar_arqueo), \
         patch.object(handler_mod.repo_arqueo, "cerrar_sesiones_del_dia_bulk", m_cerrar_sesiones), \
         patch.object(handler_mod.repo_arqueo, "insertar_alerta_descuadre_critico", m_insertar_alerta):
        result = await handler_mod.post_arqueo(
            response=response,
            payload=payload,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    session.commit.assert_called_once()
    assert response.headers["Cache-Control"] == "no-store"
    assert result.alerta_generada is False
    assert result.alerta_uuid is None
    # diferencia = 50, dentro de tolerancia (100), no alerta
    assert not m_insertar_alerta.called


@pytest.mark.asyncio
async def test_arqueo_descuadre_sobre_tolerancia_201_con_alerta() -> None:
    """MANDATED T5.4 T3: descuadre > tolerancia -> 201 + alerta_generada=true."""
    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload(
        codigo="cierre_turno",
        valor_efectivo=Decimal("100150"),  # diferencia=150 > tolerancia_efectivo=100
        valor_datafono=Decimal("50000"),
        justificacion="Vueltos",
    )
    session = MagicMock()
    session.commit = AsyncMock()

    alerta_uuid = uuid_lib.uuid4()
    alerta_row = MagicMock()
    alerta_row.uuid = alerta_uuid
    m_resolver_tipo = AsyncMock(return_value=_build_tipo_arqueo(codigo="cierre_turno"))
    m_resolver_tol = AsyncMock(return_value=_build_tolerancia())
    m_validar_sesion = AsyncMock(return_value=MagicMock())
    m_calcular_esperado = AsyncMock(return_value=(Decimal("100000"), Decimal("50000")))
    m_insertar_arqueo = AsyncMock(return_value=_build_arqueo_row())
    m_cerrar_sesiones = AsyncMock(return_value=0)
    m_insertar_alerta = AsyncMock(return_value=alerta_row)

    with patch.object(handler_mod.repo_arqueo, "resolver_tipo_arqueo_por_uuid", m_resolver_tipo), \
         patch.object(handler_mod.repo_arqueo, "resolver_tolerancia_vigente", m_resolver_tol), \
         patch.object(handler_mod.repo_arqueo, "validar_sesion_abierta_para_arqueo", m_validar_sesion), \
         patch.object(handler_mod.repo_arqueo, "calcular_esperado_sesion", m_calcular_esperado), \
         patch.object(handler_mod.repo_arqueo, "insertar_arqueo", m_insertar_arqueo), \
         patch.object(handler_mod.repo_arqueo, "cerrar_sesiones_del_dia_bulk", m_cerrar_sesiones), \
         patch.object(handler_mod.repo_arqueo, "insertar_alerta_descuadre_critico", m_insertar_alerta):
        result = await handler_mod.post_arqueo(
            response=response,
            payload=payload,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    session.commit.assert_called_once()
    assert result.alerta_generada is True
    assert result.alerta_uuid == alerta_uuid
    assert m_insertar_alerta.called
    assert m_insertar_alerta.await_count == 1


@pytest.mark.asyncio
async def test_arqueo_diferencia_sin_justificacion_400() -> None:
    """MANDATED T5.4 T4: diferencia + sin justificacion -> 400 justificacion_requerida."""
    from fastapi import HTTPException

    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload(
        codigo="cierre_turno",
        valor_efectivo=Decimal("100050"),  # diferencia=50 != 0
        valor_datafono=Decimal("50000"),
        justificacion=None,  # MISSING
    )
    session = MagicMock()
    session.commit = AsyncMock()

    m_resolver_tipo = AsyncMock(return_value=_build_tipo_arqueo(codigo="cierre_turno"))
    m_resolver_tol = AsyncMock(return_value=_build_tolerancia())
    m_validar_sesion = AsyncMock(return_value=MagicMock())
    m_calcular_esperado = AsyncMock(return_value=(Decimal("100000"), Decimal("50000")))
    m_insertar_arqueo = AsyncMock(return_value=_build_arqueo_row())

    with patch.object(handler_mod.repo_arqueo, "resolver_tipo_arqueo_por_uuid", m_resolver_tipo), \
         patch.object(handler_mod.repo_arqueo, "resolver_tolerancia_vigente", m_resolver_tol), \
         patch.object(handler_mod.repo_arqueo, "validar_sesion_abierta_para_arqueo", m_validar_sesion), \
         patch.object(handler_mod.repo_arqueo, "calcular_esperado_sesion", m_calcular_esperado), \
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
    assert exc_info.value.detail == {"error": "justificacion_requerida"}
    assert exc_info.value.headers == {"Cache-Control": "no-store"}
    # Step 6 short-circuits BEFORE Step 8 (no arqueo INSERT)
    assert not m_insertar_arqueo.called
    # No commit
    assert not session.commit.called


# ---------------------------------------------------------------------------
# T5.4 -- 7 extra asymmetry / error-path tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_arqueo_auditoria_con_diferencia_sin_justificacion_accepted() -> None:
    """DEC-ARQUEO-07 asymmetry: auditoria+diferencia+sin_justificacion -> 201."""
    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload(
        codigo="auditoria",
        valor_efectivo=Decimal("100050"),  # diferencia=50 dentro de tolerancia
        valor_datafono=Decimal("50000"),
        justificacion=None,
    )
    session = MagicMock()
    session.commit = AsyncMock()

    m_resolver_tipo = AsyncMock(return_value=_build_tipo_arqueo(codigo="auditoria"))
    m_resolver_tol = AsyncMock(return_value=_build_tolerancia())
    m_validar_sesion = AsyncMock(return_value=MagicMock())
    m_calcular_esperado = AsyncMock(return_value=(Decimal("100000"), Decimal("50000")))
    m_insertar_arqueo = AsyncMock(return_value=_build_arqueo_row())
    m_cerrar_sesiones = AsyncMock(return_value=0)
    m_insertar_alerta = AsyncMock(return_value=_build_alerta_row())

    with patch.object(handler_mod.repo_arqueo, "resolver_tipo_arqueo_por_uuid", m_resolver_tipo), \
         patch.object(handler_mod.repo_arqueo, "resolver_tolerancia_vigente", m_resolver_tol), \
         patch.object(handler_mod.repo_arqueo, "validar_sesion_abierta_para_arqueo", m_validar_sesion), \
         patch.object(handler_mod.repo_arqueo, "calcular_esperado_sesion", m_calcular_esperado), \
         patch.object(handler_mod.repo_arqueo, "insertar_arqueo", m_insertar_arqueo), \
         patch.object(handler_mod.repo_arqueo, "cerrar_sesiones_del_dia_bulk", m_cerrar_sesiones), \
         patch.object(handler_mod.repo_arqueo, "insertar_alerta_descuadre_critico", m_insertar_alerta):
        result = await handler_mod.post_arqueo(
            response=response,
            payload=payload,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    session.commit.assert_called_once()
    # auditoria asymmetry: sin justificacion accepted (diferencia < tolerancia)
    assert result.alerta_generada is False


@pytest.mark.asyncio
async def test_arqueo_cierre_dia_no_acepta_uuid_sesion_returns_400() -> None:
    """V2: cierre_dia + uuid_sesion present -> 400 cierre_dia_no_acepta_uuid_sesion."""
    from fastapi import HTTPException

    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload(
        codigo="cierre_dia",
        uuid_sesion=uuid_lib.uuid4(),  # closure_dia MUST have None
    )
    session = MagicMock()
    session.commit = AsyncMock()

    m_resolver_tipo = AsyncMock(return_value=_build_tipo_arqueo(codigo="cierre_dia"))

    with patch.object(handler_mod.repo_arqueo, "resolver_tipo_arqueo_por_uuid", m_resolver_tipo):
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


@pytest.mark.asyncio
async def test_arqueo_sesion_ya_cerrada_returns_409() -> None:
    """V4 / REQ-OPS-096 Scenario 2: sesion cerrada -> 409 sesion_ya_cerrada."""
    from fastapi import HTTPException

    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    sesion_uuid = uuid_lib.uuid4()
    payload = _build_payload(codigo="cierre_turno", uuid_sesion=sesion_uuid)
    session = MagicMock()
    session.commit = AsyncMock()

    m_resolver_tipo = AsyncMock(return_value=_build_tipo_arqueo(codigo="cierre_turno"))
    m_resolver_tol = AsyncMock(return_value=_build_tolerancia())

    from parkos_core.repo.arqueo import SesionYaCerradaError

    m_validar_sesion = AsyncMock(
        side_effect=SesionYaCerradaError(uuid_sesion=sesion_uuid)
    )

    with patch.object(handler_mod.repo_arqueo, "resolver_tipo_arqueo_por_uuid", m_resolver_tipo), \
         patch.object(handler_mod.repo_arqueo, "resolver_tolerancia_vigente", m_resolver_tol), \
         patch.object(handler_mod.repo_arqueo, "validar_sesion_abierta_para_arqueo", m_validar_sesion):
        with pytest.raises(HTTPException) as exc_info:
            await handler_mod.post_arqueo(
                response=response,
                payload=payload,
                session=session,
                ctx=ctx,
                _claims=None,
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "sesion_ya_cerrada"


@pytest.mark.asyncio
async def test_arqueo_tipo_arqueo_no_encontrado_returns_404() -> None:
    """V1: random uuid_tipo_arqueo -> 404 tipo_arqueo_no_encontrado."""
    from fastapi import HTTPException

    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload(codigo="auditoria")
    session = MagicMock()
    session.commit = AsyncMock()

    random_uuid = uuid_lib.uuid4()
    from parkos_core.repo.arqueo import TipoArqueoNoEncontradoError

    m_resolver_tipo = AsyncMock(
        side_effect=TipoArqueoNoEncontradoError(uuid_tipo_arqueo=random_uuid)
    )

    with patch.object(handler_mod.repo_arqueo, "resolver_tipo_arqueo_por_uuid", m_resolver_tipo):
        with pytest.raises(HTTPException) as exc_info:
            await handler_mod.post_arqueo(
                response=response,
                payload=payload,
                session=session,
                ctx=ctx,
                _claims=None,
            )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "tipo_arqueo_no_encontrado"


@pytest.mark.asyncio
async def test_arqueo_tolerancia_no_configurada_returns_404() -> None:
    """V3: no tolerancia -> 404 tolerancia_no_configurada."""
    from fastapi import HTTPException

    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload(codigo="auditoria")
    session = MagicMock()
    session.commit = AsyncMock()

    from parkos_core.repo.arqueo import ToleranciaNoConfiguradaError

    m_resolver_tipo = AsyncMock(return_value=_build_tipo_arqueo(codigo="auditoria"))
    m_resolver_tol = AsyncMock(
        side_effect=ToleranciaNoConfiguradaError(uuid_sucursal=ctx.sucursal_uuid)
    )

    with patch.object(handler_mod.repo_arqueo, "resolver_tipo_arqueo_por_uuid", m_resolver_tipo), \
         patch.object(handler_mod.repo_arqueo, "resolver_tolerancia_vigente", m_resolver_tol):
        with pytest.raises(HTTPException) as exc_info:
            await handler_mod.post_arqueo(
                response=response,
                payload=payload,
                session=session,
                ctx=ctx,
                _claims=None,
            )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "tolerancia_no_configurada"


@pytest.mark.asyncio
async def test_arqueo_no_store_header_on_400() -> None:
    """DEC-ARQUEO-06: 4xx responses MUST carry Cache-Control: no-store."""
    from fastapi import HTTPException

    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload(codigo="cierre_dia", uuid_sesion=uuid_lib.uuid4())
    session = MagicMock()
    session.commit = AsyncMock()

    m_resolver_tipo = AsyncMock(return_value=_build_tipo_arqueo(codigo="cierre_dia"))

    with patch.object(handler_mod.repo_arqueo, "resolver_tipo_arqueo_por_uuid", m_resolver_tipo):
        with pytest.raises(HTTPException) as exc_info:
            await handler_mod.post_arqueo(
                response=response,
                payload=payload,
                session=session,
                ctx=ctx,
                _claims=None,
            )

    assert exc_info.value.headers["Cache-Control"] == "no-store"
