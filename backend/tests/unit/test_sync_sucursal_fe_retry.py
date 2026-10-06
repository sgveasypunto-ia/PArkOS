"""The branch worker runs the automatic FE retry first and never lets it break the sync cycle."""
from __future__ import annotations

import uuid as uuid_lib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from parkos_core.jobs import sync_sucursal as mod

SUCURSAL = uuid_lib.uuid4()


def _worker(uuid_sucursal=SUCURSAL):
    session = MagicMock()
    session.rollback = AsyncMock()
    return mod.SyncSucursalWorker(
        jwt_path=Path("jwt"), base_url="http://cloud", session=session, uuid_sucursal=uuid_sucursal
    )


async def test_retry_is_invoked_with_branch_and_scheduler(monkeypatch) -> None:
    m = AsyncMock(return_value={"emitidas": 1, "fallidas": 0, "alertas": 0})
    monkeypatch.setattr(mod, "reintentar_pendientes", m)
    w = _worker()
    await w._retry_pending_fe()
    kw = m.await_args.kwargs
    assert kw["uuid_sucursal"] == SUCURSAL
    assert kw["scheduler"] is w._fe_retry


async def test_retry_failure_is_isolated_from_the_sync_cycle(monkeypatch) -> None:
    monkeypatch.setattr(mod, "reintentar_pendientes", AsyncMock(side_effect=RuntimeError("x")))
    w = _worker()
    await w._retry_pending_fe()  # must not raise
    w._session.rollback.assert_awaited()


async def test_retry_skipped_without_branch_uuid(monkeypatch) -> None:
    m = AsyncMock()
    monkeypatch.setattr(mod, "reintentar_pendientes", m)
    await _worker(uuid_sucursal=None)._retry_pending_fe()
    m.assert_not_awaited()
