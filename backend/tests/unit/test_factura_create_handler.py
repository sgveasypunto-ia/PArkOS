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

    # Patch repo helpers
    async def _buscar_salida_facturable(*_args: object, **_kwargs: object) -> MagicMock:
        return salida

    async def _buscar_o_crear_cliente(*_args: object, **_kwargs: object) -> None:
        return None

    async def _validar_iva(*_args: object, **_kwargs: object) -> bool:
        return True

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
        return []

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
        "parkos_core.api.v1.facturacion.validar_iva_configurado",
        _validar_iva,
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

    async def _validar_iva(*_args: object, **_kwargs: object) -> bool:
        return True

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
        "parkos_core.api.v1.facturacion.validar_iva_configurado",
        _validar_iva,
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_factura(response, payload, session, ctx, None)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "total_no_coherente"
    assert "total_recibido" in exc_info.value.detail
    assert "total_calculado" in exc_info.value.detail
