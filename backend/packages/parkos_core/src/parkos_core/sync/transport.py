"""Sync HTTP transport client (T-PR9-02).

Branch→cloud + cloud→branch HTTP client for the sync workers. Reads the
JWT from ``PARKOS_SYNC_JWT_PATH`` lazily (the file may not exist at boot —
the CLI pair flow writes it once after the first pairing).

Endpoints (per design §21.7 / §21.9):

- ``POST {base_url}/api/v1/sync/push`` — branch → cloud
- ``POST {base_url}/api/v1/sync/pull`` — branch ← cloud
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
            raise RuntimeError(
                f"PARKOS_SYNC_JWT_PATH={self.jwt_path} missing — branch must pair first"
            )
        return self.jwt_path.read_text().strip()

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._read_jwt()}"}

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
        """POST /sync/heartbeat (both directions)."""
        async with self._session_factory() as session:
            await session.post(
                f"{self.base_url}/api/v1/sync/heartbeat",
                json=state,
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
    "NewJwt",
    "PullResponse",
    "PushResponse",
    "SyncHttpClient",
]
