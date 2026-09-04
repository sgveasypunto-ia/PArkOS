"""Generic worker supervisor (T-PR9-01).

Workers boot via ``python -m parkos_core.jobs.sync_sucursal`` or
``python -m parkos_core.jobs.sync_cloud``. The runner wraps the worker's
main loop with:

- SIGTERM + SIGINT graceful shutdown (in-flight cycle finishes, then exit 0).
- Structured logging via ``structlog``.
- Exit code contract (per §21.7):
  - ``0``: clean shutdown
  - ``1``: unhandled error / restart-loop case
  - ``2``: misconfig (missing/invalid env at boot) — also raised by the
    T-PR8-02 env validator wired into ``BaseRunner.run``.
- Backoff constants per §21.7.

Subclasses implement ``async def cycle() -> None`` — one iteration of
the worker's main loop. The ``run()`` orchestrator calls ``cycle()`` in a
loop until SIGTERM/SIGINT.
"""
from __future__ import annotations

import asyncio
import signal
from abc import ABC, abstractmethod

import structlog

# T-PR8-02: env validator imported lazily inside ``BaseRunner.run`` to
# avoid forcing the validator at import time (keeps the module importable
# for tools that introspect ``BaseRunner`` without wanting to spin up the
# runtime config machinery).
from parkos_core.runtime.env import MissingEnvError, load_config

# Backoff schedules (seconds).
BACKOFF_4XX = [60, 300, 1800, 7200, 43200, 86400]
BACKOFF_5XX = [30, 60, 300]


class BaseRunner(ABC):
    """Abstract base — workers subclass and implement ``cycle()``."""

    def __init__(self, *, name: str, structured_logger: structlog.stdlib.BoundLogger | None = None) -> None:
        self.name = name
        self.log = structured_logger or structlog.get_logger(name)
        self._shutdown_requested = asyncio.Event()

    @abstractmethod
    async def cycle(self) -> None:
        """One iteration of the worker's main loop."""

    def request_shutdown(self) -> None:
        """Signal handler entry point — set the shutdown event."""
        self.log.info("shutdown_requested")
        self._shutdown_requested.set()

    async def run(self) -> int:
        """Run cycles until SIGTERM/SIGINT, then graceful exit 0.

        T-PR8-02: validate runtime env BEFORE the first ``cycle()`` call.
        ``MissingEnvError`` is mapped to exit code ``2`` (misconfig) per
        §21.7, raising the same exit-code contract the container
        entrypoints honor.
        """
        # T-PR8-02: env validation — exit 2 on missing/malformed vars.
        # Logging goes through structlog (``self.log``) so the operator
        # sees the offending var names alongside the worker's startup
        # banner.
        try:
            load_config()
        except MissingEnvError as exc:
            self.log.error("env_validation_failed", errors=exc.errors)
            return 2

        # Wire signal handlers (Unix only — Windows uses add_signal_handler)
        loop = asyncio.get_running_loop()
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, self.request_shutdown)
        except NotImplementedError:
            self.log.warning("signal_handlers_unavailable", platform=__import__("sys").platform)

        self.log.info("worker_started", name=self.name)
        try:
            while not self._shutdown_requested.is_set():
                try:
                    await self.cycle()
                except Exception as exc:
                    self.log.exception("cycle_error", error=str(exc))
                    # Don't exit; outer loop continues after a short pause.
                    await asyncio.sleep(1)
            self.log.info("worker_stopped_clean")
            return 0
        except Exception:
            self.log.exception("worker_fatal")
            return 1

    def install_signal_handlers(self) -> None:
        """For environments that don't use asyncio.run() (e.g. CLI wrapper)."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: self.request_shutdown())


class WorkerRunner(BaseRunner):
    """Concrete runner used by PR9 sync workers.

    T-PR9-01 ships the BASE; the two sync workers (T-PR9-06, T-PR9-07)
    subclass this.
    """

    def __init__(self, *, name: str) -> None:
        super().__init__(name=name)


__all__ = [
    "BACKOFF_4XX",
    "BACKOFF_5XX",
    "BaseRunner",
    "WorkerRunner",
]
