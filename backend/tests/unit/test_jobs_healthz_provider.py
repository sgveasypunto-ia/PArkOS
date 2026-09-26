"""Liveness must distinguish "alive" from "actually consuming changes".

THE DEFECT THIS PINS
--------------------
``GET /healthz`` answered a constant ``200 ok`` for the whole life of the
process. The branch worker rejected 522 consecutive pull batches with
``ForeignKeyViolationError`` over 11 hours, applied none of them, and
``docker ps`` reported ``healthy`` throughout - because process liveness and
functional liveness were the same signal, and only the first was ever
measured.

These tests drive the real server on an ephemeral port. Asserting on the
handler class directly would miss the two things most likely to break again:
that the provider is actually consulted per request, and that the status
code is derived from the report rather than hard-coded.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import pytest
from parkos_core.jobs.healthz import start_healthz, stop_healthz


def _probe(port: int, path: str = "/healthz") -> tuple[int, bytes]:
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


@pytest.fixture
def serve():
    """Start ``/healthz`` on an ephemeral port; yield a ``(provider)`` setter."""
    server = None
    state: dict[str, Any] = {"provider": None}

    def _start(provider):
        nonlocal server
        server = start_healthz(port=0, health_provider=provider)
        return server.server_address[1]

    yield _start, state
    if server is not None:
        stop_healthz(server)


def test_healthy_report_is_200_with_the_report_as_body(serve) -> None:
    _start, _state = serve
    port = _start(lambda: {"ok": True, "consecutive_apply_failures": 0})
    status, body = _probe(port)
    assert status == 200
    assert json.loads(body) == {"consecutive_apply_failures": 0, "ok": True}


def test_degraded_report_is_503(serve) -> None:
    """The assertion that would have surfaced the 522-batch outage."""
    _start, _state = serve
    port = _start(
        lambda: {
            "ok": False,
            "consecutive_apply_failures": 3,
            "last_apply_error": "fk_violation:fk_permisos_usuario_uuid_permiso",
        }
    )
    status, body = _probe(port)
    assert status == 503, "a node consuming nothing must not report healthy"
    report = json.loads(body)
    assert report["ok"] is False
    assert report["consecutive_apply_failures"] == 3


def test_the_provider_is_consulted_per_request_not_captured_once(serve) -> None:
    """A provider wired as a one-shot snapshot would report stale health.

    The degradation happens over successive polls, so the endpoint has to
    call the provider on every probe rather than bind its first answer.
    """
    _start, _state = serve
    calls = {"n": 0}

    def provider() -> dict[str, Any]:
        calls["n"] += 1
        return {"ok": calls["n"] < 2, "calls": calls["n"]}

    port = _start(provider)
    first_status, _first_body = _probe(port)
    second_status, second_body = _probe(port)

    assert first_status == 200
    assert second_status == 503
    assert json.loads(second_body)["calls"] == 2


def test_a_broken_provider_degrades_to_plain_ok(serve) -> None:
    """A raising probe must not turn into a 500 that kills the worker."""
    _start, _state = serve

    def provider() -> dict[str, Any]:
        raise RuntimeError("probe exploded")

    port = _start(provider)
    status, body = _probe(port)
    assert status == 200
    assert body == b"ok"


def test_a_provider_returning_junk_does_not_500(serve) -> None:
    """Only a dict is a report; anything else is treated as no report."""
    _start, _state = serve
    port = _start(lambda: "not-a-dict")  # type: ignore[arg-type,return-value]
    status, body = _probe(port)
    assert status == 200
    assert body == b"ok"


def test_unknown_path_is_still_404_under_a_provider(serve) -> None:
    """The provider must not change the routing contract."""
    _start, _state = serve
    port = _start(lambda: {"ok": False})
    status, _body = _probe(port, path="/nope")
    assert status == 404
