"""test_tenancy_admin.py — REQ-X2 (admin scope filtering + tenancy rules).

Verifies that ``admin-`` JWTs carry a ``sucursales_permitidas`` claim that
(i) drives every query through :func:`parkos_core.db.tenancy.apply_admin_scope`
and (ii) is enforced at the request layer by
:func:`parkos_core.auth.tenancy.get_tenant_ctx`.

These tests run WITHOUT a DB — they exercise the dependency's request
scoping logic directly. They mirror the pattern in
``test_admin_views_scope.py`` (T-PR10-06) which already covers the SQL
composition of ``apply_admin_scope``; this file extends coverage to the
HTTP + dependency surface that ``apply_admin_scope`` plugs into.

Failure semantics under REQ-X2:

  - ``apply_admin_scope`` with empty / missing ``sucursales_permitidas`` =>
    ``WHERE FALSE`` (fail closed). An admin with no branches sees nothing,
    never everything.
  - ``get_tenant_ctx`` with no ``X-Sucursal-Context`` =>
    ``HTTPException 400`` ``missing_sucursal_context``.
  - ``get_tenant_ctx`` with header uuid not in ``sucursales_permitidas`` =>
    ``HTTPException 403`` ``unauthorized_sucursal_context``.
  - ``get_tenant_ctx`` with header uuid in ``sucursales_permitidas`` =>
    returns a ``TenantContext`` with ``sucursal_uuid=header_uuid``.
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest
from fastapi import HTTPException, Request
from parkos_core.models.V.sucursal import Sucursal
from sqlalchemy import select

# ---------------------------------------------------------------------------
# Helpers — keep parity with test_jwt_issuer_guard.py + test_pairing_endpoints.py.
# ---------------------------------------------------------------------------

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

    The ``X-Sucursal-Context`` header is NOT injected here; the tests
    pass the resolved value (or ``None``) explicitly as the kwarg, see
    the comment block in ``test_tenancy_operador.py`` for why.
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


# ---------------------------------------------------------------------------
# ``apply_admin_scope`` SQL composition (REQ-X2, defense in depth).
# ---------------------------------------------------------------------------

class TestApplyAdminScopeFiltersResults:
    """Confirm the helper narrows every query to ``claims.sucursales_permitidas``.

    Pure-SQL composition tests, no DB required. The helper is the
    single source of truth for admin scope (T-PR10-04), and these
    checks exercise the same paths that ``admin_views.py`` relies on
    for ``GET /sucursales`` and ``GET /admin/me``.
    """

    def test_apply_admin_scope_is_callable(self) -> None:
        from parkos_core.db.tenancy import apply_admin_scope

        assert callable(apply_admin_scope)

    def test_apply_admin_scope_filters_to_permitidas(self) -> None:
        """Permitidas set is bound to the WHERE clause."""
        from parkos_core.db.tenancy import apply_admin_scope

        permitidas = [
            uuid_lib.UUID("00000000-0000-0000-0000-000000000a01"),
            uuid_lib.UUID("00000000-0000-0000-0000-000000000a02"),
        ]
        claims = {"sucursales_permitidas": [str(u) for u in permitidas]}
        stmt = apply_admin_scope(None, select(Sucursal), claims)
        rendered = str(
            stmt.compile(compile_kwargs={"literal_binds": True})
        )
        for u in permitidas:
            assert u.hex in rendered
        # A different uuid MUST NOT be in the rendered filter.
        stranger = uuid_lib.UUID("00000000-0000-0000-0000-000000000bff")
        assert stranger.hex not in rendered

    def test_apply_admin_scope_empty_permitidas_fails_closed(self) -> None:
        """Empty permitidas => ``WHERE FALSE`` (admin sees nothing)."""
        from parkos_core.db.tenancy import apply_admin_scope

        stmt = apply_admin_scope(
            None,
            select(Sucursal),
            {"sucursales_permitidas": []},
        )
        rendered = str(
            stmt.compile(compile_kwargs={"literal_binds": True})
        )
        assert "FALSE" in rendered

    def test_apply_admin_scope_missing_claim_fails_closed(self) -> None:
        """No ``sucursales_permitidas`` at all => ``WHERE FALSE``."""
        from parkos_core.db.tenancy import apply_admin_scope

        stmt = apply_admin_scope(None, select(Sucursal), {})
        rendered = str(
            stmt.compile(compile_kwargs={"literal_binds": True})
        )
        assert "FALSE" in rendered

    def test_extract_drops_malformed_entries(self) -> None:
        """Bad claim entries are dropped, NOT widened."""
        from parkos_core.db.tenancy import extract_sucursales_permitidas

        good = uuid_lib.UUID("00000000-0000-0000-0000-000000000a01")
        out = extract_sucursales_permitidas(
            {"sucursales_permitidas": [str(good), "not-a-uuid", None, 42]}
        )
        assert out == [good]


# ---------------------------------------------------------------------------
# ``get_tenant_ctx`` for the admin- flow (REQ-X2: header is mandatory).
# ---------------------------------------------------------------------------

class TestAdminTenantDependency:
    """Verify the request-layer enforcement of ``sucursales_permitidas``.

    These tests do NOT touch the DB — they exercise
    :func:`parkos_core.auth.tenancy.get_tenant_ctx` directly via the
    same mock-Request pattern as ``test_tenancy_operador.py``.
    """

    @pytest.mark.asyncio
    async def test_missing_x_sucursal_context_returns_400(self) -> None:
        """admin- token without ``X-Sucursal-Context`` => 400 missing_sucursal_context."""
        from parkos_core.auth.tenancy import get_tenant_ctx

        permitidas = [uuid_lib.uuid4()]
        token = _issue(
            "admin",
            rol="admin",
            sucursales_permitidas=[str(u) for u in permitidas],
        )
        request = _build_request(token)

        with pytest.raises(HTTPException) as exc:
            await get_tenant_ctx(request=request, x_sucursal_context=None)
        assert exc.value.status_code == 400
        assert exc.value.detail["error"] == "missing_sucursal_context"

    @pytest.mark.asyncio
    async def test_header_not_in_permitidas_returns_403(self) -> None:
        """admin- token whose header uuid is NOT in permitidas => 403 unauthorized."""
        from parkos_core.auth.tenancy import get_tenant_ctx

        allowed = uuid_lib.UUID("00000000-0000-0000-0000-000000000a01")
        forbidden = uuid_lib.UUID("00000000-0000-0000-0000-000000000bff")
        token = _issue(
            "admin",
            rol="admin",
            sucursales_permitidas=[str(allowed)],
        )
        request = _build_request(token)

        with pytest.raises(HTTPException) as exc:
            await get_tenant_ctx(
                request=request,
                x_sucursal_context=str(forbidden),
            )
        assert exc.value.status_code == 403
        assert exc.value.detail["error"] == "unauthorized_sucursal_context"

    @pytest.mark.asyncio
    async def test_header_in_permitidas_succeeds(self) -> None:
        """admin- token whose header IS in permitidas => TenantContext bound."""
        from parkos_core.auth.tenancy import get_tenant_ctx

        allowed = uuid_lib.UUID("00000000-0000-0000-0000-000000000a01")
        token = _issue(
            "admin",
            rol="admin",
            sucursales_permitidas=[str(allowed)],
        )
        request = _build_request(token)

        ctx = await get_tenant_ctx(
            request=request,
            x_sucursal_context=str(allowed),
        )
        assert ctx.issuer_prefix == "admin-"
        assert ctx.sucursal_uuid == allowed

    @pytest.mark.asyncio
    async def test_admin_token_with_no_permitidas_returns_403(self) -> None:
        """admin- token with empty permitidas + any header => 403 (fail closed)."""
        from parkos_core.auth.tenancy import get_tenant_ctx

        some_uuid = uuid_lib.UUID("00000000-0000-0000-0000-000000000a01")
        token = _issue(
            "admin",
            rol="admin",
            sucursales_permitidas=[],  # empty
        )
        request = _build_request(token)

        with pytest.raises(HTTPException) as exc:
            await get_tenant_ctx(
                request=request,
                x_sucursal_context=str(some_uuid),
            )
        assert exc.value.status_code == 403
        assert exc.value.detail["error"] == "unauthorized_sucursal_context"

    @pytest.mark.asyncio
    async def test_cross_issuer_sync_token_against_admin_dep_returns_401(self) -> None:
        """sync-agent- token against admin ``requires_issuer`` => 401 wrong_issuer."""
        from parkos_core.auth.jwt_issuer_guard import requires_issuer

        dep = requires_issuer("admin-")
        token = _issue("sync-agent", scope="cloud")
        request = _build_request(token)

        with pytest.raises(HTTPException) as exc:
            await dep(request)
        assert exc.value.status_code == 401
        assert exc.value.detail["error"] == "wrong_issuer"
