"""test_dispatcher.py — DIAN dispatcher paths (T-PR11-08 + T-PR11-09).

End-to-end walks through the state machine in
:func:`parkos_core.dian.cloud.dispatcher.dispatch_factura_electronica`,
driven by ``httpx.MockTransport`` against the REAL :class:`FactusProvider`
HTTP surface (URL shapes, Bearer header, JSON parsing) so the adapter
and the state machine are exercised together.

T-PR11-08 — 3 success paths: ``aceptado``, ``rechazado``, timeout.
T-PR11-09 — 3 rejection paths: ``POST`` 4xx, ``GET`` 5xx, missing auth.

No database: the ``AsyncSession`` is a double (``session.execute`` is an
``AsyncMock`` whose *return value* is a plain ``MagicMock``).

Per the ER 4FN canon (``modelo_datos_er.mmd`` lines 700-702) the DIAN
outcome lives in ``envio_dian.respuesta_proveedor`` JSONB; there is no
``estado`` / ``motivo_rechazo`` / ``reportado_dian`` column. ``estado``
on the ORM is the bi-temporal flag.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from parkos_core.models.L_W.alerta import Alerta
from parkos_core.models.L_W.envio_dian import EnvioDian

# ``conftest.py`` handles the ``PARKOS_DEPLOY`` save/restore for the
# dispatcher's import-time guard (T-PR11-07) and re-exports the shared
# constants + ``dispatcher`` + the rejection-transport + sleep-shim
# + test-double helpers. ``token_path`` is auto-injected as a fixture.
from .conftest import (
    _HEX,
    ACTOR_UUID,
    FACTURA_UUID,
    PROVIDER_URL,
    dispatcher,
    factura_row,
    install_append_event_mock,
    install_dian_timeout_env,
    install_poll_sleep_shim,
    install_rejection_transport,
    mock_session_with_factura,
)

# ---------------------------------------------------------------------------
# Helpers (success-path only; token_path is the conftest fixture)
# ---------------------------------------------------------------------------


def _install_transport(
    monkeypatch: pytest.MonkeyPatch, *, track_id: str, poll_body: dict[str, Any]
) -> list[httpx.Request]:
    """Route ``FactusProvider``'s client through ``MockTransport``.

    Patches the documented ``session_factory`` seam (via the class-level
    default) so the provider's own URL/header/JSON code still runs.
    Returns the list the handler records every request into.
    """
    seen: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"trackId": track_id})
        return httpx.Response(200, json=poll_body)

    transport = httpx.MockTransport(_handler)
    monkeypatch.setattr(
        dispatcher.FactusProvider,
        "_default_session_factory",
        lambda _self: httpx.AsyncClient(transport=transport),
    )
    return seen


async def _dispatch(session: MagicMock, token_path: Path) -> EnvioDian:
    return await dispatcher.dispatch_factura_electronica(
        session,
        uuid_factura_electronica=FACTURA_UUID,
        actor_uuid=ACTOR_UUID,
        dian_provider_url=PROVIDER_URL,
        dian_token_path=token_path,
    )


# ---------------------------------------------------------------------------
# 1. aceptado
# ---------------------------------------------------------------------------


async def test_dispatcher_accepts_and_writes_envio_dian(
    monkeypatch: pytest.MonkeyPatch, token_path: Path
) -> None:
    """trackId -> poll -> ``aceptado``: cufe stamped, no alerta emitted."""
    seen = _install_transport(
        monkeypatch,
        track_id="track-123",
        poll_body={"estado": "aceptado", "cufe": "cufe-abc-123"},
    )
    append_event = AsyncMock(name="append_event")
    monkeypatch.setattr(dispatcher, "append_event", append_event)
    session = mock_session_with_factura(factura_row())

    envio = await _dispatch(session, token_path)

    assert session.add.call_count == 1
    assert isinstance(session.add.call_args.args[0], EnvioDian)
    assert envio is session.added[0]
    assert envio.respuesta_proveedor["estado_dian"] == dispatcher.ESTADO_ACEPTADO
    assert envio.cufe == "cufe-abc-123"
    assert envio.payload["track_id"] == "track-123"
    assert len(envio.payload["xml_sha256"]) == 64
    assert set(envio.payload["xml_sha256"]) <= _HEX
    # Alerta is a failure-only side effect.
    append_event.assert_not_called()
    assert [r.method for r in seen] == ["POST", "GET"]
    assert seen[0].url.path == "/api/ubl2.1"
    assert seen[1].url.path == "/api/ubl2.1/track-123"
    assert seen[0].headers["Authorization"] == "Bearer test-bearer-token"


# ---------------------------------------------------------------------------
# 2. rechazado
# ---------------------------------------------------------------------------


async def test_dispatcher_rechazado_writes_envio_dian_and_alerta(
    monkeypatch: pytest.MonkeyPatch, token_path: Path
) -> None:
    """``rechazado``: motive captured + one ``dian_rechazada`` alerta chain root."""
    seen = _install_transport(
        monkeypatch,
        track_id="track-456",
        poll_body={"estado": "rechazado", "motivo_rechazo": "bad NIT"},
    )
    append_event = AsyncMock(name="append_event")
    monkeypatch.setattr(dispatcher, "append_event", append_event)
    session = mock_session_with_factura(factura_row())

    envio = await _dispatch(session, token_path)

    assert envio.respuesta_proveedor["estado_dian"] == dispatcher.ESTADO_RECHAZADO
    assert envio.respuesta_proveedor["motivo_rechazo"] == "bad NIT"
    assert envio.cufe is None

    append_event.assert_awaited_once()
    call = append_event.await_args
    assert call.args[1] is Alerta
    attrs = call.args[2]
    assert attrs["tipo_alerta"] == "dian_rechazada"
    assert attrs["uuid_arqueo"] == envio.uuid
    assert attrs["uuid_alerta_padre"] is None  # chain root
    assert call.kwargs.get("chain_hash", False) is False
    assert [r.method for r in seen] == ["POST", "GET"]


# ---------------------------------------------------------------------------
# 3. timeout (retries exhausted)
# ---------------------------------------------------------------------------


async def test_dispatcher_timeout_retries_then_alerts(
    monkeypatch: pytest.MonkeyPatch, token_path: Path
) -> None:
    """``en_proceso`` forever: retries exhaust -> timeout + ``dian_timeout`` alerta."""
    seen = _install_transport(
        monkeypatch, track_id="track-789", poll_body={"estado": "en_proceso"}
    )
    append_event = AsyncMock(name="append_event")
    monkeypatch.setattr(dispatcher, "append_event", append_event)
    monkeypatch.setenv("PARKOS_DIAN_TIMEOUT_S", "0.001")
    monkeypatch.setenv("PARKOS_DIAN_RETRY_MAX", "2")

    # One shim collapses BOTH sleeps the dispatcher awaits: the 2s poll
    # interval and the 60s/300s backoff_5xx waits. Sleeping 10ms of real
    # time (vs. the 1ms poll budget) guarantees each poll window closes
    # after exactly one GET, so the request count stays deterministic.
    real_sleep = asyncio.sleep

    async def _shim_sleep(_seconds: float) -> None:
        await real_sleep(0.01)

    monkeypatch.setattr(asyncio, "sleep", _shim_sleep)
    session = mock_session_with_factura(factura_row())

    envio = await _dispatch(session, token_path)

    assert envio.respuesta_proveedor["estado_dian"] == dispatcher.ESTADO_TIMEOUT
    assert envio.respuesta_proveedor["motivo_rechazo"] == "dian_poll_timeout"
    assert envio.cufe is None

    append_event.assert_awaited_once()
    attrs = append_event.await_args.args[2]
    assert attrs["tipo_alerta"] == "dian_timeout"
    assert attrs["uuid_arqueo"] == envio.uuid
    # 1 POST + 1 initial-window GET + PARKOS_DIAN_RETRY_MAX (2) retry GETs.
    assert [r.method for r in seen] == ["POST", "GET", "GET", "GET"]


# ---------------------------------------------------------------------------
# T-PR11-09 — 3 rejection paths (POST 4xx, poll 5xx, missing auth)
# ---------------------------------------------------------------------------


async def test_dispatcher_post_4xx_writes_rechazado(
    monkeypatch: pytest.MonkeyPatch, token_path: Path
) -> None:
    """``POST /api/ubl2.1`` 4xx → ``HTTPStatusError`` → ``rechazado`` (no trackId)."""
    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad NIT format"})

    seen = install_rejection_transport(monkeypatch, _handler)
    append_event = AsyncMock(name="append_event")
    monkeypatch.setattr(dispatcher, "append_event", append_event)
    session = mock_session_with_factura(factura_row())

    envio = await _dispatch(session, token_path)

    assert envio.respuesta_proveedor["estado_dian"] == dispatcher.ESTADO_RECHAZADO
    motivo = envio.respuesta_proveedor["motivo_rechazo"]
    assert motivo is not None
    assert motivo.startswith("send:")
    assert envio.cufe is None

    append_event.assert_awaited_once()
    attrs = append_event.await_args.args[2]
    assert attrs["tipo_alerta"] == "dian_rechazada"
    assert attrs["uuid_arqueo"] == envio.uuid
    assert attrs["uuid_alerta_padre"] is None  # chain root
    assert append_event.await_args.kwargs.get("chain_hash", False) is False

    assert [r.method for r in seen] == ["POST"]
    assert seen[0].url.path == "/api/ubl2.1"


async def test_dispatcher_poll_4xx_writes_rechazado(
    monkeypatch: pytest.MonkeyPatch, token_path: Path
) -> None:
    """``GET /api/ubl2.1/{trackId}`` 5xx → ``rechazado`` (poll loop exits, no retry)."""
    def _handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"trackId": "track-poll-fail"})
        return httpx.Response(500, json={"error": "provider internal"})

    seen = install_rejection_transport(monkeypatch, _handler)
    append_event = AsyncMock(name="append_event")
    monkeypatch.setattr(dispatcher, "append_event", append_event)
    session = mock_session_with_factura(factura_row())

    envio = await _dispatch(session, token_path)

    assert envio.respuesta_proveedor["estado_dian"] == dispatcher.ESTADO_RECHAZADO
    motivo = envio.respuesta_proveedor["motivo_rechazo"]
    assert motivo is not None
    assert motivo.startswith("poll:")
    assert envio.cufe is None

    append_event.assert_awaited_once()
    attrs = append_event.await_args.args[2]
    assert attrs["tipo_alerta"] == "dian_rechazada"
    assert attrs["uuid_arqueo"] == envio.uuid

    # No retry on terminal poll rejection: 1 POST + 1 GET (retry loop only
    # fires on 'en_proceso' past budget, not on a terminal rejection).
    assert [r.method for r in seen] == ["POST", "GET"]
    assert seen[1].url.path == "/api/ubl2.1/track-poll-fail"


async def test_dispatcher_missing_auth_writes_rechazado(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Empty token file → provider returns 401 → ``rechazado`` (send: motive)."""
    token_path = tmp_path / "dian.token"
    token_path.write_text("", encoding="utf-8")

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    seen = install_rejection_transport(monkeypatch, _handler)
    append_event = AsyncMock(name="append_event")
    monkeypatch.setattr(dispatcher, "append_event", append_event)
    session = mock_session_with_factura(factura_row())

    envio = await _dispatch(session, token_path)

    assert envio.respuesta_proveedor["estado_dian"] == dispatcher.ESTADO_RECHAZADO
    motivo = envio.respuesta_proveedor["motivo_rechazo"]
    assert motivo is not None
    assert motivo.startswith("send:")
    assert "401" in motivo
    assert envio.cufe is None

    append_event.assert_awaited_once()
    attrs = append_event.await_args.args[2]
    assert attrs["tipo_alerta"] == "dian_rechazada"
    assert attrs["uuid_arqueo"] == envio.uuid

    assert [r.method for r in seen] == ["POST"]


