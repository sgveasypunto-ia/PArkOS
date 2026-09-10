"""test_sync_heartbeat_real_http.py — regression coverage for a real gap
confirmed against the live Docker cloud+branch stack (2026-09-10, post-sync
audit): ``POST /api/v1/sync/heartbeat`` returned 422 on every single call
from ``job-sync-sucursal``, silently — ``SyncHttpClient.heartbeat`` never
checks the response status, so the failure never surfaced anywhere except
the raw ``docker logs parkos-api-admin`` output.

Root cause: the endpoint's ``_HeartbeatRequest`` schema is
``{"state": {...}}`` (a wrapper), but ``SyncHttpClient.heartbeat`` posted
the caller's ``state`` dict directly as the body — unwrapped. The existing
unit test (``test_sync_transport.py::TestHeartbeat``) mocked the HTTP call
and asserted the WRONG (unwrapped) shape as correct, so it never caught
this — exactly the "mocked test enshrines the bug" pattern found repeatedly
in this codebase's sync layer this session.

This test drives the REAL, unmodified ``sync_router`` (mounted the same way
production does, under ``/api/v1``) through ``httpx.ASGITransport`` — no
mocks — and exercises BOTH the real production ``SyncHttpClient.heartbeat``
method AND the raw wire shape, so a regression to the unwrapped body fails
here instead of 422ing silently in Docker again.
"""

from __future__ import annotations

import uuid as uuid_lib
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import APIRouter, FastAPI


def _build_cloud_app() -> FastAPI:
    from parkos_core.api.v1.sync_router import _sync_agent_claims
    from parkos_core.api.v1.sync_router import router as sync_router_obj

    app = FastAPI()
    outer = APIRouter(prefix="/api/v1")
    outer.include_router(sync_router_obj)
    app.include_router(outer)

    def _claims_override() -> dict[str, Any]:
        return {
            "iss": "sync-agent-branch",
            "sub": str(uuid_lib.uuid4()),
            "jti": "heartbeat-real-http-test",
            "scope": "branch",
            "sucursal": str(uuid_lib.uuid4()),
        }

    app.dependency_overrides[_sync_agent_claims] = _claims_override
    return app


async def test_heartbeat_wire_shape_wrapped_succeeds_unwrapped_422s(tmp_path: Path) -> None:
    """Pins the server's real contract: wrapped body succeeds, the old
    (buggy) unwrapped shape 422s — proves this isn't a hypothetical."""
    app = _build_cloud_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud") as raw_client:
        state = {"state": "alive", "ts": "2026-09-10T00:00:00", "pid": 1, "host": "test"}

        unwrapped = await raw_client.post("/api/v1/sync/heartbeat", json=state)
        assert unwrapped.status_code == 422, unwrapped.text

        wrapped = await raw_client.post("/api/v1/sync/heartbeat", json={"state": state})
        assert wrapped.status_code == 204, wrapped.text


async def test_real_sync_http_client_heartbeat_succeeds_against_real_endpoint(
    tmp_path: Path,
) -> None:
    """Drives the actual production ``SyncHttpClient.heartbeat`` — not a
    hand-rolled POST — against the real router. Before the fix this 422'd
    every time; ``SyncHttpClient.heartbeat`` swallows the response, so the
    only way to observe the failure is to capture it via an event hook."""
    from parkos_core.sync.transport import SyncHttpClient

    app = _build_cloud_app()
    jwt_path = tmp_path / "sync.jwt"
    jwt_path.write_text("fake-jwt-not-verified-by-overridden-claims", encoding="utf-8")

    captured_statuses: list[int] = []

    async def _log_response(response: httpx.Response) -> None:
        captured_statuses.append(response.status_code)

    def _session_factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://cloud",
            event_hooks={"response": [_log_response]},
        )

    client = SyncHttpClient(
        session_factory=_session_factory,
        base_url="http://cloud",
        jwt_path=jwt_path,
    )

    await client.heartbeat(
        state={"state": "alive", "ts": "2026-09-10T00:00:00", "pid": 1, "host": "test"}
    )

    assert captured_statuses == [204], (
        "SyncHttpClient.heartbeat sent a body the real endpoint rejected "
        f"(status={captured_statuses}) — this is the exact silent failure "
        "confirmed in production Docker logs."
    )
