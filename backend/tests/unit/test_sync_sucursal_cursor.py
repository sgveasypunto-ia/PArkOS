"""Unit tests — CU-07 pull-cursor wiring in ``jobs/sync_sucursal``.

Pins the worker's cursor behavior WITHOUT a real DB (the wiring layer:
``since_seq`` derivation, ``_persist_pull_cursor`` guard rails). DB-level
semantics live in ``test_sync_cursor_repo.py`` / ``test_sync_cursor_table.py``.

Scenarios:

  C1 -- ``_persist_pull_cursor`` with ``uuid_sucursal=None`` NEVER calls
    ``set_seq`` (the legacy full-resnapshot default must not touch the
    cursor table; guards the constructor default).
  C2 -- ``_persist_pull_cursor`` blocks advancing when ``unresolved > 0``
    (a row outside THIS branch's catalog must be re-delivered, never
    skipped — REQ-CUT-015).
  C3 -- ``_persist_pull_cursor`` persists ``next_seq`` when safe.
  C4 -- ``_pull_and_apply`` pulls ``since_seq = cursor - 1`` (re-delivers
    the last epoch-ms so a same-``created_at``-ms sibling is not skipped);
    with ``uuid_sucursal=None`` it pulls ``since_seq = 0`` (unchanged).
  C5 -- after a clean ``apply_batch`` with no unresolved row, the cursor
    advances to ``pulled.next_seq``.
  C6 -- an unresolved row freezes the cursor even when the rest applied.
"""
from __future__ import annotations

import uuid as uuid_lib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from parkos_core.jobs.sync_sucursal import SyncSucursalWorker
from parkos_core.sync.transport import PullResponse


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


def _pull_response(*, rows: list[dict], next_seq: int) -> PullResponse:
    return PullResponse(status=200, rows=rows, next_seq=next_seq)


class TestPersistPullCursor:
    """C1-C3: the helper's guard rails."""

    @pytest.mark.asyncio
    async def test_none_uuid_never_persists(self, worker: SyncSucursalWorker) -> None:
        with patch(
            "parkos_core.jobs.sync_sucursal.sync_cursor_helpers.set_seq",
            AsyncMock(),
        ) as set_seq_mock:
            await worker._persist_pull_cursor(next_seq=2400, unresolved=0)
        set_seq_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unresolved_blocks_advance(self, worker: SyncSucursalWorker) -> None:
        worker.uuid_sucursal = uuid_lib.uuid4()
        with patch(
            "parkos_core.jobs.sync_sucursal.sync_cursor_helpers.set_seq",
            AsyncMock(),
        ) as set_seq_mock:
            await worker._persist_pull_cursor(next_seq=2400, unresolved=2)
        set_seq_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_persists_when_safe(self, worker: SyncSucursalWorker) -> None:
        sucursal_uuid = uuid_lib.uuid4()
        worker.uuid_sucursal = sucursal_uuid
        with patch(
            "parkos_core.jobs.sync_sucursal.sync_cursor_helpers.set_seq",
            AsyncMock(),
        ) as set_seq_mock:
            await worker._persist_pull_cursor(next_seq=2400, unresolved=0)
        set_seq_mock.assert_awaited_once()
        _, kwargs = set_seq_mock.await_args
        assert kwargs["uuid_sucursal"] == sucursal_uuid
        assert kwargs["ultimo_seq"] == 2400


