"""test_sync_cloud_skip_infra_table.py — T-PR10-003 acceptance (D21 guard 2,
REQ-OPS-014).

Pins ``is_infra_table`` / ``SyncCloudWorker._maybe_skip_infra_row``: a
``sync_queue`` row whose ``tabla`` is one of the 5 out-of-catalog names
must be skipped cleanly (logged at ``info``), never routed to
``mark_failed`` — no failure metric may increment for it.

The full catalog-driven apply loop that calls this guard on every row
lands in PR11 (T-PR11-001); this test pins the guard itself in isolation,
per the PR10/PR11 split in ``tasks.md``.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from parkos_core.jobs.sync_cloud import (
    DEFAULT_SYNC_BACK_INTERVAL_S,
    DEFAULT_VERIFY_INTERVAL_S,
    SyncCloudWorker,
    is_infra_table,
)

_OUT_OF_CATALOG_NAMES = (
    "sync_queue",
    "sync_log",
    "sync_conflict",
    "sync_queue_lw_buffer",
    "alert_types",
)


@pytest.fixture
def session_mock() -> MagicMock:
    return MagicMock()


@pytest.fixture
def worker(session_mock: MagicMock) -> SyncCloudWorker:
    return SyncCloudWorker(
        session=session_mock,
        verify_interval_s=DEFAULT_VERIFY_INTERVAL_S,
        sync_back_interval_s=DEFAULT_SYNC_BACK_INTERVAL_S,
    )


@pytest.mark.parametrize("tabla", _OUT_OF_CATALOG_NAMES)
def test_is_infra_table_true_for_all_5_out_of_catalog_names(tabla: str) -> None:
    assert is_infra_table(tabla) is True


@pytest.mark.parametrize(
    "tabla", ["usuarios", "clientes", "facturas", "log_transaccional", "alerta"]
)
def test_is_infra_table_false_for_catalog_tables(tabla: str) -> None:
    assert is_infra_table(tabla) is False


class TestMaybeSkipInfraRow:
    """``SyncCloudWorker._maybe_skip_infra_row`` — skip, never mark_failed."""

    @pytest.mark.parametrize("tabla", _OUT_OF_CATALOG_NAMES)
    def test_skips_and_logs_info_for_infra_table(
        self, worker: SyncCloudWorker, tabla: str
    ) -> None:
        worker.log = MagicMock()

        skipped = worker._maybe_skip_infra_row(tabla)

        assert skipped is True
        worker.log.info.assert_called_once_with("sync_skip_infra_table", tabla=tabla)

    def test_does_not_skip_a_real_catalog_table(self, worker: SyncCloudWorker) -> None:
        worker.log = MagicMock()

        skipped = worker._maybe_skip_infra_row("usuarios")

        assert skipped is False
        worker.log.info.assert_not_called()
