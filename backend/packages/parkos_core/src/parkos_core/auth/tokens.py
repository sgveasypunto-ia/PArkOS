"""Token issue/verify (PR1b HS256 dev mode, PR7 RS256 + JWKS).

PR1b uses HMAC-SHA256 with a shared secret for simplicity in local + CI.
PR7 swaps to RS256 with proper key rotation (AGENTS.md "JWT (three issuers)").
The grace rotation window (``JWT_OVERLAP_HOURS=24``) is plumbed in but only
applies to RS256 (where two public keys can coexist during rotation).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid as uuid_lib
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Any

logger = logging.getLogger(__name__)

ISSUER_PREFIXES = ("admin-", "operador-", "sync-agent-")
JWT_OVERLAP_HOURS = 24

# Dev secret; replaced by RS256 private key in PR7.
_DEFAULT_DEV_SECRET = b"parkos-dev-secret-do-not-use-in-prod-aaaaaaaaaaaaaaaaaaaaaaaa"


def _get_secret() -> bytes:
    """Read the JWT signing key from ``PARKOS_JWT_KEY_PATH`` or dev default.

    For HS256 dev mode the secret is the raw file bytes. For RS256 prod mode
    (PR7) this function returns the PEM-encoded private key.
    """
    path = os.environ.get("PARKOS_JWT_KEY_PATH")
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return _DEFAULT_DEV_SECRET


class JWTIssuerPrefixError(Exception):
    """Token's ``iss`` claim does not start with a known prefix."""


class JWTValidationError(Exception):
    """Token failed validation (signature, format, expiry, etc.)."""


def _b64encode(data: bytes) -> str:
    """URL-safe base64 without padding."""
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    """URL-safe base64 with auto-padding restore."""
    padding = "=" * (-len(data) % 4)
    return urlsafe_b64decode(data + padding)


def issue_token(
    *,
    subject_uuid: uuid_lib.UUID,
    issuer: str,
    claims: dict[str, Any] | None = None,
    expires_in: int = 3600,
) -> str:
    """Issue a JWT signed with HS256 (dev mode).

    Args:
        subject_uuid: ``sub`` claim — the actor's uuid.
        issuer: ``iss`` claim. MUST start with one of ``ISSUER_PREFIXES``.
        claims: Additional claims to embed (e.g. ``rol``, ``sucursales_permitidas``).
        expires_in: TTL in seconds (default 1 hour).

    Returns:
        Encoded JWT string.
    """
    if not any(issuer.startswith(prefix) for prefix in ISSUER_PREFIXES):
        raise JWTIssuerPrefixError(
            f"issuer={issuer!r} must start with one of {ISSUER_PREFIXES}"
        )

    now = int(time.time())
    payload = {
        "iss": issuer,
        "sub": str(subject_uuid),
        "iat": now,
        "exp": now + expires_in,
        "aud": _audience_for(issuer),
        "jti": str(uuid_lib.uuid4()),
    }
    if claims:
        payload.update(claims)

    header = {"alg": "HS256", "typ": "JWT", "kid": f"{issuer}{_kid_suffix(issuer)}"}
    header_b64 = _b64encode(json.dumps(header, sort_keys=True, separators=(",", ":")).encode())
    payload_b64 = _b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(_get_secret(), signing_input, hashlib.sha256).digest()
    signature_b64 = _b64encode(signature)
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def verify_token(token: str) -> dict[str, Any]:
    """Verify a JWT's signature and decode its claims.

    Returns the claims dict. Raises :class:`JWTValidationError` on any failure.
    """
    if not isinstance(token, str) or token.count(".") != 2:
        raise JWTValidationError("malformed_token")
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected = hmac.new(_get_secret(), signing_input, hashlib.sha256).digest()
        actual = _b64decode(signature_b64)
        if not hmac.compare_digest(expected, actual):
            raise JWTValidationError("signature_mismatch")

        header = json.loads(_b64decode(header_b64))
        payload = json.loads(_b64decode(payload_b64))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise JWTValidationError(f"decode_error: {e}") from e

    # Validate expiry
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        raise JWTValidationError("expired_token")

    # Validate issuer prefix
    iss = payload.get("iss", "")
    if not any(iss.startswith(prefix) for prefix in ISSUER_PREFIXES):
        raise JWTIssuerPrefixError(f"unknown_issuer={iss!r}")

    # Validate kid prefix matches iss prefix
    kid = header.get("kid", "")
    expected_prefix = iss.split("-")[0] + "-" if "-" in iss else ""
    if not kid.startswith(expected_prefix):
        raise JWTValidationError(f"kid_prefix_mismatch: kid={kid} iss={iss}")

    return payload


def _audience_for(issuer: str) -> str:
    """Return the audience string for a given issuer prefix."""
    if issuer.startswith("admin-"):
        return "parkos-admin"
    if issuer.startswith("operador-"):
        return "parkos-branch"
    if issuer.startswith("sync-agent-"):
        return "parkos-sync"
    return "parkos-unknown"


def _kid_suffix(issuer: str) -> str:
    """Return a short suffix for ``kid`` to disambiguate active/prior keys.

    PR1b HS256 dev mode uses ``kid="admin-current"`` etc. (single key).
    PR7 RS256 with rotation will append ``-prior-<n>`` for the previous key
    so verifiers can accept both during the overlap window.
    """
    return "current"


__all__ = [
    "ISSUER_PREFIXES",
    "JWT_OVERLAP_HOURS",
    "JWTIssuerPrefixError",
    "JWTValidationError",
    "issue_token",
    "verify_token",
]