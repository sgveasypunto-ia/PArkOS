"""test_idempotency_middleware_streaming.py -- defect L3.

``BaseHTTPMiddleware.call_next`` returns a streaming response with no
``.body``. The middleware used to fail inside ``_serialize_response`` on every
POST (``idempotency_key_persist_failed``) so nothing was ever persisted or
replayed. These tests pin the contract with a stubbed session (no DB):

  * the streamed body is captured, persisted and the response rebuilt intact;
  * same key + same request -> stored response + ``Idempotent-Replay: true``;
  * same key + different body/path -> 409 ``idempotency_key_conflict``;
  * 5xx and caller-transient statuses are never persisted;
  * huge bodies are forwarded whole without being buffered for persistence;
  * auth/sync/renovar paths and unverifiable bearers bypass the cache.
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse, StreamingResponse
from parkos_core.api import middleware as mw


def _drive(monkeypatch, register, *, headers=None, body=b"", row=None, path="/op"):
    """Run one POST through the middleware with a stubbed session."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()

    async def _open(_request):
        return session

    monkeypatch.setattr(mw, "_open_session_for_request", _open)

    app = FastAPI()
    app.add_middleware(mw.IdempotencyKeyMiddleware)
    calls = {"n": 0}
    register(app, calls)

    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.post(
                path, content=body, headers={"Idempotency-Key": "k1", **(headers or {})}
            )

    return asyncio.run(_go()), session, calls


def _json_route(path="/op", status=201):
    def register(app, calls):
        @app.post(path, status_code=status)
        async def op() -> dict[str, int]:
            calls["n"] += 1
            return {"n": calls["n"]}

    return register


