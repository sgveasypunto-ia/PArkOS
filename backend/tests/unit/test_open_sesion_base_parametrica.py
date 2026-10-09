"""POST /caja-sesion/sesiones — the base de caja comes from the branch parameter.

The operator no longer types the base: the handler resolves it from
``configuracion_caja`` (branch override, then global default) and ignores the
client value. The datafono never starts a shift with a value.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from parkos_core.api.v1 import caja_sesion
from parkos_core.schemas.caja import SesionCreate


class _Stop(Exception):
    """Raised by the fake ``open_session`` so the test never builds a response."""


def _install(monkeypatch: pytest.MonkeyPatch, config: Any) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    async def fake_resolve(_session: Any, _uuid_sucursal: uuid.UUID) -> Any:
        return config

    async def fake_open_session(_session: Any, **kwargs: Any) -> None:
        captured.update(kwargs)
        raise _Stop

    monkeypatch.setattr(caja_sesion, "resolve_efectiva_caja", fake_resolve)
    monkeypatch.setattr(caja_sesion, "open_session", fake_open_session)
    return captured


async def _open(payload: SesionCreate) -> None:
    ctx = SimpleNamespace(actor_uuid=uuid.uuid4())
    with pytest.raises(_Stop):
        await caja_sesion.open_sesion(payload, session=AsyncMock(), ctx=ctx, _claims=None)


def _payload(**overrides: Any) -> SesionCreate:
    return SesionCreate(uuid_sucursal=uuid.uuid4(), uuid_usuario=uuid.uuid4(), **overrides)


@pytest.mark.asyncio
async def test_configured_base_wins_over_the_client_value(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install(monkeypatch, SimpleNamespace(base_inicial_sugerida=Decimal("100000")))

    await _open(
        _payload(valor_inicial_efectivo=Decimal("5"), valor_inicial_datafono=Decimal("999"))
    )

    assert captured["valor_inicial_efectivo"] == 100000.0
    assert captured["valor_inicial_datafono"] == 0.0


@pytest.mark.asyncio
async def test_client_value_is_only_a_fallback_when_nothing_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install(monkeypatch, None)

    await _open(_payload(valor_inicial_efectivo=Decimal("70000")))

    assert captured["valor_inicial_efectivo"] == 70000.0
    assert captured["valor_inicial_datafono"] == 0.0


@pytest.mark.asyncio
async def test_config_without_base_falls_back_to_the_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install(monkeypatch, SimpleNamespace(base_inicial_sugerida=None))

    await _open(_payload())

    assert captured["valor_inicial_efectivo"] == 0.0
