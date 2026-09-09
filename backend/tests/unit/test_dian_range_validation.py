"""test_dian_range_validation.py — T-PR9-003.

``dispatcher.validate_consecutivo_range`` rejects any ``factura_electronica``
whose ``consecutivo`` falls outside its resolution's authorized range and
raises ``alerta tipo_alerta='fe_numbering_exhausted'``. Called at the top of
``dispatch_factura_electronica`` — before ANY HTTP call to the provider.

Uses the same test-double session/factura pattern as ``tests/unit/dian/``
(mocked provider, no real DB — the range check itself is pure Python
comparison logic against mocked rows).
"""
from __future__ import annotations

import os
import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock

import pytest

# Import-time guard (T-PR11-07) — same pattern as tests/unit/dian/conftest.py.
_PREV_DEPLOY = os.environ.get("PARKOS_DEPLOY")
os.environ["PARKOS_DEPLOY"] = "cloud"
try:
    from parkos_core.dian.cloud import dispatcher
finally:
    if _PREV_DEPLOY is None:
        os.environ.pop("PARKOS_DEPLOY", None)
    else:
        os.environ["PARKOS_DEPLOY"] = _PREV_DEPLOY


def _factura(*, consecutivo: int | None, uuid_resolucion_facturacion: uuid_lib.UUID) -> MagicMock:
    factura = MagicMock(name="FacturaElectronica")
    factura.uuid = uuid_lib.uuid4()
    factura.uuid_sucursal = uuid_lib.uuid4()
    factura.uuid_resolucion_facturacion = uuid_resolucion_facturacion
    factura.consecutivo = consecutivo
    return factura


def _session_with_resolucion(
    *, rango_desde: int | None, rango_hasta: int | None
) -> tuple[MagicMock, AsyncMock]:
    session = MagicMock(name="AsyncSession")
    resolucion_row = MagicMock(name="ResolucionFacturacion")
    resolucion_row.rango_desde = rango_desde
    resolucion_row.rango_hasta = rango_hasta

    result = MagicMock(name="Result")
    result.scalar_one_or_none = MagicMock(return_value=resolucion_row)
    session.execute = AsyncMock(return_value=result)

    append_event = AsyncMock(name="append_event")
    return session, append_event


def _session_with_missing_resolucion() -> tuple[MagicMock, AsyncMock]:
    session = MagicMock(name="AsyncSession")
    result = MagicMock(name="Result")
    result.scalar_one_or_none = MagicMock(return_value=None)
    session.execute = AsyncMock(return_value=result)
    append_event = AsyncMock(name="append_event")
    return session, append_event


async def _validate_alert_type_noop(*_args: object, **_kwargs: object) -> None:
    """Bypass the real ``prod.alert_types`` DB lookup — pure unit test."""
    return None


@pytest.mark.asyncio
async def test_in_range_consecutivo_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    resolucion_uuid = uuid_lib.uuid4()
    session, append_event = _session_with_resolucion(rango_desde=1000, rango_hasta=2000)
    monkeypatch.setattr(dispatcher, "append_event", append_event)
    monkeypatch.setattr(dispatcher.alert_types, "validate", _validate_alert_type_noop)

    factura = _factura(consecutivo=1500, uuid_resolucion_facturacion=resolucion_uuid)

    await dispatcher.validate_consecutivo_range(session, factura=factura)

    append_event.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("consecutivo", [999, 2001])
async def test_out_of_range_consecutivo_rejected_and_alerted(
    monkeypatch: pytest.MonkeyPatch, consecutivo: int
) -> None:
    resolucion_uuid = uuid_lib.uuid4()
    session, append_event = _session_with_resolucion(rango_desde=1000, rango_hasta=2000)
    monkeypatch.setattr(dispatcher, "append_event", append_event)
    monkeypatch.setattr(dispatcher.alert_types, "validate", _validate_alert_type_noop)

    factura = _factura(consecutivo=consecutivo, uuid_resolucion_facturacion=resolucion_uuid)

    with pytest.raises(dispatcher.ConsecutivoRangeError):
        await dispatcher.validate_consecutivo_range(session, factura=factura)

    append_event.assert_awaited_once()
    call = append_event.await_args
    assert call.args[1] is dispatcher.Alerta
    attrs = call.args[2]
    assert attrs["tipo_alerta"] == "fe_numbering_exhausted"
    assert attrs["uuid_arqueo"] == factura.uuid
    assert attrs["uuid_alerta_padre"] is None  # chain root


@pytest.mark.asyncio
async def test_missing_resolucion_rejected_and_alerted(monkeypatch: pytest.MonkeyPatch) -> None:
    session, append_event = _session_with_missing_resolucion()
    monkeypatch.setattr(dispatcher, "append_event", append_event)
    monkeypatch.setattr(dispatcher.alert_types, "validate", _validate_alert_type_noop)

    factura = _factura(consecutivo=1500, uuid_resolucion_facturacion=uuid_lib.uuid4())

    with pytest.raises(dispatcher.ConsecutivoRangeError):
        await dispatcher.validate_consecutivo_range(session, factura=factura)

    append_event.assert_awaited_once()
    assert append_event.await_args.args[2]["tipo_alerta"] == "fe_numbering_exhausted"


@pytest.mark.asyncio
async def test_missing_consecutivo_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    resolucion_uuid = uuid_lib.uuid4()
    session, append_event = _session_with_resolucion(rango_desde=1000, rango_hasta=2000)
    monkeypatch.setattr(dispatcher, "append_event", append_event)
    monkeypatch.setattr(dispatcher.alert_types, "validate", _validate_alert_type_noop)

    factura = _factura(consecutivo=None, uuid_resolucion_facturacion=resolucion_uuid)

    with pytest.raises(dispatcher.ConsecutivoRangeError):
        await dispatcher.validate_consecutivo_range(session, factura=factura)


@pytest.mark.asyncio
async def test_unbounded_range_never_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both bounds ``None`` (defensive default) never flags a violation."""
    resolucion_uuid = uuid_lib.uuid4()
    session, append_event = _session_with_resolucion(rango_desde=None, rango_hasta=None)
    monkeypatch.setattr(dispatcher, "append_event", append_event)
    monkeypatch.setattr(dispatcher.alert_types, "validate", _validate_alert_type_noop)

    factura = _factura(consecutivo=123456, uuid_resolucion_facturacion=resolucion_uuid)

    await dispatcher.validate_consecutivo_range(session, factura=factura)
    append_event.assert_not_awaited()
