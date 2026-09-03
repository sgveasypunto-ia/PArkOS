"""Factus provider adapter (T-PR11-04).

``FactusProvider`` is one concrete adapter implementing the
``DianProvider`` ABC. Provider swap is a future operator concern, so
the HTTP quirks stay isolated from the dispatcher's state machine
(adapter pattern).

Endpoints (per Factus docs):

- ``POST {base_url}/api/ubl2.1`` — send UBL → returns ``trackId``.
- ``GET {base_url}/api/ubl2.1/{trackId}`` — poll → returns
  ``{estado, cufe, ...}``.
- ``POST {base_url}/api/revocacion`` — send revocation XML → returns
  ``trackId``.

Auth is a Bearer token read from ``PARKOS_DIAN_PROVIDER_TOKEN_PATH`` on
every call, so a token rotation on disk is picked up without a process
restart.

Issuer: cloud-only (module-level import guard below).
"""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

# Module-level import guard (T-PR11-07 — DIAN boundary layer 2).
if os.environ.get("PARKOS_DEPLOY", "cloud").lower() == "branch":
    raise ImportError(
        "dian_cloud_unavailable_on_branch (T-PR11-07, Factus adapter, REQ-X3)"
    )

_XML_CONTENT_TYPE = "application/xml"


@dataclass
class PollResult:
    """Response from :meth:`DianProvider.poll`.

    ``estado`` is the provider-reported document state:
    ``'aceptado' | 'rechazado' | 'en_proceso' | 'error' | 'timeout'``.
    ``en_proceso`` means the caller should poll again.
    """

    estado: str
    cufe: str | None = None
    motivo_rechazo: str | None = None


class DianProvider:
    """ABC for DIAN provider adapters (interface contract)."""

    async def send_ubl(self, xml_bytes: bytes) -> str:
        """Send UBL XML → returns the provider-side ``trackId``."""
        raise NotImplementedError

    async def poll(self, track_id: str) -> PollResult:
        """Poll for the document state. ``en_proceso`` means try again."""
        raise NotImplementedError

    async def send_revocacion(self, xml_bytes: bytes) -> str:
        """Send revocation XML → returns the provider-side ``trackId``."""
        raise NotImplementedError


class FactusProvider(DianProvider):
    """Factus adapter (per Factus documentation; pending real API contract).

    Args:
        base_url: ``PARKOS_DIAN_PROVIDER_URL``. Trailing slash tolerated.
        token_path: ``PARKOS_DIAN_PROVIDER_TOKEN_PATH`` — file holding
            the Bearer token.
        timeout_s: Per-request timeout. The dispatcher owns the overall
            poll budget (``PARKOS_DIAN_TIMEOUT_S``).
        session_factory: Injection seam for ``httpx.MockTransport`` in
            tests (T-PR11-14). Must return a fresh ``AsyncClient``.
    """

    def __init__(
        self,
        *,
        base_url: str,
        token_path: Path,
        timeout_s: float = 30.0,
        session_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token_path = token_path
        self.timeout_s = timeout_s
        self._session_factory: Callable[[], httpx.AsyncClient] = (
            session_factory or self._default_session_factory
        )

    def _default_session_factory(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_s))

    def _read_token(self) -> str:
        """Read the Bearer token from disk on every call (rotation-safe)."""
        return self.token_path.read_text(encoding="utf-8").strip()

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._read_token()}"}

    async def send_ubl(self, xml_bytes: bytes) -> str:
        """``POST /api/ubl2.1`` with the UBL XML body. Returns the ``trackId``."""
        async with self._session_factory() as session:
            response = await session.post(
                f"{self.base_url}/api/ubl2.1",
                content=xml_bytes,
                headers={**self._auth_headers(), "Content-Type": _XML_CONTENT_TYPE},
            )
        response.raise_for_status()
        return str(response.json()["trackId"])

    async def poll(self, track_id: str) -> PollResult:
        """``GET /api/ubl2.1/{trackId}``.

        State machine:

        - ``aceptado`` → CUFE assigned.
        - ``rechazado`` → motive in body.
        - ``en_proceso`` → caller retries.
        """
        async with self._session_factory() as session:
            response = await session.get(
                f"{self.base_url}/api/ubl2.1/{track_id}",
                headers=self._auth_headers(),
            )
        response.raise_for_status()
        body = response.json()
        return PollResult(
            estado=str(body["estado"]),
            cufe=body.get("cufe"),
            motivo_rechazo=body.get("motivo_rechazo"),
        )

    async def send_revocacion(self, xml_bytes: bytes) -> str:
        """``POST /api/revocacion``. Returns the ``trackId``."""
        async with self._session_factory() as session:
            response = await session.post(
                f"{self.base_url}/api/revocacion",
                content=xml_bytes,
                headers={**self._auth_headers(), "Content-Type": _XML_CONTENT_TYPE},
            )
        response.raise_for_status()
        return str(response.json()["trackId"])


__all__ = ["DianProvider", "FactusProvider", "PollResult"]
