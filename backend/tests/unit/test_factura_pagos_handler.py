"""HU-F1.9 / REQ-OPS-062 / T5.11 -- voucher_requerido handler tests.

V7 invariant: ``POST /api/v1/facturacion/factura-pagos`` with
``medio_pago="datafono"`` AND ``referencia=None`` (or empty) → HTTP 400
``{"error": "voucher_requerido", "medio_pago": "datafono"}``.

The Pydantic schema accepts ``referencia=None`` (gating is intentionally
at the handler layer, not at schema validation -- the discriminator
carries ``medio_pago`` context that Pydantic's cross-field validators
cannot easily express for ``Literal`` enums). See
``tests/unit/test_factura_schemas.py::test_factura_pago_adicional_rechaza_datafono_sin_referencia``
for the Pydantic-level contract.

Tests:

- T1: ``datafono`` + ``referencia=None`` → 400 voucher_requerido.
- T2: ``datafono`` + ``referencia=""`` (empty string) → 400 voucher_requerido.
- T3: ``efectivo`` + ``referencia=None`` → 201 (passes V7, INSERT proceeds).
"""
from __future__ import annotations

import uuid as uuid_lib
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from parkos_core.api.v1.facturacion import create_factura_pago
from parkos_core.schemas.facturacion import FacturaPagoAdicionalCreate


def _make_payload(
    medio_pago: str = "efectivo", referencia: str | None = None
) -> FacturaPagoAdicionalCreate:
    """Build a minimal payload with the given medio_pago + referencia."""
    return FacturaPagoAdicionalCreate(
        uuid_factura=uuid_lib.uuid4(),
        medio_pago=medio_pago,  # type: ignore[arg-type]
        valor=Decimal("1000.00"),
        referencia=referencia,
        uuid_sesion=None,
    )


@pytest.mark.asyncio
async def test_post_factura_pagos_datafono_sin_referencia_returns_400() -> None:
    """T1: ``datafono`` + ``referencia=None`` → 400 voucher_requerido.

    Handler MUST short-circuit BEFORE calling ``crear_factura_pago``
    (no INSERT issued). The handler does NOT need a real session.
    """
    response = MagicMock()
    payload = _make_payload(medio_pago="datafono", referencia=None)
    session = AsyncMock()
    ctx = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await create_factura_pago(response, payload, session, ctx, None)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "voucher_requerido"
    assert exc_info.value.detail["medio_pago"] == "datafono"
    assert exc_info.value.headers == {"Cache-Control": "no-store"}

    # KD-FACT-01: handler MUST NOT have committed (V7 fires before any INSERT).
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_post_factura_pagos_datafono_con_referencia_vacia_returns_400() -> None:
    """T2: ``datafono`` + empty-string referencia → 400 voucher_requerido.

    The handler uses ``not payload.referencia`` which treats empty string
    as missing. This matches the disk-side check the repo layer also
    performs. We use :py:meth:`pydantic.BaseModel.model_construct` to
    bypass the StringConstraints ``min_length=1`` schema gate so the
    payload reaches the handler-level guard (the real production
    scenario is a client that omits ``referencia`` entirely, leaving
    ``referencia=None``, but the test also covers the empty-string
    case at the handler boundary).
    """
    from pydantic import ValidationError

    from parkos_core.schemas.facturacion import FacturaPagoAdicionalCreate

    response = MagicMock()
    session = AsyncMock()
    ctx = MagicMock()

    # Pydantic rejects empty string at the schema gate (min_length=1).
    # Verify the schema-level rejection first (defense in depth).
    with pytest.raises(ValidationError):
        FacturaPagoAdicionalCreate(
            uuid_factura=uuid_lib.uuid4(),
            medio_pago="datafono",
            valor=Decimal("1000.00"),
            referencia="",
            uuid_sesion=None,
        )

    # Bypass the schema gate via model_construct to exercise the
    # handler-level guard (the original F1.9 intent — verify the
    # handler rejects empty-string referencia, not just the schema).
    payload = FacturaPagoAdicionalCreate.model_construct(
        uuid_factura=uuid_lib.uuid4(),
        medio_pago="datafono",
        valor=Decimal("1000.00"),
        referencia="",
        uuid_sesion=None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_factura_pago(response, payload, session, ctx, None)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "voucher_requerido"
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_post_factura_pagos_efectivo_passes_voucher_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T3: ``efectivo`` + ``referencia=None`` → passes V7, INSERT proceeds.

    Mocks ``crear_factura_pago`` repo helper; verifies single commit.
    """
    response = MagicMock()
    payload = _make_payload(medio_pago="efectivo", referencia=None)
    session = AsyncMock()

    commit_counter = {"n": 0}

    async def _commit() -> None:
        commit_counter["n"] += 1

    session.commit = AsyncMock(side_effect=_commit)
    ctx = MagicMock()
    ctx.uuid_sesion = None

    new_pago = MagicMock()
    new_pago.uuid = uuid_lib.uuid4()
    new_pago.uuid_factura = payload.uuid_factura
    new_pago.medio_pago = "efectivo"
    new_pago.valor = payload.valor
    new_pago.referencia = None
    new_pago.timestamp_evento = "2026-09-14T10:00:00"

    async def _crear_factura_pago(
        *_args: object, **_kwargs: object
    ) -> MagicMock:
        return new_pago

    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.crear_factura_pago",
        _crear_factura_pago,
    )

    result = await create_factura_pago(response, payload, session, ctx, None)

    # KD-FACT-01: exactly one commit on success.
    assert commit_counter["n"] == 1
    # Response shape returned.
    assert result.uuid == new_pago.uuid
    assert result.uuid_factura == payload.uuid_factura
    assert result.medio_pago == "efectivo"
