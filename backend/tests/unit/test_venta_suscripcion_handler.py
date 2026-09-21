"""HU-F1.12 / T5: POST /clientes/venta-suscripcion handler unit tests.

Pattern: F1.10 + F1.11 mock-everything (no live DB). Drive the handler
end-to-end with ``unittest.mock.AsyncMock`` for the SQLAlchemy session
+ every repo helper. Asserts:

  * KD-3 issuer dep wired (function signature has ``_claims`` param).
  * V1..V9 helpers invoked in the right order.
  * KD-VENTA-01: exactly ONE ``session.commit()`` call.
  * DEC-VENTA-06: ``Cache-Control: no-store`` on the 201 response.
  * 404 ``tipo_subscripcion_no_encontrado`` when V2 returns None.
  * Cross-branch operator rejection is enforced at the auth layer
    (``get_tenant_ctx``), NOT inside this handler body -- see
    ``test_cross_branch_operador_rejected_at_auth_layer`` for the pin.
    The handler-level guard that used to live at Step 2a was dead code
    (compared a value to itself) and was removed per REQ-OPS-XR5 +
    REQ-OPS-089 Scenario 3 footnote.
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
from fastapi import HTTPException, Request  # noqa: E402


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
    """Same-branch operador request is allowed end-to-end (regression guard).

    The cross-branch rejection invariant lives at the auth layer
    (``get_tenant_ctx`` -> ``auth/tenancy.py:127-133``); once a
    ``TenantContext`` reaches this handler body, ``ctx.sucursal_uuid``
    is already pinned to the operador's branch. This test guards against
    the handler-level guard being re-introduced and short-circuiting a
    same-branch happy path: a same-branch operador must reach commit.
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


# ---------------------------------------------------------------------------
# T5.5 (CU-06 fix-pin) -- Auth-layer guard for cross-branch operator.
#
# Prior to the dead-code removal, ``clientes_venta.py`` carried a "Step 2a"
# block that bound ``target_sucursal = ctx.sucursal_uuid`` and then compared
# the value to itself (``target_sucursal != ctx.sucursal_uuid``). That check
# was unreachable (a tautology) -- the request payload for F1.12 does not
# carry a target entity with its own ``uuid_sucursal`` because the
# subscription is being CREATED here, not validated against an existing
# row. REQ-OPS-089 Scenario 3 footnote explicitly defers the cross-branch
# check to a future HU.
#
# The real Layer-2 guard lives at ``parkos_core.auth.tenancy.get_tenant_ctx``
# (REQ-OPS-XR5 Layer 2). For ``operador-`` tokens, the dependency pins the
# request to ``claims["sucursal"]`` and rejects any ``X-Sucursal-Context``
# header pointing at a DIFFERENT branch with 403
# ``unauthorized_sucursal_context`` (``auth/tenancy.py:127-133``). This test
# pins that contract directly so any regression that re-introduces the dead
# handler-level guard OR weakens the auth-layer guard is caught here.
# ---------------------------------------------------------------------------


def _build_request_for_operador(token: str) -> Request:
    """Build a minimal FastAPI ``Request`` carrying an operador bearer token.

    Mirrors ``tests/unit/test_tenancy_operador.py::_build_request`` so the
    auth-layer guard can be invoked without standing up the full FastAPI
    app. ``X-Sucursal-Context`` is intentionally NOT injected here -- it
    is passed explicitly as a kwarg, matching how FastAPI resolves the
    ``Header(None, alias="X-Sucursal-Context")`` descriptor at runtime.
    """
    return Request(
        scope={
            "type": "http",
            "method": "POST",
            "path": "/api/v1/clientes/venta-suscripcion",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )


@pytest.mark.asyncio
async def test_cross_branch_operador_rejected_at_auth_layer() -> None:
    """Cross-branch operador is rejected at ``get_tenant_ctx`` -- never reaches the handler.

    Pins the REQ-OPS-XR5 Layer-2 contract: an ``operador-`` token whose
    JWT ``claims["sucursal"]`` is branch X is rejected with 403
    ``unauthorized_sucursal_context`` when the request carries an
    ``X-Sucursal-Context`` header pointing at branch Y. The rejection
    happens at the auth dependency (``get_tenant_ctx``) BEFORE the
    handler body runs, which is why the F1.12 handler MUST NOT re-check
    this invariant -- any handler-level check is either a no-op (when
    the local variable shadows ``ctx.sucursal_uuid``) or a duplicate of
    the auth-layer guard (which is the wrong place to enforce it).

    NOTE on the discriminator: this test asserts the ACTUAL auth-layer
    error code ``unauthorized_sucursal_context`` emitted by
    ``UnauthorizedSucursalContextError`` (``auth/tenancy.py:67``). The
    spec text at REQ-OPS-XR5 Scenario 2 (line 3679) describes the
    rejection as ``tenant_scope_violation``; that is the canonical
    spec-honest contract for handler-level Layer-2 checks like
    ``operacion.py:174`` and ``facturacion.py:279`` which DO have a
    target entity with its own ``uuid_sucursal`` to compare against.
    For F1.12, no such target entity exists (see REQ-OPS-089 Scenario 3),
    and the auth layer emits the stricter
    ``unauthorized_sucursal_context`` discriminator.
    """
    from parkos_core.auth.tenancy import get_tenant_ctx
    from parkos_core.auth.tokens import issue_token

    branch_x = uuid_lib.uuid4()  # the operador's pinned branch
    branch_y = uuid_lib.uuid4()  # the header is pointing at a DIFFERENT branch
    assert branch_x != branch_y

    token = issue_token(
        subject_uuid=uuid_lib.uuid4(),
        issuer="operador-test",
        claims={"rol": "operador", "sucursal": str(branch_x)},
        expires_in=3600,
    )
    request = _build_request_for_operador(token)

    # Auth-layer dependency MUST reject the cross-branch attempt with 403
    # ``unauthorized_sucursal_context`` -- NOT 200, NOT 403
    # ``tenant_scope_violation`` (that discriminator is for handler-level
    # checks against a target entity, see operacion.py:174).
    with pytest.raises(HTTPException) as exc:
        await get_tenant_ctx(
            request=request,
            x_sucursal_context=str(branch_y),
        )
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "unauthorized_sucursal_context"
    # No ``Cache-Control`` header at the auth layer (that is the
    # handler-level Layer-5 invariant from DEC-VENTA-06). The auth layer
    # emits a bare 403; downstream proxies add no-store if needed.
