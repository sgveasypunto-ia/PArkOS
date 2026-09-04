"""Unit tests for ``jobs.sync_sucursal`` (PR9b, T-PR9-06 + T-PR9-11..14).

These tests pin the contracts of the four key scenarios the worker must
handle:

  - test_poll_batch_marks_dispatched       (T-PR9-11)
  - test_401_sync_jwt_expired_triggers_rotate (T-PR9-12)
  - test_401_sync_jwt_revoked_halts         (T-PR9-13)
  - test_5xx_backoff_marks_failed_with_schedule_retry (T-PR9-14)

The full DB-backed versions of these tests live in
``tests/integration/test_sync_sucursal_cycle.py`` (PR9c scope). Here we
mock the ``SyncHttpClient`` + ``JwtManager`` collaborators and exercise
the worker's response-classifier logic directly so the contracts are
pinned even when a real Postgres container is not available.

What's mocked:

  - ``SyncHttpClient.push`` returns a chosen ``PushResponse`` so we can
    drive the 2xx / 207 / 401 / 5xx branches of ``_handle_push_response``.
  - ``JwtManager.on_401_response`` returns a chosen ``JwtAction`` so we
    can verify the rotate path without hitting the network.
  - ``session`` is an ``AsyncMock`` so ``mark_dispatched`` / ``mark_failed``
    calls are recorded without needing a real DB.

Cites design 21.7, tasks.md T-PR9-06 + T-PR9-11..14.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from parkos_core.jobs.sync_sucursal import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_POLL_INTERVAL_S,
    SyncSucursalWorker,
)
from parkos_core.sync.jwt_manager import JwtAction
from parkos_core.sync.transport import PushResponse

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def jwt_file(tmp_path: Path) -> Path:
    """Write a fake JWT to a temp file."""
    p = tmp_path / "sync.jwt"
    p.write_text("test-jwt-token", encoding="utf-8")
    return p


@pytest.fixture
def session_mock() -> MagicMock:
    """An ``AsyncMock`` standing in for ``AsyncSession``."""
    s = MagicMock()
    s.execute = AsyncMock()
    return s


@pytest.fixture
def worker(jwt_file: Path, session_mock: MagicMock) -> SyncSucursalWorker:
    """A worker with no transport / JWT manager yet — tests wire those."""
    return SyncSucursalWorker(
        jwt_path=jwt_file,
        base_url="http://cloud",
        session=session_mock,
        poll_interval_s=0,
        batch_size=DEFAULT_BATCH_SIZE,
    )


def _make_pending_row(uuid: uuid_lib.UUID | None = None) -> MagicMock:
    """Build a mock sync_queue row with the shape ``_wire_shape`` reads."""
    row = MagicMock()
    row.uuid = uuid or uuid_lib.uuid4()
    row.tabla = "factura_pagos"
    row.uuid_registro = uuid_lib.uuid4()
    row.uuid_sucursal = uuid_lib.uuid4()
    row.operacion = "insert"
    row.prioridad = 10
    row.datos = {"k": "v"}
    return row


# ---------------------------------------------------------------------------
# Construction / surface
# ---------------------------------------------------------------------------


class TestSyncSucursalWorkerConstruction:
    """The worker wires its name + interval + batch_size + collaborators."""

    def test_construction_sets_defaults(
        self, jwt_file: Path, session_mock: MagicMock
    ) -> None:
        w = SyncSucursalWorker(
            jwt_path=jwt_file,
            base_url="http://cloud/",
            session=session_mock,
        )
        # Default interval + batch size come from env defaults.
        assert w.poll_interval_s == DEFAULT_POLL_INTERVAL_S
        assert w.batch_size == DEFAULT_BATCH_SIZE
        # Base URL is stripped of trailing slash.
        assert w.base_url == "http://cloud"
        # The name comes from WorkerRunner's name= kwarg.
        assert w.name == "sync_sucursal"
        # Collaborators start lazy — the worker doesn't crash on boot
        # when the JWT file is missing or the DB isn't reachable.
        assert w._http_client is None
        assert w._jwt_manager is None

    def test_construction_clamps_zero_intervals(
        self, jwt_file: Path, session_mock: MagicMock
    ) -> None:
        # poll_interval_s < 1 must clamp to 1 (defensive).
        w = SyncSucursalWorker(
            jwt_path=jwt_file,
            base_url="http://cloud",
            session=session_mock,
            poll_interval_s=0,
        )
        assert w.poll_interval_s == 1


# ---------------------------------------------------------------------------
# T-PR9-11: poll_batch_marks_dispatched
# ---------------------------------------------------------------------------


class TestPollBatchMarksDispatched:
    """The happy path — 2xx push marks every row dispatched."""

    @pytest.mark.asyncio
    async def test_2xx_push_marks_all_rows_dispatched(
        self, worker: SyncSucursalWorker, session_mock: MagicMock
    ) -> None:
        pending = [_make_pending_row() for _ in range(3)]

        with patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.mark_dispatched",
            AsyncMock(),
        ) as mark_dispatched_mock:
            # Wire the http client directly so _push_and_handle's assert
            # passes. The push returns 200 with empty body (the simple
            # happy-path contract).
            worker._http_client = MagicMock()
            worker._http_client.push = AsyncMock(
                return_value=PushResponse(status=200, body={"accepted": 3})
            )
            await worker._push_and_handle(pending)

        # mark_dispatched called once per row.
        assert mark_dispatched_mock.await_count == 3
        call_uuids = {c.args[1] for c in mark_dispatched_mock.await_args_list}
        assert call_uuids == {row.uuid for row in pending}


# ---------------------------------------------------------------------------
# T-PR9-12: 401 sync_jwt_expired triggers rotate
# ---------------------------------------------------------------------------


class Test401SyncJwtExpiredTriggersRotate:
    """JWT lifecycle — 401 sync_jwt_expired → RETRY_NEW_JWT → rotate."""

    @pytest.mark.asyncio
    async def test_401_expired_triggers_rotate_and_marks_failed(
        self, worker: SyncSucursalWorker, session_mock: MagicMock
    ) -> None:
        pending = [_make_pending_row() for _ in range(2)]

        with patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed",
            AsyncMock(),
        ) as mark_failed_mock, patch(
            "parkos_core.jobs.sync_sucursal.JwtManager"
        ) as manager_cls:
            manager = MagicMock()
            manager.on_401_response = AsyncMock(return_value=JwtAction.RETRY_NEW_JWT)
            manager.rotate = AsyncMock(return_value="new-jwt")
            manager_cls.return_value = manager
            manager_cls.call_args  # silence unused
            worker._jwt_manager = manager

            worker._http_client = MagicMock()
            worker._http_client.push = AsyncMock(
                return_value=PushResponse(
                    status=401, body={"error": "sync_jwt_expired"}
                )
            )

            await worker._handle_push_response(
                worker._http_client.push.return_value, pending
            )

        # rotate called exactly once.
        manager.rotate.assert_awaited_once()
        # mark_failed called once per row (next cycle retries the push).
        assert mark_failed_mock.await_count == 2
        # Error message tags the rotation so the metric panel can show
        # the 401-rotate traffic.
        error_messages = {c.args[2] for c in mark_failed_mock.await_args_list}
        assert any("401_sync_jwt_rotated" in m for m in error_messages)


# ---------------------------------------------------------------------------
# T-PR9-13: 401 sync_jwt_revoked halts
# ---------------------------------------------------------------------------


class Test401SyncJwtRevokedHalts:
    """JWT lifecycle — 401 sync_jwt_revoked → HALT_REVOKED → mark_failed."""

    @pytest.mark.asyncio
    async def test_401_revoked_returns_halt_action_and_marks_failed(
        self, worker: SyncSucursalWorker, session_mock: MagicMock
    ) -> None:
        pending = [_make_pending_row() for _ in range(2)]

        with patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed",
            AsyncMock(),
        ) as mark_failed_mock:
            manager = MagicMock()
            manager.on_401_response = AsyncMock(return_value=JwtAction.HALT_REVOKED)
            manager.rotate = AsyncMock()
            worker._jwt_manager = manager

            response = PushResponse(status=401, body={"error": "sync_jwt_revoked"})
            await worker._handle_push_response(response, pending)

        # rotate NOT called (revoked is permanent).
        manager.rotate.assert_not_awaited()
        # Every row marked failed with the halt-action tag.
        assert mark_failed_mock.await_count == 2
        error_messages = {c.args[2] for c in mark_failed_mock.await_args_list}
        assert any("401_halt_revoked" in m for m in error_messages)


# ---------------------------------------------------------------------------
# T-PR9-14: 5xx backoff
# ---------------------------------------------------------------------------


class Test5xxBackoffMarksFailed:
    """5xx → mark_failed with retry info; backoff schedule lives in repo."""

    @pytest.mark.asyncio
    async def test_503_marks_failed_with_status_tag(
        self, worker: SyncSucursalWorker, session_mock: MagicMock
    ) -> None:
        pending = [_make_pending_row() for _ in range(2)]

        with patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed",
            AsyncMock(),
        ) as mark_failed_mock:
            worker._http_client = MagicMock()
            response = PushResponse(status=503, body={"error": "service_unavailable"})
            await worker._handle_push_response(response, pending)

        assert mark_failed_mock.await_count == 2
        error_messages = {c.args[2] for c in mark_failed_mock.await_args_list}
        # Status tag is the canonical marker for the 5xx branch.
        assert all(m == "http_503" for m in error_messages)

    @pytest.mark.asyncio
    async def test_transport_error_marks_failed(
        self, worker: SyncSucursalWorker, session_mock: MagicMock
    ) -> None:
        """A push that raises (DNS / timeout) is treated as 5xx-equivalent."""
        pending = [_make_pending_row() for _ in range(2)]

        with patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed",
            AsyncMock(),
        ) as mark_failed_mock:
            worker._http_client = MagicMock()
            worker._http_client.push = AsyncMock(
                side_effect=ConnectionError("dns blew up")
            )
            await worker._push_and_handle(pending)

        assert mark_failed_mock.await_count == 2
        error_messages = {c.args[2] for c in mark_failed_mock.await_args_list}
        assert all("transport:" in m for m in error_messages)


# ---------------------------------------------------------------------------
# 207 partial push
# ---------------------------------------------------------------------------


class Test207PartialPush:
    """207 Multi-Status — only the success_uuids are dispatched."""

    @pytest.mark.asyncio
    async def test_partial_dispatch_marks_only_accepted(
        self, worker: SyncSucursalWorker, session_mock: MagicMock
    ) -> None:
        rows = [_make_pending_row() for _ in range(3)]
        # Cloud accepts only the first row.
        accepted = rows[0].uuid

        with patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.mark_dispatched",
            AsyncMock(),
        ) as mark_dispatched_mock, patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed",
            AsyncMock(),
        ) as mark_failed_mock:
            response = PushResponse(
                status=207,
                body={"success_uuids": [str(accepted)]},
            )
            await worker._handle_push_response(response, rows)

        # 1 dispatched (the accepted one), 2 failed (the rejected).
        assert mark_dispatched_mock.await_count == 1
        assert mark_failed_mock.await_count == 2
        dispatched_uuid = mark_dispatched_mock.await_args.args[1]
        assert dispatched_uuid == accepted


# ---------------------------------------------------------------------------
# Module entrypoint import sanity
# ---------------------------------------------------------------------------


def test_module_exports_main() -> None:
    """``main`` is the CLI entrypoint — Dockerfile CMD wires to it."""
    from parkos_core.jobs import sync_sucursal as m

    assert callable(m.main)
    assert m.SyncSucursalWorker.__module__ == "parkos_core.jobs.sync_sucursal"
    assert "parkos_core.jobs.sync_sucursal" in sys.modules
