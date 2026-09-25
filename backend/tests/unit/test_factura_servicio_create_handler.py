"""HU-F8.3 (ajuste 2026-09-25) -- POST /api/v1/facturacion/factura-servicio.

Mirrors ``tests/unit/test_factura_create_handler.py``'s mock-everything
pattern (no DB): mocks the ``AsyncSession`` + repo helpers and drives
``create_factura_servicio`` end-to-end. Asserts:

  - V1 ingreso_no_encontrado (404) when ``session.get(Ingreso, ...)``
    returns ``None``.
  - Tenant scope violation (403) when ``ctx.sucursal_uuid`` differs
    from the ingreso's ``uuid_sucursal``.
  - V5 total_no_coherente (422) when the server-recomputed total
    differs from the payload by more than 0.01 COP.
  - KD-FACT-01 single-commit + correct ``crear_factura_evento`` /
    ``crear_factura_pago`` call args on the happy path -- in
    particular ``uuid_salida=None`` and ``uuid_sesion=ctx.uuid_sesion``
    (never ``None`` when the operator's JWT carries a session).

``build_display_factura`` is mocked directly (NOT exercised for real)
-- ``test_factura_create_handler.py`` already demonstrates that letting
it run against a bare ``AsyncMock`` session crashes on 3 pre-existing
tests (``session.execute(...).scalar_one_or_none()`` resolves as an
un-awaited coroutine through the mock chain) -- a PRE-EXISTING,
unrelated bug in that test file, not touched here.
"""
from __future__ import annotations

import uuid as uuid_lib
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from parkos_core.api.v1.facturacion import create_factura_servicio
from parkos_core.schemas.facturacion import FacturaItemCreate, FacturaServicioCreate


def _make_payload(*, uuid_ingreso: uuid_lib.UUID | None = None) -> FacturaServicioCreate:
    return FacturaServicioCreate(
        uuid_ingreso=uuid_ingreso or uuid_lib.uuid4(),
        items=[
            FacturaItemCreate(
                tipo="servicio",
                concepto="Reimpresión de tiquete",
                cantidad=1,
                valor_unitario=Decimal("2000.00"),
                uuid_tarifa_sucursal=None,
            ),
        ],
        subtotal=Decimal("2000.00"),
        total=Decimal("2380.00"),  # 2000 + 19% IVA
        medio_pago="efectivo",
        referencia=None,
        fe_con_datos=False,
        fe_datos_cliente=None,
    )


def _patch_happy_path(monkeypatch: pytest.MonkeyPatch, *, new_factura: MagicMock) -> dict:
    """Patch every repo helper for the happy path; returns call-arg spies."""
    spies: dict = {}

    async def _obtener_iva(*_a: object, **_k: object) -> Decimal:
        return Decimal("0.19")

    def _validar_items(items: list[FacturaItemCreate]) -> list[FacturaItemCreate]:
        return items

    async def _lock(*_a: object, **_k: object) -> None:
        return None

    def _compute_total(
        items: list[FacturaItemCreate], iva: Decimal, retencion: Decimal
    ) -> Decimal:
        return Decimal("2380.00")

    def _compute_descuento(items: list[FacturaItemCreate]) -> Decimal:
        return Decimal("0")

    def _compute_base_bruta(items: list[FacturaItemCreate]) -> Decimal:
        return Decimal("2000.00")

    async def _crear_factura_evento(session, *, actor_uuid, new_attrs) -> MagicMock:
        spies["new_attrs"] = new_attrs
        return new_factura

    async def _crear_factura_detalle_bulk(*_a: object, **_k: object) -> list:
        return [MagicMock()]

    async def _crear_factura_impuesto_iva(*_a: object, **_k: object) -> MagicMock:
        return MagicMock()

    async def _crear_factura_pago(session, **kwargs: object) -> MagicMock:
        spies["pago_kwargs"] = kwargs
        return MagicMock()

    async def _build_display_factura(*_a: object, **_k: object) -> MagicMock:
        result = MagicMock()
        result.uuid = new_factura.uuid
        result.estado = "emitida"
        return result

    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.obtener_iva_vigente", _obtener_iva
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.validar_items", _validar_items
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.lock_tarifas_sucursal_para_items",
        _lock,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.compute_total", _compute_total
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.compute_descuento",
        _compute_descuento,
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.compute_base_bruta",
        _compute_base_bruta,
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
        "parkos_core.api.v1.facturacion.build_display_factura",
        _build_display_factura,
    )
    return spies


