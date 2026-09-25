"""test_runner_healthz.py — T-PR9-09 (Track 1, feature/worker-healthz).

Integration coverage that ``WorkerRunner.run()`` actually binds the
liveness server (the composition the unit tests split apart):
env validation OK → healthz binds → ``/healthz`` answers 200 on the
DAEMON thread while the main loop runs → shutdown is graceful.

Env is faked through ``monkeypatch`` so the test never validates real
``PARKOS_*`` vars. The runner re-reads ``PARKOS_HEALTHZ_PORT`` from
``os.environ``, so the ephemeral-test-port trick keeps it off 9999.
"""
from __future__ import annotations

import asyncio
import socket

from parkos_core.jobs.runner import WorkerRunner


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _NoopWorker(WorkerRunner):
    """A worker whose cycle returns immediately (no DB, no network)."""

    def __init__(self) -> None:
        super().__init__(name="noop-worker")

    async def cycle(self) -> None:
        await asyncio.sleep(0.01)


async def test_run_binds_healthz_and_answers_200(monkeypatch) -> None:
    """run() with valid env: /healthz answers 200 while the loop runs."""
    from parkos_core.jobs import runner as runner_mod

    port = _free_port()
    # Valid-env shortcut: monkeypatch load_config to a no-op success so
    # the runner reaches the healthz-bind stage without requiring the
    # full PARKOS_* matrix.
    monkeypatch.setattr(runner_mod, "load_config", lambda: None)
    # Point the liveness server at the ephemeral port (env override path).
    monkeypatch.setenv("PARKOS_HEALTHZ_PORT", str(port))

    worker = _NoopWorker()
    task = asyncio.create_task(worker.run())

    try:
        # Give the runner time to validate env + bind the socket.
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                await asyncio.sleep(0.05)
        else:
            raise AssertionError(f"healthz server never bound :{port}")

        with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
            sock.sendall(
                b"GET /healthz HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
            )
            chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        response = b"".join(chunks)
        headers, _, body = response.partition(b"\r\n\r\n")
        assert headers.split(b"\r\n", 1)[0].decode("latin-1").split(" ")[1] == "200"
        assert body == b"ok"

        worker.request_shutdown()
        exit_code = await asyncio.wait_for(task, timeout=5)
        assert exit_code == 0, "graceful shutdown must exit 0"
    finally:
        if not task.done():
            task.cancel()
            await asyncio.sleep(0)


async def test_run_malformed_healthz_port_exits_2(monkeypatch) -> None:
    """A bogus PARKOS_HEALTHZ_PORT is a misconfig → exit 2 (never starts)."""
    from parkos_core.jobs import runner as runner_mod

    monkeypatch.setattr(runner_mod, "load_config", lambda: None)
    monkeypatch.setenv("PARKOS_HEALTHZ_PORT", "not-a-port")

    worker = _NoopWorker()
    assert await worker.run() == 2


async def test_run_bind_conflict_exits_1(monkeypatch) -> None:
    """Port already taken → boot-time failure → exit 1, main loop never runs."""
    from parkos_core.jobs import runner as runner_mod
    from parkos_core.jobs.healthz import start_healthz, stop_healthz

    port = _free_port()
    monkeypatch.setattr(runner_mod, "load_config", lambda: None)
    monkeypatch.setenv("PARKOS_HEALTHZ_PORT", str(port))

    occupied = start_healthz(port=port)
    try:
        worker = _NoopWorker()
        assert await worker.run() == 1
    finally:
        stop_healthz(occupied)


def test_env_override_default_port(monkeypatch) -> None:
    """Without PARKOS_HEALTHZ_PORT the module default is 9999 (RNF-DISP-03)."""
    from parkos_core.jobs import healthz

    monkeypatch.delenv("PARKOS_HEALTHZ_PORT", raising=False)
    assert healthz._resolve_port() == 9999
    assert healthz.DEFAULT_HEALTHZ_PORT == 9999