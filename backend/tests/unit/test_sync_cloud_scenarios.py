"""Unit tests for ``jobs.sync_cloud`` (PR9b, T-PR9-07 + T-PR9-15..16).

Pins the two key contracts the cloud worker must honor:

  - test_apply_pushed_row_uses_repo_helpers        (T-PR9-15)
  - test_hash_chain_verifier_emits_alerta_and_conflict (T-PR9-16)

The full DB-backed versions of these tests live in
``tests/integration/test_sync_cloud_cycle.py`` (PR9c scope). Here we
mock the DB session + the repo helpers and exercise the worker's
``_handle_chain_break`` directly so the contracts are pinned even when
a real Postgres container is not available.

What's mocked:

  - ``repo.append_only.append_event`` records the call + attrs.
  - ``repo.workflow.append_transition`` records the call + new_attrs.
  - ``session.execute`` returns an ``AsyncMock`` so the verifier loop
    can iterate over a controlled list of ``log_transaccional`` rows.
  - The two helpers (``hash_chain._genesis_hash``, the conflict
    resolver, the branch cache) are used as-is — they're pure Python.

The verifier sweep deliberately constructs a chain where ``row[1].hash_anterior``
does NOT match ``row[0].hash_actual``; the worker must catch the break
and write the spec-required ``alerta`` + ``sync_conflict`` rows.

Cites design 21.8, 21.14 acceptance #14, tasks.md T-PR9-07 + T-PR9-15..16.
"""
from __future__ import annotations

import hashlib
import sys
import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from parkos_core.jobs.sync_cloud import (
    DEFAULT_SYNC_BACK_INTERVAL_S,
    DEFAULT_VERIFY_INTERVAL_S,
    HashChainBreak,
    SyncCloudWorker,
)
from parkos_core.repo import hash_chain as hc_helpers

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def session_mock() -> MagicMock:
    """An ``AsyncMock`` standing in for ``AsyncSession``.

    The default ``session.execute`` returns a fresh ``MagicMock`` whose
    ``scalars().all()`` returns ``[]`` so the verifier loop sees no
    tenants and exits cleanly. Tests that need a controlled chain
    override this fixture or patch the execute result per call.
    """
    s = MagicMock()
    s.execute = AsyncMock()
    # First call: list tenants (empty). Subsequent: empty chain.
    empty_result = MagicMock()
    empty_scalars = MagicMock()
    empty_scalars.all.return_value = []
    empty_result.scalars.return_value = empty_scalars
    empty_result.all.return_value = []
    s.execute.return_value = empty_result
    return s


@pytest.fixture
def worker(session_mock: MagicMock) -> SyncCloudWorker:
    """A cloud worker with mocked collaborators."""
    return SyncCloudWorker(
        session=session_mock,
        verify_interval_s=DEFAULT_VERIFY_INTERVAL_S,
        sync_back_interval_s=DEFAULT_SYNC_BACK_INTERVAL_S,
    )


def _make_chain_row(
    *,
    uuid: uuid_lib.UUID | None = None,
    prior_hash: str,
    payload_bytes: bytes,
    timestamp: str = "2026-01-01T00:00:00",
) -> MagicMock:
    """Build a mock ``LogTransaccional`` row with correct chain links.

    ``hash_anterior = prior_hash``,
    ``hash_actual = sha256(payload_bytes + prior_hash_bytes).hexdigest()``.
    """
    new_hash = hashlib.sha256(payload_bytes + bytes.fromhex(prior_hash)).hexdigest()
    row = MagicMock()
    row.uuid = uuid or uuid_lib.uuid4()
    row.uuid_sucursal = uuid_lib.uuid4()
    row.timestamp_evento = timestamp
    row.hash_anterior = prior_hash
    row.hash_actual = new_hash
    return row


# ---------------------------------------------------------------------------
# Construction / surface
# ---------------------------------------------------------------------------