@pytest.mark.asyncio
async def test_create_factura_servicio_happy_path_uuid_sesion_and_uuid_salida_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: 1 commit, uuid_salida=None, uuid_sesion=ctx.uuid_sesion (never None)."""
    uuid_ingreso = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    uuid_sesion = uuid_lib.uuid4()
    payload = _make_payload(uuid_ingreso=uuid_ingreso)

    ingreso = MagicMock()
    ingreso.uuid = uuid_ingreso
    ingreso.uuid_sucursal = uuid_sucursal

    new_factura = MagicMock()
    new_factura.uuid = uuid_lib.uuid4()

    session = AsyncMock()
    session.get = AsyncMock(return_value=ingreso)
    commit_counter = {"n": 0}

    async def _commit() -> None:
        commit_counter["n"] += 1

    session.commit = AsyncMock(side_effect=_commit)

    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.sucursal_uuid = uuid_sucursal
    ctx.issuer_prefix = "operador-"
    ctx.uuid_sesion = uuid_sesion

    response = MagicMock()

    spies = _patch_happy_path(monkeypatch, new_factura=new_factura)

    result = await create_factura_servicio(response, payload, session, ctx, None)

    assert commit_counter["n"] == 1
    assert result.uuid == new_factura.uuid

    # uuid_salida MUST be None (no prod.salidas for a service-only factura).
    assert spies["new_attrs"]["uuid_salida"] is None
    assert spies["new_attrs"]["uuid_ingreso"] == uuid_ingreso
    assert spies["new_attrs"]["uuid_sucursal"] == uuid_sucursal

    # uuid_sesion MUST be ctx.uuid_sesion (never None/omitted) so arqueo's
    # _sum_factura_pagos_by_medio_pago (repo/arqueo.py) picks up this pago.
    assert spies["pago_kwargs"]["uuid_sesion"] == uuid_sesion
    assert spies["pago_kwargs"]["medio_pago"] == "efectivo"
    assert spies["pago_kwargs"]["valor"] == payload.total


@pytest.mark.asyncio
async def test_create_factura_servicio_v1_ingreso_no_encontrado_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V1 404: session.get(Ingreso, ...) returns None -> ingreso_no_encontrado."""
    payload = _make_payload()
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    ctx = MagicMock()
    response = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await create_factura_servicio(response, payload, session, ctx, None)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "ingreso_no_encontrado"
    assert exc_info.value.detail["uuid_ingreso"] == str(payload.uuid_ingreso)
    assert exc_info.value.headers == {"Cache-Control": "no-store"}


@pytest.mark.asyncio
async def test_create_factura_servicio_returns_403_tenant_scope_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tenant scope: operador cross-branch -> 403 (ctx.sucursal_uuid != ingreso.uuid_sucursal)."""
    uuid_ingreso = uuid_lib.uuid4()
    payload = _make_payload(uuid_ingreso=uuid_ingreso)

    ingreso = MagicMock()
    ingreso.uuid = uuid_ingreso
    ingreso.uuid_sucursal = uuid_lib.uuid4()

    session = AsyncMock()
    session.get = AsyncMock(return_value=ingreso)

    ctx = MagicMock()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = uuid_lib.uuid4()  # different branch

    response = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await create_factura_servicio(response, payload, session, ctx, None)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "tenant_scope_violation"


@pytest.mark.asyncio
async def test_create_factura_servicio_v5_total_no_coherente_returns_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V5 422: server-recomputed total differs from payload by >0.01 COP."""
    uuid_ingreso = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    payload = _make_payload(uuid_ingreso=uuid_ingreso)

    ingreso = MagicMock()
    ingreso.uuid = uuid_ingreso
    ingreso.uuid_sucursal = uuid_sucursal

    session = AsyncMock()
    session.get = AsyncMock(return_value=ingreso)

    ctx = MagicMock()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = uuid_sucursal

    response = MagicMock()

    async def _obtener_iva(*_a: object, **_k: object) -> Decimal:
        return Decimal("0.19")

    def _validar_items(items: list[FacturaItemCreate]) -> list[FacturaItemCreate]:
        return items

    def _compute_total(
        items: list[FacturaItemCreate], iva: Decimal, retencion: Decimal
    ) -> Decimal:
        return Decimal("999.00")  # deliberately wrong vs payload.total=2380.00

    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.obtener_iva_vigente", _obtener_iva
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.validar_items", _validar_items
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.compute_total", _compute_total
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_factura_servicio(response, payload, session, ctx, None)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "total_no_coherente"


@pytest.mark.asyncio
async def test_create_factura_servicio_datafono_sin_referencia_returns_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V6 400: medio_pago='datafono' sin referencia -> voucher_requerido."""
    uuid_ingreso = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    payload = FacturaServicioCreate(
        uuid_ingreso=uuid_ingreso,
        items=[
            FacturaItemCreate(
                tipo="servicio",
                concepto="Reimpresión de tiquete",
                cantidad=1,
                valor_unitario=Decimal("2000.00"),
            ),
        ],
        subtotal=Decimal("2000.00"),
        total=Decimal("2380.00"),
        medio_pago="datafono",
        referencia=None,
    )

    ingreso = MagicMock()
    ingreso.uuid = uuid_ingreso
    ingreso.uuid_sucursal = uuid_sucursal

    session = AsyncMock()
    session.get = AsyncMock(return_value=ingreso)

    ctx = MagicMock()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = uuid_sucursal

    response = MagicMock()

    async def _obtener_iva(*_a: object, **_k: object) -> Decimal:
        return Decimal("0.19")

    def _validar_items(items: list[FacturaItemCreate]) -> list[FacturaItemCreate]:
        return items

    def _compute_total(
        items: list[FacturaItemCreate], iva: Decimal, retencion: Decimal
    ) -> Decimal:
        return Decimal("2380.00")

    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.obtener_iva_vigente", _obtener_iva
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.validar_items", _validar_items
    )
    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.repo_factura.compute_total", _compute_total
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_factura_servicio(response, payload, session, ctx, None)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "voucher_requerido"
