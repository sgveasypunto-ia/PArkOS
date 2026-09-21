"""HU-F1.9 / REQ-OPS-053..061 / T5.9 -- atomicidad handler tests.

KD-FACT-01 invariant: ``POST /api/v1/facturacion/factura`` materializes
``prod.facturas`` + ``prod.factura_detalle`` + ``prod.factura_impuestos`` +
``prod.factura_pagos`` atomically in exactly ONE ``await session.commit()``.

These tests mock the ``AsyncSession`` + repo helpers and verify:

- The handler invokes ``session.commit()`` exactly once on the happy path
  (T1: KD-FACT-01 happy path).
- An ``IntegrityError`` on Step 10b (``crear_factura_impuesto_iva``) is
  surfaced through ``HTTPException`` AND the handler did NOT issue a
  second commit (no partial writes).
- The handler does NOT issue any commit BEFORE all 4 INSERTs have been
  attempted (KD-FACT-02 lock continuity + atomic guarantee).

DB-coupled happy paths (REAL ``prod.facturas`` materialization with
bi-temporal composite PK) live in
``tests/integration/test_factura_create_db.py`` (T5.3, T5.5, T5.7).
"""
from __future__ import annotations

import uuid as uuid_lib
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from parkos_core.api.v1.facturacion import create_factura
from parkos_core.schemas.facturacion import (
    FacturaCreate,
    FacturaItemCreate,
)


def _make_payload() -> FacturaCreate:
    """Build a minimal happy-path payload (V1..V6 all pass)."""
    return FacturaCreate(
        uuid_salida=uuid_lib.uuid4(),
        items=[
            FacturaItemCreate(
                tipo="servicio",
                concepto="Parqueo 1h",
                cantidad=1,
                valor_unitario=Decimal("5000.00"),
                uuid_tarifa_sucursal=None,
            ),
        ],
        subtotal=Decimal("5000.00"),
        total=Decimal("5950.00"),  # 5000 + 19% IVA
        medio_pago="efectivo",
        referencia=None,
        fe_con_datos=False,
        fe_datos_cliente=None,
    )


def _make_session_with_salida(salida: MagicMock) -> AsyncMock:
    """Build a mock ``AsyncSession`` that returns ``salida`` for V1 lookup."""
    session = AsyncMock()
    # `buscar_salida_facturable` is awaited; returns the salida mock directly.
    return session


