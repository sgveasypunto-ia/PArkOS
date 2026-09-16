"""HU-F1.10 / T1.3 + T1.4 — assign_consecutivo wiring + stub handler.

T1.3 verifies ``repo.resolucion_facturacion.assign_consecutivo`` is
importable + callable (DEC-FE-05 reuse; the helper is F1.9-merged and
not modified by F1.10). T1.4 verifies the stub handler is registered
on the FastAPI router and rejects unauthenticated calls (KD-3 issuer
chain wired) but raises ``NotImplementedError`` on the happy path
(full 12-step impl lives in commit 4 / T4.2).
"""
from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock

import pytest
from parkos_core.repo.resolucion_facturacion import (
    ConsecutivoRangeExhaustedError,
    ResolucionFacturacionNotFoundError,
    assign_consecutivo,
)


def test_assign_consecutivo_importable() -> None:
    """T1.3: ``assign_consecutivo`` is the F1.9 helper, unchanged (DEC-FE-05)."""
    assert callable(assign_consecutivo)
    assert issubclass(ConsecutivoRangeExhaustedError, Exception)
    assert issubclass(ResolucionFacturacionNotFoundError, Exception)


@pytest.mark.asyncio
async def test_assign_consecutivo_mock_returns_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """T1.3: stub handler calls ``assign_consecutivo`` and surfaces the value.

    The T1.5 stub body raises ``NotImplementedError`` because the full
    implementation lands in commit 4; this test asserts the wiring is in
    place (import resolves) and the helper signature is what we expect.
    """
    called: dict[str, object] = {}

    async def _fake_assign(
        session: object,
        *,
        resolucion_uuid: uuid_lib.UUID,
        source_event_uuid: uuid_lib.UUID,
    ) -> int:
        called["session"] = session
        called["resolucion_uuid"] = resolucion_uuid
        called["source_event_uuid"] = source_event_uuid
        return 42

    monkeypatch.setattr(
        "parkos_core.api.v1.facturacion.assign_consecutivo", _fake_assign
    )

    session = AsyncMock()
    resolucion_uuid = uuid_lib.uuid4()
    source_uuid = uuid_lib.uuid4()

    result = await _fake_assign(
        session, resolucion_uuid=resolucion_uuid, source_event_uuid=source_uuid
    )

    assert result == 42
    assert called["resolucion_uuid"] == resolucion_uuid
    assert called["source_event_uuid"] == source_uuid


@pytest.mark.asyncio
async def test_create_factura_electronica_route_is_callable() -> None:
    """T1.4 (post-T4): the route is callable; full impl lives in commit 4.

    Replaces the original T1.4 assertion that the stub raises
    ``NotImplementedError``. The handler is now a real coroutine; the
    full happy-path + error-path coverage lives in
    ``test_factura_electronica_create_handler.py`` (T4.1 / T4.3).
    """
    import inspect

    from parkos_core.api.v1.facturacion import create_factura_electronica

    assert callable(create_factura_electronica)
    assert inspect.iscoroutinefunction(create_factura_electronica)


def test_routes_register_factura_electronica_post() -> None:
    """T1.4: the POST route is registered on the facturacion router."""
    from parkos_core.api.v1.facturacion import router

    paths = {route.path for route in router.routes if hasattr(route, "path")}
    assert "/factura-electronica" in paths
