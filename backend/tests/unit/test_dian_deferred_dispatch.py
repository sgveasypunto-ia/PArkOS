"""D5 — a slow/unreachable DIAN provider must never hold the sync transaction.

The cloud apply path used to ``await dispatch_*_with_backoff`` INSIDE the
transaction of ``POST /sync/push`` (and of the cloud apply loop). With an
unreachable provider the dispatcher slept in transport backoff
(60+300+900 s) with an uncommitted ``INSERT INTO prod.envio_dian``: the
connection sat ``idle in transaction`` and later pushes blocked behind it.
"""
from __future__ import annotations

import asyncio
import importlib
import uuid as uuid_lib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from parkos_core.sync.hooks import base as hook_base
from parkos_core.sync.hooks.impls import dian_dispatch_on_sync as hooks

FE = uuid_lib.UUID("00000000-0000-0000-0000-0000000000d1")


def _session() -> MagicMock:
    s = MagicMock(name="session")
    s.sync_session = SimpleNamespace(info={})
    return s


@pytest.fixture(autouse=True)
def _no_listeners():
    with patch.object(hooks.event, "listen"):
        yield


@pytest.fixture
def dispatcher(monkeypatch: pytest.MonkeyPatch):
    """The cloud-only dispatcher (import-time guard needs PARKOS_DEPLOY=cloud)."""
    monkeypatch.setenv("PARKOS_DEPLOY", "cloud")
    return importlib.import_module("parkos_core.dian.cloud.dispatcher")


@pytest.mark.asyncio
async def test_hook_returns_immediately_with_a_hanging_provider(dispatcher) -> None:
    """The hook only queues; a dispatcher that never returns cannot block it."""
    hang = asyncio.Event()

    async def hanging(*_a, **_k):
        await hang.wait()

    session = _session()
    ctx = hook_base.HookContext(
        spec=MagicMock(), payload={}, session=session,
        actor_uuid=uuid_lib.uuid4(), row_uuid=FE,
    )
    with patch.object(dispatcher, "dispatch_factura_electronica_with_backoff", new=hanging):
        res = await asyncio.wait_for(hooks.dian_factura_electronica_dispatch_hook(ctx), 1.0)
    assert res.proceed is True
    assert len(session.sync_session.info[hooks._PENDING_KEY]) == 1


@pytest.mark.asyncio
async def test_after_commit_spawns_detached_task_and_never_blocks() -> None:
    hang = asyncio.Event()
    started = asyncio.Event()

    async def hanging(_session):
        started.set()
        await hang.wait()

    sync_session = SimpleNamespace(info={hooks._PENDING_KEY: [hanging]})
    fake_local = MagicMock()
    fake_local.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
    fake_local.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("parkos_core.db.engine.SessionLocal", new=fake_local):
        hooks._on_after_commit(sync_session)  # synchronous, returns at once
        assert sync_session.info[hooks._PENDING_KEY] == []
        await asyncio.wait_for(started.wait(), 1.0)
    hang.set()
    await asyncio.gather(*hooks._BACKGROUND_TASKS)


@pytest.mark.asyncio
async def test_deferred_failure_is_swallowed() -> None:
    async def boom(_session):
        raise httpx.ConnectError("dns")

    fake_local = MagicMock()
    fake_local.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
    fake_local.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("parkos_core.db.engine.SessionLocal", new=fake_local):
        await hooks._run_deferred(boom)  # must not raise


def test_rollback_drops_queued_dispatches() -> None:
    sync_session = SimpleNamespace(info={hooks._PENDING_KEY: [object()]})
    hooks._on_after_rollback(sync_session)
    assert sync_session.info[hooks._PENDING_KEY] == []