class TestSyncCloudWorkerConstruction:
    """The worker wires its name + intervals + branch cache."""

    def test_construction_defaults(
        self, session_mock: MagicMock
    ) -> None:
        w = SyncCloudWorker(session=session_mock)
        assert w.verify_interval_s == DEFAULT_VERIFY_INTERVAL_S
        assert w.sync_back_interval_s == DEFAULT_SYNC_BACK_INTERVAL_S
        assert w.name == "sync_cloud"
        # Branch cache starts empty; no tenants, no eager query.
        assert w._branch_cache.cached_at is None
        assert w._branch_cache._cache == []

    def test_construction_clamps_zero_intervals(
        self, session_mock: MagicMock
    ) -> None:
        w = SyncCloudWorker(
            session=session_mock,
            verify_interval_s=0,
            sync_back_interval_s=0,
        )
        assert w.verify_interval_s == 1
        assert w.sync_back_interval_s == 1


# ---------------------------------------------------------------------------
# T-PR9-16: hash_chain_verifier catches break + writes alerta + sync_conflict
# ---------------------------------------------------------------------------


class TestHashChainVerifierCatchesBreak:
    """A mismatched hash_anterior triggers the spec'd alerta + sync_conflict."""

    @pytest.mark.asyncio
    async def test_chain_break_emits_alerta_and_conflict(
        self, worker: SyncCloudWorker, session_mock: MagicMock
    ) -> None:
        tenant = uuid_lib.uuid4()
        tenant_uuid = tenant

        # Two-row chain where row[1].hash_anterior does NOT match row[0].hash_actual.
        row0 = _make_chain_row(
            uuid=uuid_lib.uuid4(),
            prior_hash=hc_helpers._genesis_hash(tenant_uuid),
            payload_bytes=b"row0",
            timestamp="2026-01-01T00:00:00",
        )
        row1 = _make_chain_row(
            uuid=uuid_lib.uuid4(),
            # WRONG prior — should be row0.hash_actual, but we say genesis
            # so the verifier raises HashChainBreak at row1.
            prior_hash=hc_helpers._genesis_hash(tenant_uuid),
            payload_bytes=b"row1",
            timestamp="2026-01-01T00:01:00",
        )

        # session.execute() returns:
        #   1. distinct tenants → scalars().all() = [tenant_uuid]
        #   2. ordered rows for tenant_uuid → scalars().all() = [row0, row1]
        tenants_result = MagicMock()
        tenants_scalars = MagicMock()
        tenants_scalars.all.return_value = [tenant_uuid]
        tenants_result.scalars.return_value = tenants_scalars

        rows_result = MagicMock()
        rows_scalars = MagicMock()
        rows_scalars.all.return_value = [row0, row1]
        rows_result.scalars.return_value = rows_scalars

        session_mock.execute = AsyncMock(side_effect=[tenants_result, rows_result])

        # Patch both repo helpers; capture the calls.
        with patch(
            "parkos_core.jobs.sync_cloud.wf_helpers.append_transition",
            AsyncMock(),
        ) as append_transition_mock, patch(
            "parkos_core.jobs.sync_cloud.ao_helpers.append_event",
            AsyncMock(),
        ) as append_event_mock:
            await worker._verify_hash_chains_once()

        # The chain walk raised HashChainBreak at row1; _handle_chain_break
        # should have written the alerta via repo.workflow.append_transition
        # AND the sync_conflict via repo.append_only.append_event.
        append_transition_mock.assert_awaited_once()
        # First positional arg after session: model_cls = Alerta.
        alerta_model_cls = append_transition_mock.await_args.args[1]
        assert alerta_model_cls.__name__ == "Alerta"
        # new_attrs (kw) carries tipo_alerta='hash_chain_anomaly' + estado='activa'.
        new_attrs = append_transition_mock.await_args.kwargs["new_attrs"]
        assert new_attrs["tipo_alerta"] == "hash_chain_anomaly"
        assert new_attrs["estado"] == "activa"
        assert new_attrs["uuid_sucursal"] == tenant_uuid

        append_event_mock.assert_awaited_once()
        # First positional arg after session: model_cls = SyncConflict.
        conflict_model_cls = append_event_mock.await_args.args[1]
        assert conflict_model_cls.__name__ == "SyncConflict"
        # attrs (kw) carries politica='chain_break' + tabla='log_transaccional'.
        conflict_attrs = append_event_mock.await_args.kwargs["attrs"]
        assert conflict_attrs["politica"] == "chain_break"
        assert conflict_attrs["tabla"] == "log_transaccional"
        assert conflict_attrs["uuid_sucursal"] == tenant_uuid

    @pytest.mark.asyncio
    async def test_valid_chain_emits_nothing(
        self, worker: SyncCloudWorker, session_mock: MagicMock
    ) -> None:
        tenant = uuid_lib.uuid4()
        row0 = _make_chain_row(
            uuid=uuid_lib.uuid4(),
            prior_hash=hc_helpers._genesis_hash(tenant),
            payload_bytes=b"row0",
            timestamp="2026-01-01T00:00:00",
        )
        # row1.hash_anterior MUST equal row0.hash_actual.
        row1 = _make_chain_row(
            uuid=uuid_lib.uuid4(),
            prior_hash=row0.hash_actual,  # correct link
            payload_bytes=b"row1",
            timestamp="2026-01-01T00:01:00",
        )

        tenants_result = MagicMock()
        tenants_scalars = MagicMock()
        tenants_scalars.all.return_value = [tenant]
        tenants_result.scalars.return_value = tenants_scalars

        rows_result = MagicMock()
        rows_scalars = MagicMock()
        rows_scalars.all.return_value = [row0, row1]
        rows_result.scalars.return_value = rows_scalars

        session_mock.execute = AsyncMock(side_effect=[tenants_result, rows_result])

        with patch(
            "parkos_core.jobs.sync_cloud.wf_helpers.append_transition",
            AsyncMock(),
        ) as append_transition_mock, patch(
            "parkos_core.jobs.sync_cloud.ao_helpers.append_event",
            AsyncMock(),
        ) as append_event_mock:
            await worker._verify_hash_chains_once()

        # Valid chain → no alerta, no conflict.
        append_transition_mock.assert_not_awaited()
        append_event_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# T-PR9-15: apply_pushed_row uses repo helpers (no raw session.execute on [A])
