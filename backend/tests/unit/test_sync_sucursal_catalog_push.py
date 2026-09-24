"""Unit tests — sender-side catalog push (``_push_and_handle_catalog``).

Companion of ``test_sync_sucursal_retry_parent_missing.py`` (T-PR12-005),
focused on the BATCH-SELECTION + payload-shaping + batch-failure layer of
``jobs/sync_sucursal.py::_push_and_handle_catalog`` (T-PR12-006):

  - A1 — a mixed batch (infra rows / catalog rows / unknown tables) is
    routed correctly: infra rows settle dispatched and NEVER enter the
    wire events, unknown names fail ``unknown_table``, and exactly ONE
    ``push_events`` call happens with only the resolved catalog rows.
  - A2 — a pg_partman child-partition suffix (``caja_p_current``) is
    normalized to the logical catalog name before both the lookup AND
    the wire event (``resolve_catalog_name``).
  - A3 — ``_business_payload_for_apply`` strips exactly the queue/audit
    metadata, and for ``[V]`` additionally the versioned-only metadata,
    while preserving every business key.
  - A4 — **BUG 1 (xfail)**: a 401 from ``/sync/events`` marks the batch
    ``http_401`` without ever consulting ``JwtManager``, so the expired
    sync-agent JWT never rotates. Correct behaviour is the SAME JWT
    lifecycle handling the legacy ``_handle_push_response`` performs.
  - A5 — result-count mismatch fails the WHOLE batch loudly, never a
    silent partial drop.
  - A6 — an unrecognized per-row wire status settles as
    ``events_<status>`` (never silent, REQ-CUT-015).

See ``engram`` observation ``mapa-de-cobertura-bugs-del-job-sync-sucursal``
for the full inventory.
"""
from __future__ import annotations

import uuid as uuid_lib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from parkos_core.jobs.sync_sucursal import DEFAULT_BATCH_SIZE, SyncSucursalWorker
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
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


def _make_pending_row(
    tabla: str = "caja",
    *,
    uuid_registro: uuid_lib.UUID | None = None,
    datos: dict | None = None,
) -> MagicMock:
    row = MagicMock()
    row.uuid = uuid_lib.uuid4()
    row.tabla = tabla
    row.uuid_registro = uuid_registro or uuid_lib.uuid4()
    row.uuid_sucursal = uuid_lib.uuid4()
    row.operacion = "insert"
    row.prioridad = 10
    row.datos = datos or {"k": "v"}
    return row


def _wire_up_push_events(worker: SyncSucursalWorker, response: EventsPushResponse) -> AsyncMock:
    worker._http_client = MagicMock()
    worker._http_client.push_events = AsyncMock(return_value=response)
    return worker._http_client.push_events


# ---------------------------------------------------------------------------
# A1 — mixed batch routing (infra / catalog / unknown) + single push call
# ---------------------------------------------------------------------------


class TestMixedBatchRouting:
    @pytest.mark.asyncio
    async def test_infra_and_unknown_and_catalog_route_cleanly(
        self, worker: SyncSucursalWorker
    ) -> None:
        infra = _make_pending_row(tabla="sync_log")
        unknown = _make_pending_row(tabla="not_a_table")
        catalog = _make_pending_row(tabla="caja")

        with (
            patch(
                "parkos_core.jobs.sync_sucursal.sq_helpers.mark_dispatched", AsyncMock()
            ) as mark_dispatched_mock,
            patch(
                "parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed", AsyncMock()
            ) as mark_failed_mock,
        ):
            push_events = _wire_up_push_events(
                worker,
                EventsPushResponse(status=207, results=[{"event_type": "caja", "status": "applied"}]),
            )
            await worker._push_and_handle_catalog([infra, unknown, catalog])

        # Exactly ONE wire call, with ONLY the resolved catalog row.
        push_events.assert_awaited_once()
        sent_events = push_events.await_args.args[0]
        assert isinstance(sent_events, list)
        assert [e["event_type"] for e in sent_events] == ["caja"]
        assert all(e.get("tabla") == "caja" for e in sent_events)

        # Infra settles dispatched (never sent, never failed — D21 guard).
        assert await_args_dispatched(mark_dispatched_mock) == {infra.uuid, catalog.uuid}
        # Unknown settles failed, loudly, with the canonical error.
        assert mark_failed_mock.await_count == 1
        assert mark_failed_mock.await_args.args[1] == unknown.uuid
        assert mark_failed_mock.await_args.args[2] == "unknown_table"

    @pytest.mark.asyncio
    async def test_infra_partition_row_also_dispatched(self, worker: SyncSucursalWorker) -> None:
        """``sync_log_p_current`` (pg_partman child) resolves to the infra
        name ``sync_log`` and never enters the wire."""
        infra_partition = _make_pending_row(tabla="sync_log_p_current")

        with patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.mark_dispatched", AsyncMock()
        ) as mark_dispatched_mock:
            push_events = _wire_up_push_events(
                worker,
                EventsPushResponse(status=207, results=[{"event_type": "caja", "status": "applied"}]),
            )
            await worker._push_and_handle_catalog([infra_partition])

        assert mark_dispatched_mock.await_count == 1
        assert mark_dispatched_mock.await_args.args[1] == infra_partition.uuid
        push_events.assert_not_awaited()