def _stored(body: bytes = b"", *, path="/op", **overrides):
    base = {
        "expires_at": datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
        "response_status": 201,
        "response_body": {
            "kind": "json",
            "body": {"n": 99},
            "headers": {"x-custom": "yes", "content-length": "9999"},
        },
        "request_body_hash": hashlib.sha256(body).hexdigest(),
        "method": "POST",
        "path": path,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_first_call_persists_streamed_body_status_and_request_hash(monkeypatch) -> None:
    resp, session, calls = _drive(monkeypatch, _json_route(), body=b'{"a":1}')

    assert resp.status_code == 201
    assert resp.json() == {"n": 1}
    assert calls["n"] == 1
    session.add.assert_called_once()
    row = session.add.call_args.args[0]
    assert row.response_status == 201
    assert row.response_body["body"] == {"n": 1}
    assert row.response_body["kind"] == "json"
    assert row.request_body_hash == hashlib.sha256(b'{"a":1}').hexdigest()
    assert (row.method, row.path) == ("POST", "/op")
    assert "content-length" not in row.response_body["headers"]
    session.commit.assert_awaited_once()


def test_response_headers_and_repeated_cookies_survive(monkeypatch) -> None:
    def register(app, calls):
        @app.post("/op")
        async def op() -> JSONResponse:
            r = JSONResponse({"ok": True}, status_code=202, headers={"X-Custom": "yes"})
            r.set_cookie("a", "1")
            r.set_cookie("b", "2")
            return r

    resp, session, _ = _drive(monkeypatch, register)

    assert resp.status_code == 202
    assert resp.headers["x-custom"] == "yes"
    assert len(resp.headers.get_list("set-cookie")) == 2
    stored = session.add.call_args.args[0].response_body["headers"]
    assert stored["x-custom"] == "yes"
    assert "set-cookie" not in stored  # cookies are never persisted


def test_background_task_still_runs(monkeypatch) -> None:
    ran = {"v": False}

    def register(app, calls):
        @app.post("/op")
        async def op(bg: BackgroundTasks) -> dict[str, bool]:
            bg.add_task(lambda: ran.__setitem__("v", True))
            return {"ok": True}

    resp, _, _ = _drive(monkeypatch, register)
    assert resp.status_code == 200
    assert ran["v"] is True


def _raising(code):
    def register(app, calls):
        @app.post("/op")
        async def op() -> None:
            raise HTTPException(status_code=code, detail="x")

    return register


def test_5xx_is_returned_but_not_persisted(monkeypatch) -> None:
    resp, session, _ = _drive(monkeypatch, _raising(503))
    assert resp.status_code == 503
    session.add.assert_not_called()


def test_operation_4xx_is_persisted_transient_caller_errors_are_not(monkeypatch) -> None:
    _, s422, _ = _drive(monkeypatch, _raising(422))
    s422.add.assert_called_once()
    for code in (401, 403, 429):
        _, s, _ = _drive(monkeypatch, _raising(code))
        s.add.assert_not_called()


def test_empty_204_roundtrips(monkeypatch) -> None:
    def register(app, calls):
        @app.post("/op", status_code=204)
        async def op() -> Response:
            return Response(status_code=204)

    resp, session, _ = _drive(monkeypatch, register)
    assert resp.status_code == 204
    assert session.add.call_args.args[0].response_body["kind"] == "empty"

    empty = {"kind": "empty", "body": None, "headers": {}}
    replay_row = _stored(response_status=204, response_body=empty)
    resp2, _, calls = _drive(monkeypatch, _json_route(), row=replay_row)
    assert resp2.status_code == 204
    assert resp2.content == b""
    assert resp2.headers["idempotent-replay"] == "true"
    assert calls["n"] == 0


def test_large_streamed_body_is_forwarded_whole_and_not_persisted(monkeypatch) -> None:
    chunk = b"x" * 100_000
    n_chunks = 5
    assert len(chunk) * n_chunks > mw.MAX_PERSIST_BODY_BYTES

    def register(app, calls):
        @app.post("/op")
        async def op() -> StreamingResponse:
            async def gen():
                for _ in range(n_chunks):
                    yield chunk

            return StreamingResponse(gen(), media_type="application/octet-stream")

    resp, session, _ = _drive(monkeypatch, register)
    assert resp.status_code == 200
    assert len(resp.content) == len(chunk) * n_chunks
    session.add.assert_not_called()


def test_replay_same_request_returns_stored_response_with_marker(monkeypatch) -> None:
    resp, session, calls = _drive(
        monkeypatch, _json_route(), body=b'{"a":1}', row=_stored(b'{"a":1}')
    )

    assert resp.status_code == 201
    assert resp.json() == {"n": 99}
    assert resp.headers["idempotent-replay"] == "true"
    assert resp.headers["x-custom"] == "yes"
    assert calls["n"] == 0
    session.add.assert_not_called()


def test_same_key_different_body_is_409_conflict(monkeypatch) -> None:
    resp, session, calls = _drive(
        monkeypatch, _json_route(), body=b'{"a":2}', row=_stored(b'{"a":1}')
    )

    assert resp.status_code == 409
    assert resp.json() == {"detail": {"error": "idempotency_key_conflict"}}
    assert calls["n"] == 0
    session.add.assert_not_called()


def test_same_key_different_path_is_409_conflict(monkeypatch) -> None:
    resp, _, calls = _drive(monkeypatch, _json_route(), row=_stored(path="/other"))
    assert resp.status_code == 409
    assert calls["n"] == 0


def test_expired_key_runs_handler_and_does_not_persist(monkeypatch) -> None:
    expired = _stored(expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1))
    resp, session, calls = _drive(monkeypatch, _json_route(), row=expired)
    assert resp.status_code == 201
    assert calls["n"] == 1
    session.add.assert_not_called()


def test_self_managed_paths_are_bypassed(monkeypatch) -> None:
    """auth/sync (tokens) and renovar (own replay) never touch the cache."""
    for path in (
        "/api/v1/auth/login",
        "/api/v1/sync/pair",
        "/api/v1/clientes/subscripciones/abc/renovar",
    ):
        resp, session, calls = _drive(monkeypatch, _json_route(path), path=path)
        assert resp.status_code == 201
        assert calls["n"] == 1
        session.execute.assert_not_called()
        session.add.assert_not_called()


def test_unverifiable_bearer_bypasses_idempotency(monkeypatch) -> None:
    """A token that does not verify never gets a cached response served."""
    _, session, calls = _drive(
        monkeypatch,
        _json_route(),
        headers={"Authorization": "Bearer nope"},
        row=_stored(),
    )
    assert calls["n"] == 1  # handler ran; no replay
    session.execute.assert_not_called()
