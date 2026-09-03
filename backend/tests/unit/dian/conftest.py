"""Directory-scoped conftest for ``tests/unit/dian/`` (T-PR11-08 + T-PR11-09 + T-PR11-10).

Sets ``PARKOS_DEPLOY=cloud`` for the dispatcher's import-time guard
(T-PR11-07 — REQ-X3, design §10 Layer 2) BEFORE the dispatcher module
loads, then restores the previous value. Leaking ``cloud`` would mount
the cloud router on the branch app in
``test_openapi_branch_excludes_cloud``; the guard is import-time only,
so once the import window closes the env var can revert.

Hoists the ``token_path`` fixture, the ``_factura_row`` /
``_mock_session_with_factura`` test doubles, the rejection-transport +
sleep-shim helpers, and the constant UUIDs used by every dispatcher
test. T-PR11-10 reuses everything; the timeout-specific env-var +
append-event mock helpers keep the two timeout tests within the
~50-line per-test budget.
"""
from __future__ import annotations

import asyncio
import os
import uuid as uuid_lib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

# ---------------------------------------------------------------------------
# Dispatcher import — guarded by env var (T-PR11-07).
# ---------------------------------------------------------------------------

_PREV_DEPLOY = os.environ.get("PARKOS_DEPLOY")
os.environ["PARKOS_DEPLOY"] = "cloud"
try:
    from parkos_core.dian.cloud import dispatcher
finally:
    if _PREV_DEPLOY is None:
        os.environ.pop("PARKOS_DEPLOY", None)
    else:
        os.environ["PARKOS_DEPLOY"] = _PREV_DEPLOY


# ---------------------------------------------------------------------------
# Stable UUIDs + provider URL shared by every dispatcher test.
# ---------------------------------------------------------------------------

FACTURA_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000001")
ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000002")
SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000003")
RESOLUCION_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000004")
PROVIDER_URL = "http://test"
_HEX = set("0123456789abcdef")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def token_path(tmp_path: Path) -> Path:
    """Bearer-token file. ``FactusProvider`` re-reads it on every call.

    Tests that need an EMPTY or invalid token (e.g. the 401 missing-auth
    rejection) should NOT use this fixture; instead write ``""`` to
    ``tmp_path / "dian.token"`` inline.
    """
    path = tmp_path / "dian.token"
    path.write_text("test-bearer-token", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def install_rejection_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> list[httpx.Request]:
    """``MockTransport`` wrapper for the rejection tests (T-PR11-09).

    Distinct from the success-path ``_install_transport`` (fixed
    POST→track_id, GET→poll_body): rejections need per-request custom
    responses. The caller supplies a handler that builds the right
    response per call.
    """
    seen: list[httpx.Request] = []

    def _wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    transport = httpx.MockTransport(_wrapped)
    monkeypatch.setattr(
        dispatcher.FactusProvider,
        "_default_session_factory",
        lambda _self: httpx.AsyncClient(transport=transport),
    )
    return seen


def install_poll_sleep_shim(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shim ``asyncio.sleep`` so the dispatcher's poll/retry loops run fast.

    Replaces every ``asyncio.sleep(seconds)`` with ``asyncio.sleep(0.01)``
    — enough wall time for the dispatcher's ``loop.time()`` budget check
    (``PARKOS_DIAN_TIMEOUT_S=0.001``) to fire after exactly one poll GET
    per window, keeping the request count deterministic across the
    initial window + retry windows.
    """
    real_sleep = asyncio.sleep

    async def _shim_sleep(_seconds: float) -> None:
        await real_sleep(0.01)

    monkeypatch.setattr(asyncio, "sleep", _shim_sleep)


def install_dian_timeout_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set ``PARKOS_DIAN_TIMEOUT_S`` + ``PARKOS_DIAN_RETRY_MAX`` to test-fast defaults.

    Both timeout-path tests (T-PR11-10) and the existing ``en_proceso``
    test (T-PR11-08) use these values to keep the poll budget + retry
    count deterministic.
    """
    monkeypatch.setenv("PARKOS_DIAN_TIMEOUT_S", "0.001")
    monkeypatch.setenv("PARKOS_DIAN_RETRY_MAX", "2")


def install_append_event_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Patch the dispatcher's ``append_event`` import and return the mock.

    Used by every test that asserts on alerta side effects (T-PR11-08
    failure paths + T-PR11-10 timeout path).
    """
    mock = AsyncMock(name="append_event")
    monkeypatch.setattr(dispatcher, "append_event", mock)
    return mock


# ---------------------------------------------------------------------------
# Test doubles — shared by every dispatcher test.
# ---------------------------------------------------------------------------


def factura_row() -> MagicMock:
    """``factura_electronica`` row double — only what the dispatcher reads.

    ``ubl_serializer.serialize`` touches ``uuid``/``created_at``/``prefijo``/
    ``consecutivo``; fixing them keeps ``xml_sha256`` deterministic.
    """
    row = MagicMock(name="FacturaElectronica")
    row.uuid = FACTURA_UUID
    row.uuid_sucursal = SUCURSAL_UUID
    row.uuid_resolucion_facturacion = RESOLUCION_UUID
    row.created_at = datetime(2026, 1, 15, tzinfo=UTC).replace(tzinfo=None)
    row.prefijo = "SETP"
    row.consecutivo = 990000001
    return row


def mock_session_with_factura(row: MagicMock) -> MagicMock:
    """``AsyncSession`` double wired for the dispatcher's exact call shape.

    ``execute`` is an ``AsyncMock``; the awaited result is a ``MagicMock``
    so both ``select(...).scalar_one_or_none()`` (load the factura) and
    the ``text(...)`` retention UPDATE (result discarded) are covered by
    one return value. Objects handed to ``add`` are tracked on
    ``session.added``.
    """
    session = MagicMock(name="AsyncSession")
    added: list[Any] = []

    result = MagicMock(name="Result")
    result.scalar_one_or_none = MagicMock(return_value=row)
    result.scalar = MagicMock(return_value=None)
    session.execute = AsyncMock(return_value=result)

    async def _flush() -> None:
        # Stand in for the server-side ``gen_random_uuid()`` PK default a
        # real flush would populate — ``_record_terminal`` reads ``uuid``.
        for obj in added:
            if getattr(obj, "uuid", None) is None:
                obj.uuid = uuid_lib.uuid4()

    session.add = MagicMock(side_effect=added.append)
    session.flush = AsyncMock(side_effect=_flush)
    session.commit = AsyncMock(return_value=None)
    session.refresh = AsyncMock(return_value=None)
    session.added = added
    return session