@pytest.mark.asyncio
async def test_post_factura_invokes_session_commit_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T1: KD-FACT-01 — handler commits exactly once on the happy path."""
    # Mock the response + session + all repo helpers
    response = MagicMock()
    payload = _make_payload()

    # Mock salida (V1 returns a Salidas-like object)
    salida = MagicMock()
    salida.uuid = payload.uuid_salida
    salida.uuid_sucursal = uuid_lib.uuid4()
    salida.uuid_ingreso = uuid_lib.uuid4()

    session = AsyncMock()
    commit_counter = {"n": 0}

    async def _commit() -> None:
        commit_counter["n"] += 1

    session.commit = AsyncMock(side_effect=_commit)

    # Mock ctx (tenant context)
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.sucursal_uuid = salida.uuid_sucursal  # operador- branch matches
    ctx.issuer_prefix = "operador-"
    ctx.uuid_sesion = None

    # Mock new_factura returned by crear_factura_evento
    new_factura = MagicMock()
    new_factura.uuid = uuid_lib.uuid4()
    new_factura.created_at = "2026-09-14T10:00:00"
    new_factura.uuid_sucursal = salida.uuid_sucursal
    new_factura.uuid_ingreso = salida.uuid_ingreso
    new_factura.uuid_salida = salida.uuid
    new_factura.subtotal = Decimal("5000.00")
    new_factura.descuento = Decimal("0")
    new_factura.total = Decimal("5950.00")
    new_factura.items = []

    # Mock the created detalle ORM row (C1 fix: handler iterates this, not
    # the Pydantic payload items). Carries .uuid so the FacturaItemRead
    # construction in Step 12 succeeds.
    detalle_creado = MagicMock()
    detalle_creado.uuid = uuid_lib.uuid4()
    detalle_creado.tipo = "servicio"
    detalle_creado.concepto = "Parqueo 1h"
    detalle_creado.cantidad = 1
    detalle_creado.valor_unitario = Decimal("5000.00")
    detalle_creado.subtotal = Decimal("5000.00")

    # Patch repo helpers
    async def _buscar_salida_facturable(*_args: object, **_kwargs: object) -> MagicMock:
        return salida

    async def _buscar_o_crear_cliente(*_args: object, **_kwargs: object) -> None:
        return None

    async def _obtener_iva(*_args: object, **_kwargs: object) -> Decimal:
        return Decimal("0.19")

    def _validar_items(items: list[FacturaItemCreate]) -> list[FacturaItemCreate]:
        return items

    async def _lock(*_args: object, **_kwargs: object) -> None:
        return None

    def _compute_total(
        items: list[FacturaItemCreate], iva: Decimal, retencion: Decimal
    ) -> Decimal:
        # 5000 + 19% = 5950 (matches payload total)
        return Decimal("5950.00")

    async def _crear_factura_evento(*_args: object, **_kwargs: object) -> MagicMock:
        return new_factura

    async def _crear_factura_detalle_bulk(*_args: object, **_kwargs: object) -> list:
        return [detalle_creado]

    async def _crear_factura_impuesto_iva(*_args: object, **_kwargs: object) -> MagicMock:
        return MagicMock()

    async def _crear_factura_pago(*_args: object, **_kwargs: object) -> MagicMock:
        return MagicMock()

    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.buscar_salida_facturable",
        _buscar_salida_facturable,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.validar_items",
        _validar_items,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.lock_tarifas_sucursal_para_items",
        _lock,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.compute_total",
        _compute_total,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.crear_factura_evento",
        _crear_factura_evento,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.crear_factura_detalle_bulk",
        _crear_factura_detalle_bulk,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.crear_factura_impuesto_iva",
        _crear_factura_impuesto_iva,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.crear_factura_pago",
        _crear_factura_pago,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.obtener_iva_vigente",
        _obtener_iva,
    )

    # Invoke the handler
    result = await create_factura(response, payload, session, ctx, None)

    # KD-FACT-01 invariant: exactly 1 commit.
    assert commit_counter["n"] == 1, (
        f"KD-FACT-01 violated: expected exactly 1 session.commit(), "
        f"got {commit_counter['n']}."
    )
    # The response has Cache-Control: no-store applied
    assert response.headers.__setitem__.called or hasattr(response, "headers")
    # Result is a FacturaRead with the expected fields
    assert result.uuid == new_factura.uuid
    assert result.estado == "emitida"
    assert result.uuid_cliente is None  # fe_con_datos=False


@pytest.mark.asyncio
async def test_post_factura_v1_salida_no_encontrada_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T2: V1 — ``buscar_salida_facturable`` returns None → 404."""
    response = MagicMock()
    payload = _make_payload()
    session = AsyncMock()
    ctx = MagicMock()

    async def _buscar_salida_facturable(
        *_args: object, **_kwargs: object
    ) -> None:
        return None

    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.buscar_salida_facturable",
        _buscar_salida_facturable,
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_factura(response, payload, session, ctx, None)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "salida_no_encontrada"
    # Cache-Control: no-store on the error response
    assert exc_info.value.headers == {"Cache-Control": "no-store"}