@pytest.mark.asyncio
async def test_revocacion_commits_before_http_and_degrades_on_transport_error(dispatcher) -> None:
    """envio_dian is committed BEFORE the provider call; DNS/connect errors
    degrade to a retryable ``timeout`` outcome instead of propagating."""
    order: list[str] = []
    row = SimpleNamespace(
        uuid=uuid_lib.uuid4(), uuid_sucursal=uuid_lib.uuid4(),
        uuid_factura_electronica=uuid_lib.uuid4(),
    )
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    session.execute = AsyncMock(return_value=result)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    async def commit():
        order.append("commit")

    session.commit = commit

    class Provider:
        def __init__(self, **_k): ...

        async def send_revocacion(self, _xml):
            order.append("http")
            raise httpx.ConnectError("name resolution failed")

    with (
        patch.object(dispatcher, "FactusProvider", Provider),
        patch.object(dispatcher, "_write_alerta", new=AsyncMock()),
    ):
        envio = await dispatcher.dispatch_revocacion(
            session, uuid_revocacion_factura=row.uuid, actor_uuid=uuid_lib.uuid4(),
            dian_provider_url="https://x.invalid", dian_token_path=MagicMock(),
        )
    assert order[:2] == ["commit", "http"]
    assert envio.respuesta_proveedor["estado_dian"] == "timeout"


@pytest.mark.asyncio
async def test_deferred_failure_log_carries_class_and_sanitized_message() -> None:
    """JB2: the warning had no cause (structlog does not render exc_info)."""

    async def boom(_session):
        raise FileNotFoundError(
            "[Errno 2] token https://user:s3cret@provider.example/x missing"
        )

    fake_local = MagicMock()
    fake_local.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
    fake_local.return_value.__aexit__ = AsyncMock(return_value=False)
    with (
        patch("parkos_core.db.engine.SessionLocal", new=fake_local),
        patch.object(hooks, "_log") as log,
    ):
        await hooks._run_deferred(boom)
    (event,), kwargs = log.warning.call_args
    assert event == "dian_dispatch.deferred_failed"
    assert kwargs["error_class"] == "FileNotFoundError"
    assert "token" in kwargs["error"] and "s3cret" not in kwargs["error"]


@pytest.mark.asyncio
async def test_unreadable_token_ends_in_terminal_error_not_an_orphan_row(dispatcher) -> None:
    """JB2: a missing provider token (OSError, not httpx) left the envio_dian
    inserted by the dispatcher with no outcome and no alerta, never retried."""
    row = SimpleNamespace(
        uuid=uuid_lib.uuid4(), uuid_sucursal=uuid_lib.uuid4(),
        uuid_factura_electronica=uuid_lib.uuid4(),
    )
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    session.execute = AsyncMock(return_value=result)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()

    class Provider:
        def __init__(self, **_k): ...

        async def send_revocacion(self, _xml):
            raise FileNotFoundError("/var/run/parkos/factus_token")

    alerta = AsyncMock()
    with (
        patch.object(dispatcher, "FactusProvider", Provider),
        patch.object(dispatcher, "_write_alerta", new=alerta),
    ):
        envio = await dispatcher.dispatch_revocacion(
            session, uuid_revocacion_factura=row.uuid, actor_uuid=uuid_lib.uuid4(),
            dian_provider_url="https://x.invalid", dian_token_path=MagicMock(),
        )
    assert envio.estado == "error"
    assert envio.respuesta_proveedor["estado_dian"] == "error"
    assert "FileNotFoundError" in envio.respuesta_proveedor["motivo_rechazo"]
    assert alerta.await_args.kwargs["tipo_alerta"] == "dian_error"


@pytest.mark.asyncio
async def test_send_initial_maps_oserror_to_error_outcome(dispatcher) -> None:
    class Provider:
        async def send_ubl(self, _xml):
            raise PermissionError("denied")

    track, rechazo = await dispatcher._send_initial(Provider(), b"<x/>")
    assert track is None
    assert rechazo.estado == dispatcher.ESTADO_ERROR
    assert "PermissionError" in rechazo.motivo_rechazo
