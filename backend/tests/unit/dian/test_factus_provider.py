"""test_factus_provider.py -- T-PR11-14 (Factus provider adapter unit tests).

Direct tests for ``FactusProvider`` -- the low-level HTTP adapter wrapping
Factus's three endpoints. The dispatcher's state machine has its own
end-to-end tests (T-PR11-08..13); this file pins the adapter's HTTP surface
in isolation so a transport-level regression fails fast. The fourth test
pins rotation safety: ``_auth_headers()`` re-reads the token file on every
call (per the constructor docstring).

No database, no network: ``httpx.MockTransport`` + the provider's
``session_factory`` seam keep every request off the wire.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import httpx

# Parkos cloud-import guard (T-PR11-07 -- REQ-X3, design section 10 Layer 2).
# Mirror the dispatcher conftest pattern: stamp PARKOS_DEPLOY=cloud for the
# import window only, then restore. ``FactusProvider`` is cloud-only.
_PREV_DEPLOY = os.environ.get("PARKOS_DEPLOY")
os.environ["PARKOS_DEPLOY"] = "cloud"
try:
    from parkos_core.dian.cloud.dian_providers.factus import FactusProvider, PollResult
finally:
    if _PREV_DEPLOY is None:
        os.environ.pop("PARKOS_DEPLOY", None)
    else:
        os.environ["PARKOS_DEPLOY"] = _PREV_DEPLOY

_BASE_URL = "http://test"


def _wire(
    handler: Callable[[httpx.Request], httpx.Response],
    token_path: Path,
) -> tuple[FactusProvider, list[httpx.Request]]:
    """Wire ``FactusProvider`` through ``MockTransport``; return ``(provider, seen)``."""
    seen: list[httpx.Request] = []

    def _wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    transport = httpx.MockTransport(_wrapped)
    provider = FactusProvider(
        base_url=_BASE_URL,
        token_path=token_path,
        session_factory=lambda: httpx.AsyncClient(transport=transport),
    )
    return provider, seen


async def test_factus_send_ubl_posts_to_api_ubl_2_1(tmp_path: Path) -> None:
    """POST /api/ubl2.1 with Bearer auth + application/xml body; returns trackId."""
    token_path = tmp_path / "dian.token"
    token_path.write_text("test-bearer-token", encoding="utf-8")

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"trackId": "track-abc"})

    provider, seen = _wire(_handler, token_path)
    track_id = await provider.send_ubl(b"<Invoice/>")

    assert track_id == "track-abc"
    assert len(seen) == 1
    req = seen[0]
    assert req.method == "POST"
    assert str(req.url) == f"{_BASE_URL}/api/ubl2.1"
    assert req.headers["Authorization"] == "Bearer test-bearer-token"
    assert req.headers["Content-Type"] == "application/xml"
    assert req.content == b"<Invoice/>"


async def test_factus_poll_gets_trackId_path(tmp_path: Path) -> None:
    """GET /api/ubl2.1/{trackId} with Bearer auth; PollResult mirrors body fields."""
    token_path = tmp_path / "dian.token"
    token_path.write_text("test-bearer-token", encoding="utf-8")

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "estado": "aceptado",
                "cufe": "cufe-xyz",
                "motivo_rechazo": None,
            },
        )

    provider, seen = _wire(_handler, token_path)
    result = await provider.poll("track-abc")

    assert isinstance(result, PollResult)
    assert result.estado == "aceptado"
    assert result.cufe == "cufe-xyz"
    assert result.motivo_rechazo is None
    assert len(seen) == 1
    req = seen[0]
    assert req.method == "GET"
    assert str(req.url) == f"{_BASE_URL}/api/ubl2.1/track-abc"
    assert req.headers["Authorization"] == "Bearer test-bearer-token"


async def test_factus_send_revocacion_posts_to_api_revocacion(tmp_path: Path) -> None:
    """POST /api/revocacion with Bearer auth + application/xml body; returns trackId."""
    token_path = tmp_path / "dian.token"
    token_path.write_text("test-bearer-token", encoding="utf-8")

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"trackId": "track-rev"})

    provider, seen = _wire(_handler, token_path)
    track_id = await provider.send_revocacion(b"<Revocation/>")

    assert track_id == "track-rev"
    assert len(seen) == 1
    req = seen[0]
    assert req.method == "POST"
    assert str(req.url) == f"{_BASE_URL}/api/revocacion"
    assert req.headers["Authorization"] == "Bearer test-bearer-token"
    assert req.headers["Content-Type"] == "application/xml"
    assert req.content == b"<Revocation/>"


async def test_factus_re_reads_token_on_every_call(tmp_path: Path) -> None:
    """Write a new token after construction; next call sees it in Authorization."""
    token_path = tmp_path / "dian.token"
    token_path.write_text("token-v1", encoding="utf-8")

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"trackId": "track-rot"})

    provider, seen = _wire(_handler, token_path)
    await provider.send_ubl(b"<Invoice/>")
    token_path.write_text("token-v2", encoding="utf-8")
    await provider.send_ubl(b"<Invoice/>")

    assert [r.headers["Authorization"] for r in seen] == [
        "Bearer token-v1",
        "Bearer token-v2",
    ]