# ---------------------------------------------------------------------------
# A2 — pg_partman suffix normalization on the wire
# ---------------------------------------------------------------------------


class TestPartmanSuffixNormalization:
    @pytest.mark.asyncio
    async def test_partition_table_name_resolved_before_wire(
        self, worker: SyncSucursalWorker
    ) -> None:
        from parkos_core.sync.catalog.sync_catalog import resolve_catalog_name

        table_name = "caja_p_current"
        assert resolve_catalog_name(table_name) == "caja"

        row = _make_pending_row(tabla=table_name)
        with patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.mark_dispatched", AsyncMock()
        ):
            push_events = _wire_up_push_events(
                worker,
                EventsPushResponse(status=207, results=[{"event_type": "caja", "status": "applied"}]),
            )
            await worker._push_and_handle_catalog([row])

        push_events.assert_awaited_once()
        event = push_events.await_args.args[0][0]
        # The WIRE event carries the logical name, never the partition suffix.
        assert event["event_type"] == "caja"
        assert event["tabla"] == "caja"


# ---------------------------------------------------------------------------
# A3 — exact metadata stripping of _business_payload_for_apply
# ---------------------------------------------------------------------------


class TestBusinessPayloadForApply:
    def test_v_entry_strips_queue_meta_and_versioned_meta(self) -> None:
        from parkos_core.jobs.sync_cloud import _business_payload_for_apply

        spec = SYNC_CATALOG_BY_NAME["tipos_vehiculo"]
        assert spec.audit_class == "V"

        raw = {
            "uuid": "11111111-1111-1111-1111-111111111111",
            "vigente_desde": "2026-01-01T00:00:00",
            "vigente_hasta": None,
            "estado": "activo",
            "seq": 3,
            "created_at": "2026-01-01T00:00:00",
            "created_by": "operador@parkos.local",
            "sync_status": "pendiente",
            "sync_timestamp": "2026-01-01T00:00:00",
            "sync_attempts": 0,
            "descripcion": "carro",
        }
        payload = _business_payload_for_apply(spec, raw)
        assert payload == {"descripcion": "carro"}

    def test_a_entry_keeps_uuid_and_versioned_lookalikes(self) -> None:
        from parkos_core.jobs.sync_cloud import _business_payload_for_apply

        spec = SYNC_CATALOG_BY_NAME["caja"]
        assert spec.audit_class == "A"

        raw = {
            "uuid": "11111111-1111-1111-1111-111111111111",
            "uuid_sucursal": "22222222-2222-2222-2222-222222222222",
            "valor_efectivo": 100,
            "valor_datafono": 50,
            "seq": 1,
            "created_at": "2026-01-01T00:00:00",
            "sync_attempts": 0,
        }
        payload = _business_payload_for_apply(spec, raw)
        # Only the queue metadata is stripped for [A]; identity + business
        # attributes survive untouched.
        assert payload == {
            "uuid": raw["uuid"],
            "uuid_sucursal": raw["uuid_sucursal"],
            "valor_efectivo": 100,
            "valor_datafono": 50,
        }

    @pytest.mark.asyncio
    async def test_wire_payload_is_exactly_stripped_payload(
        self, worker: SyncSucursalWorker
    ) -> None:
        """The event the worker puts on the wire is precisely the output of
        ``_business_payload_for_apply`` — no raw ``sync_queue.datos`` leak."""
        from parkos_core.jobs.sync_cloud import _business_payload_for_apply

        spec = SYNC_CATALOG_BY_NAME["caja"]
        datos = {
            "uuid": "11111111-1111-1111-1111-111111111111",
            "uuid_sucursal": "22222222-2222-2222-2222-222222222222",
            "valor_efectivo": 100,
            "valor_datafono": 50,
            "seq": 1,
        }
        row = _make_pending_row(tabla="caja", datos=datos)
        with (
            patch("parkos_core.jobs.sync_sucursal.sq_helpers.mark_dispatched", AsyncMock()),
            patch("parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed", AsyncMock()),
        ):
            push_events = _wire_up_push_events(
                worker,
                EventsPushResponse(status=207, results=[{"event_type": "caja", "status": "applied"}]),
            )
            await worker._push_and_handle_catalog([row])

        event = push_events.await_args.args[0][0]
        assert event["payload"] == _business_payload_for_apply(spec, datos)
        assert "seq" not in event["payload"]


