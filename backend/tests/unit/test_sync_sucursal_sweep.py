"""Unit tests — CU-07 BR3 SLA-exhaustion sweep in ``jobs/sync_sucursal``.

Pins the worker's sweep wiring WITHOUT a real DB (the decision layer:
``list_exhausted`` → ``mark_exhausted`` + ``evento_no_procesado`` alert,
call ordering, and the structural dedup by state). DB-level semantics
for ``mark_exhausted`` / ``list_exhausted`` live in
``test_sync_queue_exhaustion.py``.

Scenarios:

  S1 -- ``_sweep_exhausted`` does nothing when nothing is exhausted.
  S2 -- it converts every exhausted row via ``mark_exhausted`` with a
        descriptive error and raises exactly ONE ``evento_no_procesado``
        alert for the batch.
  S3 -- conversion is idempotent per row: the alert fires once per sweep,
        and the next sweep can't double-alert (state-level dedup is the
        repo contract; here we pin that the worker never calls
        ``mark_failed`` — the re-queue path that would keep the row alive).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from parkos_core.jobs.sync_sucursal import SyncSucursalWorker
from parkos_core.models.A.sync_queue import SyncQueue


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _queue_row(*, uuid: uuid_lib.UUID, intentos: int) -> SyncQueue:
    """A minimal fake ``SyncQueue`` ORM instance (only read attrs needed)."""
    row = MagicMock(spec=SyncQueue)
    row.uuid = uuid
    row.tabla = "ingreso"
    row.operacion = "insert"
    row.intentos = intentos
    row.created_at = _now()
    return row


@pytest.fixture
def worker() -> SyncSucursalWorker:
    """A worker with a mock session + no uuid_sucursal (the default)."""
    session_mock = MagicMock()
    session_mock.execute = AsyncMock()
    w = SyncSucursalWorker(
        jwt_path=Path("unused.jwt"),
        base_url="http://cloud",
        session=session_mock,
        poll_interval_s=0,
    )
    w._http_client = MagicMock()
    return w


class TestSweepExhausted:
    """S1-S3: the slew wiring block triggered from :meth:`cycle`."""

    @pytest.mark.asyncio
    async def test_noop_when_nothing_exhausted(
        self, worker: SyncSucursalWorker
    ) -> None:
        with (
            patch(
                "parkos_core.jobs.sync_sucursal.sq_helpers.list_exhausted",
                AsyncMock(return_value=[]),
            ) as list_mock,
            patch(
                "parkos_core.jobs.sync_sucursal.sq_helpers.mark_exhausted",
                AsyncMock(),
            ) as mark_mock,
            patch(
                "parkos_core.sync.hooks.impls.alert_emitter.alert_emitter",
                AsyncMock(),
            ) as alert_mock,
        ):
            await worker._sweep_exhausted()

        list_mock.assert_awaited_once_with(
            worker._session, limit=worker.batch_size, uuid_sucursal=None
        )
        mark_mock.assert_not_awaited()
        alert_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_converts_each_row_and_emits_one_alert(
        self, worker: SyncSucursalWorker
    ) -> None:
        exhausted = [_queue_row(uuid=uuid_lib.uuid4(), intentos=6)]
        with (
            patch(
                "parkos_core.jobs.sync_sucursal.sq_helpers.list_exhausted",
                AsyncMock(return_value=exhausted),
            ),
            patch(
                "parkos_core.jobs.sync_sucursal.sq_helpers.mark_exhausted",
                AsyncMock(),
            ) as mark_mock,
            patch(
                "parkos_core.sync.hooks.impls.alert_emitter.alert_emitter",
                AsyncMock(),
            ) as alert_mock,
        ):
            await worker._sweep_exhausted()

        mark_mock.assert_awaited_once()
        _session, row_uuid, error = mark_mock.await_args.args
        assert row_uuid == exhausted[0].uuid
        # The error must be descriptive (operator-facing: what/why).
        assert "ingreso" in error and "6" in error

        alert_mock.assert_awaited_once()
        alert_kwargs = alert_mock.await_args.kwargs
        assert alert_kwargs["tipo_alerta"] == "evento_no_procesado"
        assert alert_kwargs["uuid_sucursal"] is None

    @pytest.mark.asyncio
    async def test_never_requeues_via_mark_failed(
        self, worker: SyncSucursalWorker
    ) -> None:
        """S3: the sweep is terminal — ``mark_failed`` (re-queue) must never run."""
        exhausted = [_queue_row(uuid=uuid_lib.uuid4(), intentos=9)]
        with (
            patch(
                "parkos_core.jobs.sync_sucursal.sq_helpers.list_exhausted",
                AsyncMock(return_value=exhausted),
            ),
            patch(
                "parkos_core.jobs.sync_sucursal.sq_helpers.mark_exhausted",
                AsyncMock(),
            ),
            patch(
                "parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed",
                AsyncMock(),
            ) as mark_failed_mock,
            patch(
                "parkos_core.sync.hooks.impls.alert_emitter.alert_emitter",
                AsyncMock(),
            ),
        ):
            await worker._sweep_exhausted()

        mark_failed_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sweep_respects_uuid_sucursal_filter(
        self, worker: SyncSucursalWorker
    ) -> None:
        """An explicit branch UUID is forwarded to the selection."""
        sucursal_uuid = uuid_lib.uuid4()
        worker.uuid_sucursal = sucursal_uuid
        with patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.list_exhausted",
            AsyncMock(return_value=[_queue_row(uuid=uuid_lib.uuid4(), intentos=6)]),
        ) as list_mock, patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.mark_exhausted",
            AsyncMock(),
        ), patch(
            "parkos_core.sync.hooks.impls.alert_emitter.alert_emitter",
            AsyncMock(),
        ) as alert_mock:
            await worker._sweep_exhausted()

        list_mock.assert_awaited_once_with(
            worker._session, limit=worker.batch_size, uuid_sucursal=sucursal_uuid
        )
        alert_kwargs = alert_mock.await_args.kwargs
        assert alert_kwargs["uuid_sucursal"] == sucursal_uuid