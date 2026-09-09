"""Unit tests — sender-side ``retry_parent_missing`` handling (T-PR12-005).

Req: REQ-CUT-015, ADR-003 Part 2 · Design: §2 Issue #8 · Depends on: T-PR12-004.

``jobs/sync_sucursal.py``'s catalog-driven push (``_push_and_handle_
catalog``, T-PR12-006) must, on a ``retry_parent_missing`` per-row wire
status, call ``repo.sync_queue.mark_dispatched`` ("mark_success" in
design.md's naming) — never increment ``intentos`` or set
``next_retry_at`` (those only live inside ``mark_failed``). This mirrors
the SAME outbox action as ``applied``/``conflict`` per design.md §2 Issue
#8's table: a dependency wait is not a transport failure.
"""
from __future__ import annotations

import uuid as uuid_lib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from parkos_core.jobs.sync_sucursal import DEFAULT_BATCH_SIZE, SyncSucursalWorker
from parkos_core.sync.transport import EventsPushResponse


@pytest.fixture
def jwt_file(tmp_path: Path) -> Path:
    p = tmp_path / "sync.jwt"
    p.write_text("test-jwt-token", encoding="utf-8")
    return p


@pytest.fixture
def session_mock() -> MagicMock:
    s = MagicMock(name="AsyncSession")
    s.execute = AsyncMock()
    return s


@pytest.fixture
def worker(jwt_file: Path, session_mock: MagicMock) -> SyncSucursalWorker:
    return SyncSucursalWorker(
        jwt_path=jwt_file,
        base_url="http://cloud",
        session=session_mock,
        poll_interval_s=0,
        batch_size=DEFAULT_BATCH_SIZE,
    )


def _make_pending_row(tabla: str = "factura_pagos") -> MagicMock:
    row = MagicMock()
    row.uuid = uuid_lib.uuid4()
    row.tabla = tabla
    row.uuid_registro = uuid_lib.uuid4()
    row.uuid_sucursal = uuid_lib.uuid4()
    row.operacion = "insert"
    row.prioridad = 10
    row.datos = {"k": "v"}
    return row


class TestRetryParentMissingSettlesAsDispatched:
    @pytest.mark.asyncio
    async def test_retry_parent_missing_calls_mark_dispatched_not_mark_failed(
        self, worker: SyncSucursalWorker
    ) -> None:
        pending = [_make_pending_row()]

        with (
            patch(
                "parkos_core.jobs.sync_sucursal.sq_helpers.mark_dispatched", AsyncMock()
            ) as mark_dispatched_mock,
            patch(
                "parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed", AsyncMock()
            ) as mark_failed_mock,
        ):
            worker._http_client = MagicMock()
            worker._http_client.push_events = AsyncMock(
                return_value=EventsPushResponse(
                    status=207,
                    results=[{"event_type": "factura_pagos", "status": "retry_parent_missing"}],
                )
            )
            await worker._push_and_handle_catalog(pending)

        mark_dispatched_mock.assert_awaited_once()
        mark_failed_mock.assert_not_awaited()
        assert mark_dispatched_mock.await_args.args[1] == pending[0].uuid

    @pytest.mark.asyncio
    async def test_intentos_byte_identical_before_after(
        self, worker: SyncSucursalWorker, session_mock: MagicMock
    ) -> None:
        """``mark_dispatched`` never touches ``intentos``/``next_retry_at`` —
        only ``mark_failed`` does (repo/sync_queue.py contract). Asserting
        mark_failed was never called IS the "byte-identical intentos"
        guarantee, since intentos only ever changes inside mark_failed."""
        pending = [_make_pending_row()]

        with patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed", AsyncMock()
        ) as mark_failed_mock:
            worker._http_client = MagicMock()
            worker._http_client.push_events = AsyncMock(
                return_value=EventsPushResponse(
                    status=207,
                    results=[{"event_type": "factura_pagos", "status": "retry_parent_missing"}],
                )
            )
            await worker._push_and_handle_catalog(pending)

        mark_failed_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_applied_and_conflict_also_settle_as_dispatched(
        self, worker: SyncSucursalWorker
    ) -> None:
        """design.md §2 Issue #8's table: applied/conflict/retry_parent_missing
        are ALL the same outbox action."""
        pending = [_make_pending_row(), _make_pending_row()]

        with patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.mark_dispatched", AsyncMock()
        ) as mark_dispatched_mock:
            worker._http_client = MagicMock()
            worker._http_client.push_events = AsyncMock(
                return_value=EventsPushResponse(
                    status=207,
                    results=[
                        {"event_type": "factura_pagos", "status": "applied"},
                        {"event_type": "factura_pagos", "status": "conflict"},
                    ],
                )
            )
            await worker._push_and_handle_catalog(pending)

        assert mark_dispatched_mock.await_count == 2

    @pytest.mark.asyncio
    async def test_unknown_wire_status_marks_failed_never_silent(
        self, worker: SyncSucursalWorker
    ) -> None:
        pending = [_make_pending_row()]

        with patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed", AsyncMock()
        ) as mark_failed_mock:
            worker._http_client = MagicMock()
            worker._http_client.push_events = AsyncMock(
                return_value=EventsPushResponse(
                    status=207,
                    results=[{"event_type": "factura_pagos", "status": "unknown_table"}],
                )
            )
            await worker._push_and_handle_catalog(pending)

        mark_failed_mock.assert_awaited_once()
        assert "events_unknown_table" in mark_failed_mock.await_args.args[2]
