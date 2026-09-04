"""JWT three-issuer verification (design §7).

The three issuers (``admin-``, ``operador-``, ``sync-agent-``) are mutually
exclusive. The same code path that rejects ``operador-`` on admin routes also
rejects ``admin-`` on sync routes — there is no implicit hierarchy.

PR1b uses HS256 with a shared secret (loaded from ``PARKOS_JWT_KEY_PATH`` or
a static dev default). Production RS256 + JWKS lands in PR7.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request

from .tokens import JWTIssuerPrefixError, JWTValidationError, verify_token

logger = logging.getLogger(__name__)

ISSUER_PREFIXES = ("admin-", "operador-", "sync-agent-")


class InvalidTokenError(HTTPException):
    """401: token is malformed, expired, signature invalid, or missing."""

    def __init__(self, detail: str = "invalid_token") -> None:
        super().__init__(
            status_code=401,
            detail={"error": "invalid_token", "detail": detail},
        )


class CrossIssuerError(HTTPException):
    """401: token's issuer prefix doesn't match the route's required issuer."""

    def __init__(self, detail: str = "wrong_issuer") -> None:
        super().__init__(
            status_code=401,
            detail={"error": "wrong_issuer", "detail": detail},
        )


async def verify_jwt(request: Request) -> dict[str, Any]:
    """Verify the bearer token and return its claims.

    Caches the decoded claims on ``request.state.jwt_claims`` so downstream
    dependencies (``get_tenant_ctx``, ``require_permission``) don't re-decode.

    All JWT validation failures surface as ``InvalidTokenError`` (401)
    instead of leaking an unhandled exception that FastAPI's default
    handler would convert to 500. Maps to:

    - ``JWTValidationError`` (malformed, expired, bad signature, kid mismatch)
      → ``InvalidTokenError`` (401 ``invalid_token``)
    - ``JWTIssuerPrefixError`` (iss prefix not in canonical set) →
      ``CrossIssuerError`` (401 ``wrong_issuer``) so route-level
      ``requires_issuer(...)`` calls return a meaningful error code
    - Any other ``Exception`` (defense in depth — base64 decoding, JSON
      parsing, unexpected module errors) → ``InvalidTokenError`` (401)
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise InvalidTokenError("missing_bearer_token")
    token = auth[7:].strip()
    if not token:
        raise InvalidTokenError("empty_bearer_token")

    try:
        claims = verify_token(token)
    except JWTIssuerPrefixError as e:
        raise CrossIssuerError(str(e)) from e
    except JWTValidationError as e:
        raise InvalidTokenError(str(e)) from e
    except (ValueError, TypeError) as e:
        # base64 decode failures, type coercion, JSON edge cases —
        # surfaced by ``tokens.verify_token`` internals. Still a
        # client-side token problem → 401, not 500.
        raise InvalidTokenError(f"decode_error: {e}") from e
    except Exception as e:  # pragma: no cover -- defense-in-depth
        # Catch-all so uncaught token-decoding bugs surface as 401
        # instead of 500. Logged so the bug isn't invisible.
        logger.exception("Unexpected JWT verification error")
        raise InvalidTokenError("invalid_token") from e

    iss = claims.get("iss", "")
    prefix = iss.split("-")[0] + "-" if "-" in iss else ""
    if prefix not in ISSUER_PREFIXES:
        raise CrossIssuerError(f"unknown_issuer_prefix={prefix}")

    request.state.jwt_claims = claims
    return claims


def requires_issuer(*allowed: str):
    """FastAPI dependency factory. Accepts one or more issuer prefixes.

    Returns a dependency that 401s if the token's issuer is not in ``allowed``.

    Usage:
        @router.get(..., dependencies=[Depends(requires_issuer("admin-"))])
    """
    allowed_set = frozenset(allowed)

    async def _dep(request: Request) -> dict[str, Any]:
        claims = await verify_jwt(request)
        iss = claims.get("iss", "")
        prefix = iss.split("-")[0] + "-" if "-" in iss else ""
        if prefix not in allowed_set:
            raise CrossIssuerError(
                f"issuer={prefix} not in allowed={sorted(allowed_set)}"
            )
        return claims

    return _dep


__all__ = [
    "ISSUER_PREFIXES",
    "InvalidTokenError",
    "CrossIssuerError",
    "verify_jwt",
    "requires_issuer",
]