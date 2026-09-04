"""test_tenancy_operador.py — REQ-X1, SC-X1 (operator tenancy pin).

Verifies that ``operador-`` JWTs are pinned to a single branch
(``claims.sucursal``) and that the FastAPI dependency
:func:`parkos_core.auth.tenancy.get_tenant_ctx` enforces the rule for
every protected endpoint.

These tests run WITHOUT a DB — they exercise the dependency's request
scoping logic directly, mirroring the pattern in
``test_jwt_issuer_guard.py``. The dependency only reads the JWT + the
optional ``X-Sucursal-Context`` header; it never touches the session.

Scenarios:

  - matching pin + matching header => TenantContext with the correct
    ``sucursal_uuid``, no exception.
  - matching pin + mismatched header => HTTPException 403
    ``unauthorized_sucursal_context``.
  - sync-agent token against an admin-only issuer guard => 401
    ``wrong_issuer`` (cross-issuer 401, the REQ-X7 / REQ-X8 invariant).
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest
from fastapi import HTTPException, Request


def _issue(issuer_prefix: str, **claims) -> str:
    """Mint a JWT via the same helper used by ``test_jwt_issuer_guard.py``."""
    from parkos_core.auth.tokens import issue_token

    return issue_token(
        subject_uuid=uuid_lib.uuid4(),
        issuer=f"{issuer_prefix}-test",
        claims=claims,
        expires_in=3600,
    )


def _build_request(token: str | None) -> Request:
    """Build a minimal FastAPI ``Request`` carrying an Authorization header.

    The ``X-Sucursal-Context`` header is NOT injected here: when we call
    :func:`get_tenant_ctx` directly (rather than through a FastAPI route)
    the ``Header(None, alias="X-Sucursal-Context")`` default does NOT get
    resolved by FastAPI's dependency machinery — it stays a ``Header``
    descriptor, not the resolved value. The tests therefore pass the
    resolved value (or ``None``) explicitly as the ``x_sucursal_context``
    kwarg, which is what the FastAPI router does internally.
    """
    headers: list[tuple[bytes, bytes]] = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/x",
            "headers": headers,
        }
    )


@pytest.mark.asyncio
async def test_operador_jwt_pinned_to_branch_succeeds_when_header_matches() -> None:
    """operador- token with matching X-Sucursal-Context => tenant context bound."""
    from parkos_core.auth.tenancy import get_tenant_ctx

    branch_uuid = uuid_lib.uuid4()
    token = _issue("operador", rol="operador", sucursal=str(branch_uuid))
    request = _build_request(token)

    ctx = await get_tenant_ctx(
        request=request,
        x_sucursal_context=str(branch_uuid),
    )
    assert ctx.issuer_prefix == "operador-"
    assert ctx.sucursal_uuid == branch_uuid
    assert str(ctx.sucursal_uuid) == str(branch_uuid)


@pytest.mark.asyncio
async def test_operador_jwt_pinned_to_branch_succeeds_without_header() -> None:
    """operador- token alone (no header) => tenant context bound to JWT claim."""
    from parkos_core.auth.tenancy import get_tenant_ctx

    branch_uuid = uuid_lib.uuid4()
    token = _issue("operador", rol="operador", sucursal=str(branch_uuid))
    request = _build_request(token)

    ctx = await get_tenant_ctx(request=request, x_sucursal_context=None)
    assert ctx.issuer_prefix == "operador-"
    assert ctx.sucursal_uuid == branch_uuid


@pytest.mark.asyncio
async def test_operador_jwt_header_mismatch_returns_403() -> None:
    """operador- token + X-Sucursal-Context pointing at a DIFFERENT branch => 403."""
    from parkos_core.auth.tenancy import get_tenant_ctx

    branch_x = uuid_lib.uuid4()
    branch_y = uuid_lib.uuid4()
    assert branch_x != branch_y

    token = _issue("operador", rol="operador", sucursal=str(branch_x))
    request = _build_request(token)

    with pytest.raises(HTTPException) as exc:
        await get_tenant_ctx(
            request=request,
            x_sucursal_context=str(branch_y),
        )
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "unauthorized_sucursal_context"


@pytest.mark.asyncio
async def test_operador_jwt_missing_sucursal_claim_returns_401() -> None:
    """operador- token without a ``sucursal`` claim => 401 (the JWT is unusable)."""
    from parkos_core.auth.tenancy import get_tenant_ctx

    # Missing the ``sucursal`` claim entirely; the dependency MUST refuse.
    token = _issue("operador", rol="operador")  # no sucursal claim
    request = _build_request(token)

    with pytest.raises(HTTPException) as exc:
        await get_tenant_ctx(request=request, x_sucursal_context=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_cross_issuer_returns_401() -> None:
    """sync-agent- token against an admin- issuer guard => 401 wrong_issuer.

    Three-issuer separation is enforced by
    :func:`parkos_core.auth.jwt_issuer_guard.requires_issuer`. A
    ``sync-agent-`` token has the wrong ``iss`` prefix for an
    ``admin-`` only route and MUST be rejected with 401 ``wrong_issuer``
    — never ``wrong_issuer`` widening to a wider scope.
    """
    from parkos_core.auth.jwt_issuer_guard import requires_issuer

    dep = requires_issuer("admin-")
    token = _issue("sync-agent", scope="branch")
    request = _build_request(token)

    with pytest.raises(HTTPException) as exc:
        await dep(request)
    assert exc.value.status_code == 401
    assert exc.value.detail["error"] == "wrong_issuer"


@pytest.mark.asyncio
async def test_operador_token_against_admin_guard_returns_401() -> None:
    """operador- token against an admin-only issuer guard => 401 wrong_issuer.

    Symmetric to the sync-agent case: each issuer is locked to its own
    routes. A branch operator hitting ``/admin/...`` MUST be rejected by
    the guard before any tenant-scope check runs.
    """
    from parkos_core.auth.jwt_issuer_guard import requires_issuer

    dep = requires_issuer("admin-")
    branch_uuid = uuid_lib.uuid4()
    token = _issue("operador", rol="operador", sucursal=str(branch_uuid))
    request = _build_request(token)

    with pytest.raises(HTTPException) as exc:
        await dep(request)
    assert exc.value.status_code == 401
    assert exc.value.detail["error"] == "wrong_issuer"
