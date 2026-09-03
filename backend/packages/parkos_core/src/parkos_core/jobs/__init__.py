"""parkos_core.jobs — generic worker supervisors (PR9, T-PR9-01).

Workers boot via ``python -m parkos_core.jobs.sync_sucursal`` or
``python -m parkos_core.jobs.sync_cloud``. The :class:`WorkerRunner`
base class wraps each worker's main loop with:

- SIGTERM + SIGINT graceful shutdown (in-flight cycle finishes, exit 0).
- Structured logging via ``structlog``.
- Exit-code contract per §21.7 (``0`` clean, ``1`` unhandled, ``2`` misconfig).
- Backoff constants shared across sync workers.

Subclasses implement :meth:`BaseRunner.cycle` — one iteration of the
worker's main loop. The :meth:`BaseRunner.run` orchestrator calls
:meth:`cycle` in a loop until SIGTERM/SIGINT.
"""
from __future__ import annotations

__all__: list[str] = []
