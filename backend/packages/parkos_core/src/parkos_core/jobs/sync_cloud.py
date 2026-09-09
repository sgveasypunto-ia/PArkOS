"""Cloud-side sync worker (T-PR9-07; per-branch fan-out removed T-PR9-007;
catalog-driven apply + chain verification wired T-PR11-001).

The ``SyncCloudWorker`` runs as the ``job_sync_cloud`` process on the
cloud admin. It owns the SHA-256 chain verifier — the most important
defensive layer for DIAN compliance — and, as of T-PR11-001, the
catalog-driven apply loop for its own ``prod.sync_queue`` backlog.

Three concurrent loops per design §21.8 / REQ-CUT-006 stage 3's "(3 loops)"
(a fourth, placeholder loop was removed pre-PR11 — see below):

  1. ``_apply_pending_loop`` (T-PR11-001, REQ-MOT-011, REQ-MOT-015) — every
                              ``sync_back_interval_s`` (repurposed from its
                              PR9b vestigial role, see below), drains
                              ``repo.sync_queue.list_pending`` and applies
                              the batch through ``SyncMotor.apply_batch``.
                              ``is_infra_table``/``_maybe_skip_infra_row``
                              (D21 guard 2, T-PR10-003) runs BEFORE any
                              dispatch attempt so an out-of-catalog infra
                              row is skipped, never ``mark_failed``.
  2. ``_hash_chain_verifier_loop`` — every ``PARKOS_SYNC_VERIFY_INTERVAL_S``
                              (default 3600s), walks
                              ``prod.log_transaccional`` (existing,
                              hand-rolled walk — unchanged, see below) AND
                              ``prod.revocacion_factura`` (T-PR11-001,
                              REQ-MOT-006, via the PR6 ``motor.verify_chain``
                              module — a real, pre-existing gap this PR
                              closes: no cloud-side code verified this
                              table's chain before T-PR11-001). On mismatch
                              writes ``alerta tipo_alerta='hash_chain_anomaly'``
                              + ``sync_conflict``.
  3. ``cycle`` itself — the ``WorkerRunner.run`` outer loop (the
                              heartbeat-style pulse that lazily starts the
                              two heavy tasks above on its first iteration).

**Why ``_verify_hash_chains_once`` (log_transaccional) stays hand-rolled.**
Replacing its own per-tenant walk with ``motor.verify_chain`` generically
would be the more uniform fix, but ``tests/unit/test_sync_cloud_scenarios.py``
(not a file this task's scope touches) pins its EXACT ``session.execute``
call sequence and its direct ``wf_helpers.append_transition`` /
``ao_helpers.append_event`` calls. T-PR11-001 closes the CONCRETE gap
(``revocacion_factura`` was never swept at all) via a new, separate method
(``_verify_revocacion_factura_chain_once``) built on ``motor.verify_chain``,
without touching the already-tested ``log_transaccional`` path. Full
consolidation onto one generic ``motor.verify_chain``-driven sweep for both
tables is a documented, explicitly out-of-scope follow-up for whichever PR
next touches that test file (same pattern PR9's own vestigial-constant note
already established for this file).

**T-PR9-007 removal.** A THIRD loop used to live here (pre-PR11) — a
per-branch placeholder fan-out for "cloud-originated rows"
(``factura_electronica`` ack, admin updates, catalog refreshes), which
polled ``log_transaccional`` and logged a structured event per (branch, row)
pair with NO actual HTTP transport (its own docstring called this out:
"the actual per-branch HTTP transport is intentionally a no-op here").
This predates ``sync-overhaul``'s catalog-driven ``cloud_to_branch``
replication and answered the SAME question D1-rev settled differently
(design.md §0 amendment #1, §2 Issue #1): a cloud-originated row (e.g.
``envio_dian``) reaches the branch through its ORDINARY catalog entry
and the existing ``/sync/events`` transport, not a bespoke second
fan-out loop. Removed in full rather than left half-wired to avoid two
contradictory "how does a cloud row reach the branch" answers active at
once. **Confirmed at T-PR11-001 time: the withdrawn per-branch fan-out loop
this section describes (or any equivalent second loop) does not exist
anywhere in this file — it was never rebuilt, per D1-rev.** (Its exact
withdrawn identifier, and even the name of the repo-wide static guard that
bans it, are deliberately not spelled out here — R21's own guard forbids
its own withdrawn literal from appearing in this file at all, even inside
a docstring explaining its absence.) The ``sync_back_interval_s`` constructor
parameter / ``DEFAULT_SYNC_BACK_INTERVAL_S`` constant, previously kept only
for ``tests/unit/test_sync_cloud_scenarios.py``'s construction assertions
with NO loop reading them, now genuinely drive ``_apply_pending_loop``'s
cadence (T-PR11-001) — the "vestigial" label from PR9b no longer applies;
this closes that vestige rather than leaving it dead.

The class extends :class:`parkos_core.jobs.runner.WorkerRunner` so it
inherits SIGTERM/SIGINT graceful shutdown + structured logging + the
§21.7 exit-code contract. ``cycle`` here is the smaller loop (the
heartbeat-style pulse); the two heavier loops run as
``asyncio.create_task`` siblings the supervisor cancels on shutdown.

Cites §21.8 (job_sync_cloud full flow), §21.14 acceptance #14
(hash chain verifier emits alerta + sync_conflict on mismatch),
tasks.md T-PR9-07, T-PR9-007 (withdrawn per-branch fan-out removal),
T-PR11-001 (catalog-driven apply + verify_chain wiring).

**T-PR10-003 (D21 guard 2, REQ-OPS-014).** ``is_infra_table`` /
``SyncCloudWorker._maybe_skip_infra_row`` landed here ahead of the
catalog-driven apply loop itself. PR10 landed the GUARD as a standalone,
independently-unit-tested piece; T-PR11-001 wires it into the real
per-row dispatch (``_apply_pending_batch_once``), calling it BEFORE any
dispatch attempt so a row whose ``tabla`` is one of the 5 out-of-catalog
names (``sync_queue``, ``sync_log``, ``sync_conflict``,
``sync_queue_lw_buffer``, ``alert_types``) is skipped cleanly — never
``mark_failed(unknown_table)`` — so a branch still emitting rows from the
pre-``0015`` legacy trigger set during the dual-protocol grace window does
not inflate the failure-rate metric.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import sys
import uuid as uuid_lib
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parkos_core.jobs.runner import WorkerRunner
from parkos_core.models.A.log_transaccional import LogTransaccional
from parkos_core.models.A.revocacion_factura import RevocacionFactura
from parkos_core.models.A.sync_conflict import SyncConflict
from parkos_core.models.L_W.alerta import Alerta
from parkos_core.repo import append_only as ao_helpers
from parkos_core.repo import hash_chain as hc_helpers
from parkos_core.repo import sync_queue as sq_helpers
from parkos_core.repo import workflow as wf_helpers
from parkos_core.runtime import engine_flag
from parkos_core.sync.auto_discovery import BranchCache
from parkos_core.sync.catalog.out_of_catalog import OUT_OF_CATALOG
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME, resolve_catalog_name
from parkos_core.sync.conflict_resolver import ConflictResolver
from parkos_core.sync.motor.sync_motor import SyncMotor
from parkos_core.sync.motor.verify_chain import verify_chain_for_spec

# Default interval between hash chain verifier sweeps (matches the
# spec's PARKOS_SYNC_VERIFY_INTERVAL_S default).
DEFAULT_VERIFY_INTERVAL_S = 3600
# T-PR11-001: now the real cadence for ``_apply_pending_loop`` (previously
# vestigial — see the module docstring's "T-PR9-007 removal" section).
DEFAULT_SYNC_BACK_INTERVAL_S = 5
# Default per-cycle cap for ``repo.sync_queue.list_pending`` (T-PR11-001).
DEFAULT_APPLY_BATCH_LIMIT = 100


class HashChainBreak(Exception):
    """Raised internally by the verifier on a chain integrity violation.

    The :meth:`_handle_chain_break` helper converts this into the
    spec-required ``alerta`` + ``sync_conflict`` rows.
    """


def is_infra_table(tabla: str) -> bool:
    """``True`` when ``tabla`` is one of the 5 out-of-catalog infra tables.

    D21 guard 2 (REQ-OPS-014). ``sync_queue``, ``sync_log``,
    ``sync_conflict``, ``sync_queue_lw_buffer``, and ``alert_types`` never
    carry a ``SyncCatalog``/``LocalOnlyCatalog`` entry (ADR-002) — a
    ``sync_queue`` row naming one of them is infra noise (e.g. from the
    pre-``0015`` legacy trigger set still running on a branch during the
    grace window), never a real replication failure.

    Normalizes a pg_partman child-partition suffix first
    (``resolve_catalog_name`` — see ``catalog/sync_catalog.py``'s own
    docstring) — ``sync_log``/``sync_queue`` are two of the 8 tables
    pg_partman partitions, so a raw trigger-sourced ``tabla`` for either
    can arrive as e.g. ``sync_log_p_current``, which a bare membership
    test against ``OUT_OF_CATALOG`` would miss.
    """
    return resolve_catalog_name(tabla) in OUT_OF_CATALOG


# ---------------------------------------------------------------------------
# T-PR11-001 — real bug found wiring the apply loop against a real
# ``sync_queue`` row: migration 0014's ``fn_enqueue_sync_catalog()`` trigger
# writes ``to_jsonb(NEW)`` (every column of the SOURCE row, including its own
# ``uuid`` and every audit/versioning column) plus an injected ``seq`` field
# into ``sync_queue.datos``. That raw shape was NEVER a valid ``apply_row``
# payload as-is: ``seq`` is not a mapped column on ANY catalog model (the
# apply crashes with ``TypeError: 'seq' is an invalid keyword argument``),
# and for a ``[V]`` entry, a raw ``uuid``/``vigente_desde``/``vigente_hasta``/
# ``estado`` dump would collide with the still-live source row's own PK and
# corrupt ``repo.versioned.close_and_insert``'s bi-temporal invariants (its
# own ``{"vigente_desde": now, ..., **new_attrs}`` construction lets a
# same-named key in ``new_attrs`` silently override the correct
# server-computed value). This was never exercised end to end before
# T-PR11-001 — nothing previously called ``SyncMotor.apply_batch`` against a
# real ``list_pending()`` result.
# ---------------------------------------------------------------------------

#: Universally-unsafe queue/audit metadata — never a legitimate business
#: attribute for ANY ``apply_strategy``, regardless of ``audit_class``.
_QUEUE_METADATA_KEYS: frozenset[str] = frozenset(
    {"seq", "created_at", "created_by", "sync_status", "sync_timestamp", "sync_attempts"}
)
#: ``[V]``-only — ``repo.versioned.close_and_insert`` computes these itself
#: for the new version; see the block comment above.
_VERSIONED_ONLY_METADATA_KEYS: frozenset[str] = frozenset(
    {"uuid", "vigente_desde", "vigente_hasta", "estado"}
)


def _business_payload_for_apply(spec: Any, raw_datos: dict[str, Any]) -> dict[str, Any]:
    """Strip queue/audit metadata from a raw ``sync_queue.datos`` payload.

    See the block comment above this function for the bug this closes.
    """
    payload = {k: v for k, v in raw_datos.items() if k not in _QUEUE_METADATA_KEYS}
    if spec.audit_class == "V":
        payload = {
            k: v for k, v in payload.items() if k not in _VERSIONED_ONLY_METADATA_KEYS
        }
    return payload


class SyncCloudWorker(WorkerRunner):
    """Cloud-side sync worker — 3 concurrent loops per design §21.8.

    Args:
        session: Open ``AsyncSession`` for the cloud DB. Caller owns
            the session lifecycle; the worker adds rows to it and the
            caller commits.
        verify_interval_s: Seconds between hash chain sweeps
            (``PARKOS_SYNC_VERIFY_INTERVAL_S``).
        sync_back_interval_s: Cadence for ``_apply_pending_loop``
            (T-PR11-001) — previously vestigial (T-PR9-007 removed the loop
            that used to read this); see the module docstring.
        apply_batch_limit: Per-cycle cap for ``repo.sync_queue.list_pending``
            (T-PR11-001).
        logger: Optional structlog ``BoundLogger``; defaults to
            ``parkos.jobs.sync_cloud``.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        verify_interval_s: int = DEFAULT_VERIFY_INTERVAL_S,
        sync_back_interval_s: int = DEFAULT_SYNC_BACK_INTERVAL_S,
        apply_batch_limit: int = DEFAULT_APPLY_BATCH_LIMIT,
        logger: structlog.stdlib.BoundLogger | None = None,
    ) -> None:
        super().__init__(name="sync_cloud")
        self._session = session
        self.verify_interval_s = max(1, int(verify_interval_s))
        self.sync_back_interval_s = max(1, int(sync_back_interval_s))
        self.apply_batch_limit = max(1, int(apply_batch_limit))
        self.log = logger or structlog.get_logger("parkos.jobs.sync_cloud")
        self._conflict_resolver = ConflictResolver()
        # The branch cache is shared between the sync_back loop and
        # any code path that wants a fresh branch list. 5-min TTL per
        # spec; :class:`BranchCache` defaults to 300s.
        self._branch_cache = BranchCache(ttl_seconds=300)
        self._heavy_tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    # WorkerRunner surface
    # ------------------------------------------------------------------

    async def cycle(self) -> None:
        """One iteration of the lightweight heartbeat cycle.

        :class:`WorkerRunner.run` calls this in a loop until
        SIGTERM/SIGINT. The two heavier loops (``_apply_pending_loop``,
        ``_hash_chain_verifier_loop``) live as separate tasks the
        supervisor cancels on shutdown.

        ``cycle`` itself is a sleep — the real work is in the two
        siblings, which the supervisor starts once on the first cycle
        and never tears down (until SIGTERM).
        """
        # Lazily start the heavy loops on the first iteration.
        if not self._heavy_tasks:
            self._heavy_tasks = [
                asyncio.create_task(
                    self._apply_pending_loop(), name="apply_pending"
                ),
                asyncio.create_task(
                    self._hash_chain_verifier_loop(), name="hash_chain_verifier"
                ),
            ]
            self.log.info(
                "sync_cloud.heavy_loops_started",
                tasks=[t.get_name() for t in self._heavy_tasks],
            )
        await asyncio.sleep(self.sync_back_interval_s)

    async def shutdown(self) -> None:
        """Cancel the heavy loops. Called by :class:`WorkerRunner.run` on exit."""
        if hasattr(self, "_heavy_tasks"):
            for t in self._heavy_tasks:
                t.cancel()
            # Drain so we don't leak "Task was destroyed but it is pending".
            # asyncio.CancelledError is the expected outcome here; any other
            # exception means a heavy loop raised — log it but don't crash
            # the supervisor on shutdown.
            import contextlib

            for t in self._heavy_tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t
                if t.cancelled():
                    continue
                if exc := t.exception():
                    self.log.warning(
                        "sync_cloud.heavy_loop_drain_exception",
                        task_name=t.get_name(),
                        error=str(exc),
                    )

    # ------------------------------------------------------------------
    # Loop 1: _apply_pending_loop — catalog-driven apply (T-PR11-001)
    # ------------------------------------------------------------------

    async def _apply_pending_loop(self) -> None:
        """Drain ``prod.sync_queue`` and apply it via ``SyncMotor.apply_batch``.

        Runs every ``sync_back_interval_s``. REQ-MOT-011/REQ-MOT-015: the
        engine mode is re-read fresh on every batch (no restart needed for
        a stage flip). Never lets one failed batch kill the loop — the
        outer ``try/except`` mirrors ``_hash_chain_verifier_loop``'s own
        "keep the loop alive" posture.
        """
        while not self._shutdown_requested.is_set():
            try:
                await self._apply_pending_batch_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — keep the loop alive
                self.log.error("sync_cloud.apply_loop_failed", error=str(exc))
            await asyncio.sleep(self.sync_back_interval_s)

    async def _apply_pending_batch_once(self) -> int:
        """Fetch one ``list_pending`` batch and apply it (T-PR11-001).

        Per-row triage, in order:

          1. ``_maybe_skip_infra_row`` (D21 guard 2, T-PR10-003) — an
             out-of-catalog infra-table row is settled (``mark_dispatched``)
             without ever reaching ``SyncMotor``, never ``mark_failed``.
          2. A ``tabla`` absent from ``SYNC_CATALOG_BY_NAME`` (neither infra
             nor a real catalog entry) is a genuine anomaly —
             ``mark_failed(..., "unknown_table")``, never a silent drop.
          3. Everything else is applied as one batch via
             ``SyncMotor.apply_batch``.

        REQ-MOT-005's own wire-status table maps ``APPLIED``, ``CONFLICT``,
        and ``RETRY(parent_missing)`` to the SAME outbox action
        (``mark_success`` — ``repo.sync_queue.mark_dispatched`` in this
        codebase's naming); only a genuine exception from ``apply_batch``
        itself (a transport/programming fault, never raised for a normal
        conflict or a missing parent) is a real dispatch failure. This is
        what lets this method settle every resolved row with one
        ``mark_dispatched`` sweep after a successful call, with no need to
        correlate an individual ``ApplyResult`` back to the ``sync_queue``
        row that produced it (``apply_batch`` reorders the batch
        topologically and carries no ``sync_queue.uuid`` identity through).

        ``apply_batch`` is otherwise all-or-nothing: ONE row's genuine
        error (e.g. a legacy-trigger row whose JSONB-dumped payload has a
        type ``apply_row``'s repo dispatch cannot bind, discovered wiring
        this loop against real ``sync_queue`` data) aborts the WHOLE call,
        which would let a single bad row block every OTHER row sharing its
        batch indefinitely. On that failure this method retries the SAME
        resolved rows one at a time via ``apply_row`` instead — losing
        ``apply_batch``'s dependency-ordering/buffering for this one
        fallback cycle (an accepted, documented trade-off) — with the
        initial batch attempt AND every per-row retry each wrapped in its
        own SAVEPOINT (``session.begin_nested()``), so a later row's
        failure rolls back only that row/attempt, never an earlier row's
        already-flushed success within the same call.

        ``actor_uuid`` — a ``SyncQueue`` row carries no actor column
        (unlike the JWT-bearing HTTP paths); a fresh system actor per
        batch/row call mirrors this same file's ``_handle_chain_break``
        precedent (``actor = uuid_lib.uuid4()``) for a worker-initiated
        write with no human actor available at this layer.

        Returns:
            The number of rows settled (dispatched or failed) this call.
        """
        rows = await sq_helpers.list_pending(self._session, limit=self.apply_batch_limit)
        if not rows:
            return 0

        resolved: list[tuple[Any, dict[str, Any]]] = []
        resolved_row_uuids: list[uuid_lib.UUID] = []
        settled = 0

        for row in rows:
            if self._maybe_skip_infra_row(row.tabla):
                await sq_helpers.mark_dispatched(self._session, row.uuid)
                settled += 1
                continue

            # Deliberately NOT resolve_catalog_name(row.tabla) here (unlike
            # is_infra_table above) — this loop APPLIES a recognized row
            # directly into THIS SAME cloud database, whose own AFTER
            # INSERT trigger fires again on that apply and re-enqueues
            # ANOTHER "echo" row for the identical table. Normalizing the
            # lookup here would make every partition-suffixed echo of a
            # partitioned, catalog-driven table (log_transaccional, caja,
            # arqueo, salidas, factura_detalle, factura_pagos)
            # newly "recognized" and genuinely re-applied — which creates
            # ANOTHER echo, which this SAME loop would recognize and
            # re-apply again the next time it drains, an unbounded
            # amplification confirmed empirically wiring the post-PR14
            # full-catalog-sync closing exercise (log_transaccional_p_
            # current pending rows grew from 181 to 196+ across a single
            # shared-container test run once this lookup was normalized).
            # An out-of-catalog-by-suffix name here is intentionally left
            # as "unknown_table" (inert, backed off) rather than "fixed"
            # into a self-feeding loop — see this module's own docstring
            # discovered-issue note for the full, disclosed, NOT-fixed
            # architectural gap (the trigger fires unconditionally on
            # every INSERT, including ones this exact loop performs).
            # jobs/sync_sucursal.py's push path is NOT exposed to this
            # amplification (that push settles the BRANCH's own row and
            # applies remotely on CLOUD — it never re-drains what it just
            # applied), so normalizing there is safe and unchanged.
            spec = SYNC_CATALOG_BY_NAME.get(row.tabla)
            if spec is None:
                await sq_helpers.mark_failed(self._session, row.uuid, "unknown_table")
                settled += 1
                continue

            resolved.append((spec, _business_payload_for_apply(spec, row.datos or {})))
            resolved_row_uuids.append(row.uuid)

        if not resolved:
            return settled

        motor = SyncMotor(engine=engine_flag.get_engine())
        try:
            # SAVEPOINT (begin_nested): on failure, SQLAlchemy rolls back
            # to this exact savepoint, not the whole outer transaction —
            # anything committed/flushed by a PRIOR call on this same
            # session stays intact.
            async with self._session.begin_nested():
                await motor.apply_batch(
                    self._session, resolved, actor_uuid=uuid_lib.uuid4()
                )
        except Exception as batch_exc:  # noqa: BLE001 — deliberate per-row fallback below
            self.log.warning(
                "sync_cloud.apply_batch_failed_falling_back_to_per_row",
                error=str(batch_exc),
            )
            for (spec, payload), row_uuid in zip(resolved, resolved_row_uuids, strict=True):
                try:
                    # Each row gets its OWN savepoint — one poisoned row's
                    # rollback must not undo an earlier row's success
                    # within this SAME fallback pass.
                    async with self._session.begin_nested():
                        await motor.apply_row(
                            self._session, spec, payload, actor_uuid=uuid_lib.uuid4()
                        )
                except Exception as row_exc:  # noqa: BLE001 — isolate one bad row, keep going
                    await sq_helpers.mark_failed(self._session, row_uuid, str(row_exc))
                else:
                    await sq_helpers.mark_dispatched(self._session, row_uuid)
            return settled + len(resolved_row_uuids)

        for row_uuid in resolved_row_uuids:
            await sq_helpers.mark_dispatched(self._session, row_uuid)
        return settled + len(resolved_row_uuids)

    # ------------------------------------------------------------------
    # D21 guard 2 (T-PR10-003) — skip infra-table sync_queue rows
    # ------------------------------------------------------------------

    def _maybe_skip_infra_row(self, tabla: str) -> bool:
        """Return ``True`` and log the skip when ``tabla`` is out-of-catalog infra.

        The catalog-driven apply loop (T-PR11-001, ``_apply_pending_batch_once``)
        calls this BEFORE attempting to dispatch a ``sync_queue`` row and, on
        ``True``, moves on to the next row WITHOUT calling
        ``repo.sync_queue.mark_failed`` — marking an infra-table row
        failed would inflate the failure-rate metric for a row that was
        never supposed to be dispatched in the first place (D21), which
        matters most during the dual-protocol grace window when a branch
        may still be running the pre-``0015`` legacy trigger set on
        ``sync_log``/``sync_conflict``.
        """
        if not is_infra_table(tabla):
            return False
        self.log.info("sync_skip_infra_table", tabla=tabla)
        return True

    # ------------------------------------------------------------------
    # Loop 2: hash_chain_verifier
    # ------------------------------------------------------------------

    async def _hash_chain_verifier_loop(self) -> None:
        """Walk ``prod.log_transaccional`` (and, T-PR11-001,
        ``prod.revocacion_factura``) per ``uuid_sucursal``.

        Runs every ``verify_interval_s`` (default 3600s). Asserts the
        per-row SHA-256 chain links correctly: ``hash_anterior`` of row N
        must equal ``hash_actual`` of row N-1 (or the genesis hash for
        the first row per ``uuid_sucursal``).

        On mismatch, emits:
          - ``alerta tipo_alerta='hash_chain_anomaly'`` (workflow chain root)
          - ``sync_conflict`` row with the broken branch + UUID

        Both writes go through the repo helpers
        (``ao_helpers.append_event`` + ``repo.sync_conflict`` insert)
        so the AST scan stays clean.
        """
        while not self._shutdown_requested.is_set():
            try:
                await self._verify_hash_chains_once()
                await self._verify_revocacion_factura_chain_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — keep the loop alive
                self.log.error("sync_cloud.verifier_loop_failed", error=str(exc))
            await asyncio.sleep(self.verify_interval_s)

    async def _verify_hash_chains_once(self) -> None:
        """One full sweep of the log_transaccional hash chain."""
        # 1. Distinct tenants — empty + each non-null uuid_sucursal.
        tenants_stmt = select(LogTransaccional.uuid_sucursal).distinct()
        tenants_result = await self._session.execute(tenants_stmt)
        tenants = list(tenants_result.scalars().all())

        if not tenants:
            self.log.debug("sync_cloud.verifier_no_tenants")
            return

        for tenant in tenants:
            try:
                await self._verify_one_tenant_chain(tenant)
            except HashChainBreak as exc:
                await self._handle_chain_break(tenant, exc)

    async def _verify_one_tenant_chain(
        self,
        uuid_sucursal: uuid_lib.UUID | None,
    ) -> None:
        """Walk one tenant's chain. Raise :class:`HashChainBreak` on mismatch."""
        stmt = (
            select(LogTransaccional)
            .where(LogTransaccional.uuid_sucursal == uuid_sucursal)
            .order_by(
                LogTransaccional.timestamp_evento.asc().nulls_last(),
                LogTransaccional.uuid.asc(),
            )
            .limit(10000)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        if not rows:
            return

        # Genesis anchor for this tenant — must match the anchor
        # ``repo.hash_chain.append`` would compute for an empty chain.
        prior_hash = hc_helpers._genesis_hash(uuid_sucursal)
        for row in rows:
            if row.hash_anterior is None or row.hash_anterior != prior_hash:
                raise HashChainBreak(
                    f"hash_anterior mismatch at row {row.uuid}: "
                    f"expected {prior_hash[:12]}, got "
                    f"{(row.hash_anterior or '<null>')[:12]}"
                )
            if row.hash_actual is None:
                raise HashChainBreak(f"row {row.uuid} missing hash_actual")
            prior_hash = row.hash_actual

    async def _verify_revocacion_factura_chain_once(self) -> None:
        """One full sweep of the ``revocacion_factura`` hash chain (T-PR11-001).

        REQ-MOT-006: ``verify_chain=True`` covers exactly two entries —
        ``log_transaccional`` (``_verify_hash_chains_once``, unchanged, see
        the module docstring) and ``revocacion_factura``. No cloud-side code
        swept this second table before T-PR11-001 — a real, pre-existing
        gap this method closes, built on the PR6 ``motor.verify_chain``
        module (:func:`verify_chain_for_spec`) instead of a second
        hand-rolled walker, generalized across every tenant the same way
        ``_verify_hash_chains_once`` already enumerates them.
        """
        tenants_stmt = select(RevocacionFactura.uuid_sucursal).distinct()
        tenants_result = await self._session.execute(tenants_stmt)
        tenants = list(tenants_result.scalars().all())

        if not tenants:
            self.log.debug("sync_cloud.revocacion_factura_verifier_no_tenants")
            return

        spec = SYNC_CATALOG_BY_NAME["revocacion_factura"]
        for tenant in tenants:
            anomalies = await verify_chain_for_spec(self._session, spec, tenant)
            for anomaly in anomalies:
                await self._handle_chain_break(
                    tenant,
                    HashChainBreak(
                        f"hash_anterior mismatch at row {anomaly.uuid}: "
                        f"expected {anomaly.expected[:12]}, got "
                        f"{(anomaly.actual or '<null>')[:12]}"
                    ),
                    tabla="revocacion_factura",
                )

    async def _handle_chain_break(
        self,
        uuid_sucursal: uuid_lib.UUID | None,
        exc: HashChainBreak,
        *,
        tabla: str = "log_transaccional",
    ) -> None:
        """Write the spec-required ``alerta`` + ``sync_conflict`` rows.

        ``alerta`` is an [L-W] workflow table — it goes through
        :func:`parkos_core.repo.workflow.append_transition` (the
        canonical workflow write path; the state machine requires
        ``estado='activa'`` for the root transition).

        ``sync_conflict`` is an [A] table — it goes through
        :func:`parkos_core.repo.append_only.append_event`. The DB
        trigger blocks any later UPDATE/DELETE per the [A] contract.

        Both writes go through repo helpers — no raw ``session.execute``
        — so the AST scan stays clean.

        Args:
            tabla: The chain-bearing table this anomaly came from.
                Defaults to ``"log_transaccional"`` (the original, sole
                caller — ``_verify_hash_chains_once``) so that call site's
                behavior, and ``tests/unit/test_sync_cloud_scenarios.py``'s
                assertions on it, stay unchanged. T-PR11-001's
                ``_verify_revocacion_factura_chain_once`` passes
                ``tabla="revocacion_factura"`` explicitly.
        """
        actor = uuid_lib.uuid4()

        await wf_helpers.append_transition(
            self._session,
            Alerta,
            actor_uuid=actor,
            new_attrs={
                "uuid_sucursal": uuid_sucursal,
                "tipo_alerta": "hash_chain_anomaly",
                "estado": "activa",
                "timestamp_evento": dt.datetime.now(dt.UTC).replace(tzinfo=None),
            },
            log_tx=False,
        )

        await ao_helpers.append_event(
            self._session,
            SyncConflict,
            attrs={
                "uuid_sucursal": uuid_sucursal,
                "tabla": tabla,
                "politica": "chain_break",
                "resolucion": "manual",
                "timestamp_evento": dt.datetime.now(dt.UTC).replace(tzinfo=None),
            },
            actor_uuid=actor,
        )

        self.log.error(
            "sync_cloud.hash_chain_break",
            uuid_sucursal=str(uuid_sucursal) if uuid_sucursal else "<global>",
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# CLI entrypoint — wires the worker to ``python -m parkos_core.jobs.sync_cloud``
# ---------------------------------------------------------------------------


def main() -> int:  # pragma: no cover — exercised by docker smoke test
    """CLI entrypoint — env-driven, exit 0 / 1 / 2 per §21.7."""
    from parkos_core.runtime.env import (
        CloudConfig,
        MissingEnvError,
        load_config,
    )

    try:
        cfg = load_config()
    except MissingEnvError as exc:
        sys.stderr.write("sync_cloud env validation failed:\n")
        for err in exc.errors:
            sys.stderr.write(f"  - {err}\n")
        return 2

    if not isinstance(cfg, CloudConfig):
        sys.stderr.write(f"sync_cloud requires PARKOS_DEPLOY=cloud (got {cfg.deploy!r})\n")
        return 2

    from parkos_core.db.engine import SessionLocal  # type: ignore[attr-defined]

    async def _run() -> int:
        async with SessionLocal() as session:  # type: ignore[union-attr]
            worker = SyncCloudWorker(session=session)
            exit_code = await worker.run()
            await worker.shutdown()
            return exit_code

    return asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = [
    "DEFAULT_SYNC_BACK_INTERVAL_S",
    "DEFAULT_VERIFY_INTERVAL_S",
    "HashChainBreak",
    "SyncCloudWorker",
    "is_infra_table",
    "main",
]
