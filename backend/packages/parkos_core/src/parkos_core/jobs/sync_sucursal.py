"""Branch-side sync worker — 6-step main loop (T-PR9-06).

The ``SyncSucursalWorker`` runs as the ``job_sync_sucursal`` process on
each branch. It owns the local ``prod.sync_queue`` ([A] carved-out
table) and the long-lived ``sync-agent-`` JWT; every cycle it:

    1. ``poll sync_queue``          → ``repo.sync_queue.list_pending``
    2. ``push batch``               → ``SyncHttpClient.push``
    3. ``handle response``          → mark_dispatched / mark_failed /
                                       JwtManager.on_401_response
    4. ``pull cloud changes``       → ``SyncHttpClient.pull`` →
                                       ``ConflictResolver.apply_pushed_row``
    5. ``heartbeat``                → ``SyncHttpClient.heartbeat``
    6. ``sleep until next cycle``   → ``PARKOS_SYNC_POLL_INTERVAL_S``

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

Cites §21.7 (job_sync_sucursal main loop), tasks.md T-PR9-06.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid as uuid_lib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from parkos_core.jobs.runner import WorkerRunner
from parkos_core.repo import sync_queue as sq_helpers
from parkos_core.sync.conflict_resolver import (
    ApplyOutcome,
    ConflictResolver,
)
from parkos_core.sync.jwt_manager import JwtAction, JwtManager
from parkos_core.sync.transport import (
    PushResponse,
    SyncHttpClient,
)

# Default cycle cadence if the env does not set PARKOS_SYNC_POLL_INTERVAL_S.
DEFAULT_POLL_INTERVAL_S = 10
# Default batch size cap per cycle.
DEFAULT_BATCH_SIZE = 100


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
        logger: structlog.stdlib.BoundLogger | None = None,
    ) -> None:
        super().__init__(name="sync_sucursal")
        self.jwt_path = Path(jwt_path)
        self.base_url = base_url.rstrip("/")
        self._session = session
        self.poll_interval_s = max(1, int(poll_interval_s))
        self.batch_size = max(1, int(batch_size))
        self.log = logger or structlog.get_logger("parkos.jobs.sync_sucursal")

        # Per-cycle collaborators — instantiated lazily inside cycle()
        # so a misconfigured JWT path doesn't fail at __init__ time (the
        # worker is meant to log + retry on every cycle, not crash on
        # boot).
        self._jwt_manager: JwtManager | None = None
        self._http_client: SyncHttpClient | None = None
        self._conflict_resolver: ConflictResolver = ConflictResolver()
        # Track per-row in-flight seq so a partial-push (HTTP 207) can
        # tell which rows the cloud accepted vs rejected.
        self._last_pushed_uuids: list[uuid_lib.UUID] = []

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    async def cycle(self) -> None:
        """One iteration of the 6-step main loop.

        :class:`WorkerRunner.run` calls this in a loop until SIGTERM/SIGINT.
        """
        # Lazily build collaborators — JWT file might be missing on first
        # boot (pre-pairing); the loop tolerates that and retries next cycle.
        if self._http_client is None:
            self._http_client = SyncHttpClient(
                base_url=self.base_url,
                jwt_path=self.jwt_path,
            )
        if self._jwt_manager is None:
            self._jwt_manager = JwtManager(jwt_path=self.jwt_path, base_url=self.base_url)

        # 1. Poll sync_queue.
        pending = await sq_helpers.list_pending(
            self._session,
            limit=self.batch_size,
        )
        if pending:
            self._last_pushed_uuids = [row.uuid for row in pending]
            await self._push_and_handle(pending)
        else:
            self.log.debug("sync_sucursal.idle", batch_size=self.batch_size)

        # 4. Pull cloud changes (always — even when there's nothing to push).
        await self._pull_and_apply()

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
        - 207      → partial: body has ``success_uuids``; mark those
                     dispatched, the rest failed.
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

        # 207 Multi-Status — partial. Cloud returns the accepted UUIDs
        # in ``body.success_uuids``. We check 207 BEFORE the 2xx range
        # because 207 is technically in 200-299; without this ordering
        # the worker would treat every partial push as a clean success.
        if status == 207:
            success_ids = _extract_success_uuids(response.body)
            accepted = 0
            rejected = 0
            for row in pending:
                if row.uuid in success_ids:
                    await sq_helpers.mark_dispatched(self._session, row.uuid)
                    accepted += 1
                else:
                    await sq_helpers.mark_failed(
                        self._session,
                        row.uuid,
                        "rejected_by_cloud",
                    )
                    rejected += 1
            self.log.warning(
                "sync_sucursal.push_partial",
                status=status,
                accepted=accepted,
                rejected=rejected,
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
    # Step 4: pull + apply
    # ------------------------------------------------------------------

    async def _pull_and_apply(self) -> None:
        """Pull cloud changes and apply each one through ConflictResolver."""
        assert self._http_client is not None
        try:
            pulled = await self._http_client.pull(since_seq=0)
        except (TimeoutError, httpx.HTTPError, OSError) as exc:
            self.log.error("sync_sucursal.pull_transport_error", error=str(exc))
            return

        if pulled.status != 200:
            self.log.warning("sync_sucursal.pull_non_ok", status=pulled.status)
            return

        applied = 0
        conflicts = 0
        errors = 0
        for row in pulled.rows:
            outcome = await self._conflict_resolver.apply_pushed_row(self._session, row)
            if outcome == ApplyOutcome.APPLIED:
                applied += 1
            elif outcome == ApplyOutcome.CONFLICT_V or outcome == ApplyOutcome.CONFLICT_LS:
                conflicts += 1
            else:
                errors += 1

        self.log.info(
            "sync_sucursal.pull_applied",
            pulled=len(pulled.rows),
            applied=applied,
            conflicts=conflicts,
            errors=errors,
            next_seq=pulled.next_seq,
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
        "uuid_registro": str(getattr(row, "uuid_registro", "")) or None,
        "uuid_sucursal": str(getattr(row, "uuid_sucursal", "")) or None,
        "operacion": getattr(row, "operacion", None),
        "prioridad": getattr(row, "prioridad", None),
        "datos": getattr(row, "datos", None) or {},
    }


def _extract_success_uuids(body: dict[str, Any]) -> set[uuid_lib.UUID]:
    """Parse ``{"success_uuids": ["<uuid>", ...]}`` into a ``set``."""
    raw = body.get("success_uuids") or body.get("accepted") or []
    out: set[uuid_lib.UUID] = set()
    for item in raw:
        try:
            out.add(uuid_lib.UUID(str(item)))
        except (TypeError, ValueError):
            continue
    return out


def _fake_httpx_response(response: PushResponse) -> Any:
    """Build a minimal ``httpx.Response``-shaped object for ``JwtManager``.

    :class:`parkos_core.sync.jwt_manager.JwtManager.on_401_response`
    expects an object with ``.status_code`` + ``.json()``. We don't
    import httpx at module level to keep this worker dependency-light
    (the actual transport is owned by ``SyncHttpClient``).
    """

    class _Mini:
        def __init__(self, status: int, body: dict[str, Any]) -> None:
            self.status_code = status
            self._body = body

        def json(self) -> dict[str, Any]:
            return self._body

    return _Mini(response.status, response.body)


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
            )
            return await worker.run()

    return asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_POLL_INTERVAL_S",
    "SyncSucursalWorker",
    "main",
]
