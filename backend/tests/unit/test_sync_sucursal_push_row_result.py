"""Unit tests -- per-row result handling of the legacy ``/sync/push`` client.

A poison row (e.g. one violating ``factura_electronica_uk01``) is reported by
the cloud as ``apply_error`` for THAT row only. The sender must settle every
other row of the 207 batch as delivered and fail only the bad one (own
backoff / exhaustion sweep), keeping the diagnostic (class + SQLSTATE +
constraint, no row values) in ``ultimo_error``.
"""
from __future__ import annotations

import uuid as uuid_lib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from parkos_core.jobs.sync_sucursal import DEFAULT_BATCH_SIZE, SyncSucursalWorker
from parkos_core.sync.transport import PushResponse


@pytest.fixture
def worker(tmp_path: Path) -> SyncSucursalWorker:
    jwt = tmp_path / "sync.jwt"
    jwt.write_text("test-jwt-token", encoding="utf-8")
    session = MagicMock(name="AsyncSession")
    session.execute = AsyncMock()
    return SyncSucursalWorker(
        jwt_path=jwt,
        base_url="http://cloud",
        session=session,
        poll_interval_s=0,
        batch_size=DEFAULT_BATCH_SIZE,
    )


def _row() -> MagicMock:
    row = MagicMock()
    row.uuid = uuid_lib.uuid4()
    return row


async def test_apply_error_fails_only_that_row_and_settles_the_rest(
    worker: SyncSucursalWorker,
) -> None:
    pending = [_row(), _row(), _row()]
    detail = "UniqueViolationError:23505:factura_electronica_uk01"
    response = PushResponse(
        status=207,
        body={
            "results": [
                {"uuid_registro": str(uuid_lib.uuid4()), "status": "applied"},
                {"uuid_registro": str(uuid_lib.uuid4()), "status": "apply_error", "detail": detail},
                {"uuid_registro": str(uuid_lib.uuid4()), "status": "applied"},
            ]
        },
    )

    with (
        patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.mark_dispatched", AsyncMock()
        ) as dispatched,
        patch("parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed", AsyncMock()) as failed,
    ):
        await worker._handle_push_response(response, pending)

    assert [c.args[1] for c in dispatched.await_args_list] == [pending[0].uuid, pending[2].uuid]
    failed.assert_awaited_once()
    assert failed.await_args.args[1] == pending[1].uuid
    assert failed.await_args.args[2] == f"push_apply_error:{detail}"


async def test_apply_error_without_detail_still_fails_the_row(
    worker: SyncSucursalWorker,
) -> None:
    pending = [_row()]
    response = PushResponse(
        status=207,
        body={"results": [{"uuid_registro": str(uuid_lib.uuid4()), "status": "apply_error"}]},
    )

    with (
        patch("parkos_core.jobs.sync_sucursal.sq_helpers.mark_dispatched", AsyncMock()) as ok,
        patch("parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed", AsyncMock()) as failed,
    ):
        await worker._handle_push_response(response, pending)

    ok.assert_not_awaited()
    assert failed.await_args.args[2] == "push_apply_error"
