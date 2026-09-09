"""test_jwt_issuer_guard.py — REQ-X7, REQ-X8.

Unit tests for the three-issuer JWT enforcement. The three issuers are
mutually exclusive:

  - ``admin-``     → admin scope
  - ``operador-``  → branch operator scope (pinned to one branch)
  - ``sync-agent-``→ sync worker scope (branch or cloud)

The guard returns 401 on a cross-issuer token (a token whose
``iss`` prefix is not in the route's allowed list).

These tests run WITHOUT a DB — they exercise only the in-process token
verification (``auth.tokens.verify_token`` and
``auth.jwt_issuer_guard.requires_issuer``).
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest


def _issue(issuer_prefix: str, **claims) -> str:
    from parkos_core.auth.tokens import issue_token

    return issue_token(
        subject_uuid=uuid_lib.uuid4(),
        issuer=f"{issuer_prefix}-test",
        claims=claims,
        expires_in=3600,
    )


def _tamper_signature(token: str) -> str:
    """Return ``token`` with its signature segment corrupted.

    Flips a full DECODED byte of the signature rather than substituting the
    token string's last character. Base64url packs 3 bytes into 4
    characters; when the signature's byte length isn't a multiple of 3, the
    final character encodes some bits that are pure padding and get
    discarded on decode. Substituting that last character can therefore be
    a no-op — the mutated string decodes back to the SAME signature bytes
    (observed as an intermittent flake in this suite). Decoding, XOR-ing a
    real byte, and re-encoding guarantees the underlying bytes actually
    differ.
    """
    from base64 import urlsafe_b64decode, urlsafe_b64encode

    header_b64, payload_b64, sig_b64 = token.split(".")
    sig_bytes = bytearray(urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4)))
    sig_bytes[0] ^= 0xFF
    tampered_sig = urlsafe_b64encode(bytes(sig_bytes)).rstrip(b"=").decode("ascii")
    return f"{header_b64}.{payload_b64}.{tampered_sig}"


# ---------------------------------------------------------------------------
# ``verify_token`` direct tests
# ---------------------------------------------------------------------------

def test_verify_token_accepts_admin_token() -> None:
    """``verify_token`` returns claims for a well-formed ``admin-`` token."""
    from parkos_core.auth.tokens import verify_token

    token = _issue("admin", rol="admin", sucursales_permitidas=[str(uuid_lib.uuid4())])
    claims = verify_token(token)
    assert claims["iss"].startswith("admin-")
    assert claims["rol"] == "admin"


def test_verify_token_accepts_operador_token() -> None:
    """``verify_token`` returns claims for a well-formed ``operador-`` token."""
    from parkos_core.auth.tokens import verify_token

    token = _issue("operador", rol="operador", sucursal=str(uuid_lib.uuid4()))
    claims = verify_token(token)
    assert claims["iss"].startswith("operador-")


def test_verify_token_accepts_sync_agent_token() -> None:
    """``verify_token`` returns claims for a well-formed ``sync-agent-`` token."""
    from parkos_core.auth.tokens import verify_token

    token = _issue("sync-agent", scope="cloud")
    claims = verify_token(token)
    assert claims["iss"].startswith("sync-agent-")


def test_issue_token_rejects_unknown_issuer_prefix() -> None:
    """``issue_token`` rejects unknown issuer prefixes up front (validation fails before signing).

    The helper refuses to mint a JWT with an unknown ``iss`` prefix
    because downstream verifiers will reject it anyway. PR1c verifies
    the defensive gate here.
    """
    from parkos_core.auth.tokens import JWTIssuerPrefixError, issue_token

    with pytest.raises(JWTIssuerPrefixError):
        issue_token(
            subject_uuid=uuid_lib.uuid4(),
            issuer="rogue-prefix",  # not in ISSUER_PREFIXES
            expires_in=3600,
        )


def test_verify_token_rejects_tampered_signature() -> None:
    """Mutating the signature segment yields ``JWTValidationError``."""
    from parkos_core.auth.tokens import JWTValidationError, verify_token

    token = _issue("admin", rol="admin")
    tampered = _tamper_signature(token)
    with pytest.raises(JWTValidationError):
        verify_token(tampered)


def test_verify_token_rejects_expired() -> None:
    """An expired token raises ``JWTValidationError``."""
    from parkos_core.auth.tokens import JWTValidationError, issue_token, verify_token

    token = issue_token(
        subject_uuid=uuid_lib.uuid4(),
        issuer="admin-test",
        expires_in=-10,  # already expired
    )
    with pytest.raises(JWTValidationError):
        verify_token(token)


def test_verify_token_rejects_malformed_token() -> None:
    """A non-JWT string raises ``JWTValidationError``."""
    from parkos_core.auth.tokens import JWTValidationError, verify_token

    with pytest.raises(JWTValidationError):
        verify_token("not.a.valid.jwt")


# ---------------------------------------------------------------------------
# ``requires_issuer`` factory tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_requires_issuer_accepts_matching_prefix() -> None:
    """A token whose issuer matches the allowed prefix returns its claims."""
    from fastapi import Request
    from parkos_core.auth.jwt_issuer_guard import requires_issuer

    dep = requires_issuer("admin-")
    token = _issue("admin", rol="admin", sucursales_permitidas=[str(uuid_lib.uuid4())])

    request = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/x",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )
    claims = await dep(request)
    assert claims["iss"].startswith("admin-")


@pytest.mark.asyncio
async def test_requires_issuer_rejects_cross_audience() -> None:
    """An ``operador-`` token against an admin-only route → 401 ``wrong_issuer``."""
    from fastapi import HTTPException, Request
    from parkos_core.auth.jwt_issuer_guard import requires_issuer

    dep = requires_issuer("admin-")
    token = _issue("operador", rol="operador", sucursal=str(uuid_lib.uuid4()))

    request = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/x",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )
    with pytest.raises(HTTPException) as exc:
        await dep(request)
    assert exc.value.status_code == 401
    assert exc.value.detail["error"] == "wrong_issuer"


@pytest.mark.asyncio
async def test_requires_issuer_rejects_sync_agent_on_branch_route() -> None:
    """A ``sync-agent-`` token against an operador-only route → 401 ``wrong_issuer``."""
    from fastapi import HTTPException, Request
    from parkos_core.auth.jwt_issuer_guard import requires_issuer

    dep = requires_issuer("operador-")
    token = _issue("sync-agent", scope="branch")

    request = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/x",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )
    with pytest.raises(HTTPException) as exc:
        await dep(request)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_requires_issuer_accepts_multiple_prefixes() -> None:
    """A multi-prefix dependency accepts any token in the allowed set."""
    from fastapi import Request
    from parkos_core.auth.jwt_issuer_guard import requires_issuer

    dep = requires_issuer("admin-", "operador-")

    admin_token = _issue("admin", rol="admin")
    request = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/x",
            "headers": [(b"authorization", f"Bearer {admin_token}".encode())],
        }
    )
    claims = await dep(request)
    assert claims["iss"].startswith("admin-")

    op_token = _issue("operador", sucursal=str(uuid_lib.uuid4()))
    request2 = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/x",
            "headers": [(b"authorization", f"Bearer {op_token}".encode())],
        }
    )
    claims2 = await dep(request2)
    assert claims2["iss"].startswith("operador-")


@pytest.mark.asyncio
async def test_requires_issuer_rejects_missing_bearer() -> None:
    """No Authorization header → 401 ``missing_bearer_token``."""
    from fastapi import HTTPException, Request
    from parkos_core.auth.jwt_issuer_guard import requires_issuer

    dep = requires_issuer("admin-")
    request = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/x",
            "headers": [],
        }
    )
    with pytest.raises(HTTPException) as exc:
        await dep(request)
    assert exc.value.status_code == 401
    assert exc.value.detail["error"] == "invalid_token"


# ---------------------------------------------------------------------------
# ``verify_jwt`` (the FastAPI dependency) error surface tests
#
# Pre-fix: ``verify_token`` raised ``JWTValidationError`` (malformed /
# expired / wrong-sig) which was uncaught — FastAPI's default exception
# handler surfaced it as 500. Post-fix: ``verify_jwt`` catches it and
# returns HTTP 401 ``invalid_token``. These tests pin that contract.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_jwt_returns_401_on_malformed_token() -> None:
    """A non-JWT string in the Bearer slot → 401 ``invalid_token``, NOT 500."""
    from fastapi import HTTPException, Request
    from parkos_core.auth.jwt_issuer_guard import verify_jwt

    request = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/x",
            "headers": [(b"authorization", b"Bearer not.a.valid.jwt")],
        }
    )
    with pytest.raises(HTTPException) as exc:
        await verify_jwt(request)
    assert exc.value.status_code == 401
    assert exc.value.detail["error"] == "invalid_token"


@pytest.mark.asyncio
async def test_verify_jwt_returns_401_on_empty_bearer() -> None:
    """``Authorization: Bearer `` (empty token after the prefix) → 401."""
    from fastapi import HTTPException, Request
    from parkos_core.auth.jwt_issuer_guard import verify_jwt

    request = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/x",
            "headers": [(b"authorization", b"Bearer ")],
        }
    )
    with pytest.raises(HTTPException) as exc:
        await verify_jwt(request)
    assert exc.value.status_code == 401
    assert exc.value.detail["error"] == "invalid_token"
    assert "empty" in exc.value.detail["detail"]


@pytest.mark.asyncio
async def test_verify_jwt_returns_401_on_wrong_signature() -> None:
    """A token whose signature segment was mutated → 401 ``invalid_token``."""
    from fastapi import HTTPException, Request
    from parkos_core.auth.jwt_issuer_guard import verify_jwt

    token = _issue("admin", rol="admin")
    tampered = _tamper_signature(token)
    request = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/x",
            "headers": [(b"authorization", f"Bearer {tampered}".encode())],
        }
    )
    with pytest.raises(HTTPException) as exc:
        await verify_jwt(request)
    assert exc.value.status_code == 401
    assert exc.value.detail["error"] == "invalid_token"
    # The detail should mention the specific validation failure mode
    # (``signature_mismatch``) for operability — proving the inner
    # ``JWTValidationError`` was caught and translated, not swallowed.
    assert "signature" in exc.value.detail["detail"].lower()


@pytest.mark.asyncio
async def test_verify_jwt_returns_401_on_expired_token() -> None:
    """An expired token (issued with negative TTL) → 401, not 500."""
    from fastapi import HTTPException, Request
    from parkos_core.auth.jwt_issuer_guard import verify_jwt
    from parkos_core.auth.tokens import issue_token

    expired = issue_token(
        subject_uuid=uuid_lib.uuid4(),
        issuer="admin-test",
        expires_in=-10,
    )
    request = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/x",
            "headers": [(b"authorization", f"Bearer {expired}".encode())],
        }
    )
    with pytest.raises(HTTPException) as exc:
        await verify_jwt(request)
    assert exc.value.status_code == 401
    assert exc.value.detail["error"] == "invalid_token"
    assert "expired" in exc.value.detail["detail"].lower()


@pytest.mark.asyncio
async def test_verify_jwt_returns_401_on_garbage_token() -> None:
    """Pure garbage (no dots, no base64) → 401, not 500.

    Defends against base64 decoding or JSON parsing errors leaking
    as 500 in production.
    """
    from fastapi import HTTPException, Request
    from parkos_core.auth.jwt_issuer_guard import verify_jwt

    request = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/x",
            "headers": [(b"authorization", b"Bearer !!!garbage!!!")],
        }
    )
    with pytest.raises(HTTPException) as exc:
        await verify_jwt(request)
    assert exc.value.status_code == 401
    assert exc.value.detail["error"] == "invalid_token"