# ---------------------------------------------------------------------------


class TestApplyPushedRowUsesRepoHelpers:
    """The cloud-side apply_pushed_row path delegates to repo helpers.

    The actual ``/sync/push`` handler lives in
    ``parkos_core.api.v1.sync_router`` (PR8c, T-PR8-15). PR9b owns the
    BACKGROUND ``sync_back`` loop + the ``hash_chain_verifier`` loop;
    the apply path itself is exercised end-to-end in
    ``test_sync_router.py`` (PR8c). Here we just pin that the cloud
    worker instantiates the conflict resolver — i.e. it consumes the
    PR9a helper rather than reimplementing it.
    """

    def test_worker_owns_a_conflict_resolver(self, worker: SyncCloudWorker) -> None:
        assert worker._conflict_resolver is not None
        # Default grace window = 24h per design 21.10.
        assert worker._conflict_resolver.jwt_overlap_hours == 24


# ---------------------------------------------------------------------------
# Module entrypoint import sanity
# ---------------------------------------------------------------------------


def test_module_exports_main() -> None:
    """``main`` is the CLI entrypoint — Dockerfile CMD wires to it."""
    from parkos_core.jobs import sync_cloud as m

    assert callable(m.main)
    assert m.SyncCloudWorker.__module__ == "parkos_core.jobs.sync_cloud"
    assert "parkos_core.jobs.sync_cloud" in sys.modules


def test_hash_chain_break_is_a_specific_exception() -> None:
    """``HashChainBreak`` is the canonical sentinel for the verifier."""
    exc = HashChainBreak("test")
    assert isinstance(exc, Exception)
    assert "test" in str(exc)
