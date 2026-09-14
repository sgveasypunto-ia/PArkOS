"""test_auth_me_not_found.py — R-F1.2-10 (404 sin filtrar existencia).

When ``GET /api/v1/auth/me`` receives an absent, malformed or invalid
``operador-`` bearer token, the response MUST be ``404`` with a body
that does NOT distinguish between "token missing", "token expired",
"token manipulated", and "user no longer exists". Same response for all
four cases.

This is a security property: an attacker iterating JWTs cannot tell
whether a token's claims decode to a real user by probing the response.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid as uuid_lib
from base64 import urlsafe_b64decode, urlsafe_b64encode

import bcrypt
from parkos_core.auth.tokens import issue_token
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from tests.conftest import VFixtureFactory

ME_URL = "/api/v1/auth/me"

# Same default secret used by auth/tokens.py::_DEFAULT_DEV_SECRET.
_DEV_SECRET = b"parkos-dev-secret-do-not-use-in-prod-aaaaaaaaaaaaaaaaaaaaaaaa"


def _b64(data: bytes) -> str:
    """URL-safe base64 without padding — mirrors tokens._b64encode."""
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _forge_jwt(
    *,
    secret: bytes,
    iss: str = "operador-test",
    sub: str | None = None,
    exp: int | None = None,
    extra_claims: dict[str, object] | None = None,
) -> str:
    """Forge an HS256 JWT directly (no PyJWT dependency).

    Reproduces ``auth/tokens.py::issue_token`` byte-for-byte so we can
    craft adversarial tokens (expired, wrong-signature) without
    importing a third-party JWT lib.
    """
    now = int(time.time())
    payload: dict[str, object] = {
        "iss": iss,
        "sub": sub or str(uuid_lib.uuid4()),
        "iat": now,
        "exp": exp if exp is not None else now + 3600,
        "aud": "parkos-branch",
        "jti": str(uuid_lib.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)

    header = {
        "alg": "HS256",
        "typ": "JWT",
        "kid": f"{iss}current",
    }
    header_b64 = _b64(
        json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    )
    payload_b64 = _b64(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    )
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    signature_b64 = _b64(signature)
    return f"{header_b64}.{payload_b64}.{signature_b64}"


async def _seed_user_branch(
    pg_engine: AsyncEngine, *, email: str
) -> tuple[uuid_lib.UUID, uuid_lib.UUID]:
    password_hash = bcrypt.hashpw(
        b"Correcta123!", bcrypt.gensalt()
    ).decode("utf-8")
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal = VFixtureFactory.build(Sucursal, nombre="NotFound Branch")
        session.add(sucursal)
        await session.flush()

        user = VFixtureFactory.build(
            Usuarios, email=email, password_hash=password_hash, rol="operador"
        )
        session.add(user)
        await session.flush()

        session.add(
            VFixtureFactory.build(
                UsuariosSucursal,
                uuid_sucursal=sucursal.uuid,
                uuid_usuario=user.uuid,
            )
        )
        await session.commit()
        return (user.uuid, sucursal.uuid)


async def test_me_without_auth_header_returns_404_with_same_shape_as_invalid_token(
    client, pg_engine: AsyncEngine
) -> None:
    """All four "auth problem" cases must produce the same 404 + body shape.

    1. No ``Authorization`` header → 404.
    2. Bearer token with expired ``exp`` claim → 404.
    3. Bearer token with tampered signature → 404.
    4. (Sanity case — a valid token for a real user must NOT 404.)
    """
    email = f"notfound-{uuid_lib.uuid4().hex[:10]}@example.com"
    user_uuid, sucursal_uuid = await _seed_user_branch(pg_engine, email=email)

    # Case 1: no header.
    resp_no_header = await client.get(ME_URL)
    assert resp_no_header.status_code == 404, resp_no_header.text
    body_no_header = resp_no_header.json()
    assert "detail" in body_no_header
    # Shape must include ``not_found`` error code.
    assert body_no_header["detail"].get("error") == "not_found"

    # Case 2: expired token (expired 1 hour ago). Signed with the
    # legitimate dev secret so the SIGNATURE check passes — only ``exp``
    # fails, which is exactly what R-F1.2-10 requires us to collapse to 404.
    expired_token = _forge_jwt(
        secret=_DEV_SECRET,
        sub=str(user_uuid),
        exp=int(time.time()) - 3600,
        extra_claims={"rol": "operador", "sucursal": str(sucursal_uuid)},
    )
    resp_expired = await client.get(
        ME_URL, headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert resp_expired.status_code == 404, resp_expired.text
    body_expired = resp_expired.json()
    assert body_expired["detail"].get("error") == "not_found"

    # Case 3: manipulated signature (valid shape, wrong secret).
    bad_token = _forge_jwt(
        secret=b"definitely-the-wrong-secret-aaaaaaaaaaaaaaaaaa",
        sub=str(user_uuid),
        extra_claims={"rol": "operador", "sucursal": str(sucursal_uuid)},
    )
    resp_bad = await client.get(
        ME_URL, headers={"Authorization": f"Bearer {bad_token}"}
    )
    assert resp_bad.status_code == 404, resp_bad.text
    body_bad = resp_bad.json()
    assert body_bad["detail"].get("error") == "not_found"

    # Case 4: valid token for a real user → 200 (sanity).
    valid_token = issue_token(
        subject_uuid=user_uuid,
        issuer="operador-test",
        claims={"rol": "operador", "sucursal": str(sucursal_uuid)},
        expires_in=3600,
    )
    resp_valid = await client.get(
        ME_URL, headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert resp_valid.status_code == 200, resp_valid.text