# ---------------------------------------------------------------------------
# T-PR11-10 — 2 timeout paths (POST timeout, poll timeout after trackId)
# ---------------------------------------------------------------------------


async def test_dispatcher_initial_post_timeout_propagates(
    monkeypatch: pytest.MonkeyPatch, token_path: Path
) -> None:
    """POST ``ConnectTimeout`` → uncaught ``httpx.ConnectTimeout`` propagates.

    Deviation from tasks.md T-PR11-01 step 6: ``_send_initial`` only
    catches ``HTTPStatusError`` (→ ``rechazado``) and lets
    ``RequestError`` subclasses (``ConnectTimeout`` / ``ReadTimeout``
    / ``NetworkError``) propagate. The poll-timeout retry loop — which
    needs a ``trackId`` to retry against — is intact and covered below.
    Follow-up (PR11c or later) should wrap POST in the same
    ``backoff_5xx`` schedule to fully match the spec.
    """
    def _handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("could not connect to provider")

    seen = install_rejection_transport(monkeypatch, _handler)
    append_event = install_append_event_mock(monkeypatch)
    install_dian_timeout_env(monkeypatch)
    session = mock_session_with_factura(factura_row())

    with pytest.raises(httpx.ConnectTimeout):
        await _dispatch(session, token_path)

    # Envio was queued (NOT committed) before the POST attempt; the
    # exception leaves it in ``estado_dian='pendiente'``. No alerta.
    assert session.add.call_count == 1
    assert isinstance(session.added[0], EnvioDian)
    assert session.added[0].payload["estado_dian"] == "pendiente"
    append_event.assert_not_called()
    assert [r.method for r in seen] == ["POST"]