# ---------------------------------------------------------------------------
# A4 — BUG 1 (xfail): catalog push never rotates an expired sync-agent JWT
# ---------------------------------------------------------------------------


class TestCatalogPushJwtRotate:
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG 1: catalog push treats a 401 from /sync/events as a plain "
            "transport failure (sync_sucursal.py:554 -> mark_failed http_401) "
            "and never consults JwtManager — the expired sync-agent JWT is "
            "never rotated. Fix: mirror the legacy _handle_push_response "
            "(sync_sucursal.py:352-380) and dispatch through "
            "JwtManager.on_401_response here."
        ),
    )
    async def test_401_rotates_jwt_like_legacy_path(self, worker: SyncSucursalWorker) -> None:
        pending = [_make_pending_row(tabla="caja")]

        manager = MagicMock()
        manager.on_401_response = AsyncMock(return_value="RETRY_NEW_JWT")
        manager.rotate = AsyncMock(return_value="rotated-jwt")
        worker._jwt_manager = manager

        with patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed", AsyncMock()
        ) as mark_failed_mock:
            _wire_up_push_events(
                worker,
                EventsPushResponse(status=401, results=[]),
            )
            await worker._push_and_handle_catalog(pending)

        # Correct behaviour = JWT lifecycle consulted, exactly once, and the
        # failure tag makes the rotation visible in observability.
        manager.on_401_response.assert_awaited_once()
        error_messages = {c.args[2] for c in mark_failed_mock.await_args_list}
        assert any("401_sync" in m for m in error_messages)


# ---------------------------------------------------------------------------
# A5 — result-count mismatch fails the whole batch
# ---------------------------------------------------------------------------


class TestResultCountMismatch:
    @pytest.mark.asyncio
    async def test_count_mismatch_fails_whole_batch_never_silent_partial(
        self, worker: SyncSucursalWorker
    ) -> None:
        rows = [_make_pending_row(tabla="caja") for _ in range(2)]

        with (
            patch(
                "parkos_core.jobs.sync_sucursal.sq_helpers.mark_dispatched", AsyncMock()
            ) as mark_dispatched_mock,
            patch(
                "parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed", AsyncMock()
            ) as mark_failed_mock,
        ):
            _wire_up_push_events(
                worker,
                # 2 rows sent, 1 result returned — no safe correlation exists.
                EventsPushResponse(status=207, results=[{"event_type": "caja", "status": "applied"}]),
            )
            await worker._push_and_handle_catalog(rows)

        mark_dispatched_mock.assert_not_awaited()
        assert mark_failed_mock.await_count == 2
        assert {c.args[2] for c in mark_failed_mock.await_args_list} == {"result_count_mismatch"}

    @pytest.mark.asyncio
    async def test_non_ok_whole_batch_body_mark_failed(self, worker: SyncSucursalWorker) -> None:
        rows = [_make_pending_row(tabla="caja") for _ in range(2)]

        with patch(
            "parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed", AsyncMock()
        ) as mark_failed_mock:
            _wire_up_push_events(worker, EventsPushResponse(status=503, results=[]))
            await worker._push_and_handle_catalog(rows)

        assert mark_failed_mock.await_count == 2
        assert {c.args[2] for c in mark_failed_mock.await_args_list} == {"http_503"}


# ---------------------------------------------------------------------------
# A6 — unrecognized per-row wire status settles loud
# ---------------------------------------------------------------------------


class TestUnknownWireStatus:
    @pytest.mark.asyncio
    async def test_unknown_wire_status_marks_failed_with_tag(
        self, worker: SyncSucursalWorker
    ) -> None:
        row = _make_pending_row(tabla="caja")

        with (
            patch(
                "parkos_core.jobs.sync_sucursal.sq_helpers.mark_dispatched", AsyncMock()
            ) as mark_dispatched_mock,
            patch(
                "parkos_core.jobs.sync_sucursal.sq_helpers.mark_failed", AsyncMock()
            ) as mark_failed_mock,
        ):
            _wire_up_push_events(
                worker,
                EventsPushResponse(
                    status=207, results=[{"event_type": "caja", "status": "weirdo"}]
                ),
            )
            await worker._push_and_handle_catalog([row])

        mark_dispatched_mock.assert_not_awaited()
        mark_failed_mock.assert_awaited_once()
        assert mark_failed_mock.await_args.args[1] == row.uuid
        assert mark_failed_mock.await_args.args[2] == "events_weirdo"


# ---------------------------------------------------------------------------
# Local helper
# ---------------------------------------------------------------------------


def await_args_dispatched(mock: AsyncMock) -> set:
    """The set of uuids passed to ``mark_dispatched`` across calls."""
    return {c.args[1] for c in mock.await_args_list}