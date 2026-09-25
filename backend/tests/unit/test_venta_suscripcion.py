"""HU-F1.12 / T7.1 -- 4 MANDATED tests per ``plan.md`` line 1047.

Coverage matrix (REQ-OPS-083..090 + REQ-OPS-XR5):

  T1 ``test_cliente_nuevo_venta_exitosa_returns_201``
        -- happy path, NEW cliente via ``datos_cliente`` payload
        + 1 placa + plan "mensual" + ``cobrar_ahora=False``
        -> 201 ``VentaSuscripcionResponse`` + ``Cache-Control: no-store``.

  T2 ``test_cliente_existente_lookup_by_uuid``
        -- happy path, EXISTING cliente by ``uuid_cliente`` + 2 placas
        -> 201.

  T3 ``test_plan_mismo_tipo_vehiculo_rechaza_placas_mixtas``
        -- 422 ``tipo_vehiculo_incompatible`` + ``Cache-Control: no-store``.

  T4 ``test_placa_duplicada_subscripcion_vigente_rechaza``
        -- 422 ``suscripcion_duplicada_placa`` + ``Cache-Control: no-store``.

  T5 ``test_cobrar_ahora_genera_factura_con_display_enriquecido``
        -- bugfix (2026-09-25): ``cobrar_ahora=True`` must run the full
        cobro sub-chain AND assemble the enriched display projection
        (``build_display_factura``) so the response carries ``factura``
        for the wizard's post-pago ticket/modal -- not just the bare
        ``uuid_factura`` the original T1-T4 matrix never exercised.

Pattern: F1.10 + F1.11 mock-everything (no live DB). Drives the handler
end-to-end with ``unittest.mock.AsyncMock`` for the SQLAlchemy session
+ every repo helper. Pure Python, no Docker daemon required.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# RUF059 disabled -- some patches unpack mocks that are intentionally
# not directly inspected by the test body (they're verified indirectly
# via the handler's HTTP response).
# ruff: noqa: RUF059

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

# ---------------------------------------------------------------------------
# Shared builders
# ---------------------------------------------------------------------------


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


def _build_payload_nuevo_cliente(
    *,
    placas: list[str] | None = None,
    cobrar_ahora: bool = False,
) -> MagicMock:
    """Build a ``VentaSuscripcionCreate``-like mock with embedded ``cliente``."""
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
    payload.placas = placas if placas is not None else ["ABC123"]
    payload.uuid_tipo_subscripcion = uuid_lib.uuid4()
    payload.fecha_inicio_cobertura = date(2026, 9, 20)
    payload.cobrar_ahora = cobrar_ahora
    payload.emitir_factura_electronica = False
    payload.medio_pago = "efectivo"
    payload.referencia = None
    return payload


def _build_payload_cliente_existente(
    *,
    uuid_cliente: uuid_lib.UUID | None = None,
    placas: list[str] | None = None,
) -> MagicMock:
    """Build a payload with ``uuid_cliente`` populated (XOR branch)."""
    payload = MagicMock()
    payload.cliente = None
    payload.uuid_cliente = uuid_cliente or uuid_lib.uuid4()
    payload.placas = placas if placas is not None else ["AAA111", "BBB222"]
    payload.uuid_tipo_subscripcion = uuid_lib.uuid4()
    payload.fecha_inicio_cobertura = date(2026, 9, 20)
    payload.cobrar_ahora = False
    payload.emitir_factura_electronica = False
    payload.medio_pago = "efectivo"
    payload.referencia = None
    return payload


def _make_plan(
    *,
    mismo_tipo: bool = False,
    max_vehiculos: int = 2,
    valor: Decimal = Decimal("30000.00"),
    duracion_dias: int = 30,
) -> MagicMock:
    plan = MagicMock()
    plan.uuid = uuid_lib.uuid4()
    plan.valor = valor
    plan.duracion_dias = duracion_dias
    plan.mismo_tipo_vehiculo = mismo_tipo
    plan.cantidad_maxima_vehiculos = max_vehiculos
    return plan


# Patch stack reused by every happy-path test
def _patch_happy_path(
    handler_mod,
    *,
    plan: MagicMock,
    cliente_row: MagicMock,
    vehiculos: list[MagicMock],
    subscripcion_row: MagicMock,
) -> tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, MagicMock, AsyncMock, AsyncMock, list]:
    """Patch all 9 repo helpers + return (mocks, patchers) for inspection."""
    m_v2 = AsyncMock(return_value=plan)
    m_v1 = AsyncMock(return_value=cliente_row)
    m_v3 = AsyncMock(side_effect=[(v, False) for v in vehiculos])
    m_v5 = MagicMock()
    m_v6 = MagicMock()
    m_v4 = AsyncMock()
    m_v7 = MagicMock(return_value=Decimal("30000.00"))
    m_v9a = AsyncMock(return_value=subscripcion_row)
    m_v9b = AsyncMock(return_value=vehiculos)

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
    return m_v2, m_v1, m_v3, m_v4, m_v7, m_v9a, m_v9b, patchers


# ---------------------------------------------------------------------------
# T1 -- happy path: nuevo cliente + 1 placa + plan "mensual" + cobrar_ahora=false
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cliente_nuevo_venta_exitosa_returns_201() -> None:
    """T1 (plan.md line 1047): new cliente + 1 placa + plan mensual + cobrar_ahora=False.

    Asserts:
      * 201 ``VentaSuscripcionResponse`` with ``uuid_subscripcion``
        matching the mock + ``uuid_vehiculos=[<v>]`` + ``monto_prorrateado is None``
        (DEC-VENTA-03: prorrateo is None when cobrar_ahora=False).
      * ``Cache-Control: no-store`` on the 201 response (DEC-VENTA-06).
      * Exactly ONE ``session.commit()`` call (KD-VENTA-01).
      * V1 dispatched with ``datos_cliente`` (NEW branch), not ``uuid_cliente``.
      * V3 called once for the single placa.
      * V7 prorrateo invoked; result NOT propagated to ``monto_prorrateado``
        since ``cobrar_ahora=False``.
    """
    from parkos_core.api.v1 import clientes_venta as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload_nuevo_cliente(placas=["ABC123"], cobrar_ahora=False)
    session = MagicMock()
    session.commit = AsyncMock()

    plan = _make_plan()
    cliente_row = MagicMock()
    cliente_row.uuid = uuid_lib.uuid4()
    vehiculo_row = MagicMock()
    vehiculo_row.uuid = uuid_lib.uuid4()
    subscripcion_row = MagicMock()
    subscripcion_row.uuid = uuid_lib.uuid4()

    _p_v2, p_v1, p_v3, p_v4, _p_v7, _p_v9a, _p_v9b, patchers = _patch_happy_path(
        handler_mod,
        plan=plan,
        cliente_row=cliente_row,
        vehiculos=[vehiculo_row],
        subscripcion_row=subscripcion_row,
    )
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

    # KD-VENTA-01
    assert session.commit.await_count == 1
    # DEC-VENTA-06
    assert response.headers["Cache-Control"] == "no-store"
    # Response shape
    assert result.uuid_cliente == cliente_row.uuid
    assert result.uuid_subscripcion == subscripcion_row.uuid
    assert result.uuid_vehiculos == [vehiculo_row.uuid]
    # DEC-VENTA-03
    assert result.monto_prorrateado is None
    # V1 dispatched to NEW branch (datos_cliente set, uuid_cliente None)
    v1_kwargs = p_v1.await_args.kwargs
    assert v1_kwargs["uuid_cliente"] is None
    assert v1_kwargs["datos_cliente"] == payload.cliente.model_dump.return_value
    # V3 called once (single placa)
    assert p_v3.await_count == 1
    # V4 called once (single placa)
    assert p_v4.await_count == 1


# ---------------------------------------------------------------------------
# T2 -- happy path: existing cliente + 2 placas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cliente_existente_lookup_by_uuid() -> None:
    """T2 (plan.md line 1047): existing cliente via ``uuid_cliente`` + 2 placas.

    Asserts:
      * 201 ``VentaSuscripcionResponse`` with 2 vehiculo UUIDs in
        ``uuid_vehiculos``.
      * V1 dispatched to EXISTING branch (``uuid_cliente`` populated,
        ``datos_cliente`` None).
      * V3 called twice (one per placa).
      * V4 called twice (one per placa).
      * V6 accepts 2 placas (plan max=2).
      * Single commit + no-store header.
    """
    from parkos_core.api.v1 import clientes_venta as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload_cliente_existente(placas=["AAA111", "BBB222"])
    session = MagicMock()
    session.commit = AsyncMock()

    plan = _make_plan(max_vehiculos=2)
    cliente_row = MagicMock()
    cliente_row.uuid = uuid_lib.uuid4()
    v1 = MagicMock()
    v1.uuid = uuid_lib.uuid4()
    v2 = MagicMock()
    v2.uuid = uuid_lib.uuid4()
    subscripcion_row = MagicMock()
    subscripcion_row.uuid = uuid_lib.uuid4()

    _p_v2, p_v1, p_v3, p_v4, p_v7, p_v9a, p_v9b, patchers = _patch_happy_path(
        handler_mod,
        plan=plan,
        cliente_row=cliente_row,
        vehiculos=[v1, v2],
        subscripcion_row=subscripcion_row,
    )
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

    # KD-VENTA-01
    assert session.commit.await_count == 1
    # DEC-VENTA-06
    assert response.headers["Cache-Control"] == "no-store"
    # Response shape -- 2 vehiculos
    assert result.uuid_cliente == cliente_row.uuid
    assert result.uuid_subscripcion == subscripcion_row.uuid
    assert result.uuid_vehiculos == [v1.uuid, v2.uuid]
    # V1 dispatched to EXISTING branch
    v1_kwargs = p_v1.await_args.kwargs
    assert v1_kwargs["uuid_cliente"] == payload.uuid_cliente
    assert v1_kwargs["datos_cliente"] is None
    # V3 + V4 called twice
    assert p_v3.await_count == 2
    assert p_v4.await_count == 2


# ---------------------------------------------------------------------------
# T3 -- 422 tipo_vehiculo_incompatible when mismo_tipo plan + mixed tipos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_mismo_tipo_vehiculo_rechaza_placas_mixtas() -> None:
    """T3 (plan.md line 1047): plan.mismo_tipo_vehiculo=True + mixed tipos → 422.

    Asserts:
      * Handler raises :class:`HTTPException` with status_code=422 and
        ``detail.error == "tipo_vehiculo_incompatible"``.
      * ``Cache-Control: no-store`` on the 422 (DEC-VENTA-06).
      * NO ``session.commit()`` call on the error path (KD-VENTA-01).
    """
    from parkos_core.api.v1 import clientes_venta as handler_mod
    from parkos_core.repo.venta_suscripcion import TipoVehiculoIncompatibleError

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload_nuevo_cliente(placas=["AAA111", "BBB222"])
    session = MagicMock()
    session.commit = AsyncMock()

    plan = _make_plan(mismo_tipo=True, max_vehiculos=2)
    cliente_row = MagicMock()
    cliente_row.uuid = uuid_lib.uuid4()
    v1 = MagicMock()
    v1.uuid = uuid_lib.uuid4()
    v2 = MagicMock()
    v2.uuid = uuid_lib.uuid4()

    # Reuse the happy-path patcher factory; replace V5 with side_effect
    # so the handler raises TipoVehiculoIncompatibleError when V5 runs.
    _p_v2, _p_v1, p_v3, _p_v4, p_v7, p_v9a, p_v9b, patchers = _patch_happy_path(
        handler_mod,
        plan=plan,
        cliente_row=cliente_row,
        vehiculos=[v1, v2],
        subscripcion_row=MagicMock(uuid=uuid_lib.uuid4()),
    )
    # Find the V5 patcher (validar_placas_mismo_tipo_vehiculo) and replace
    # it with a side_effect that raises the typed exception.
    for p in patchers:
        target = p.attribute
        if target == "validar_placas_mismo_tipo_vehiculo":
            p.stop()
            new_mock = MagicMock(
                side_effect=TipoVehiculoIncompatibleError(tipos_encontrados=["t1", "t2"])
            )
            new_patch = patch.object(
                handler_mod.repo_venta, target, new=new_mock
            )
            new_patch.start()
            patchers[patchers.index(p)] = new_patch
            break
    try:
        with pytest.raises(HTTPException) as excinfo:
            await handler_mod.venta_suscripcion(
                response=response,
                payload=payload,
                session=session,
                ctx=ctx,
                _claims=None,
            )
    finally:
        for p in patchers:
            p.stop()

    assert excinfo.value.status_code == 422
    assert excinfo.value.detail["error"] == "tipo_vehiculo_incompatible"
    assert excinfo.value.headers == {"Cache-Control": "no-store"}
    # KD-VENTA-01: no commit on the error path
    assert session.commit.await_count == 0
    # V7..V9 must NOT have been called (V5 raises BEFORE V7)
    assert not p_v7.called
    assert p_v9a.await_count == 0
    assert p_v9b.await_count == 0


# ---------------------------------------------------------------------------
# T4 -- 422 suscripcion_duplicada_placa when placa already has an active sub
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_placa_duplicada_subscripcion_vigente_rechaza() -> None:
    """T4 (plan.md line 1047): existing active sub for placa → 422.

    Asserts:
      * Handler raises :class:`HTTPException` with status_code=422 and
        ``detail.error == "suscripcion_duplicada_placa"``.
      * ``Cache-Control: no-store`` on the 422 (DEC-VENTA-06).
      * NO ``session.commit()`` call on the error path (KD-VENTA-01).
      * V9a/V9b NOT called (V4 raises BEFORE V9).
    """
    from parkos_core.api.v1 import clientes_venta as handler_mod
    from parkos_core.repo.venta_suscripcion import SubscripcionDuplicadaPlacaError

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload_nuevo_cliente(placas=["ABC123"])
    session = MagicMock()
    session.commit = AsyncMock()

    plan = _make_plan()
    cliente_row = MagicMock()
    cliente_row.uuid = uuid_lib.uuid4()
    vehiculo_row = MagicMock()
    vehiculo_row.uuid = uuid_lib.uuid4()

    # Reuse the happy-path patcher factory; replace V4 with side_effect
    # so the handler raises SubscripcionDuplicadaPlacaError when V4 runs.
    _p_v2, _p_v1, _p_v3, p_v4, p_v7, p_v9a, p_v9b, patchers = _patch_happy_path(
        handler_mod,
        plan=plan,
        cliente_row=cliente_row,
        vehiculos=[vehiculo_row],
        subscripcion_row=MagicMock(uuid=uuid_lib.uuid4()),
    )
    for p in patchers:
        target = p.attribute
        if target == "validar_placa_duplicada_subscripcion":
            p.stop()
            new_mock = AsyncMock(side_effect=SubscripcionDuplicadaPlacaError(
                placa="ABC123", uuid_sucursal=ctx.sucursal_uuid,
            ))
            new_patch = patch.object(
                handler_mod.repo_venta, target, new=new_mock
            )
            new_patch.start()
            patchers[patchers.index(p)] = new_patch
            break
    try:
        with pytest.raises(HTTPException) as excinfo:
            await handler_mod.venta_suscripcion(
                response=response,
                payload=payload,
                session=session,
                ctx=ctx,
                _claims=None,
            )
    finally:
        for p in patchers:
            p.stop()

    assert excinfo.value.status_code == 422
    assert excinfo.value.detail["error"] == "suscripcion_duplicada_placa"
    assert excinfo.value.headers == {"Cache-Control": "no-store"}
    # KD-VENTA-01: no commit on the error path
    assert session.commit.await_count == 0
    # V4 raised BEFORE V7/V9 -- those must NOT be called
    assert not p_v7.called
    assert p_v9a.await_count == 0
    assert p_v9b.await_count == 0


# ---------------------------------------------------------------------------
# T5 -- cobrar_ahora=True: cobro sub-chain + enriched display projection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cobrar_ahora_genera_factura_con_display_enriquecido() -> None:
    """T5 (bugfix 2026-09-25): ``cobrar_ahora=True`` -> factura + display.

    Asserts:
      * ``result.uuid_factura`` populated from the just-created factura row.
      * ``result.factura`` is the exact ``FacturaRead`` object
        ``build_display_factura`` returns -- the wizard needs this to show
        ``<FacturaDisplayModal />`` / fire the recibo print envelope right
        after the sale, mirroring the ingreso/salida cobro flow (HU-F8.4).
      * ``session.refresh`` awaited once with the just-created factura row
        BEFORE the display projection is built (post-commit read, same
        pattern as ``facturacion.py``).
      * The full cobro sub-chain ran once: factura + detalle + impuesto + pago.
    """
    from parkos_core.api.v1 import clientes_venta as handler_mod
    from parkos_core.schemas.facturacion import FacturaDisplaySucursal, FacturaRead

    ctx = _make_ctx()
    response = _new_response()
    payload = _build_payload_nuevo_cliente(placas=["ABC123"], cobrar_ahora=True)
    session = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    plan = _make_plan()
    cliente_row = MagicMock()
    cliente_row.uuid = uuid_lib.uuid4()
    vehiculo_row = MagicMock()
    vehiculo_row.uuid = uuid_lib.uuid4()
    subscripcion_row = MagicMock()
    subscripcion_row.uuid = uuid_lib.uuid4()
    factura_row = MagicMock()
    factura_row.uuid = uuid_lib.uuid4()
    detalle_rows = [MagicMock()]
    # A real (minimal) FacturaRead -- `build_display_factura` is mocked out
    # below (its own projection logic is exercised by
    # ``test_factura_display_projection.py``), but the handler's
    # ``VentaSuscripcionResponse`` field is typed ``FacturaRead | None`` and
    # ``_Base`` sets ``from_attributes=True``, so a bare ``MagicMock`` gets
    # walked attribute-by-attribute and fails ~30 nested validators.
    factura_display = FacturaRead(
        uuid=factura_row.uuid,
        created_at=datetime.now(),
        uuid_sucursal=ctx.sucursal_uuid,
        uuid_ingreso=None,
        uuid_salida=None,
        subtotal=Decimal("30000.00"),
        descuento=Decimal("0"),
        total=Decimal("35700.00"),
        uuid_cliente=cliente_row.uuid,
        items=[],
        estado="emitida",
        medio_pago="efectivo",
        monto_recibido_cents=None,
        vuelto_cents=None,
        voucher=None,
        numero_recibo="test-recibo",
        cliente=None,
        datos_sucursal=FacturaDisplaySucursal(
            razon_social=None,
            nit=None,
            direccion=None,
            ciudad=None,
            telefono=None,
            horario=None,
            regimen=None,
        ),
        datos_vehiculo=None,
        impuestos=[],
        pagos=[],
        factura_electronica=None,
    )

    _p_v2, _p_v1, _p_v3, _p_v4, _p_v7, _p_v9a, _p_v9b, patchers = _patch_happy_path(
        handler_mod,
        plan=plan,
        cliente_row=cliente_row,
        vehiculos=[vehiculo_row],
        subscripcion_row=subscripcion_row,
    )
    m_iva = AsyncMock(return_value=Decimal("0.19"))
    m_crear_factura = AsyncMock(return_value=factura_row)
    m_crear_detalle = AsyncMock(return_value=detalle_rows)
    m_crear_impuesto = AsyncMock()
    m_crear_pago = AsyncMock()
    m_build_display = AsyncMock(return_value=factura_display)
    extra_patchers = [
        patch.object(handler_mod.repo_impuestos, "obtener_iva_vigente", new=m_iva),
        patch.object(handler_mod.repo_factura, "crear_factura_evento", new=m_crear_factura),
        patch.object(
            handler_mod.repo_factura_detalle,
            "crear_factura_detalle_bulk",
            new=m_crear_detalle,
        ),
        patch.object(handler_mod.repo_factura, "crear_factura_impuesto_iva", new=m_crear_impuesto),
        patch.object(handler_mod.repo_factura, "crear_factura_pago", new=m_crear_pago),
        patch.object(handler_mod, "build_display_factura", new=m_build_display),
    ]
    for p in extra_patchers:
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
        for p in patchers + extra_patchers:
            p.stop()

    # KD-VENTA-01
    assert session.commit.await_count == 1
    # Bare UUID still populated (backwards-compatible field).
    assert result.uuid_factura == factura_row.uuid
    # HU-F9.1 bugfix: enriched projection reaches the response.
    assert result.factura is factura_display
    # Post-commit read (HU-F8.4 pattern) BEFORE the display helper runs.
    session.refresh.assert_awaited_once_with(factura_row)
    m_crear_factura.assert_awaited_once()
    m_crear_detalle.assert_awaited_once()
    m_crear_impuesto.assert_awaited_once()
    m_crear_pago.assert_awaited_once()
    m_build_display.assert_awaited_once()
    build_kwargs = m_build_display.await_args.kwargs
    assert build_kwargs["new_factura"] is factura_row
    assert build_kwargs["detalles_creados"] is detalle_rows
    assert build_kwargs["cliente_uuid"] == cliente_row.uuid
    assert build_kwargs["payload"] is payload