"""HU-F1.12 / T7.2 -- full-chain e2e test (mock-everything).

Mirrors F1.11 ``test_reimpresion_ticket_e2e.py`` + F1.10
``test_factura_electronica_e2e.py``. Drives the full
``POST /clientes/venta-suscripcion`` happy path with mocked repo
helpers (no DB):

  Step 1: KD-3 issuer chain wired (``_venta_suscripcion_issuer_dep``)
  Step 2: V2 plan lock + ``SELECT ... FOR UPDATE`` (mocked)
  Step 3: V1 cliente lookup-or-create (NEW branch)
  Step 4: V3 per-placa lookup-or-create (1 placa)
  Step 5: V5 in-process ``mismo_tipo_vehiculo`` check
  Step 6: V6 in-process ``cantidad_maxima_vehiculos`` check
  Step 7: V4 per-placa reverse-direction duplicate check
  Step 8: V7 A-09 prorrateo compute
  Step 9: V9 INSERT ``prod.subscripciones_cliente`` + junction
  Step 10: SINGLE ``await session.commit()`` (KD-VENTA-01)

Asserts:

  * KD-VENTA-01 single-commit: ``session.commit.assert_called_once()``
  * DEC-VENTA-06: ``Cache-Control: no-store`` on the 201 response
  * Full chain reached Step 10 (commit) -- no error path triggered
  * Response shape: ``VentaSuscripcionResponse`` with the
    expected UUIDs + DEC-VENTA-03 ``monto_prorrateado is None``
    when ``cobrar_ahora=False``
  * 5 [V] tables participate in the chain: ``tipo_subscripciones`` (V2
    read-lock) + ``clientes`` (V1 write) + ``vehiculos`` (V3 write) +
    ``subscripciones_cliente`` (V9a write) + ``subscripcion_vehiculos``
    (V9b write).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import date
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
    ctx.actor_rol = "operador"
    return ctx


def _new_response() -> MagicMock:
    r = MagicMock()
    r.headers = {}
    return r


def _build_payload() -> MagicMock:
    """Embedded ``cliente`` (NEW branch) + 1 placa + cobrar_ahora=False."""
    payload = MagicMock()
    cliente = MagicMock()
    cliente.model_dump = MagicMock(
        return_value={
            "tipo_identificador": "CC",
            "numero_identificacion": "1234567890",
            "nombre": "Juan",
            "apellido": "Perez",
        }
    )
    payload.cliente = cliente
    payload.uuid_cliente = None
    payload.placas = ["ABC123"]
    payload.uuid_tipo_subscripcion = uuid_lib.uuid4()
    payload.fecha_inicio_cobertura = date(2026, 9, 20)
    payload.cobrar_ahora = False
    payload.emitir_factura_electronica = False
    payload.medio_pago = "efectivo"
    payload.referencia = None
    return payload


@pytest.mark.asyncio
async def test_venta_suscripcion_e2e_full_chain_single_commit() -> None:
    """T7.2: POST /clientes/venta-suscripcion full happy-path chain ends in
    exactly one ``await session.commit()`` (KD-VENTA-01).

    The 9 repo helpers are mocked. The handler runs Steps 1-9 and
    commits once at Step 10. Asserts the full chain executed + the
    response carries the Cache-Control: no-store header.
    """
    from parkos_core.api.v1 import clientes_venta as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload()

    # ----- ORM-like return values ----------------------------------
    plan = MagicMock()
    plan.uuid = uuid_lib.uuid4()
    plan.valor = Decimal("30000.00")
    plan.duracion_dias = 30
    plan.mismo_tipo_vehiculo = False
    plan.cantidad_maxima_vehiculos = 2

    cliente_row = MagicMock()
    cliente_row.uuid = uuid_lib.uuid4()

    vehiculo_row = MagicMock()
    vehiculo_row.uuid = uuid_lib.uuid4()

    subscripcion_row = MagicMock()
    subscripcion_row.uuid = uuid_lib.uuid4()

    # ----- Session mock -------------------------------------------
    session = MagicMock()
    session.commit = AsyncMock()

    # ----- Patch all 9 repo helpers -------------------------------
    m_v2 = AsyncMock(return_value=plan)
    m_v1 = AsyncMock(return_value=cliente_row)
    m_v3 = AsyncMock(return_value=(vehiculo_row, False))
    m_v5 = MagicMock()
    m_v6 = MagicMock()
    m_v4 = AsyncMock()
    m_v7 = MagicMock(return_value=Decimal("30000.00"))
    m_v9a = AsyncMock(return_value=subscripcion_row)
    m_v9b = AsyncMock(return_value=[vehiculo_row])

    patchers = [
        patch.object(handler_mod.repo_venta, "buscar_tipo_subscripcion_vigente_por_uuid", new=m_v2),
        patch.object(handler_mod.repo_venta, "buscar_cliente_por_uuid_o_crear", new=m_v1),
        patch.object(handler_mod.repo_venta, "buscar_o_crear_vehiculo_por_placa", new=m_v3),
        patch.object(handler_mod.repo_venta, "validar_placas_mismo_tipo_vehiculo", new=m_v5),
        patch.object(handler_mod.repo_venta, "validar_cantidad_maxima_vehiculos", new=m_v6),
        patch.object(handler_mod.repo_venta, "validar_placa_duplicada_subscripcion", new=m_v4),
        patch.object(handler_mod.repo_venta, "calcular_prorrateo", new=m_v7),
        patch.object(handler_mod.repo_venta, "crear_subscripcion_cliente", new=m_v9a),
        patch.object(handler_mod.repo_venta, "crear_subscripcion_vehiculos_bulk", new=m_v9b),
    ]
    for p in patchers:
        p.start()
    try:
        result = await handler_mod.venta_suscripcion(
            response=response,
            payload=payload,
            session=session,
            ctx=ctx,
            _claims=None,
        )
    finally:
        for p in patchers:
            p.stop()

    # ----- KD-VENTA-01: SINGLE COMMIT (assert_called_once) ---------
    session.commit.assert_called_once()
    assert session.commit.await_count == 1

    # ----- DEC-VENTA-06: Cache-Control: no-store ------------------
    assert response.headers["Cache-Control"] == "no-store"

    # ----- 5 [V] tables participate in the chain -------------------
    # V2 [V] tipo_subscripciones read-lock (mocked AsyncMock called)
    assert m_v2.await_count == 1
    # V1 [V] clientes write (NEW branch, datos_cliente populated)
    assert m_v1.await_count == 1
    v1_kwargs = m_v1.await_args.kwargs
    assert v1_kwargs["uuid_cliente"] is None
    assert v1_kwargs["datos_cliente"] == payload.cliente.model_dump.return_value
    # V3 [V] vehiculos write (1 placa)
    assert m_v3.await_count == 1
    # V4 reverse-direction duplicate check (1 placa)
    assert m_v4.await_count == 1
    # V5 in-process mismo_tipo_vehiculo
    assert m_v5.called
    # V6 in-process cantidad_maxima_vehiculos
    assert m_v6.called
    # V7 A-09 prorrateo compute
    assert m_v7.called
    # V9a [V] subscripciones_cliente write
    assert m_v9a.await_count == 1
    v9a_kwargs = m_v9a.await_args.kwargs
    assert v9a_kwargs["uuid_cliente"] == cliente_row.uuid
    # V9b [V] subscripcion_vehiculos bulk write
    assert m_v9b.await_count == 1
    v9b_kwargs = m_v9b.await_args.kwargs
    assert v9b_kwargs["uuid_vehiculos"] == [vehiculo_row.uuid]

    # ----- Response shape -----------------------------------------
    assert result.uuid_cliente == cliente_row.uuid
    assert result.uuid_subscripcion == subscripcion_row.uuid
    assert result.uuid_vehiculos == [vehiculo_row.uuid]
    # DEC-VENTA-03: monto_prorrateado is None when cobrar_ahora=False
    assert result.monto_prorrateado is None
    # cobro stubs are None (cobrar_ahora=False)
    assert result.uuid_factura is None
    assert result.uuid_factura_electronica is None
    assert result.uuid_envio_dian is None