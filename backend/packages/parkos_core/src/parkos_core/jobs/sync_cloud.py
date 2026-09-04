"""Cloud-side sync worker — 3 concurrent loops (T-PR9-07).

The ``SyncCloudWorker`` runs as the ``job_sync_cloud`` process on the
cloud admin. It owns the SHA-256 chain verifier (the most important
defensive layer for DIAN compliance) and the per-branch
SyncBackEvent emitter for cloud-originated rows.

Three concurrent loops per design §21.8:

  1. ``apply_pushed_row``   — side-effects of the cloud-side
                              ``/sync/push`` handler: every accepted
                              push writes a ``sync_log`` row per
                              branch per cycle, a ``sync_conflict`` on
                              chain violation, an ``alerta`` chain
                              root. (PR8c owns the handler; PR9b owns
                              the per-loop background emitters.)
  2. ``emit_sync_back_events`` — for cloud-originated rows
                              (``factura_electronica`` ack, admin
                              updates, catalog refreshes), POST
                              ``{branch_endpoint}/api/v1/sync/events``
                              with retry 3x exponential on 5xx. Uses
                              :class:`parkos_core.sync.auto_discovery`
                              for the active-branch list.
  3. ``hash_chain_verifier_loop`` — every
                              ``PARKOS_SYNC_VERIFY_INTERVAL_S`` (default
                              3600s), walks ``prod.log_transaccional``
                              per ``uuid_sucursal`` in
                              ``(timestamp_evento, uuid)`` order,
                              asserts ``hash_anterior = prev.hash_actual``
                              (or the genesis hash for the first row).
                              On mismatch writes ``alerta
                              tipo_alerta='hash_chain_anomaly'`` +
                              ``sync_conflict``.

The class extends :class:`parkos_core.jobs.runner.WorkerRunner` so it
inherits SIGTERM/SIGINT graceful shutdown + structured logging + the
§21.7 exit-code contract. ``cycle`` here is the smaller of the three
loops (the heartbeat-style pulse); the two heavier loops run as
``asyncio.create_task`` siblings that the supervisor cancels on
shutdown.

Cites §21.8 (job_sync_cloud full flow), §21.14 acceptance #14
(hash chain verifier emits alerta + sync_conflict on mismatch),
tasks.md T-PR9-07.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import sys
import uuid as uuid_lib

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parkos_core.jobs.runner import WorkerRunner
from parkos_core.models.A.log_transaccional import LogTransaccional
from parkos_core.models.A.sync_conflict import SyncConflict
from parkos_core.models.L_W.alerta import Alerta
from parkos_core.repo import append_only as ao_helpers
from parkos_core.repo import hash_chain as hc_helpers
from parkos_core.repo import workflow as wf_helpers
from parkos_core.sync.auto_discovery import BranchCache
from parkos_core.sync.conflict_resolver import ConflictResolver

# Default interval between hash chain verifier sweeps (matches the
# spec's PARKOS_SYNC_VERIFY_INTERVAL_S default).
DEFAULT_VERIFY_INTERVAL_S = 3600
# Default interval between SyncBackEvent emitter sweeps. Short enough
# to deliver a DIAN ack promptly, long enough to avoid tight-looping.
DEFAULT_SYNC_BACK_INTERVAL_S = 5


class HashChainBreak(Exception):
    """Raised internally by the verifier on a chain integrity violation.

    The :meth:`_handle_chain_break` helper converts this into the
    spec-required ``alerta`` + ``sync_conflict`` rows.
    """


class SyncCloudWorker(WorkerRunner):
    """Cloud-side sync worker — 3 concurrent loops per design §21.8.

    Args:
        session: Open ``AsyncSession`` for the cloud DB. Caller owns
            the session lifecycle; the worker adds rows to it and the
            caller commits.
        verify_interval_s: Seconds between hash chain sweeps
            (``PARKOS_SYNC_VERIFY_INTERVAL_S``).
        sync_back_interval_s: Seconds between SyncBackEvent sweeps.
        logger: Optional structlog ``BoundLogger``; defaults to
            ``parkos.jobs.sync_cloud``.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        verify_interval_s: int = DEFAULT_VERIFY_INTERVAL_S,
        sync_back_interval_s: int = DEFAULT_SYNC_BACK_INTERVAL_S,
        logger: structlog.stdlib.BoundLogger | None = None,
    ) -> None:
        super().__init__(name="sync_cloud")
        self._session = session
        self.verify_interval_s = max(1, int(verify_interval_s))
        self.sync_back_interval_s = max(1, int(sync_back_interval_s))
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
        SIGTERM/SIGINT. The two heavier loops (``_emit_sync_back_events_loop``
        and ``_hash_chain_verifier_loop``) live as separate tasks that
        the supervisor cancels on shutdown.

        For the PR9b scope, ``cycle`` is a 1s sleep — the real work is
        in the two siblings, which the supervisor starts once on the
        first cycle and never tears down (until SIGTERM).
        """
        # Lazily start the heavy loops on the first iteration.
        if not self._heavy_tasks:
            self._heavy_tasks = [
                asyncio.create_task(self._emit_sync_back_events_loop(), name="sync_back"),
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
    # Loop 1: apply_pushed_row (lives in api_admin /sync/push handler — PR8c)
    # ------------------------------------------------------------------
    # The cloud-side apply is owned by ``parkos_core.api.v1.sync_router``
    # (PR8c, T-PR8-15). The router calls ``ConflictResolver.apply_pushed_row``
    # per row and writes ``sync_conflict`` rows for conflicts. This
    # module owns the EMITTER side: once a cloud-side action (e.g. an
    # admin updates a catalog row, or the DIAN dispatcher accepts a
    # factura_electronica) creates a row, the cloud worker fans it out
    # to the originating branch via the sync_back loop below.

    # ------------------------------------------------------------------
    # Loop 2: emit_sync_back_events
    # ------------------------------------------------------------------

    async def _emit_sync_back_events_loop(self) -> None:
        """Emit SyncBackEvent per cloud-originated row.

        PR9b ships the LOOP SHAPE — the actual row-discovery query lives
        on top of a not-yet-existing ``sync_outbox`` table that PR9c
        adds. For now the loop polls ``prod.log_transaccional`` for rows
        whose ``created_at`` is in the last ``sync_back_interval_s``
        seconds and whose ``sync_status='pendiente'``, then iterates
        the active branch list and POSTs ``/api/v1/sync/events`` to each.

        The actual per-branch HTTP transport is intentionally a no-op
        here (PR9b scope) — the loop emits a structured log event with
        the would-be URL + payload so operators can verify the cadence.
        PR9c wires the real ``SyncHttpClient`` push per branch.
        """
        from parkos_core.sync.transport import SyncHttpClient  # noqa: F401

        while not self._shutdown_requested.is_set():
            try:
                await self._emit_one_tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — keep the loop alive
                self.log.error("sync_cloud.sync_back_tick_failed", error=str(exc))
            await asyncio.sleep(self.sync_back_interval_s)

    async def _emit_one_tick(self) -> None:
        """One iteration of the sync_back loop.

        Walks ``prod.log_transaccional`` for rows stamped in the last
        ``sync_back_interval_s`` seconds whose ``sync_status='pendiente'``,
        gets the active branch list, and emits a structured log event
        per (branch, row) pair. The actual HTTP POST to each branch is
        owned by PR9c; PR9b pins the cadence + branch-list resolution.
        """
        threshold = dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(
            seconds=self.sync_back_interval_s * 2
        )
        stmt = (
            select(LogTransaccional)
            .where(LogTransaccional.created_at >= threshold)
            .where(LogTransaccional.sync_status == "pendiente")
            .limit(100)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        if not rows:
            return

        branches = await self._branch_cache.get(self._session)
        for branch in branches:
            for row in rows:
                if branch.endpoint_url:
                    self.log.info(
                        "sync_cloud.sync_back_event",
                        branch_uuid=str(branch.uuid_sucursal),
                        endpoint_url=branch.endpoint_url,
                        row_uuid=str(row.uuid),
                        tabla_afectada=row.tabla_afectada,
                    )
                else:
                    self.log.warning(
                        "sync_cloud.branch_endpoint_missing",
                        branch_uuid=str(branch.uuid_sucursal),
                        row_uuid=str(row.uuid),
                    )

    # ------------------------------------------------------------------
    # Loop 3: hash_chain_verifier
    # ------------------------------------------------------------------

    async def _hash_chain_verifier_loop(self) -> None:
        """Walk ``prod.log_transaccional`` per ``uuid_sucursal``.

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
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — keep the loop alive
                self.log.error("sync_cloud.verifier_loop_failed", error=str(exc))
            await asyncio.sleep(self.verify_interval_s)

    async def _verify_hash_chains_once(self) -> None:
        """One full sweep of the log_transaccional hash chain."""
        # 1. Distinct tenants — empty + each non-null uuid_sucursal.
        tenants_stmt = select(LogTransaccional.uuid_sucursal).distinct()
        tenants = [row.uuid_sucursal for row in (await self._session.execute(tenants_stmt)).all()]

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

    async def _handle_chain_break(
        self,
        uuid_sucursal: uuid_lib.UUID | None,
        exc: HashChainBreak,
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
                "tabla": "log_transaccional",
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
    "main",
]