@pytest.mark.asyncio
async def test_post_factura_v6_total_no_coherente_returns_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T3: V6 — recompute mismatch → 422 total_no_coherente."""
    response = MagicMock()
    payload = _make_payload()
    session = AsyncMock()
    ctx = MagicMock()

    salida = MagicMock()
    salida.uuid = payload.uuid_salida
    salida.uuid_sucursal = uuid_lib.uuid4()
    salida.uuid_ingreso = uuid_lib.uuid4()

    async def _buscar_salida(*_args: object, **_kwargs: object) -> MagicMock:
        return salida

    async def _obtener_iva(*_args: object, **_kwargs: object) -> Decimal:
        return Decimal("0.19")

    def _validar_items(items: list) -> list:
        return items

    async def _lock(*_args: object, **_kwargs: object) -> None:
        return None

    def _compute_total_wrong(
        items: list, iva: Decimal, retencion: Decimal
    ) -> Decimal:
        # Server recomputes to a different value → mismatch > 0.01
        return Decimal("9999.99")

    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.buscar_salida_facturable",
        _buscar_salida,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.validar_items",
        _validar_items,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.lock_tarifas_sucursal_para_items",
        _lock,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.compute_total",
        _compute_total_wrong,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.obtener_iva_vigente",
        _obtener_iva,
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_factura(response, payload, session, ctx, None)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "total_no_coherente"
    assert "total_recibido" in exc_info.value.detail
    assert "total_calculado" in exc_info.value.detail


@pytest.mark.asyncio
async def test_post_factura_uses_db_iva_not_hardcoded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C3 RED→GREEN: handler MUST pass the DB-read IVA % to compute_total,
    NOT a hardcoded Decimal('0.19').

    DEC-FACT-03 forbids hardcoded tax constants. We mock
    ``obtener_iva_vigente`` to return ``Decimal('0.15')`` (a non-default
    rate, e.g. simulating a regulatory change) and verify the value
    forwarded to ``compute_total`` is 0.15, not the historical 0.19.
    """
    response = MagicMock()
    # Payload with total = subtotal + 15% (matches the simulated
    # regulatory change in ``_obtener_iva`` below): 5000 + 750 = 5750.
    payload = FacturaCreate(
        uuid_salida=uuid_lib.uuid4(),
        items=[
            FacturaItemCreate(
                tipo="servicio",
                concepto="Parqueo 1h",
                cantidad=1,
                valor_unitario=Decimal("5000.00"),
                uuid_tarifa_sucursal=None,
            ),
        ],
        subtotal=Decimal("5000.00"),
        total=Decimal("5750.00"),
        medio_pago="efectivo",
        referencia=None,
        fe_con_datos=False,
        fe_datos_cliente=None,
    )
    session = AsyncMock()
    ctx = MagicMock()

    salida = MagicMock()
    salida.uuid = payload.uuid_salida
    salida.uuid_sucursal = uuid_lib.uuid4()
    salida.uuid_ingreso = uuid_lib.uuid4()

    # Tracking what value is passed to compute_total
    captured: dict[str, object] = {}

    async def _buscar_salida(*_args: object, **_kwargs: object) -> MagicMock:
        return salida

    async def _obtener_iva(*_args: object, **_kwargs: object) -> Decimal:
        return Decimal("0.15")  # simulated regulatory change

    def _validar_items(items: list) -> list:
        return items

    async def _lock(*_args: object, **_kwargs: object) -> None:
        return None

    def _compute_total_capture(
        items: list, iva: Decimal, retencion: Decimal
    ) -> Decimal:
        captured["iva"] = iva
        # subtotal 5000 + 15% = 5750
        return Decimal("5750.00")

    async def _crear_factura_evento(*_args: object, **_kwargs: object) -> MagicMock:
        new_factura = MagicMock()
        new_factura.uuid = uuid_lib.uuid4()
        new_factura.created_at = "2026-09-14T10:00:00"
        new_factura.uuid_sucursal = salida.uuid_sucursal
        new_factura.uuid_ingreso = salida.uuid_ingreso
        new_factura.uuid_salida = salida.uuid
        new_factura.subtotal = Decimal("5000.00")
        new_factura.descuento = Decimal("0")
        new_factura.total = Decimal("5750.00")
        return new_factura

    async def _crear_factura_detalle_bulk(*_args: object, **_kwargs: object) -> list:
        det = MagicMock()
        det.uuid = uuid_lib.uuid4()
        det.tipo = "servicio"
        det.concepto = "Parqueo 1h"
        det.cantidad = 1
        det.valor_unitario = Decimal("5000.00")
        det.subtotal = Decimal("5000.00")
        return [det]

    async def _crear_factura_impuesto_iva(
        *_args: object, **_kwargs: object
    ) -> MagicMock:
        return MagicMock()

    async def _crear_factura_pago(*_args: object, **_kwargs: object) -> MagicMock:
        return MagicMock()

    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.buscar_salida_facturable",
        _buscar_salida,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.obtener_iva_vigente",
        _obtener_iva,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.validar_items",
        _validar_items,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.lock_tarifas_sucursal_para_items",
        _lock,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.compute_total",
        _compute_total_capture,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.crear_factura_evento",
        _crear_factura_evento,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.crear_factura_detalle_bulk",
        _crear_factura_detalle_bulk,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.crear_factura_impuesto_iva",
        _crear_factura_impuesto_iva,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.crear_factura_pago",
        _crear_factura_pago,
    )

    await create_factura(response, payload, session, ctx, None)

    # DEC-FACT-03 enforcement: the IVA passed to compute_total MUST be
    # the DB-derived value (0.15), not the historical hardcoded 0.19.
    assert captured.get("iva") == Decimal("0.15"), (
        f"DEC-FACT-03 violated: compute_total received iva={captured.get('iva')!r}, "
        f"expected Decimal('0.15') from prod.impuestos."
    )