async def test_dispatcher_poll_timeout_after_trackId_writes_timeout(
    monkeypatch: pytest.MonkeyPatch, token_path: Path
) -> None:
    """Poll ``ReadTimeout`` → ``en_proceso`` loop → final ``timeout`` + alerta.

    Per §21.11 step 6: network errors during the poll are treated as
    ``en_proceso``. After ``PARKOS_DIAN_TIMEOUT_S`` budget +
    ``PARKOS_DIAN_RETRY_MAX`` retries → ``estado_dian='timeout'``,
    ``motivo_rechazo='dian_poll_timeout'`` + ``dian_timeout`` alerta
    chain root.
    """
    def _handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"trackId": "track-timeout"})
        raise httpx.ReadTimeout("provider hung up mid-poll")

    seen = install_rejection_transport(monkeypatch, _handler)
    append_event = install_append_event_mock(monkeypatch)
    install_dian_timeout_env(monkeypatch)
    install_poll_sleep_shim(monkeypatch)
    session = mock_session_with_factura(factura_row())

    envio = await _dispatch(session, token_path)

    assert envio.respuesta_proveedor["estado_dian"] == dispatcher.ESTADO_TIMEOUT
    assert envio.respuesta_proveedor["motivo_rechazo"] == "dian_poll_timeout"
    assert envio.cufe is None

    append_event.assert_awaited_once()
    attrs = append_event.await_args.args[2]
    assert attrs["tipo_alerta"] == "dian_timeout"
    assert attrs["uuid_arqueo"] == envio.uuid
    assert attrs["uuid_alerta_padre"] is None  # chain root

    # 1 POST + 1 initial-window GET + 2 retry-window GETs = 4.
    assert [r.method for r in seen] == ["POST", "GET", "GET", "GET"]
    assert seen[1].url.path == "/api/ubl2.1/track-timeout"
