"""Sync HTTP transport client (T-PR9-02; T-PR12-006/007 additions).

Branch→cloud + cloud→branch HTTP client for the sync workers. Reads the
JWT from ``PARKOS_SYNC_JWT_PATH`` lazily (the file may not exist at boot —
the CLI pair flow writes it once after the first pairing).

Endpoints (per design §21.7 / §21.9):

- ``GET {base_url}/api/v1/sync/hello`` — dual-protocol handshake
  (T-PR12-007). NO auth header — mirrors the endpoint's own "no auth
  required" contract (REQ-CUT-004).
- ``POST {base_url}/api/v1/sync/push`` — branch → cloud (legacy applier)
- ``POST {base_url}/api/v1/sync/pull`` — branch ← cloud
- ``POST {base_url}/api/v1/sync/events`` — catalog-driven row push
  (T-PR12-006, REQ-CUT-015) — the branch auto-detect table
  (``jobs/sync_sucursal.py``, T-PR12-007) switches to this endpoint
  instead of ``/sync/push`` once the catalog applier is selected.
- ``POST {base_url}/api/v1/sync/heartbeat`` — both directions
- ``POST {base_url}/api/v1/sync/rotate-jwt`` — both directions

Uses ``httpx.AsyncClient`` with timeout=30s + max 10 concurrent connections.

The constructor takes a ``session_factory`` (callable returning
``httpx.AsyncClient``) so tests can inject a mock. Production wires it
from ``app.bootstrap.http_session_factory()`` (T-PR11).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import structlog


@dataclass
class PushResponse:
    """Response from /sync/push."""

    status: int
    body: dict[str, Any]
    retry_after_seconds: int | None = None


@dataclass
class PullResponse:
    """Response from /sync/pull."""

    status: int
    rows: list[dict[str, Any]]
    next_seq: int
    retry_after_seconds: int | None = None


@dataclass
class NewJwt:
    """Response from /sync/rotate-jwt."""

    jwt: str
    expires_at: int  # unix timestamp
    grace_until: int  # unix timestamp


@dataclass
class HelloResponse:
    """Response from GET /sync/hello (T-PR12-007, REQ-CUT-004's shape).

    ``protocol_version``/``min_branch_version``/``catalog_revision`` are
    ``None`` when the response could not be parsed (non-2xx or non-JSON
    body) — the caller (``jobs/sync_sucursal.py``'s auto-detect) treats
    that the same as a transport error: fail-safe to the legacy applier.
    """

    status: int
    protocol_version: str | None
    min_branch_version: str | None
    grace_until: str | None
    catalog_revision: str | None


@dataclass
class EventsPushResponse:
    """Response from POST /sync/events (T-PR12-006).

    ``results`` is ``[{"event_type": ..., "status": ...}, ...]`` in the
    SAME order as the request's ``events`` — the router applies each row
    synchronously, in request order (never reordered), so positional
    correlation back to the pushed ``sync_queue`` rows is safe.
    """

    status: int
    results: list[dict[str, Any]]


class SyncJwtMissingError(RuntimeError):
    """Raised by ``_read_jwt`` when the branch has no JWT file provisioned.

    Semantically distinct from a transport/HTTP error: this is the
    ``pre-pairing`` state the sync worker promises to tolerate on every
    cycle (``sync_sucursal.cycle`` logs the missing JWT, skips the push +
    pull steps, and still commits), so callers must be able to catch it
    WITHOUT also turning it into a queued retry. Subclasses
    ``RuntimeError`` so pre-existing generic handlers keep working.
    """


DEFAULT_TIMEOUT_S = 30.0


class SyncHttpClient:
    def __init__(
        self,
        *,
        session_factory: Callable[[], httpx.AsyncClient] | None = None,
        base_url: str,
        jwt_path: Path,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._session_factory = session_factory or self._default_session_factory
        self.base_url = base_url.rstrip("/")
        self.jwt_path = jwt_path
        self.timeout_s = timeout_s
        self.log = structlog.get_logger("parkos.sync.transport")

    def _default_session_factory(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_s),
            limits=httpx.Limits(max_connections=10),
        )

    def _read_jwt(self) -> str:
        if not self.jwt_path.exists():
            raise SyncJwtMissingError(
                f"PARKOS_SYNC_JWT_PATH={self.jwt_path} missing — branch must pair first"
            )
        return self.jwt_path.read_text().strip()

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._read_jwt()}"}

    async def hello(self) -> HelloResponse:
        """GET /sync/hello — dual-protocol handshake (T-PR12-007).

        NO auth header — mirrors the endpoint's own contract (a branch
        calls this BEFORE it has decided which applier, and therefore
        which JWT-bearing flow, to use).
        """
        async with self._session_factory() as session:
            response = await session.get(f"{self.base_url}/api/v1/sync/hello")
        body = (
            response.json()
            if response.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        return HelloResponse(
            status=response.status_code,
            protocol_version=body.get("protocol_version"),
            min_branch_version=body.get("min_branch_version"),
            grace_until=body.get("grace_until"),
            catalog_revision=body.get("catalog_revision"),
        )

    async def push_events(self, events: list[dict[str, Any]]) -> EventsPushResponse:
        """POST /sync/events — catalog-driven row push (T-PR12-006).

        Distinct from :meth:`push` (``/sync/push``, the legacy applier's
        transport) — the auto-detect table (REQ-CUT-005) decides which of
        the two the caller uses for a given cycle.
        """
        body = {"events": events}
        async with self._session_factory() as session:
            response = await session.post(
                f"{self.base_url}/api/v1/sync/events",
                json=body,
                headers=self._auth_headers(),
            )
        body_dict = (
            response.json()
            if response.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        return EventsPushResponse(
            status=response.status_code,
            results=list(body_dict.get("results", [])),
        )

    async def push(self, rows: list[dict[str, Any]]) -> PushResponse:
        """POST /sync/push — branch → cloud."""
        body = {"rows": rows}
        async with self._session_factory() as session:
            response = await session.post(
                f"{self.base_url}/api/v1/sync/push",
                json=body,
                headers=self._auth_headers(),
            )
        retry_after_raw = response.headers.get("Retry-After")
        retry_after = int(retry_after_raw) if retry_after_raw and retry_after_raw.isdigit() else None
        body_dict = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        return PushResponse(
            status=response.status_code,
            body=body_dict,
            retry_after_seconds=retry_after,
        )

    async def pull(self, since_seq: int) -> PullResponse:
        """POST /sync/pull — branch ← cloud."""
        async with self._session_factory() as session:
            response = await session.post(
                f"{self.base_url}/api/v1/sync/pull",
                json={"since_seq": since_seq},
                headers=self._auth_headers(),
            )
        retry_after_raw = response.headers.get("Retry-After")
        retry_after = int(retry_after_raw) if retry_after_raw and retry_after_raw.isdigit() else None
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        rows = body.get("rows", [])
        next_seq = body.get("next_seq", since_seq)
        return PullResponse(
            status=response.status_code,
            rows=rows,
            next_seq=int(next_seq),
            retry_after_seconds=retry_after,
        )

    async def heartbeat(self, state: dict[str, Any]) -> None:
        """POST /sync/heartbeat (both directions).

        The endpoint's ``_HeartbeatRequest`` expects ``{"state": {...}}``
        — the caller's ``state`` dict is the *value* of that key, not the
        request body itself. Posting it unwrapped 422s on every single
        call (confirmed in real Docker logs: every heartbeat from
        ``sync_sucursal`` failed silently, since this client never checks
        the response status).
        """
        async with self._session_factory() as session:
            await session.post(
                f"{self.base_url}/api/v1/sync/heartbeat",
                json={"state": state},
                headers=self._auth_headers(),
            )

    async def rotate_jwt(self) -> NewJwt:
        """POST /sync/rotate-jwt (both directions).

        Returns the new JWT + expires_at + grace_until. Caller persists
        the new JWT to ``self.jwt_path`` mode 0600.
        """
        # The old JWT is in the Authorization header — the rotate endpoint
        # verifies it, then issues a fresh one + grace_until for the old.
        async with self._session_factory() as session:
            response = await session.post(
                f"{self.base_url}/api/v1/sync/rotate-jwt",
                headers=self._auth_headers(),
            )
        response.raise_for_status()
        body = response.json()
        return NewJwt(
            jwt=body["jwt"],
            expires_at=int(body["expires_at"]),
            grace_until=int(body["grace_until"]),
        )


__all__ = [
    "DEFAULT_TIMEOUT_S",
    "EventsPushResponse",
    "HelloResponse",
    "NewJwt",
    "PullResponse",
    "PushResponse",
    "SyncHttpClient",
    "SyncJwtMissingError",
]
