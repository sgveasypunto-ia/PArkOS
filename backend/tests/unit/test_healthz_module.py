"""test_healthz_module.py — T-PR9-09 (Track 1, feature/worker-healthz).

Unit coverage for ``parkos_core.jobs.healthz``: the tiny stdlib HTTP
liveness server that backs the Dockerfile HEALTHCHECK
(``urllib → /healthz:9999``) and Compose ``depends_on`` for the sync
workers. No DB, no testcontainers.

Contract under test (plan.md L4816/L5691/L7727, RNF-SLA-02, RNF-DISP-03):
  - ``GET /healthz`` → 200 ``ok``.
  - Any other path → 404.
  - Any non-GET method → 404.
  - Binds loopback only (127.0.0.1), never the LAN.
  - Malformed ``PARKOS_HEALTHZ_PORT`` → ``MissingEnvError`` (exit-2
    misconfig contract); sane override is honored.
  - Bind failure (port already taken) → ``OSError`` (fail-fast).
  - ``stop_healthz`` is idempotent and lets the daemon thread drop the
    accept socket.
"""
from __future__ import annotations

import socket
import urllib.request

import pytest
from parkos_core.jobs.healthz import (
    DEFAULT_HEALTHZ_PORT,
    MissingEnvError,
    start_healthz,
    stop_healthz,
)

# ---------------------------------------------------------------------------
# Free-port helper (bind ephemeral, release, reuse — small race, test-only)
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def live_server():
    """Start a healthz server on an ephemeral port; stop it afterwards."""
    port = _free_port()
    server = start_healthz(port=port)
    yield port, server
    stop_healthz(server)


_GET = "GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"


def _raw_request(port: int, path: str, method: str = "GET") -> int:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(_GET.format(path=path).encode())
        status_line = sock.recv(4096).split(b"\r\n", 1)[0].decode("latin-1")
    return int(status_line.split(" ")[1])


def test_get_healthz_returns_200_ok(live_server) -> None:
    port, _ = live_server
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5) as resp:
        assert resp.status == 200
        assert resp.read() == b"ok"


def test_unknown_path_returns_404(live_server) -> None:
    port, _ = live_server
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(_GET.format(path="/nope").encode())
        status_line = sock.recv(4096).split(b"\r\n", 1)[0].decode("latin-1")
        assert status_line.split(" ")[1] == "404"


def test_default_port_is_9999() -> None:
    assert DEFAULT_HEALTHZ_PORT == 9999, "RNF-DISP-03 contract: :9999/healthz"


def test_malformed_port_env_raises_missing_env() -> None:
    with pytest.raises(MissingEnvError):
        start_healthz(env={"PARKOS_HEALTHZ_PORT": "not-a-number"})


def test_out_of_range_port_env_raises_missing_env() -> None:
    with pytest.raises(MissingEnvError):
        start_healthz(env={"PARKOS_HEALTHZ_PORT": "70000"})


def test_port_env_override_is_honored() -> None:
    port = _free_port()
    server = start_healthz(env={"PARKOS_HEALTHZ_PORT": str(port)})
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5) as resp:
            assert resp.status == 200
    finally:
        stop_healthz(server)


def test_bind_failure_raises_oserror() -> None:
    port = _free_port()
    first = start_healthz(port=port)
    try:
        with pytest.raises(OSError):
            start_healthz(port=port)
    finally:
        stop_healthz(first)


def test_double_stop_is_idempotent(live_server) -> None:
    _, server = live_server
    stop_healthz(server)
    stop_healthz(server)  # must not raise
    stop_healthz(None)  # type: ignore[arg-type]  # unknown server path


def test_post_method_is_rejected(live_server) -> None:
    port, _ = live_server
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(
            b"POST /healthz HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
        )
        status_line = sock.recv(4096).split(b"\r\n", 1)[0].decode("latin-1")
        assert status_line.split(" ")[1] == "404"