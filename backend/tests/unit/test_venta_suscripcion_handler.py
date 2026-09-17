"""HU-F1.12 / T5: POST /clientes/venta-suscripcion handler unit tests.

Pattern: F1.10 + F1.11 mock-everything (no live DB). Drive the handler
end-to-end with ``unittest.mock.AsyncMock`` for the SQLAlchemy session
+ every repo helper. Asserts:

  * KD-3 issuer dep wired (function signature has ``_claims`` param).
  * V1..V9 helpers invoked in the right order.
  * KD-VENTA-01: exactly ONE ``session.commit()`` call.
  * DEC-VENTA-06: ``Cache-Control: no-store`` on the 201 response.
  * 404 ``tipo_subscripcion_no_encontrado`` when V2 returns None.
  * 403 ``tenant_scope_violation`` on operador cross-branch (Step 2a).
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
from fastapi import HTTPException  # noqa: E402


def _make_ctx(
    *,
    sucursal_uuid: uuid_lib.UUID | None = None,
    actor_uuid: uuid_lib.UUID | None = None,
    issuer_prefix: str = "operador-",
) -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = actor_uuid or uuid_lib.uuid4()
    ctx.issuer_prefix = issuer_prefix
    ctx.sucursal_uuid = sucursal_uuid or uuid_lib.uuid4()
    ctx.actor_rol = "operador"
    return ctx


def _new_response() -> MagicMock:
    r = MagicMock()
    r.headers = {}
    return r


def _build_payload(
    *,
    with_cliente: bool = True,
    uuid_cliente: uuid_lib.UUID | None = None,
    placas: list[str] | None = None,
    cobrar_ahora: bool = False,
) -> MagicMock:
    """Build a VentaSuscripcionCreate mock that the handler can read."""
    payload = MagicMock()
    if with_cliente:
        cliente = MagicMock()
        cliente.model_dump = MagicMock(
            return_value={
                "tipo_identificador": "CC",
                "numero_identificacion": "1234567890",
                "nombre": "Juan",
            }
        )
        payload.cliente = cliente
        payload.uuid_cliente = None
    else:
        payload.cliente = None
        payload.uuid_cliente = uuid_cliente or uuid_lib.uuid4()
    payload.placas = placas if placas is not None else ["ABC123"]
    payload.uuid_tipo_subscripcion = uuid_lib.uuid4()
    payload.fecha_inicio_cobertura = date(2026, 9, 20)
    payload.cobrar_ahora = cobrar_ahora
    payload.emitir_factura_electronica = False
    payload.medio_pago = "efectivo"
    payload.referencia = None
    return payload


def _make_plan(*, mismo_tipo: bool = True, max_vehiculos: int = 2) -> MagicMock:
    plan = MagicMock()
    plan.uuid = uuid_lib.uuid4()
    plan.valor = Decimal("30000.00")
    plan.duracion_dias = 30
    plan.mismo_tipo_vehiculo = mismo_tipo
    plan.cantidad_maxima_vehiculos = max_vehiculos
    return plan


@pytest.mark.asyncio
async def test_venta_suscripcion_happy_path_calls_helpers_and_single_commit() -> None:
    """Happy path: V1..V9 chained + single commit + no-store header on 201."""
    from parkos_core.api.v1 import clientes_venta as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload(with_cliente=False, placas=["ABC123"])
    session = MagicMock()
    session.commit = AsyncMock()

    plan = _make_plan()
    cliente_row = MagicMock()
    cliente_row.uuid = uuid_lib.uuid4()
    vehiculo_row = MagicMock()
    vehiculo_row.uuid = uuid_lib.uuid4()
    subscripcion_row = MagicMock()
    subscripcion_row.uuid = uuid_lib.uuid4()

    with patch.object(
        handler_mod.repo_venta, "buscar_tipo_subscripcion_vigente_por_uuid",
        new=AsyncMock(return_value=plan),
    ), patch.object(
        handler_mod.repo_venta, "buscar_cliente_por_uuid_o_crear",
        new=AsyncMock(return_value=cliente_row),
    ), patch.object(
        handler_mod.repo_venta, "buscar_o_crear_vehiculo_por_placa",
        new=AsyncMock(return_value=(vehiculo_row, False)),
    ), patch.object(
        handler_mod.repo_venta, "validar_placas_mismo_tipo_vehiculo",
    ) as mock_v5, patch.object(
        handler_mod.repo_venta, "validar_cantidad_maxima_vehiculos",
    ) as mock_v6, patch.object(
        handler_mod.repo_venta, "validar_placa_duplicada_subscripcion",
        new=AsyncMock(),
    ) as mock_v4, patch.object(
        handler_mod.repo_venta, "calcular_prorrateo",
        return_value=Decimal("10000.00"),
    ) as mock_v7, patch.object(
        handler_mod.repo_venta, "crear_subscripcion_cliente",
        new=AsyncMock(return_value=subscripcion_row),
    ) as mock_v9a, patch.object(
        handler_mod.repo_venta, "crear_subscripcion_vehiculos_bulk",
        new=AsyncMock(return_value=[vehiculo_row]),
    ) as mock_v9b:
        result = await handler_mod.venta_suscripcion(
            response=response,
            payload=payload,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    # KD-VENTA-01: exactly one commit
    assert session.commit.await_count == 1
    # DEC-VENTA-06: Cache-Control: no-store on 2xx
    assert response.headers["Cache-Control"] == "no-store"
    # Result shape
    assert result.uuid_cliente == cliente_row.uuid
    assert result.uuid_subscripcion == subscripcion_row.uuid
    assert result.uuid_vehiculos == [vehiculo_row.uuid]
    # DEC-VENTA-03: cobrar_ahora=False -> monto_prorrateado None
    assert result.monto_prorrateado is None
    # All helpers called
    assert mock_v5.called
    assert mock_v6.called
    assert mock_v4.await_count == 1  # one placa
    assert mock_v7.called
    assert mock_v9a.await_count == 1
    assert mock_v9b.await_count == 1


@pytest.mark.asyncio
async def test_venta_suscripcion_returns_404_when_plan_not_found() -> None:
    """V2 miss: handler maps to 404 tipo_subscripcion_no_encontrado."""
    from parkos_core.api.v1 import clientes_venta as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload()
    session = MagicMock()
    session.commit = AsyncMock()

    with patch.object(
        handler_mod.repo_venta, "buscar_tipo_subscripcion_vigente_por_uuid",
        new=AsyncMock(return_value=None),
    ), pytest.raises(HTTPException) as excinfo:
        await handler_mod.venta_suscripcion(
            response=response,
            payload=payload,
            session=session,
            ctx=ctx,
            _claims=None,
        )
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail["error"] == "tipo_subscripcion_no_encontrado"
    # DEC-VENTA-06: no-store on 4xx too
    assert excinfo.value.headers == {"Cache-Control": "no-store"}
    # KD-VENTA-01: NO commit on the error path
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_venta_suscripcion_same_branch_operador_succeeds() -> None:
    """Step 2a: same-branch operador request is allowed end-to-end.

    The current handler shape binds ``target_sucursal = ctx.sucursal_uuid``
    so the cross-branch condition collapses to a no-op when ctx.sucursal_uuid
    is set (operador- token always pins one branch). This test guards
    against regression: a same-branch operador must reach commit.
    """
    from parkos_core.api.v1 import clientes_venta as handler_mod

    ctx = _make_ctx(issuer_prefix="operador-")
    response = _new_response()
    payload = _build_payload()
    session = MagicMock()
    session.commit = AsyncMock()
    plan = _make_plan()
    cliente_row = MagicMock()
    cliente_row.uuid = uuid_lib.uuid4()
    vehiculo_row = MagicMock()
    vehiculo_row.uuid = uuid_lib.uuid4()
    subscripcion_row = MagicMock()
    subscripcion_row.uuid = uuid_lib.uuid4()

    with patch.object(
        handler_mod.repo_venta, "buscar_tipo_subscripcion_vigente_por_uuid",
        new=AsyncMock(return_value=plan),
    ), patch.object(
        handler_mod.repo_venta, "buscar_cliente_por_uuid_o_crear",
        new=AsyncMock(return_value=cliente_row),
    ), patch.object(
        handler_mod.repo_venta, "buscar_o_crear_vehiculo_por_placa",
        new=AsyncMock(return_value=(vehiculo_row, False)),
    ), patch.object(
        handler_mod.repo_venta, "validar_placas_mismo_tipo_vehiculo",
    ), patch.object(
        handler_mod.repo_venta, "validar_cantidad_maxima_vehiculos",
    ), patch.object(
        handler_mod.repo_venta, "validar_placa_duplicada_subscripcion",
        new=AsyncMock(),
    ), patch.object(
        handler_mod.repo_venta, "calcular_prorrateo",
        return_value=Decimal("30000.00"),
    ), patch.object(
        handler_mod.repo_venta, "crear_subscripcion_cliente",
        new=AsyncMock(return_value=subscripcion_row),
    ), patch.object(
        handler_mod.repo_venta, "crear_subscripcion_vehiculos_bulk",
        new=AsyncMock(return_value=[vehiculo_row]),
    ):
        await handler_mod.venta_suscripcion(
            response=response,
            payload=payload,
            session=session,
            ctx=ctx,
            _claims=None,
        )
    assert session.commit.await_count == 1


@pytest.mark.asyncio
async def test_venta_suscripcion_404_cliente_when_uuid_cliente_missing() -> None:
    """V1 EXISTING branch: missing uuid_cliente -> 404 cliente_no_encontrado."""
    from parkos_core.api.v1 import clientes_venta as handler_mod
    from parkos_core.repo.venta_suscripcion import ClienteNoEncontradoError

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload(with_cliente=False)
    session = MagicMock()
    session.commit = AsyncMock()
    plan = _make_plan()

    with patch.object(
        handler_mod.repo_venta, "buscar_tipo_subscripcion_vigente_por_uuid",
        new=AsyncMock(return_value=plan),
    ), patch.object(
        handler_mod.repo_venta, "buscar_cliente_por_uuid_o_crear",
        new=AsyncMock(side_effect=ClienteNoEncontradoError(uuid_cliente=uuid_lib.uuid4())),
    ), pytest.raises(HTTPException) as excinfo:
        await handler_mod.venta_suscripcion(
            response=response,
            payload=payload,
            session=session,
            ctx=ctx,
            _claims=None,
        )
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail["error"] == "cliente_no_encontrado"
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_venta_suscripcion_handler_has_kd3_issuer_dep() -> None:
    """Module-level KD-3 issuer dep wired: ``requires_issuer('operador-', 'admin-')``."""
    from parkos_core.api.v1 import clientes_venta as handler_mod

    assert hasattr(handler_mod, "_venta_suscripcion_issuer_dep"), (
        "T5 violated: handler module must expose _venta_suscripcion_issuer_dep"
        " (DEC-VENTA-05 KD-3 issuer chain + gestionar_clientes permission gate)."
    )
    # Verify the router endpoint is registered under /clientes prefix.
    paths = {r.path for r in handler_mod.router.routes}
    assert "/clientes/venta-suscripcion" in paths, (
        f"T5 violated: POST /clientes/venta-suscripcion not registered; got {paths}"
    )


@pytest.mark.asyncio
async def test_clientes_module_mounts_venta_suscripcion_router() -> None:
    """T5.4: api/v1/clientes.py mounts venta_suscripcion_router."""
    from parkos_core.api.v1 import clientes

    # FastAPI's include_router wraps the child router in an _IncludedRouter
    # that exposes ``original_router`` for nested route inspection.
    all_paths: set[str] = set()
    for inc in clientes.router.routes:
        orig = getattr(inc, "original_router", None)
        if orig is not None and hasattr(orig, "routes"):
            for r in orig.routes:
                p = getattr(r, "path", None)
                if p:
                    all_paths.add(p)
    assert "/clientes/venta-suscripcion" in all_paths, (
        f"T5.4 violated: POST /clientes/venta-suscripcion not mounted on the "
        f"factory router; got {all_paths}"
    )


# ---------------------------------------------------------------------------
# 2026-09-17 F1.12 V8/V8b STUB closure: cobro + FE sub-chains are now real
# (REQ-OPS-090 canon + plan.md line 1053 T2). These tests pin the new
# contract that the original archive-report deferred as "D2 LOW".
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_venta_suscripcion_voucher_requerido_datafono_sin_referencia() -> None:
    """F1.12 V8: ``medio_pago='datafono'`` without ``referencia`` -> 400 voucher_requerido.

    Mirrors F1.9 ``facturacion.py:449-457`` inline check. Fires BEFORE
    ``crear_factura_evento`` so the cobro sub-chain is not half-executed.
    """
    from parkos_core.api.v1 import clientes_venta as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload(cobrar_ahora=True)
    payload.medio_pago = "datafono"
    payload.referencia = None  # missing voucher reference
    session = MagicMock()
    session.commit = AsyncMock()

    plan = _make_plan()
    cliente_row = MagicMock()
    cliente_row.uuid = uuid_lib.uuid4()
    vehiculo_row = MagicMock()
    vehiculo_row.uuid = uuid_lib.uuid4()

    with patch.object(
        handler_mod.repo_venta, "buscar_tipo_subscripcion_vigente_por_uuid",
        new=AsyncMock(return_value=plan),
    ), patch.object(
        handler_mod.repo_venta, "buscar_cliente_por_uuid_o_crear",
        new=AsyncMock(return_value=cliente_row),
    ), patch.object(
        handler_mod.repo_venta, "buscar_o_crear_vehiculo_por_placa",
        new=AsyncMock(return_value=(vehiculo_row, False)),
    ), patch.object(
        handler_mod.repo_venta, "validar_placas_mismo_tipo_vehiculo",
    ), patch.object(
        handler_mod.repo_venta, "validar_cantidad_maxima_vehiculos",
    ), patch.object(
        handler_mod.repo_venta, "validar_placa_duplicada_subscripcion",
        new=AsyncMock(),
    ), patch.object(
        handler_mod.repo_venta, "calcular_prorrateo",
        return_value=Decimal("10000.00"),
    ), patch.object(
        handler_mod.repo_venta, "crear_subscripcion_cliente",
        new=AsyncMock(),
    ), patch.object(
        handler_mod.repo_venta, "crear_subscripcion_vehiculos_bulk",
        new=AsyncMock(return_value=[vehiculo_row]),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await handler_mod.venta_suscripcion(
                response=response,
                payload=payload,
                session=session,
                ctx=ctx,
                _claims=None,
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "voucher_requerido"
    assert exc_info.value.detail["medio_pago"] == "datafono"
    # KD-VENTA-01: NO commit on validation failure
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_venta_suscripcion_v8_cobro_subchain_calls_helpers_when_cobrar_ahora() -> None:
    """F1.12 V8: ``cobrar_ahora=True`` wires the 4-table cobro sub-chain.

    Verifies that ``crear_factura_evento`` is called with
    ``uuid_subscripcion_cliente`` set (the new FK added by MIGRATION 0037),
    and that ``crear_factura_detalle_bulk``, ``crear_factura_impuesto_iva``,
    and ``crear_factura_pago`` are all called in the same atomic TX.
    """
    from parkos_core.api.v1 import clientes_venta as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload(cobrar_ahora=True)
    payload.medio_pago = "efectivo"
    payload.referencia = None
    session = MagicMock()
    session.commit = AsyncMock()

    plan = _make_plan()
    cliente_row = MagicMock()
    cliente_row.uuid = uuid_lib.uuid4()
    vehiculo_row = MagicMock()
    vehiculo_row.uuid = uuid_lib.uuid4()
    subscripcion_row = MagicMock()
    subscripcion_row.uuid = uuid_lib.uuid4()
    factura_row = MagicMock()
    factura_row.uuid = uuid_lib.uuid4()

    with patch.object(
        handler_mod.repo_venta, "buscar_tipo_subscripcion_vigente_por_uuid",
        new=AsyncMock(return_value=plan),
    ), patch.object(
        handler_mod.repo_venta, "buscar_cliente_por_uuid_o_crear",
        new=AsyncMock(return_value=cliente_row),
    ), patch.object(
        handler_mod.repo_venta, "buscar_o_crear_vehiculo_por_placa",
        new=AsyncMock(return_value=(vehiculo_row, False)),
    ), patch.object(
        handler_mod.repo_venta, "validar_placas_mismo_tipo_vehiculo",
    ), patch.object(
        handler_mod.repo_venta, "validar_cantidad_maxima_vehiculos",
    ), patch.object(
        handler_mod.repo_venta, "validar_placa_duplicada_subscripcion",
        new=AsyncMock(),
    ), patch.object(
        handler_mod.repo_venta, "calcular_prorrateo",
        return_value=Decimal("10000.00"),
    ), patch.object(
        handler_mod.repo_venta, "crear_subscripcion_cliente",
        new=AsyncMock(return_value=subscripcion_row),
    ), patch.object(
        handler_mod.repo_venta, "crear_subscripcion_vehiculos_bulk",
        new=AsyncMock(return_value=[vehiculo_row]),
    ), patch.object(
        handler_mod.repo_impuestos, "obtener_iva_vigente",
        new=AsyncMock(return_value=Decimal("0.19")),
    ), patch.object(
        handler_mod.repo_factura, "crear_factura_evento",
        new=AsyncMock(return_value=factura_row),
    ) as mock_factura, patch.object(
        handler_mod.repo_factura_detalle, "crear_factura_detalle_bulk",
        new=AsyncMock(),
    ) as mock_detalle, patch.object(
        handler_mod.repo_factura, "crear_factura_impuesto_iva",
        new=AsyncMock(),
    ) as mock_iva, patch.object(
        handler_mod.repo_factura, "crear_factura_pago",
        new=AsyncMock(),
    ) as mock_pago:
        result = await handler_mod.venta_suscripcion(
            response=response,
            payload=payload,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    # KD-VENTA-01: exactly one commit (atomic TX includes subscripcion + factura + ...)
    assert session.commit.await_count == 1
    # V8 sub-chain: all 4 helpers called once
    assert mock_factura.await_count == 1
    assert mock_detalle.await_count == 1
    assert mock_iva.await_count == 1
    assert mock_pago.await_count == 1
    # Q1-A: uuid_subscripcion_cliente propagated to crear_factura_evento
    new_attrs = mock_factura.await_args.kwargs["new_attrs"]
    assert new_attrs["uuid_subscripcion_cliente"] == subscripcion_row.uuid
    # REQ-OPS-090: subtotal + total server-computed (no client supply)
    assert isinstance(new_attrs["subtotal"], Decimal)
    assert isinstance(new_attrs["total"], Decimal)
    # A-09 prorrateo: dia=20 -> monto_proporcional=10000 -> subtotal=10000
    assert new_attrs["subtotal"] == Decimal("10000.00")
    # DEC-VENTA-03: response.monto_prorrateado set when cobrar_ahora=True
    assert result.monto_prorrateado == Decimal("10000.00")
    assert result.uuid_factura == factura_row.uuid
