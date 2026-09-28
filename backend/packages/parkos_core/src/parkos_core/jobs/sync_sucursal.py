"""Branch-side sync worker — 6-step main loop (T-PR9-06; T-PR12-004..007
catalog cutover).

The ``SyncSucursalWorker`` runs as the ``job_sync_sucursal`` process on
each branch. It owns the local ``prod.sync_queue`` ([A] carved-out
table) and the long-lived ``sync-agent-`` JWT; every cycle it:

    1. ``poll sync_queue``          → ``repo.sync_queue.list_pending``
    2. ``push batch``               → legacy: ``SyncHttpClient.push``
                                       (``/sync/push``) — catalog:
                                       ``SyncHttpClient.push_events``
                                       (``/sync/events``, T-PR12-006)
    3. ``handle response``          → legacy: mark_dispatched /
                                       mark_failed / JwtManager.
                                       on_401_response — catalog: per-row
                                       wire status (``applied`` /
                                       ``conflict`` / ``retry_parent_
                                       missing`` all settle as
                                       dispatched, T-PR12-005; anything
                                       else is a genuine failure)
    4. ``pull cloud changes``       → ``SyncHttpClient.pull`` → legacy:
                                       ``ConflictResolver.apply_pushed_row``
                                       — catalog: ``SyncMotor.apply_batch``
                                       (T-PR12-006)
    5. ``heartbeat``                → ``SyncHttpClient.heartbeat``
    6. ``sleep until next cycle``   → ``PARKOS_SYNC_POLL_INTERVAL_S``

Which of the two (legacy vs. catalog) applies each cycle is decided by
:meth:`SyncSucursalWorker._detect_applier_mode` (T-PR12-007, REQ-CUT-005) —
the branch's own auto-detect from ``GET /sync/hello``, cached for
``dual_protocol.BRANCH_CACHE_TTL_SECONDS`` (300s) and fail-safe to the
legacy applier on ANY HTTP error/timeout, non-OK response, or a branch
version below the cloud's advertised minimum. This decision is
INDEPENDENT of this process's own ``PARKOS_SYNC_ENGINE`` env value — D11's
whole point is that a branch decides from what the CLOUD advertises, not
from its own local flag, so upgrades don't have to happen in lockstep.

The class extends :class:`parkos_core.jobs.runner.WorkerRunner` (PR9
T-PR9-01) so it inherits SIGTERM/SIGINT graceful shutdown + structured
logging + the §21.7 exit-code contract. The default ``WorkerRunner.run``
calls :meth:`cycle` in a loop; :meth:`cycle` here is the 6-step block
above.

Workers NEVER run raw ``session.execute(update/delete)`` against [A] or
[V] tables — every persistence call goes through the corresponding
``repo.*`` helper (defense in depth, AGENTS.md §1 + §3). The
``tests/static/test_no_raw_dml_on_a_tables.py`` AST scan enforces this
for the workers too.

Why we don't await ``heartbeat`` in the middle of ``cycle``: per spec
§21.7 the heartbeat is a fire-and-forget POST; if it fails the worker
should NOT halt the cycle. We ``try/except`` around it and log a
``heartbeat_failed`` event so the operator can see the trend without
the worker dying on a transient network blip.

The ``cycle`` is idempotent over a single batch — if a SIGTERM arrives
mid-push, the in-flight HTTP request finishes, the cycle returns, and
the next :meth:`run` is the one that exits. The push itself is not
retried (the cloud marks the batch as either accepted or rejected, and
the next cycle picks up any rows still ``pendiente``).

Cites §21.7 (job_sync_sucursal main loop), tasks.md T-PR9-06,
T-PR12-004..007.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid as uuid_lib
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from parkos_core.jobs.runner import WorkerRunner
from parkos_core.jobs.sync_cloud import _business_payload_for_apply, is_infra_table
from parkos_core.repo import sync_cursor as sync_cursor_helpers
from parkos_core.repo import sync_queue as sq_helpers
from parkos_core.runtime import engine_flag
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME, resolve_catalog_name
from parkos_core.sync.cutover import dual_protocol
from parkos_core.sync.jwt_manager import JwtAction, JwtManager
from parkos_core.sync.motor import apply_guard
from parkos_core.sync.motor.sync_motor import SyncMotor, describe_apply_error
from parkos_core.sync.transport import (
    EventsPushResponse,
    HelloResponse,
    PushResponse,
    SyncHttpClient,
    SyncJwtMissingError,
)

# Default cycle cadence if the env does not set PARKOS_SYNC_POLL_INTERVAL_S.
DEFAULT_POLL_INTERVAL_S = 10
# Default batch size cap per cycle.
DEFAULT_BATCH_SIZE = 100
# This branch worker's own semver — compared against /sync/hello's
# min_branch_version (REQ-CUT-005 row 3). Override via PARKOS_BRANCH_VERSION
# for a branch deliberately pinned below the cloud's minimum (tests, staged
# rollouts). Mirrors dual_protocol.DEFAULT_MIN_BRANCH_VERSION's own default.
DEFAULT_BRANCH_VERSION = dual_protocol.DEFAULT_MIN_BRANCH_VERSION


class ApplierMode(StrEnum):
    """Which applier this cycle uses (T-PR12-007, REQ-CUT-005)."""

    LEGACY = "legacy"
    CATALOG = "catalog"


def _parse_semver(value: str) -> tuple[int, int, int]:
    """Best-effort ``"X.Y.Z"`` -> ``(X, Y, Z)``; non-digit suffixes ignored.

    Never raises — an unparseable segment reads as 0 so a malformed
    version compares as "old" rather than crashing the auto-detect cycle.
    """
    parts: list[int] = []
    for chunk in value.split(".")[:3]:
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


def _version_gte(a: str, b: str) -> bool:
    """``True`` iff semver ``a >= b`` (REQ-CUT-005's branch_version compare)."""
    return _parse_semver(a) >= _parse_semver(b)


def _failed_count(result: Any) -> int:
    """How many rows in this batch raised.

    ``getattr`` rather than ``result.failed`` because ``apply_batch``'s
    result is duck-typed in several existing tests, which build it as a
    ``SimpleNamespace`` without the field. Reading it directly turned a
    green suite red for a reason that has nothing to do with behaviour.
    """
    return len(getattr(result, "failed", None) or [])


class SyncSucursalWorker(WorkerRunner):
    """Branch-side sync worker — 6-step main loop per design §21.7.

    Args:
        jwt_path: Path to the long-lived ``sync-agent-`` JWT
            (``PARKOS_SYNC_JWT_PATH``).
        base_url: Cloud API base URL (``PARKOS_CLOUD_API_URL``).
        session: An open ``AsyncSession`` for the branch DB. The
            caller owns the session lifecycle; the worker adds rows to
            it and the caller commits.
        poll_interval_s: Seconds to sleep between cycles
            (``PARKOS_SYNC_POLL_INTERVAL_S``).
        batch_size: Maximum rows per ``push`` cycle
            (``PARKOS_SYNC_BATCH_SIZE``).
        branch_version: Semver of this worker, compared against
            ``/sync/hello``'s ``min_branch_version`` (T-PR12-007,
            REQ-CUT-005). Defaults to ``PARKOS_BRANCH_VERSION`` or
            :data:`DEFAULT_BRANCH_VERSION`.
        uuid_sucursal: THIS branch's UUID (``PARKOS_SUCURSAL_UUID``).
            Optional: when set, the worker persists its cloud-pull
            high-water mark in ``prod.sync_cursor`` (CU-07) and re-pulls
            from the cursor instead of re-snapshotting ``since_seq=0``
            every cycle. When ``None`` (the safe default — keeps every
            existing test/caller working), each cycle re-pulls the full
            idempotent snapshot exactly as before.
        logger: Optional structlog ``BoundLogger``; defaults to
            ``parkos.jobs.sync_sucursal``.
    """

    def __init__(
        self,
        *,
        jwt_path: Path,
        base_url: str,
        session: AsyncSession,
        poll_interval_s: int = DEFAULT_POLL_INTERVAL_S,
        batch_size: int = DEFAULT_BATCH_SIZE,
        branch_version: str | None = None,
        uuid_sucursal: uuid_lib.UUID | None = None,
        logger: structlog.stdlib.BoundLogger | None = None,
    ) -> None:
        super().__init__(name="sync_sucursal")
        self.jwt_path = Path(jwt_path)
        self.base_url = base_url.rstrip("/")
        self._session = session
        self.poll_interval_s = max(1, int(poll_interval_s))
        self.batch_size = max(1, int(batch_size))
        self.branch_version = (
            branch_version or os.environ.get("PARKOS_BRANCH_VERSION") or DEFAULT_BRANCH_VERSION
        )
        self.uuid_sucursal = uuid_sucursal
        self.log = logger or structlog.get_logger("parkos.jobs.sync_sucursal")

        # Per-cycle collaborators — instantiated lazily inside cycle()
        # so a misconfigured JWT path doesn't fail at __init__ time (the
        # worker is meant to log + retry on every cycle, not crash on
        # boot).
        self._jwt_manager: JwtManager | None = None
        self._http_client: SyncHttpClient | None = None
        # T-PR12-006 — the catalog-driven applier, built lazily with the
        # EXPLICIT catalog_branch engine mode (never engine_flag.get_engine()
        # — D11's whole point is that the branch decides from what /sync/
        # hello advertises, not from its own local PARKOS_SYNC_ENGINE).
        self._motor: SyncMotor | None = None
        # T-PR12-007 — auto-detect cache: (mode, time.monotonic() at cache time).
        self._applier_cache: tuple[ApplierMode, float] | None = None
        # Track per-row in-flight seq so a partial-push (HTTP 207) can
        # tell which rows the cloud accepted vs rejected.
        self._last_pushed_uuids: list[uuid_lib.UUID] = []
        # Consecutive cycles in which at least one pulled row could not be
        # applied. Drives BOTH the log escalation and /healthz: this defect
        # shipped 522 identical failures over 11 hours behind a container
        # that kept reporting `healthy`, because nothing bridged a logical
        # pull failure to the process-liveness signal Docker watches.
        self._consecutive_apply_failures = 0
        self._last_apply_error: str | None = None

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    async def cycle(self) -> None:
        """One iteration of the 6-step main loop.

        :class:`WorkerRunner.run` calls this in a loop until SIGTERM/SIGINT.

        Rolls ``self._session`` back before propagating. The session is
        owned by ``main()`` for the whole container lifetime, so a raise
        that leaves the transaction aborted poisons every LATER cycle with
        ``InFailedSQLTransactionError`` and buries the original error
        forever: one transient fault would read as a permanent opaque one.
        """
        try:
            await self._run_cycle()
        except BaseException:
            try:
                await self._session.rollback()
            except Exception:  # noqa: BLE001 - any rollback failure must not mask the real error
                # Never let a failed rollback mask the original error.
                self.log.warning("sync_sucursal.cycle_rollback_failed")
            raise

    async def _run_cycle(self) -> None:
        # Lazily build collaborators — JWT file might be missing on first
        # boot (pre-pairing); the loop tolerates that and retries next cycle.
        if self._http_client is None:
            self._http_client = SyncHttpClient(
                base_url=self.base_url,
                jwt_path=self.jwt_path,
            )
        if self._jwt_manager is None:
            self._jwt_manager = JwtManager(jwt_path=self.jwt_path, base_url=self.base_url)

        # T-PR12-007 — decide the applier for THIS cycle (cached 300s).
        mode = await self._detect_applier_mode()

        # 1. Poll sync_queue (unchanged selection regardless of mode,
        #    T-PR12-006).
        pending = await sq_helpers.list_pending(
            self._session,
            limit=self.batch_size,
        )
        if pending:
            self._last_pushed_uuids = [row.uuid for row in pending]
            if mode is ApplierMode.CATALOG:
                await self._push_and_handle_catalog(pending)
            else:
                await self._push_and_handle(pending)
        else:
            self.log.debug("sync_sucursal.idle", batch_size=self.batch_size)

        # 4. Pull cloud changes (always — even when there's nothing to push).
        if mode is ApplierMode.CATALOG:
            await self._pull_and_apply_catalog()
        else:
            await self._pull_and_apply()

        # CU-07 BR3 (Track 3, sync-sucursal-sweep-exhausted): after the
        # push + pull work, one extra SELECT per cycle hunts pending rows
        # that exhausted the queue-lifetime SLA (24h since FIRST enqueue
        # or intentos >= len(BACKOFF_SCHEDULE)) and converts them to
        # ``fallido permanente`` + an ``evento_no_procesado`` alert. Runs
        # INSIDE this cycle so mark_exhausted + the alerta row commit
        # atomically with everything else below.
        await self._sweep_exhausted()

        # Real bug found + fixed (Docker deployment closing exercise,
        # post-testcontainers): ``self._session`` is owned by ``main()``'s
        # ``_run()`` for the ENTIRE container lifetime and NOTHING in this
        # file ever called ``commit()`` — every ``mark_dispatched``/
        # ``mark_failed``/applied row from steps 1-4 above sat in one
        # never-committed, ever-growing transaction for as long as the
        # process ran. Invisible in the pytest/testcontainers exercise
        # (the test itself commits explicitly after calling
        # ``_push_and_handle_catalog`` — see
        # ``test_e2e_full_catalog_sync.py::push_and_verify``) but fatal
        # for the real long-lived worker: nothing this cycle settles is
        # ever durable, and the open transaction blocks concurrent DDL
        # (confirmed: alembic upgrade 0011 failed with
        # ``LockNotAvailable`` against a real ``idle in transaction``
        # backend held by this same worker pattern on the cloud side).
        await self._session.commit()

        # 5. Heartbeat (fire-and-forget; don't fail the cycle).
        await self._heartbeat_safe()

        # 6. Sleep until the next cycle.
        await asyncio.sleep(self.poll_interval_s)

    # ------------------------------------------------------------------
    # Step 2+3: push + handle response
    # ------------------------------------------------------------------

    async def _push_and_handle(self, pending: list) -> None:
        """Push the batch and handle the cloud's response.

        Status code contract (per spec §21.7):

        - 2xx      → ``mark_dispatched`` for every row.
        - 207      → partial: body has ``results`` (one per request row,
                     in request order); ``applied``/``conflict``/
                     ``retry_parent_missing`` settle the row, anything
                     else (e.g. ``unknown_table``) fails it. Correlated
                     by INDEX, never by uuid.
        - 401      → ``JwtManager.on_401_response``. ``RETRY_NEW_JWT``
                     triggers a rotate and the next cycle retries the
                     push. Anything else (HALT_*) raises out so the
                     worker exits.
        - 4xx      → ``mark_failed`` for every row + backoff_4xx[i].
        - 5xx      → ``mark_failed`` for every row + backoff_5xx[i]
                     (short backoff — cloud is transiently down).
        """
        assert self._http_client is not None
        # Serialize sync_queue rows for the wire. We use ``to_dict()`` if
        # present; otherwise build the wire shape explicitly so the helper
        # doesn't depend on a custom ORM mixin.
        payload = [_wire_shape(row) for row in pending]

        try:
            response = await self._http_client.push(payload)
        except SyncJwtMissingError as exc:
            # Pre-pairing — same contract as the catalog push path (Bug 6):
            # log, skip, never schedule a retry for a missing JWT.
            self.log.warning("sync_sucursal.push_skipped_jwt_missing", error=str(exc))
            return
        except (TimeoutError, httpx.HTTPError, OSError) as exc:
            # Transport / DNS / timeout failure — treat as transient
            # (5xx-equivalent) so mark_failed schedules a retry via
            # the backoff schedule.
            self.log.error("sync_sucursal.push_transport_error", error=str(exc))
            await self._mark_failed_batch(
                pending,
                error=f"transport: {exc}",
            )
            return

        await self._handle_push_response(response, pending)

    async def _handle_push_response(
        self,
        response: PushResponse,
        pending: list,
    ) -> None:
        """Translate a ``PushResponse`` into repo writes."""
        status = response.status

        # 207 Multi-Status — partial. Correlate by INDEX, not by uuid.
        # The response rows carry ``uuid_registro`` (the BUSINESS row's
        # uuid) while ``row.uuid`` here is the sync_queue row's own uuid —
        # two different namespaces that can never match, so a
        # ``success_uuids`` intersection would be empty for EVERY row and
        # wedge the whole batch in a retry loop. The receiver echoes one
        # result per request row in request order, so index is the
        # authoritative correlation — the same convention
        # ``_push_and_handle_catalog`` already uses.
        if status == 207:
            results = _push_results(response)
            if results is None or len(results) != len(pending):
                # Never guess a correlation across a mismatched count — fail
                # the whole batch loudly (never a silent partial drop).
                self.log.error(
                    "sync_sucursal.push_result_count_mismatch",
                    sent=len(pending),
                    received=len(results) if results is not None else None,
                )
                await self._mark_failed_batch(pending, error="result_count_mismatch")
                return
            accepted = 0
            rejected = 0
            for row, result in zip(pending, results, strict=True):
                wire_status = result.get("status")
                if wire_status in ("applied", "conflict", "retry_parent_missing"):
                    # design.md §2 Issue #8's table — the same three are the
                    # SAME outbox action here as on the catalog path: a
                    # conflict is a decision and a dependency wait is not a
                    # transport failure (T-PR12-005 leaves intentos/
                    # next_retry_at untouched).
                    await sq_helpers.mark_dispatched(self._session, row.uuid)
                    accepted += 1
                else:
                    # "unknown_table" or anything unrecognized — never a
                    # silent drop (REQ-CUT-015).
                    await sq_helpers.mark_failed(
                        self._session,
                        row.uuid,
                        f"push_{wire_status}",
                    )
                    rejected += 1
            if rejected:
                self.log.warning(
                    "sync_sucursal.push_partial",
                    status=status,
                    accepted=accepted,
                    rejected=rejected,
                )
            else:
                self.log.info(
                    "sync_sucursal.push_ok",
                    sent=len(pending),
                    status=status,
                )
            return

        # 2xx (except 207) — clean success.
        if 200 <= status < 300:
            for row in pending:
                await sq_helpers.mark_dispatched(self._session, row.uuid)
            self.log.info("sync_sucursal.push_ok", sent=len(pending), status=status)
            return

        # 401 — JWT lifecycle event.
        if status == 401:
            assert self._jwt_manager is not None
            # ``on_401_response`` may raise SystemExit on the revoked
            # case (per jwt_manager docstring). Let it propagate —
            # WorkerRunner.run maps it to the orchestrator restart-loop.
            action = await self._jwt_manager.on_401_response(_fake_httpx_response(response))
            if action == JwtAction.RETRY_NEW_JWT:
                self.log.info("sync_sucursal.rotating_jwt_after_401")
                await self._jwt_manager.rotate()
                # Don't retry the SAME push in this cycle — the next
                # cycle picks it up cleanly (mark_failed for now so we
                # see the gap in metrics).
                for row in pending:
                    await sq_helpers.mark_failed(
                        self._session,
                        row.uuid,
                        "401_sync_jwt_rotated_will_retry_next_cycle",
                    )
            else:
                # HALT_REVOKED / HALT_EXPIRED — defensive. The worker
                # will exit on the next iteration; mark failed so the
                # metrics reflect what happened.
                for row in pending:
                    await sq_helpers.mark_failed(
                        self._session,
                        row.uuid,
                        f"401_{action}",
                    )
            return

        # 4xx (non-401) — permanent client error; no retry.
        if 400 <= status < 500:
            for row in pending:
                await sq_helpers.mark_failed(self._session, row.uuid, f"http_{status}")
            self.log.warning("sync_sucursal.push_4xx", status=status, sent=len(pending))
            return

        # 5xx — transient cloud failure; backoff.
        if 500 <= status < 600:
            # Use the FIRST 5xx step (30s) as the initial delay; the
            # repo's ``mark_failed`` schedules the next retry via
            # ``next_retry_delay`` which reads the row's own intentos
            # count. We pass an error message that records the status.
            for row in pending:
                await sq_helpers.mark_failed(self._session, row.uuid, f"http_{status}")
            self.log.warning("sync_sucursal.push_5xx", status=status, sent=len(pending))
            return

        # Anything else — defensive: log and mark failed so we don't
        # tight-loop on an unknown status.
        self.log.error("sync_sucursal.push_unknown_status", status=status, sent=len(pending))
        for row in pending:
            await sq_helpers.mark_failed(self._session, row.uuid, f"http_unknown_{status}")

    async def _mark_failed_batch(
        self,
        pending: list,
        *,
        error: str,
    ) -> None:
        """Mark every row failed with a custom error message.

        ``sq_helpers.mark_failed`` increments ``intentos`` and computes
        ``next_retry_at`` from the backoff schedule. The schedule is
        the canonical retry clock per AGENTS.md §1 — we don't pass a
        delay directly because that would bypass the schedule.
        """
        for row in pending:
            await sq_helpers.mark_failed(self._session, row.uuid, error)
        # The caller may also want to sleep; this helper does NOT
        # sleep itself — the cycle's outer ``asyncio.sleep`` does.

    # ------------------------------------------------------------------
    # T-PR12-007 — branch auto-detect from /sync/hello (REQ-CUT-005)
    # ------------------------------------------------------------------

    async def _detect_applier_mode(self) -> ApplierMode:
        """Decide legacy vs. catalog applier for THIS cycle (REQ-CUT-005).

        | Condition | Applier |
        |---|---|
        | ``protocol_version == "legacy"`` | Legacy (current code) |
        | ``protocol_version == "catalog"`` AND ``branch_version >= min_branch_version`` | Catalog (``SyncMotor``, ``catalog_branch``) |
        | ``protocol_version == "catalog"`` AND ``branch_version < min_branch_version`` | Legacy + ``WARN catalog_too_new`` |
        | HTTP error / timeout | Legacy (fail-safe — never blocks branch operations) |

        Cached for ``dual_protocol.BRANCH_CACHE_TTL_SECONDS`` (300s,
        REQ-CUT-004) so the worker doesn't hammer ``/sync/hello`` every
        cycle. This decision is INDEPENDENT of this process's own
        ``PARKOS_SYNC_ENGINE`` — see the module docstring.
        """
        now = time.monotonic()
        if (
            self._applier_cache is not None
            and (now - self._applier_cache[1]) < dual_protocol.BRANCH_CACHE_TTL_SECONDS
        ):
            return self._applier_cache[0]

        assert self._http_client is not None
        try:
            hello: HelloResponse = await self._http_client.hello()
        except (TimeoutError, httpx.HTTPError, OSError) as exc:
            self.log.warning("sync_sucursal.hello_failed_fallback_legacy", error=str(exc))
            mode = ApplierMode.LEGACY
            self._applier_cache = (mode, now)
            return mode

        if hello.status != 200 or hello.protocol_version is None:
            self.log.warning("sync_sucursal.hello_non_ok_fallback_legacy", status=hello.status)
            mode = ApplierMode.LEGACY
        elif hello.protocol_version == "legacy":
            mode = ApplierMode.LEGACY
        elif hello.protocol_version == "catalog":
            min_version = hello.min_branch_version or DEFAULT_BRANCH_VERSION
            if _version_gte(self.branch_version, min_version):
                mode = ApplierMode.CATALOG
            else:
                self.log.warning(
                    "sync_sucursal.catalog_too_new",
                    branch_version=self.branch_version,
                    min_branch_version=min_version,
                )
                mode = ApplierMode.LEGACY
        else:
            self.log.warning(
                "sync_sucursal.hello_unknown_protocol_fallback_legacy",
                protocol_version=hello.protocol_version,
            )
            mode = ApplierMode.LEGACY

        self._applier_cache = (mode, now)
        return mode

    # ------------------------------------------------------------------
    # T-PR12-006 — catalog-driven push via /sync/events
    # ------------------------------------------------------------------

    async def _push_and_handle_catalog(self, pending: list) -> None:
        """Catalog-driven push via ``/sync/events`` (T-PR12-006).

        Batch SELECTION is unchanged — ``pending`` already comes from
        ``list_pending``'s ordering/limit (step 1); only the wire contract
        + per-row settlement changes versus the legacy ``/sync/push`` path.
        The receiver (cloud's ``/sync/events``, T-PR11-006) applies each
        row through ``SyncMotor`` and returns REQ-MOT-005's wire vocabulary,
        which this method maps 1:1 to ``sync_queue`` actions per design.md
        §2 Issue #8's table: ``applied``/``conflict``/``retry_parent_
        missing`` are ALL "delivered" — none of them touch ``intentos`` or
        ``next_retry_at`` (T-PR12-005). Only a genuine transport failure or
        an unrecognized wire status is a real dispatch failure.
        """
        assert self._http_client is not None

        events: list[dict[str, Any]] = []
        resolved_rows: list[Any] = []

        for row in pending:
            tabla = getattr(row, "tabla", None)
            if is_infra_table(tabla):
                # D21 guard — an out-of-catalog infra row never reaches
                # sync in the first place; settle it, never mark_failed.
                await sq_helpers.mark_dispatched(self._session, row.uuid)
                continue
            # Normalize a pg_partman child-partition suffix BEFORE the
            # catalog lookup (see catalog/sync_catalog.py::resolve_catalog_
            # name's docstring) — 3 of the 8 partitioned tables
            # (log_transaccional, caja, arqueo) can be branch-authored
            # branch_to_cloud rows reaching this exact push path, and a raw
            # trigger-sourced ``tabla`` for them never matches
            # SYNC_CATALOG_BY_NAME directly. The WIRE event below carries
            # the already-normalized name so the cloud-side receiver
            # (sync_router.py::sync_events, unmodified) never has to
            # perform this normalization itself.
            catalog_tabla = resolve_catalog_name(tabla) if tabla else tabla
            spec = SYNC_CATALOG_BY_NAME.get(catalog_tabla)
            if spec is None:
                # Never a silent drop (REQ-CUT-015) — a tabla outside the
                # catalog is a genuine anomaly.
                await sq_helpers.mark_failed(self._session, row.uuid, "unknown_table")
                continue

            payload = _business_payload_for_apply(spec, row.datos or {})
            events.append(
                {
                    "event_type": catalog_tabla,
                    "tabla": catalog_tabla,
                    "uuid_registro": str(row.uuid_registro) if row.uuid_registro else None,
                    "payload": payload,
                }
            )
            resolved_rows.append(row)

        if not resolved_rows:
            return

        try:
            response: EventsPushResponse = await self._http_client.push_events(events)
        except SyncJwtMissingError as exc:
            # Pre-pairing state — the cycle docstring promises the loop
            # tolerates a missing JWT and retries next cycle (it is NOT a
            # dispatch failure: don't touch intentos/next_retry_at). Log and
            # let cycle() move on to step 4 (pull) + commit.
            self.log.warning("sync_sucursal.push_skipped_jwt_missing", error=str(exc))
            return
        except (TimeoutError, httpx.HTTPError, OSError) as exc:
            self.log.error("sync_sucursal.push_events_transport_error", error=str(exc))
            await self._mark_failed_batch(resolved_rows, error=f"transport: {exc}")
            return

        if response.status not in (200, 207):
            self.log.warning("sync_sucursal.push_events_non_ok", status=response.status)
            # 401 — JWT lifecycle event (Bug 1): mirror the legacy
            # ``_handle_push_response`` 401 branch so an expired sync-agent
            # JWT is rotated instead of being treated as a plain transport
            # failure. ``on_401_response`` may raise SystemExit on the
            # revoked case; let it propagate (orchestrator restart-loop).
            if response.status == 401:
                assert self._jwt_manager is not None
                action = await self._jwt_manager.on_401_response(_fake_httpx_response(response))
                if action == JwtAction.RETRY_NEW_JWT:
                    self.log.info("sync_sucursal.rotating_jwt_after_401_catalog")
                    await self._jwt_manager.rotate()
                    # Don't retry the SAME push in this cycle — the next
                    # cycle picks it up cleanly (mark_failed for now so we
                    # see the gap in metrics).
                    await self._mark_failed_batch(
                        resolved_rows,
                        error="401_sync_jwt_rotated_will_retry_next_cycle",
                    )
                else:
                    # HALT_REVOKED / HALT_EXPIRED — defensive. mark failed so
                    # the metrics reflect what happened.
                    await self._mark_failed_batch(resolved_rows, error=f"401_{action}")
                return
            await self._mark_failed_batch(resolved_rows, error=f"http_{response.status}")
            return

        results = response.results
        if len(results) != len(resolved_rows):
            # Never guess a correlation across a mismatched count — fail
            # the whole batch loudly (never a silent partial drop).
            self.log.error(
                "sync_sucursal.push_events_result_count_mismatch",
                sent=len(resolved_rows),
                received=len(results),
            )
            await self._mark_failed_batch(resolved_rows, error="result_count_mismatch")
            return

        for row, result in zip(resolved_rows, results, strict=True):
            wire_status = result.get("status")
            if wire_status in ("applied", "conflict", "retry_parent_missing"):
                # design.md §2 Issue #8's table — all three are the SAME
                # outbox action; a dependency wait is not a transport
                # failure (T-PR12-005: intentos/next_retry_at untouched).
                await sq_helpers.mark_dispatched(self._session, row.uuid)
            else:
                # "unknown_table" (receiver-side) or anything unrecognized
                # — never a silent drop (REQ-CUT-015).
                await sq_helpers.mark_failed(self._session, row.uuid, f"events_{wire_status}")

    # ------------------------------------------------------------------
    # Step 4: pull + apply
    # ------------------------------------------------------------------

    async def _persist_pull_cursor(
        self, *, next_seq: int, unresolved: int, failed: int = 0
    ) -> None:
        """Advance the branch pull watermark (CU-07) when safe.

        Three hard guards before persisting ``next_seq``:

        * ``uuid_sucursal`` is set — without it there is no cursor,
          behavior stays the legacy full ``since_seq=0`` resnapshot. The
          callers below run for the default ``uuid_sucursal=None``
          constructor (existing tests), so this helper MUST check it:
          ``set_seq`` would otherwise INSERT a NULL ``uuid_sucursal`` and
          violate the column's NOT NULL.
        * ``unresolved == 0`` — a row whose ``tabla`` is outside THIS
          branch's catalog was NOT applied. Advancing past it would make
          the next pull (``since_seq`` above it) skip it forever: a
          silent drop (REQ-CUT-015). Freezing the watermark re-delivers
          it next cycle, idempotent via ``apply_guard.row_already_present``.
        * ``failed == 0`` — same reasoning for a row that raised inside its
          SAVEPOINT. The rows around it DID land, and re-delivering the
          batch is free (``row_already_present`` skips them), so freezing
          is correct: it retries the poison row without re-doing the rest.
        """
        if self.uuid_sucursal is None or unresolved or failed:
            return
        await sync_cursor_helpers.set_seq(
            self._session,
            uuid_sucursal=self.uuid_sucursal,
            ultimo_seq=next_seq,
        )

    # Consecutive cycles with at least one unappliable pulled row before the
    # node reports itself degraded. Three is the same threshold AGENTS.md
    # already uses for the container healthcheck restart policy, so the two
    # signals escalate on the same cadence instead of inventing a new one.
    APPLY_FAILURE_DEGRADED_THRESHOLD = 3

    def sync_health(self) -> dict[str, Any]:
        """LOGICAL sync health, for the container's ``/healthz`` probe.

        Docker's HEALTHCHECK answers "is the process alive?", which stayed
        true for 11 hours while this worker rejected every batch it pulled.
        This answers the question the incident actually needed answered:
        is this node CONSUMING its cloud-to-branch changes?

        Kept separate from process liveness on purpose. Restarting the
        process would not have fixed the divergence it was reporting, and a
        crash-loop would have hidden a still-alive-but-starved node behind a
        restarting one.
        """
        consecutive = self._consecutive_apply_failures
        return {
            "ok": consecutive < self.APPLY_FAILURE_DEGRADED_THRESHOLD,
            "consecutive_apply_failures": consecutive,
            "degraded_threshold": self.APPLY_FAILURE_DEGRADED_THRESHOLD,
            # The constraint name, not the driver message. /healthz is polled
            # live and repeatedly; the log line it mirrors rotates away, and
            # this is the difference between "something is wrong" and "this
            # exact foreign key has no parent on this node".
            "last_apply_error": self._last_apply_error,
        }

    def health_report(self) -> dict[str, Any]:
        """Wire this worker's logical sync health into ``/healthz``."""
        return self.sync_health()

    def _note_clean_cycle(self) -> None:
        """A cycle landed everything it pulled: clear the failure streak.

        Called for a genuinely clean cycle INCLUDING one that had nothing to
        apply. Without the empty-batch case, a node that degraded during an
        incident would stay 503 forever afterwards, because a quiet cloud
        produces no further cycles to clear it.
        """
        if self._consecutive_apply_failures:
            self.log.info(
                "sync_sucursal.pull_apply_recovered",
                previous_consecutive=self._consecutive_apply_failures,
            )
        self._consecutive_apply_failures = 0
        self._last_apply_error = None

    def _record_apply_outcome(self, result: Any) -> None:
        """Report per-row apply failures and update the health counter.

        The counter RESETS on a fully clean cycle, so a transient bad batch
        does not permanently degrade a node that has since recovered.
        """
        failed = getattr(result, "failed", None) or []
        if not failed:
            self._note_clean_cycle()
            return

        self._consecutive_apply_failures += 1
        # Count by reason so a recurring constraint is visible as a pattern
        # rather than as N indistinguishable rows.
        reasons: dict[str, int] = {}
        for _spec, _payload, reason in failed:
            reasons[reason] = reasons.get(reason, 0) + 1
        self._last_apply_error = max(reasons, key=lambda r: (reasons[r], r))
        self._log_degraded(
            "sync_sucursal.pull_apply_rows_failed",
            failed=len(failed),
            reasons=reasons,
            tables=sorted({spec.name for spec, _p, _r in failed if spec is not None}),
        )

    def _note_batch_failure(self, exc: BaseException) -> None:
        """A whole-batch raise is still "this node is not consuming".

        ``apply_batch`` isolates per-row failures, but a fault in the batch
        itself - ordering, session state - escapes it. That path must count
        too, or a node wedging on every cycle reports itself healthy, which
        is the failure mode this whole change exists to end.
        """
        self._consecutive_apply_failures += 1
        self._last_apply_error = describe_apply_error(exc)
        self._log_degraded(
            "sync_sucursal.pull_apply_batch_failed",
            failed=1,
            reasons={self._last_apply_error: 1},
            tables=[],
        )

    def _log_degraded(self, event: str, **fields: Any) -> None:
        """Log at ``error`` once the streak is past the threshold, else ``warn``.

        The level flip is the escalation: a single bad row is a warning, a
        sustained streak stops being noise and becomes the reason a node is
        not syncing.
        """
        consecutive = self._consecutive_apply_failures
        log = (
            self.log.error
            if consecutive >= self.APPLY_FAILURE_DEGRADED_THRESHOLD
            else self.log.warning
        )
        log(
            event,
            consecutive=consecutive,
            degraded=consecutive >= self.APPLY_FAILURE_DEGRADED_THRESHOLD,
            **fields,
        )

    async def _pull_and_apply(self) -> None:
        """Pull cloud changes and apply each one (Bug 4 fix).

        The pre-PR7 ``ConflictResolver.apply_pushed_row`` used to APPLY the
        row and return the outcome; PR7 (T-PR7-004) turned it into a pure
        decision shim ("the caller is responsible for translating outcomes
        into repo writes") but this legacy caller was never updated --
        since PR7 it only COLLECTED the decision and never wrote a single
        row. Two pulls of the same remote row landed ZERO local rows
        (test C5 pinned ``count == 0`` under LEG), and the fresh-uuid
        duplicate concern in the old comment described a path that never
        even reached an INSERT.

        Fix (Bug 4): dedup each delivery by ``uuid_registro`` via the
        shared ``apply_guard.row_already_present`` guard (the same one
        ``_pull_and_apply_catalog`` uses) and apply resolved rows through
        ``SyncMotor.apply_batch`` -- the same catalog pipeline, which
        preserves the incoming ``uuid`` end to end
        (``repo.versioned.close_and_insert`` carries ``payload["uuid"]``
        into the new version via ``new_attrs``). A decision-only no-op is
        not an applier.

        CU-07 (pull cursor): when ``self.uuid_sucursal`` is set, the
        branch pulls from its persisted high-water mark instead of
        re-snapshotting ``since_seq=0`` every cycle, and advances the
        cursor ONLY after a batch that applied cleanly with NO unresolved
        row. ``since_seq`` is the cursor minus 1 (epoch-ms) so a second
        row sharing the same ``created_at`` ms as the high-water mark is
        re-delivered instead of silently skipped (``apply_guard.
        row_already_present`` dedups it). When the cursor is ``None``
        (default), behavior is unchanged: full ``since_seq=0`` resnapshot.
        """
        assert self._http_client is not None

        cursor_seq = 0
        if self.uuid_sucursal is not None:
            cursor_seq = await sync_cursor_helpers.get_seq(
                self._session, uuid_sucursal=self.uuid_sucursal
            )
        # ``max(0, cursor - 1)``: re-deliver the last epoch-ms so a row
        # with the SAME ``created_at`` ms as the cursor is not skipped.
        since_seq = max(0, cursor_seq - 1)

        try:
            pulled = await self._http_client.pull(since_seq=since_seq)
        except SyncJwtMissingError as exc:
            # Pre-pairing — same contract as the push path (Bug 6): the
            # cycle keeps committing, JWT rotation not involved.
            self.log.warning("sync_sucursal.pull_skipped_jwt_missing", error=str(exc))
            return
        except (TimeoutError, httpx.HTTPError, OSError) as exc:
            self.log.error("sync_sucursal.pull_transport_error", error=str(exc))
            return

        if pulled.status != 200:
            self.log.warning("sync_sucursal.pull_non_ok", status=pulled.status)
            return

        if not pulled.rows:
            return

        # Echo-amplification fix (post-PR14 real-Docker closing exercise,
        # real defect #3; migration 0016_add_sync_apply_guard). SET LOCAL
        # the echo-suppression GUC ONCE, before the apply savepoint below,
        # mirroring _pull_and_apply_catalog's own placement.
        await apply_guard.enable_echo_suppression(self._session)

        resolved: list[tuple[Any, dict[str, Any]]] = []
        unresolved = 0
        already_applied = 0
        for row in pulled.rows:
            tabla = row.get("tabla")
            spec = SYNC_CATALOG_BY_NAME.get(tabla)
            if spec is None:
                unresolved += 1
                continue

            raw_uuid_registro = row.get("uuid_registro")
            try:
                uuid_registro = (
                    uuid_lib.UUID(str(raw_uuid_registro)) if raw_uuid_registro is not None else None
                )
            except ValueError:
                uuid_registro = None
            if uuid_registro is not None and await apply_guard.row_already_present(
                self._session, spec.model_cls, uuid_registro
            ):
                already_applied += 1
                continue

            resolved.append((spec, row.get("datos") or {}))

        if unresolved:
            self.log.warning("sync_sucursal.pull_unknown_tables", count=unresolved)
        if already_applied:
            self.log.debug("sync_sucursal.pull_skipped_already_applied", count=already_applied)
        if not resolved:
            # Everything was already applied (or unresolved) — the cursor
            # only advances when nothing is left behind (CU-07); already-
            # applied rows are local, so marking them consumed is safe.
            await self._persist_pull_cursor(next_seq=pulled.next_seq, unresolved=unresolved)
            # Nothing was attempted, so nothing failed: this is a clean cycle
            # and must clear the streak, or a node that degraded during an
            # incident stays 503 for as long as the cloud is quiet.
            self._note_clean_cycle()
            return

        if self._motor is None:
            self._motor = SyncMotor(engine=engine_flag.EngineMode.CATALOG_BRANCH)
        actor_uuid = uuid_lib.uuid4()

        try:
            async with self._session.begin_nested():
                result = await self._motor.apply_batch(
                    self._session, resolved, actor_uuid=actor_uuid
                )
        except Exception as exc:  # noqa: BLE001 — keep the cycle alive (mirrors sync_cloud.py)
            self.log.warning("sync_sucursal.pull_apply_batch_failed", error=str(exc))
            self._note_batch_failure(exc)
            return

        # Applied cleanly with no unresolved row — advance the watermark.
        self._record_apply_outcome(result)
        # Advance only with no unresolved AND no failed row, so a poison row
        # is retried next cycle instead of being silently skipped.
        await self._persist_pull_cursor(
            next_seq=pulled.next_seq,
            unresolved=unresolved,
            failed=_failed_count(result),
        )

        self.log.info(
            "sync_sucursal.pull_applied",
            pulled=len(pulled.rows),
            applied=len(result.applied),
            buffered=len(result.buffered),
            failed=_failed_count(result),
            next_seq=pulled.next_seq,
        )

    # ------------------------------------------------------------------
    # T-PR12-006 — catalog-driven pull + apply via SyncMotor.apply_batch
    # ------------------------------------------------------------------

    async def _pull_and_apply_catalog(self) -> None:
        """Pull cloud changes and apply the WHOLE batch via ``SyncMotor.
        apply_batch`` (T-PR12-006) — dependency-ordered + buffered, unlike
        the legacy path's per-row ``ConflictResolver.apply_pushed_row``.

        Built with the EXPLICIT ``catalog_branch`` engine mode — never
        ``engine_flag.get_engine()`` — for the same D11 reason
        :meth:`_detect_applier_mode` doesn't read the env flag either.

        CU-07 (pull cursor): same delivery-incremental behavior as
        :meth:`_pull_and_apply` — pulls from the persisted watermark when
        ``uuid_sucursal`` is set and advances it only after a clean apply
        with no unresolved row.
        """
        assert self._http_client is not None

        cursor_seq = 0
        if self.uuid_sucursal is not None:
            cursor_seq = await sync_cursor_helpers.get_seq(
                self._session, uuid_sucursal=self.uuid_sucursal
            )
        # ``max(0, cursor - 1)``: re-deliver the last epoch-ms so a row
        # sharing the high-water mark's ``created_at`` ms is not skipped.
        since_seq = max(0, cursor_seq - 1)

        try:
            pulled = await self._http_client.pull(since_seq=since_seq)
        except SyncJwtMissingError as exc:
            # Pre-pairing — same contract as the push path (Bug 6): the
            # cycle keeps committing, JWT rotation not involved.
            self.log.warning("sync_sucursal.pull_skipped_jwt_missing", error=str(exc))
            return
        except (TimeoutError, httpx.HTTPError, OSError) as exc:
            self.log.error("sync_sucursal.pull_transport_error", error=str(exc))
            return

        if pulled.status != 200:
            self.log.warning("sync_sucursal.pull_non_ok", status=pulled.status)
            return

        resolved: list[tuple[Any, dict[str, Any]]] = []
        unresolved = 0
        already_applied = 0
        for row in pulled.rows:
            tabla = row.get("tabla")
            spec = SYNC_CATALOG_BY_NAME.get(tabla)
            if spec is None:
                unresolved += 1
                continue

            # Real defect this closes: a since_seq>0 call means the SAME
            # row is delivered again on the next cycle — a blind
            # ``close_and_insert`` would try to re-insert it with a FRESH
            # uuid (identical class of bug already fixed in
            # ``jobs/sync_cloud.py``'s ``_apply_pending_batch_once``, see
            # its own comment). A row whose own ``uuid_registro`` already
            # exists in this table on THIS branch is already correctly
            # applied — skip it instead of duplicating or crashing on a
            # PK collision.
            raw_uuid_registro = row.get("uuid_registro")
            try:
                uuid_registro = (
                    uuid_lib.UUID(str(raw_uuid_registro)) if raw_uuid_registro is not None else None
                )
            except ValueError:
                uuid_registro = None
            if uuid_registro is not None and await apply_guard.row_already_present(
                self._session, spec.model_cls, uuid_registro
            ):
                already_applied += 1
                continue

            resolved.append((spec, row.get("datos") or {}))

        if unresolved:
            self.log.warning("sync_sucursal.pull_unknown_tables", count=unresolved)
        if already_applied:
            self.log.debug("sync_sucursal.pull_skipped_already_applied", count=already_applied)
        if not resolved:
            # All rows were already applied locally (or unresolved) — the
            # cursor advances only when nothing is left behind (CU-07).
            await self._persist_pull_cursor(next_seq=pulled.next_seq, unresolved=unresolved)
            # Nothing was attempted, so nothing failed: this is a clean cycle
            # and must clear the streak, or a node that degraded during an
            # incident stays 503 for as long as the cloud is quiet.
            self._note_clean_cycle()
            return

        if self._motor is None:
            self._motor = SyncMotor(engine=engine_flag.EngineMode.CATALOG_BRANCH)
        actor_uuid = uuid_lib.uuid4()

        # Echo-amplification fix (post-PR14 real-Docker closing exercise,
        # real defect #3; migration 0016_add_sync_apply_guard). Every row
        # in ``resolved`` already arrived via sync — SET LOCAL the echo-
        # suppression GUC ONCE, before entering the SAVEPOINT below, so it
        # covers every row ``apply_batch`` applies in this call without
        # being re-set per row (mirrors jobs/sync_cloud.py's own placement
        # — see that file's comment for the transaction-nesting rationale,
        # and sync.motor.apply_guard's own docstring for the full "why").
        await apply_guard.enable_echo_suppression(self._session)

        try:
            async with self._session.begin_nested():
                result = await self._motor.apply_batch(
                    self._session, resolved, actor_uuid=actor_uuid
                )
        except Exception as exc:  # noqa: BLE001 — keep the cycle alive (mirrors sync_cloud.py)
            self.log.warning("sync_sucursal.pull_apply_batch_failed", error=str(exc))
            self._note_batch_failure(exc)
            return

        # Applied cleanly with no unresolved row — advance the watermark.
        self._record_apply_outcome(result)
        # Advance only with no unresolved AND no failed row, so a poison row
        # is retried next cycle instead of being silently skipped.
        await self._persist_pull_cursor(
            next_seq=pulled.next_seq,
            unresolved=unresolved,
            failed=_failed_count(result),
        )

        self.log.info(
            "sync_sucursal.pull_applied_catalog",
            pulled=len(pulled.rows),
            applied=len(result.applied),
            buffered=len(result.buffered),
            failed=_failed_count(result),
            next_seq=pulled.next_seq,
        )

    # ------------------------------------------------------------------
    # CU-07 BR3 — SLA-exhaustion sweep (Track 3, plan.md L6969/L6980)
    # ------------------------------------------------------------------

    async def _sweep_exhausted(self) -> None:
        """Convert SLA-exhausted ``sync_queue`` rows + raise an alert (BR3).

        One ``SELECT`` per cycle (runs inside :meth:`cycle`, right after
        push+pull and before the commit, so the conversions and the alerta
        row land atomically). Any ``pendiente`` row past the queue-lifetime
        SLA — ``EXHAUSTION_MAX_AGE`` (24h from FIRST enqueue, BR3) or
        ``intentos >= len(BACKOFF_SCHEDULE)`` — is converted to
        ``fallido permanente`` via ``repo.sync_queue.mark_exhausted``
        (NEVER ``mark_failed``, which would only re-queue it forever), and
        a single ``evento_no_procesado`` alert is raised for the batch.

        Dedup is structural: the DB row leaves ``estado='pendiente'`` on
        conversion, so the next cycle's ``list_exhausted`` re-select cannot
        match it again — the same event never raises a second alert.
        """
        exhausted = await sq_helpers.list_exhausted(
            self._session,
            limit=self.batch_size,
            uuid_sucursal=self.uuid_sucursal,
        )
        if not exhausted:
            return

        for row in exhausted:
            await sq_helpers.mark_exhausted(
                self._session,
                row.uuid,
                (
                    f"exhausted_sla tabla={row.tabla} intentos={row.intentos} "
                    f"created_at={row.created_at} operacion={row.operacion}"
                ),
            )

        # Lazy import — mirrors the other hooks/impls callers; keeps the
        # worker's boot graph light (the hook self-registers on import).
        from parkos_core.sync.hooks.impls.alert_emitter import alert_emitter

        await alert_emitter(
            self._session,
            tipo_alerta="evento_no_procesado",
            uuid_sucursal=self.uuid_sucursal,
        )

        self.log.warning(
            "sync_sucursal.sweep_exhausted",
            count=len(exhausted),
            sq_uuids=[str(r.uuid) for r in exhausted],
        )

    # ------------------------------------------------------------------
    # Step 5: heartbeat (fire-and-forget)
    # ------------------------------------------------------------------

    async def _heartbeat_safe(self) -> None:
        """POST a heartbeat; never raise — log and continue."""
        assert self._http_client is not None
        try:
            await self._http_client.heartbeat(
                state={
                    "state": "alive",
                    "ts": _now_iso(),
                    "pid": os.getpid(),
                    "host": os.environ.get("HOSTNAME", ""),
                }
            )
        except (TimeoutError, httpx.HTTPError, OSError) as exc:
            self.log.warning("sync_sucursal.heartbeat_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _wire_shape(row: Any) -> dict[str, Any]:
    """Serialize a :class:`SyncQueue` row for the wire.

    The cloud expects ``{tabla, uuid_registro, datos, uuid_sucursal,
    timestamp_evento, operacion, prioridad}`` — see
    :class:`parkos_core.sync.transport.PushResponse`. We pass the
    minimum needed to route + apply the row on the cloud side.
    """
    return {
        "tabla": getattr(row, "tabla", None),
        # Bug 9 fix: ``str(None)`` is the literal ``'None'`` — the legacy
        # receiver parses these columns as UUIDs and a string ``'None'``
        # would crash it. Coerce a missing uuid to real JSON null.
        "uuid_registro": _str_or_none(getattr(row, "uuid_registro", None)),
        "uuid_sucursal": _str_or_none(getattr(row, "uuid_sucursal", None)),
        "operacion": getattr(row, "operacion", None),
        "prioridad": getattr(row, "prioridad", None),
        "datos": getattr(row, "datos", None) or {},
    }


def _str_or_none(value: Any) -> str | None:
    """Return ``str(value)`` unless value is missing, then ``None``."""
    if value is None:
        return None
    text = str(value)
    return text or None


def _push_results(response: PushResponse) -> list[dict[str, Any]] | None:
    """Extract the per-row ``results`` list from a 207 push response.

    The receiver answers with ``{"results": [...]}``, one entry per
    request row, in request order. Returns ``None`` when the body does
    not carry a list, so the caller can fail the batch instead of
    guessing a correlation.

    Replaces the previous ``_extract_success_uuids`` helper, which read
    ``body["success_uuids"]`` / ``body["accepted"]`` — keys this endpoint
    never returned — and then intersected them against ``row.uuid`` (the
    sync_queue row uuid) while the receiver reports ``uuid_registro``
    (the business row uuid). Both halves of that comparison were wrong,
    so every row of a 207 push was marked ``rejected_by_cloud``.
    """
    body = getattr(response, "body", None)
    if not isinstance(body, dict):
        return None
    results = body.get("results")
    if not isinstance(results, list):
        return None
    return [r for r in results if isinstance(r, dict)]


def _fake_httpx_response(response: PushResponse | EventsPushResponse) -> Any:
    """Build a minimal ``httpx.Response``-shaped object for ``JwtManager``.

    :class:`parkos_core.sync.jwt_manager.JwtManager.on_401_response`
    expects an object with ``.status_code`` + ``.json()``. We don't
    import httpx at module level to keep this worker dependency-light
    (the actual transport is owned by ``SyncHttpClient``).
    ``EventsPushResponse`` carries ``results`` instead of ``body`` — the
    JWT lifecycle handler only reads ``.json()``, so either shape works.
    """

    class _Mini:
        def __init__(self, status: int, body: dict[str, Any]) -> None:
            self.status_code = status
            self._body = body

        def json(self) -> dict[str, Any]:
            return self._body

    return _Mini(response.status, getattr(response, "body", None) or {})


def _now_iso() -> str:
    """Naive UTC ISO timestamp for the heartbeat payload."""
    return datetime.now(UTC).replace(tzinfo=None).isoformat()


# ---------------------------------------------------------------------------
# CLI entrypoint — wires the worker to ``python -m parkos_core.jobs.sync_sucursal``
# ---------------------------------------------------------------------------


def main() -> int:  # pragma: no cover — exercised by docker smoke test
    """CLI entrypoint — env-driven, exit 0 / 1 / 2 per §21.7."""

    from parkos_core.runtime.env import (
        BranchConfig,
        MissingEnvError,
        load_config,
    )

    try:
        cfg = load_config()
    except MissingEnvError as exc:
        sys.stderr.write("sync_sucursal env validation failed:\n")
        for err in exc.errors:
            sys.stderr.write(f"  - {err}\n")
        return 2

    if not isinstance(cfg, BranchConfig):
        sys.stderr.write(f"sync_sucursal requires PARKOS_DEPLOY=branch (got {cfg.deploy!r})\n")
        return 2

    # Late import — the session factory depends on the runtime config.
    from parkos_core.db.engine import SessionLocal  # type: ignore[attr-defined]

    async def _run() -> int:
        async with SessionLocal() as session:  # type: ignore[union-attr]
            worker = SyncSucursalWorker(
                jwt_path=cfg.sync_jwt_path,
                base_url=cfg.cloud_api_url,
                session=session,
                poll_interval_s=cfg.sync_poll_interval_s,
                batch_size=cfg.sync_batch_size,
                uuid_sucursal=cfg.uuid_sucursal,
            )
            return await worker.run()

    return asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_BRANCH_VERSION",
    "DEFAULT_POLL_INTERVAL_S",
    "ApplierMode",
    "SyncSucursalWorker",
    "main",
]
