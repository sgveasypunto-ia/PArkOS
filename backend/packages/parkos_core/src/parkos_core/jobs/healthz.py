"""Tiny HTTP liveness endpoint for sync workers (T-PR9-09, Track 1).

PR9 shipped the ``Dockerfile`` HEALTHCHECK (``urllib`` → `/healthz` on
port 9999) and the Compose ``depends_on.condition: service_healthy``
chain, but left the server itself unimplemented — the worker ran with a
''pseudo-healthcheck'' override (``os.getppid() != 1``) in Compose and
no TCP listener. This module closes that gap with a stdlib-only server
so the container liveness signal actually reflects the worker process.

Why a standalone HTTP server instead of checking the process/loop?
The worker main loop is a long-running ``while True`` with no natural
health signal; a wedged main loop still keeps the process alive. A tiny
HTTP endpoint gives the orchestrator a cheap, port-based liveness
distinction ("TCP accepts + 200 on /healthz") exactly as the docs
specify: internal-only, bound to loopback, never exposed to the LAN.

Contract (plan.md L4816 / L5691 / L7727, RNF-SLA-02, RNF-DISP-03):
  - Bind: ``127.0.0.1`` (loopback only — never the LAN).
  - Port: ``PARKOS_HEALTHZ_PORT`` env override, default ``9999``.
  - ``GET /healthz`` → ``200`` + ``ok``; any other path/method → ``404``.
  - Daemon thread: never blocks the runner's graceful shutdown.
  - The caller (worker ``run()``) starts it via :func:`start_healthz`
    and calls :func:`stop_healthz` on shutdown.
  - Fail-fast: ``PARKOS_HEALTHZ_PORT`` malformed → ``MissingEnvError``
    (exit 2 contract); bind failure (port already in use) → re-raised
    ``OSError`` so the runner exits 1 before the main loop starts.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

from parkos_core.runtime.env import MissingEnvError

DEFAULT_HEALTHZ_HOST = "127.0.0.1"
DEFAULT_HEALTHZ_PORT = 9999
_HEALTHZ_PORT_ENV = "PARKOS_HEALTHZ_PORT"


def _resolve_port(*, env: dict[str, str] | None = None) -> int:
    """Parse ``PARKOS_HEALTHZ_PORT`` (malformed values fail fast, exit 2)."""
    raw = (env if env is not None else os.environ).get(_HEALTHZ_PORT_ENV)
    if raw is None or raw == "":
        return DEFAULT_HEALTHZ_PORT
    try:
        port = int(raw)
    except ValueError:
        raise MissingEnvError([f"{_HEALTHZ_PORT_ENV}={raw!r} (must be an integer)"])\
            from None
    if not 1 <= port <= 65535:
        raise MissingEnvError([f"{_HEALTHZ_PORT_ENV}={raw!r} (must be 1..65535)"])
    return port


class _HealthzHandler(BaseHTTPRequestHandler):
    """Answer ``GET /healthz`` ��' 200; everything else ��' 404.

    ``log_message`` is silenced �?" a worker that emits a health probe per
    HEALTHCHECK interval would otherwise spam stdout with access lines.

    A class-level ``health_provider`` (``() -> dict``) is consulted when
    present. Returning ``{"ok": False, ...}`` downgrades the response to
    ``503`` with the report as the body, so a node that is ALIVE but no
    longer consuming its cloud changes stops reporting plain ``ok``.

    That distinction is the whole point: this endpoint shipped answering a
    constant ``200 ok`` while the branch worker had rejected 522 consecutive
    pull batches over 11 hours. ``docker ps`` showed ``healthy`` throughout,
    because process liveness and functional liveness were the same signal.
    Under plain ``docker compose`` an unhealthy container is NOT restarted
    (that is a Swarm behaviour), so a degraded node becomes VISIBLE in
    ``docker ps`` without entering a restart loop that would not fix
    anything.
    """

    health_provider: Any = None

    def do_GET(self) -> None:
        if self.path != "/healthz":
            self._reject()
            return

        report: dict[str, Any] | None = None
        provider = self.health_provider
        if provider is not None:
            try:
                candidate = provider()
            except Exception:  # noqa: BLE001 — a broken probe must not kill the worker
                candidate = None
            if isinstance(candidate, dict):
                report = candidate

        if report is None:
            body, status = b"ok", 200
        else:
            body = json.dumps(report, sort_keys=True).encode("utf-8")
            status = 503 if report.get("ok") is False else 200

        self.send_response(status)
        self.send_header(
            "Content-Type", "application/json" if report is not None else "text/plain"
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        self._reject()

    def do_PUT(self) -> None:
        self._reject()

    def do_DELETE(self) -> None:
        self._reject()

    def _reject(self) -> None:
        self.send_response(404)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass

    def log_error(self, fmt: str, *args: object) -> None:
        del fmt, args  # sink — health probes must not flood stderr either


class HealthzServer(ThreadingHTTPServer):
    """Marker subclass: lets callers/tests hold a typed server reference.

    ``allow_reuse_address = False`` — an unexported ``BaseServer`` knob
    that the stdlib ``HTTPServer`` defaults to **True** via ``SO_REUSEADDR``.
    For a worker liveness socket that is wrong on two counts:

    - Fail-fast contract: with ``SO_REUSEADDR`` a second bind to the same
      address succeeds silently, so the "port already taken" boot error
      this module is supposed to surface (exit 1) would never fire. An
      exclusive bind makes the conflict a hard ``OSError``.
    - Listeners don't accumulate ``TIME_WAIT`` on close (that is a
      post-established-connection state), so there is no restart-loop
      penalty from disabling reuse.
    """

    allow_reuse_address = False
    daemon_threads = True


def start_healthz(
    *,
    env: dict[str, str] | None = None,
    host: str = DEFAULT_HEALTHZ_HOST,
    port: int | None = None,
    health_provider: Callable[[], dict[str, Any] | None] | None = None,
) -> HealthzServer:
    """Start the liveness server on a daemon thread and return it.

    ``port`` short-circuits the ``PARKOS_HEALTHZ_PORT`` env lookup �?"
    used by tests to bind an ephemeral port without touching the
    process environment.

    ``health_provider`` is an optional ``() -> dict`` consulted on every
    probe (see ``_HealthzHandler``). It is injected as a per-server
    subclass attribute rather than a module global so that a test binding
    two servers with different providers cannot observe each other's state.

    Raises:
        MissingEnvError: ``PARKOS_HEALTHZ_PORT`` malformed (only when
            ``port`` is not supplied).
        OSError: bind failure (e.g. port 9999 already taken) �?" the runner
            must treat this as fatal (exit 1), never "start anyway".
    """
    resolved = port if port is not None else _resolve_port(env=env)
    handler: type[BaseHTTPRequestHandler] = _HealthzHandler
    if health_provider is not None:
        handler = type(
            "_HealthzHandlerWithProvider",
            (_HealthzHandler,),
            {"health_provider": staticmethod(health_provider)},
        )
    server = HealthzServer((host, resolved), handler)
    thread = Thread(
        target=server.serve_forever,
        name=f"parkos-healthz-{resolved}",
        daemon=True,
    )
    thread.start()
    return server


def stop_healthz(server: HealthzServer) -> None:
    """Shut the liveness server down (idempotent)."""
    if server is None:
        return
    try:
        server.shutdown()
        server.server_close()
    except OSError:
        pass


__all__ = [
    "DEFAULT_HEALTHZ_HOST",
    "DEFAULT_HEALTHZ_PORT",
    "HealthzServer",
    "MissingEnvError",
    "start_healthz",
    "stop_healthz",
]