class TestPullAndApplyCursor:
    """C4-C6: the pull wiring."""

    async def _run_pull(
        self,
        *,
        worker: SyncSucursalWorker,
        cursor_seq: int,
        rows: list[dict],
        next_seq: int,
        motor: bool = False,
    ) -> MagicMock:
        """Drive ``_pull_and_apply`` with mocked cursor + transport + motor."""
        with (
            patch(
                "parkos_core.jobs.sync_sucursal.sync_cursor_helpers.get_seq",
                AsyncMock(return_value=cursor_seq),
            ),
            patch(
                "parkos_core.jobs.sync_sucursal.sync_cursor_helpers.set_seq",
                AsyncMock(),
            ) as set_seq_mock,
            patch(
                "parkos_core.jobs.sync_sucursal.apply_guard.enable_echo_suppression",
                AsyncMock(),
            ) as echo_mock,
        ):
            worker._http_client.pull = AsyncMock(
                return_value=_pull_response(rows=rows, next_seq=next_seq)
            )
            if motor:
                worker._motor = MagicMock()
                worker._motor.apply_batch = AsyncMock(
                    return_value=SimpleNamespace(applied=["a"], buffered=[])
                )
            await worker._pull_and_apply()
        return SimpleNamespace(set_seq=set_seq_mock, echo=echo_mock)

    @pytest.mark.asyncio
    async def test_pull_since_seq_is_cursor_minus_one(
        self, worker: SyncSucursalWorker
    ) -> None:
        worker.uuid_sucursal = uuid_lib.uuid4()
        worker._http_client.pull = AsyncMock(
            return_value=_pull_response(
                rows=[
                    {"tabla": "tipos_vehiculo", "uuid_registro": str(uuid_lib.uuid4())}
                ],
                next_seq=2400,
            )
        )
        # ``row_already_present`` resolves the one row as applied -> the
        # not-resolved path runs _persist_pull_cursor with the raw next_seq.
        with patch(
            "parkos_core.jobs.sync_sucursal.sync_cursor_helpers.get_seq",
            AsyncMock(return_value=1750),
        ), patch(
            "parkos_core.jobs.sync_sucursal.sync_cursor_helpers.set_seq",
            AsyncMock(),
        ), patch(
            "parkos_core.jobs.sync_sucursal.apply_guard.row_already_present",
            AsyncMock(return_value=True),
        ), patch(
            "parkos_core.jobs.sync_sucursal.apply_guard.enable_echo_suppression",
            AsyncMock(),
        ):
            await worker._pull_and_apply()
        received_since = worker._http_client.pull.await_args.kwargs["since_seq"]
        assert received_since == 1749, "since_seq must be (cursor - 1) to cover same-ms rows"

    @pytest.mark.asyncio
    async def test_none_uuid_pulls_full_snapshot(
        self, worker: SyncSucursalWorker
    ) -> None:
        worker.uuid_sucursal = None
        worker._http_client.pull = AsyncMock(return_value=_pull_response(rows=[], next_seq=0))
        with patch(
            "parkos_core.jobs.sync_sucursal.sync_cursor_helpers.get_seq",
            AsyncMock(),
        ) as get_seq_mock:
            await worker._pull_and_apply()
        get_seq_mock.assert_not_awaited()
        received_since = worker._http_client.pull.await_args.kwargs["since_seq"]
        assert received_since == 0

    @pytest.mark.asyncio
    async def test_cursor_advances_after_clean_batch(
        self, worker: SyncSucursalWorker
    ) -> None:
        sucursal_uuid = uuid_lib.uuid4()
        worker.uuid_sucursal = sucursal_uuid
        row_uuid = uuid_lib.uuid4()
        with (
            patch(
                "parkos_core.jobs.sync_sucursal.sync_cursor_helpers.get_seq",
                AsyncMock(return_value=1750),
            ),
            patch(
                "parkos_core.jobs.sync_sucursal.sync_cursor_helpers.set_seq",
                AsyncMock(),
            ) as set_seq_mock,
            patch(
                "parkos_core.jobs.sync_sucursal.apply_guard.enable_echo_suppression",
                AsyncMock(),
            ),
            patch(
                "parkos_core.jobs.sync_sucursal.apply_guard.row_already_present",
                AsyncMock(return_value=False),
            ),
        ):
            worker._motor = MagicMock()
            worker._motor.apply_batch = AsyncMock(
                return_value=SimpleNamespace(applied=["a"], buffered=[])
            )
            worker._http_client.pull = AsyncMock(
                return_value=_pull_response(
                    rows=[
                        {"tabla": "tipos_vehiculo", "uuid_registro": str(row_uuid)}
                    ],
                    next_seq=2500,
                )
            )
            await worker._pull_and_apply()
        set_seq_mock.assert_awaited_once()
        _, kwargs = set_seq_mock.await_args
        assert kwargs["uuid_sucursal"] == sucursal_uuid
        assert kwargs["ultimo_seq"] == 2500

    @pytest.mark.asyncio
    async def test_unresolved_row_freezes_cursor(
        self, worker: SyncSucursalWorker
    ) -> None:
        worker.uuid_sucursal = uuid_lib.uuid4()
        row_uuid = uuid_lib.uuid4()
        with (
            patch(
                "parkos_core.jobs.sync_sucursal.sync_cursor_helpers.get_seq",
                AsyncMock(return_value=1750),
            ),
            patch(
                "parkos_core.jobs.sync_sucursal.sync_cursor_helpers.set_seq",
                AsyncMock(),
            ) as set_seq_mock,
            patch(
                "parkos_core.jobs.sync_sucursal.apply_guard.enable_echo_suppression",
                AsyncMock(),
            ),
            patch(
                "parkos_core.jobs.sync_sucursal.apply_guard.row_already_present",
                AsyncMock(return_value=False),
            ),
        ):
            worker._motor = MagicMock()
            worker._motor.apply_batch = AsyncMock(
                return_value=SimpleNamespace(applied=["a"], buffered=[])
            )
            # One resolvable + one UNKNOWN tabla (outside the catalog):
            # the unknown row leaves unresolved > 0, so the cursor must
            # freeze even though the known row applied cleanly.
            worker._http_client.pull = AsyncMock(
                return_value=_pull_response(
                    rows=[
                        {"tabla": "tipos_vehiculo", "uuid_registro": str(row_uuid)},
                        {"tabla": "tabla_inexistente_xyz", "uuid_registro": str(row_uuid)},
                    ],
                    next_seq=2500,
                )
            )
            await worker._pull_and_apply()
        set_seq_mock.assert_not_awaited()