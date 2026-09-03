"""Tests for ``GET /sucursal/{uuid}/pairing-token`` endpoint (REQ-OP-15).

Cloud-only endpoint (issuer ``admin-``). Mints a 24h single-use JWT that the
branch operator redeems at ``POST /sync/pair`` (PR8) for a long-lived
``sync-agent-`` JWT.

Per PR4 acceptance:
  curl -X GET .../sucursal/{uuid}/pairing-token -H 'Authorization: Bearer $ADMIN_JWT' -> 200
  curl -X GET .../sucursal/{uuid}/pairing-token -H 'Authorization: Bearer $OPERADOR_JWT' -> 401

Per the PR3 plan, this PR ships unit tests on the token issuance/verify path
(no DB). The integration test against a live server lands in PR8.
"""
from __future__ import annotations

import asyncio
import time
import uuid as uuid_lib

import pytest
from fastapi import HTTPException
from parkos_core.api.deps import requires_issuer
from parkos_core.auth.tokens import (
    ISSUER_PREFIXES,
    JWTIssuerPrefixError,
    issue_token,
    verify_token,
)
from starlette.requests import Request

SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000099")
PAIRING_PATH = (
    f"/api/v1/sucursal/{SUCURSAL_UUID}/pairing-token"
)


def _build_request(token: str | None) -> Request:
    """Build a minimal Starlette ``Request`` carrying the Authorization header.

    ``requires_issuer`` reads the token from
    ``request.headers.get('authorization')``, so the rest of the ASGI scope
    is irrelevant — we only need ``type=http`` plus the header list.
    """
    headers: list[tuple[bytes, bytes]] = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode("ascii")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": PAIRING_PATH,
        "headers": headers,
    }
    return Request(scope)


class TestPairingTokenIssuance:
    """``issue_token`` with pairing-specific args produces a 24h single-use token."""

    def _issue_pairing(
        self,
        subject_uuid: uuid_lib.UUID = SUCURSAL_UUID,
        ttl: int = 86400,
    ) -> str:
        """Replicate the endpoint's token mint logic exactly."""
        return issue_token(
            subject_uuid=subject_uuid,
            issuer="admin-cloud-pairing",
            claims={
                "purpose": "pairing",
                "single_use": True,
                "uuid_sucursal": str(subject_uuid),
            },
            expires_in=ttl,
        )

    def test_token_decodes(self):
        """Issued token verifies and yields the expected claims."""
        token = self._issue_pairing()
        claims = verify_token(token)
        assert claims["iss"] == "admin-cloud-pairing"
        assert claims["sub"] == str(SUCURSAL_UUID)
        assert claims["purpose"] == "pairing"
        assert claims["single_use"] is True
        assert claims["uuid_sucursal"] == str(SUCURSAL_UUID)

    def test_token_has_24h_ttl(self):
        """``exp - iat`` MUST be exactly 86400 (24 hours)."""
        before = int(time.time())
        token = self._issue_pairing()
        after = int(time.time())
        claims = verify_token(token)
        assert before <= claims["iat"] <= after
        assert claims["exp"] - claims["iat"] == 86400

    def test_token_issuer_prefix_matches_admin(self):
        """``admin-cloud-pairing`` starts with ``admin-`` → satisfies ``ISSUER_PREFIXES`` check."""
        token = self._issue_pairing()
        claims = verify_token(token)
        assert any(claims["iss"].startswith(p) for p in ISSUER_PREFIXES)
        assert claims["iss"].startswith("admin-")

    def test_token_audience_is_parkos_admin(self):
        """Admin-prefixed issuers get ``aud=parkos-admin`` per ``_audience_for``."""
        token = self._issue_pairing()
        claims = verify_token(token)
        assert claims["aud"] == "parkos-admin"

    def test_token_has_jti(self):
        """Every issued token carries a ``jti`` (used by the PR8 single-use gate)."""
        token = self._issue_pairing()
        claims = verify_token(token)
        assert "jti" in claims
        # UUID-shaped string.
        uuid_lib.UUID(claims["jti"])

    def test_rejects_non_admin_prefix_issuer(self):
        """Issuer missing a known prefix is rejected at mint time."""
        with pytest.raises(JWTIssuerPrefixError):
            issue_token(
                subject_uuid=SUCURSAL_UUID,
                issuer="rogue-pairing",
                claims={"purpose": "pairing"},
                expires_in=86400,
            )

    def test_token_for_different_sucursal(self):
        """Each pairing token is tied to its own sucursal UUID via ``sub`` and ``uuid_sucursal``."""
        other = uuid_lib.UUID("00000000-0000-0000-0000-000000000fff")
        token = self._issue_pairing(subject_uuid=other)
        claims = verify_token(token)
        assert claims["sub"] == str(other)
        assert claims["uuid_sucursal"] == str(other)

    def test_short_ttl_works(self):
        """Smaller TTLs are honored (sanity check for the ttl parameter)."""
        token = self._issue_pairing(ttl=60)
        claims = verify_token(token)
        assert claims["exp"] - claims["iat"] == 60


class TestPairingEndpointIssuerGuard:
    """``requires_issuer('admin-')`` rejects ``operador-`` and ``sync-agent-`` claims."""

    def _dep(self):
        """Mirror the ``_pairing_issuer_dep`` construction in ``api/v1/sucursal.py``."""
        return requires_issuer("admin-")

    def test_admin_passes(self):
        """Admin issuer passes the guard (no HTTPException raised)."""
        dep = self._dep()
        token = issue_token(
            subject_uuid=uuid_lib.uuid4(),
            issuer="admin-cloud-001",
            expires_in=3600,
        )
        request = _build_request(token)
        # The dep is async — call it directly. Success = no HTTPException.
        asyncio.run(dep(request))

    def test_operador_rejected(self):
        """Operador issuer rejected (cloud-only — 401 per the actual guard)."""
        dep = self._dep()
        token = issue_token(
            subject_uuid=uuid_lib.uuid4(),
            issuer="operador-cloud-001",
            expires_in=3600,
        )
        request = _build_request(token)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(dep(request))
        assert exc_info.value.status_code == 401

    def test_sync_agent_rejected(self):
        """Sync-agent issuer rejected (cloud-only — 401 per the actual guard)."""
        dep = self._dep()
        token = issue_token(
            subject_uuid=uuid_lib.uuid4(),
            issuer="sync-agent-cloud-001",
            expires_in=3600,
        )
        request = _build_request(token)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(dep(request))
        assert exc_info.value.status_code == 401

    def test_missing_token_rejected(self):
        """No Authorization header → 401."""
        dep = self._dep()
        request = _build_request(None)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(dep(request))
        assert exc_info.value.status_code == 401