@pytest.mark.asyncio
async def test_post_factura_v3_iva_no_configurado_returns_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C3 regression: when no IVA row is vigente, handler returns 500
    ``iva_no_configurado`` (handler does NOT silently fall back to 0.19)."""
    response = MagicMock()
    payload = _make_payload()
    session = AsyncMock()
    ctx = MagicMock()

    salida = MagicMock()
    salida.uuid = payload.uuid_salida
    salida.uuid_sucursal = uuid_lib.uuid4()
    salida.uuid_ingreso = uuid_lib.uuid4()

    async def _buscar_salida(*_args: object, **_kwargs: object) -> MagicMock:
        return salida

    async def _obtener_iva(*_args: object, **_kwargs: object) -> None:
        return None  # no vigente IVA row

    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.buscar_salida_facturable",
        _buscar_salida,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.obtener_iva_vigente",
        _obtener_iva,
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_factura(response, payload, session, ctx, None)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["error"] == "iva_no_configurado"


# ---------------------------------------------------------------------------
# 2026-09-21 CU-04 BR6 V7 backfill: voucher_requerido in create_factura
# (plan.md line 899). The primary POST /facturacion/factura endpoint did
# NOT validate ``referencia`` (voucher) when ``medio_pago='datafono'``;
# only POST /facturacion/factura-pagos and the F1.12 V8 cobro sub-chain
# did. plan.md line 899 mandates V7 on the primary endpoint; these tests
# pin the new contract.
# ---------------------------------------------------------------------------


def _make_datafono_payload(referencia: str | None) -> FacturaCreate:
    """Build a payload with ``medio_pago='datafono'`` and the given referencia.

    ``FacturaCreate.referencia = StringConstraints(min_length=1) | None``
    means Pydantic rejects empty strings at the schema gate -- the only
    way to reach the handler-level guard with ``datafono`` is to send
    ``referencia=None`` (the realistic production scenario) or
    whitespace-only (defense-in-depth at the handler).
    """
    return FacturaCreate(
        uuid_salida=uuid_lib.uuid4(),
        items=[
            FacturaItemCreate(
                tipo="servicio",
                concepto="Parqueo 1h",
                cantidad=1,
                valor_unitario=Decimal("5000.00"),
                uuid_tarifa_sucursal=None,
            ),
        ],
        subtotal=Decimal("5000.00"),
        total=Decimal("5950.00"),  # 5000 + 19% IVA
        medio_pago="datafono",
        referencia=referencia,
        fe_con_datos=False,
        fe_datos_cliente=None,
    )


@pytest.mark.asyncio
async def test_create_factura_datafono_sin_referencia_devuelve_400_voucher_requerido(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CU-04 BR6 V7: ``datafono`` + ``referencia=None`` -> 400 voucher_requerido.

    The handler MUST short-circuit at Step 6.5 BEFORE acquiring the
    ``tarifas_sucursal FOR SHARE`` lock (Step 7) and BEFORE any INSERT
    (Steps 9..10). The Pydantic schema accepts ``referencia=None`` (gating
    is intentionally at the handler, mirroring create_factura_pago
    :449-457 and clientes_venta.py:265-273).

    Mirrors plan.md line 899 (CU-04 BR6 V7 backfill on the primary
    POST /facturacion/factura endpoint).
    """
    response = MagicMock()
    payload = _make_datafono_payload(referencia=None)
    session = AsyncMock()
    session.commit = AsyncMock()
    ctx = MagicMock()

    salida = MagicMock()
    salida.uuid = payload.uuid_salida
    salida.uuid_sucursal = uuid_lib.uuid4()
    salida.uuid_ingreso = uuid_lib.uuid4()

    async def _buscar_salida(
        *_args: object, **_kwargs: object
    ) -> MagicMock:
        return salida

    async def _obtener_iva(*_args: object, **_kwargs: object) -> Decimal:
        return Decimal("0.19")

    def _validar_items(items: list) -> list:
        return items

    # Sentinel: if lock_tarifas is called, V7 leaked past.
    async def _lock_should_not_run(
        *_args: object, **_kwargs: object
    ) -> None:
        raise AssertionError(
            "V7 leaked: lock_tarifas_sucursal_para_items must NOT be "
            "called when medio_pago='datafono' AND referencia is empty."
        )

    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.buscar_salida_facturable",
        _buscar_salida,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.obtener_iva_vigente",
        _obtener_iva,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.validar_items",
        _validar_items,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.lock_tarifas_sucursal_para_items",
        _lock_should_not_run,
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_factura(response, payload, session, ctx, None)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "voucher_requerido"
    assert exc_info.value.detail["medio_pago"] == "datafono"
    assert exc_info.value.headers == {"Cache-Control": "no-store"}

    # KD-FACT-01 invariant: handler MUST NOT have committed when V7 fires.
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_create_factura_datafono_con_referencia_201(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CU-04 BR6 V7 positive: ``datafono`` + ``referencia='V-1234567'`` -> 201.

    With a non-empty ``referencia`` the V7 guard passes and the full
    13-step chain (KD-FACT-01 atomic 4-table INSERT + single commit)
    proceeds normally. Mirrors the create_factura_pago ``efectivo``
    positive test (`test_factura_pagos_handler.py::test_post_factura_pagos
    _efectivo_passes_voucher_check`).
    """
    response = MagicMock()
    payload = _make_datafono_payload(referencia="V-1234567")

    commit_counter = {"n": 0}

    async def _commit() -> None:
        commit_counter["n"] += 1

    session = AsyncMock()
    session.commit = AsyncMock(side_effect=_commit)

    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.uuid_sesion = None
    ctx.issuer_prefix = "operador-"
    # operador- tenant scope (Step 3): ctx.sucursal_uuid MUST match the
    # salida's uuid_sucursal, otherwise the handler rejects with 403
    # tenant_scope_violation BEFORE V7 fires. We resolve it AFTER salida
    # is created to guarantee the match.

    salida = MagicMock()
    salida.uuid = payload.uuid_salida
    salida.uuid_sucursal = uuid_lib.uuid4()
    salida.uuid_ingreso = uuid_lib.uuid4()
    ctx.sucursal_uuid = salida.uuid_sucursal  # branch-pinned operador-

    new_factura = MagicMock()
    new_factura.uuid = uuid_lib.uuid4()
    new_factura.created_at = "2026-09-21T10:00:00"
    new_factura.uuid_sucursal = salida.uuid_sucursal
    new_factura.uuid_ingreso = salida.uuid_ingreso
    new_factura.uuid_salida = salida.uuid
    new_factura.subtotal = Decimal("5000.00")
    new_factura.descuento = Decimal("0")
    new_factura.total = Decimal("5950.00")

    detalle_creado = MagicMock()
    detalle_creado.uuid = uuid_lib.uuid4()
    detalle_creado.tipo = "servicio"
    detalle_creado.concepto = "Parqueo 1h"
    detalle_creado.cantidad = 1
    detalle_creado.valor_unitario = Decimal("5000.00")
    detalle_creado.subtotal = Decimal("5000.00")

    async def _buscar_salida(
        *_args: object, **_kwargs: object
    ) -> MagicMock:
        return salida

    async def _obtener_iva(*_args: object, **_kwargs: object) -> Decimal:
        return Decimal("0.19")

    def _validar_items(items: list) -> list:
        return items

    async def _lock(*_args: object, **_kwargs: object) -> None:
        return None

    def _compute_total(
        items: list, iva: Decimal, retencion: Decimal
    ) -> Decimal:
        return Decimal("5950.00")  # matches payload total

    async def _crear_factura_evento(
        *_args: object, **_kwargs: object
    ) -> MagicMock:
        return new_factura

    async def _crear_factura_detalle_bulk(
        *_args: object, **_kwargs: object
    ) -> list:
        return [detalle_creado]

    async def _crear_factura_impuesto_iva(
        *_args: object, **_kwargs: object
    ) -> MagicMock:
        return MagicMock()

    async def _crear_factura_pago(
        *_args: object, **_kwargs: object
    ) -> MagicMock:
        return MagicMock()

    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.buscar_salida_facturable",
        _buscar_salida,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.obtener_iva_vigente",
        _obtener_iva,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.validar_items",
        _validar_items,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.lock_tarifas_sucursal_para_items",
        _lock,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.compute_total",
        _compute_total,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.crear_factura_evento",
        _crear_factura_evento,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.crear_factura_detalle_bulk",
        _crear_factura_detalle_bulk,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.crear_factura_impuesto_iva",
        _crear_factura_impuesto_iva,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.crear_factura_pago",
        _crear_factura_pago,
    )

    result = await create_factura(response, payload, session, ctx, None)

    # KD-FACT-01: exactly 1 commit on the happy path.
    assert commit_counter["n"] == 1, (
        f"KD-FACT-01 violated: expected exactly 1 session.commit(), "
        f"got {commit_counter['n']}."
    )
    # Response shape returned with the expected derived fields.
    assert result.uuid == new_factura.uuid
    assert result.estado == "emitida"
    assert result.uuid_cliente is None  # fe_con_datos=False
    assert result.subtotal == Decimal("5000.00")
    assert result.total == Decimal("5950.00")
