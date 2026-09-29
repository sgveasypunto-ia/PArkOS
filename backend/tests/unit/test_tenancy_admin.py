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
  - ``get_tenant_ctx`` with header uuid not among the actor's open
    ``usuarios_sucursal`` rows => ``HTTPException 403``
    ``unauthorized_sucursal_context``.
  - ``get_tenant_ctx`` with header uuid among those rows => returns a
    ``TenantContext`` with ``sucursal_uuid=header_uuid``.

The scope is read FRESH from the DB, not from the ``sucursales_permitidas``
claim, which is a login-time snapshot. See
``TestAdminTenantDependency`` for both directions of that contract.
"""
from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock

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
    """Verify the request-layer enforcement of the admin branch scope.

    These tests do NOT touch the DB — they exercise
    :func:`parkos_core.auth.tenancy.get_tenant_ctx` directly via the
    same mock-Request pattern as ``test_tenancy_operador.py``.

    The scope is resolved by ``extract_sucursales_permitidas_fresh``
    (a DB read), which is stubbed here. The JWT
    ``sucursales_permitidas`` claim is a login-time snapshot and is
    deliberately NOT consulted: both directions are pinned below, so a
    future refactor cannot quietly fall back to it.
    """

    @staticmethod
    def _patch_scope(monkeypatch, permitted):
        """Stub the DB scope read to return ``permitted``."""
        from parkos_core.auth import tenancy as tenancy_mod

        stub = AsyncMock(return_value=list(permitted))
        monkeypatch.setattr(
            tenancy_mod, "extract_sucursales_permitidas_fresh", stub, raising=True
        )
        return stub

    @pytest.mark.asyncio
    async def test_missing_x_sucursal_context_returns_global_mode(
        self, monkeypatch
    ) -> None:
        """admin- token without ``X-Sucursal-Context`` => global mode (sucursal_uuid=None).

        Global endpoints (``/empresa/empresa``, ``/catalogos/*``) don't need a
        branch selected, so the header is optional. The request runs without a
        tenant filter. Endpoints that DO require a branch use
        ``requires_sucursal`` (tested separately) to raise 400.
        """
        from parkos_core.auth.tenancy import get_tenant_ctx
        
        permitidas = [uuid_lib.uuid4()]
        token = _issue(
            "admin",
            rol="admin",
            sucursales_permitidas=[str(u) for u in permitidas],
        )
        request = _build_request(token)
        self._patch_scope(monkeypatch, permitidas)
        
        ctx = await get_tenant_ctx(
            request=request,
            x_sucursal_context=None,
            session=AsyncMock(),
        )
        
        assert ctx.sucursal_uuid is None
        assert ctx.actor_rol == "admin"

    @pytest.mark.asyncio
    async def test_header_not_in_permitidas_returns_403(
        self, monkeypatch
    ) -> None:
        """Header uuid absent from the DB assignments => 403 unauthorized."""
        from parkos_core.auth.tenancy import get_tenant_ctx

        allowed = uuid_lib.UUID("00000000-0000-0000-0000-000000000a01")
        forbidden = uuid_lib.UUID("00000000-0000-0000-0000-000000000bff")
        token = _issue(
            "admin",
            rol="admin",
            sucursales_permitidas=[str(allowed)],
        )
        request = _build_request(token)
        self._patch_scope(monkeypatch, [allowed])

        with pytest.raises(HTTPException) as exc:
            await get_tenant_ctx(
                request=request,
                x_sucursal_context=str(forbidden),
                session=AsyncMock(),
            )
        assert exc.value.status_code == 403
        assert exc.value.detail["error"] == "unauthorized_sucursal_context"

    @pytest.mark.asyncio
    async def test_header_in_permitidas_succeeds(
        self, monkeypatch
    ) -> None:
        """Header uuid present in the DB assignments => TenantContext bound."""
        from parkos_core.auth.tenancy import get_tenant_ctx

        allowed = uuid_lib.UUID("00000000-0000-0000-0000-000000000a01")
        token = _issue(
            "admin",
            rol="admin",
            sucursales_permitidas=[str(allowed)],
        )
        request = _build_request(token)
        self._patch_scope(monkeypatch, [allowed])

        ctx = await get_tenant_ctx(
            request=request,
            x_sucursal_context=str(allowed),
            session=AsyncMock(),
        )
        assert ctx.issuer_prefix == "admin-"
        assert ctx.sucursal_uuid == allowed

    @pytest.mark.asyncio
    async def test_admin_token_with_no_permitidas_returns_403(
        self, monkeypatch
    ) -> None:
        """No open DB assignments + any header => 403 (fail closed)."""
        from parkos_core.auth.tenancy import get_tenant_ctx

        some_uuid = uuid_lib.UUID("00000000-0000-0000-0000-000000000a01")
        token = _issue(
            "admin",
            rol="admin",
            sucursales_permitidas=[],  # empty
        )
        request = _build_request(token)
        self._patch_scope(monkeypatch, [])

        with pytest.raises(HTTPException) as exc:
            await get_tenant_ctx(
                request=request,
                x_sucursal_context=str(some_uuid),
                session=AsyncMock(),
            )
        assert exc.value.status_code == 403
        assert exc.value.detail["error"] == "unauthorized_sucursal_context"

    @pytest.mark.asyncio
    async def test_branch_missing_from_claim_is_allowed(
        self, monkeypatch
    ) -> None:
        """THE REPORTED BUG: a branch auto-assigned after login is usable
        even though the active token's claim predates it.

        The claim is a login-time snapshot. Reading scope from it locked
        admins out of branches they had just created until the token
        expired.
        """
        from parkos_core.auth.tenancy import get_tenant_ctx

        old_branch = uuid_lib.UUID("00000000-0000-0000-0000-000000000a01")
        new_branch = uuid_lib.UUID("00000000-0000-0000-0000-00000000c0de")
        token = _issue(
            "admin",
            rol="admin",
            sucursales_permitidas=[str(old_branch)],  # claim lacks new_branch
        )
        request = _build_request(token)
        # DB has both: the create hook inserted the new row in the same TX.
        self._patch_scope(monkeypatch, [old_branch, new_branch])

        ctx = await get_tenant_ctx(
            request=request,
            x_sucursal_context=str(new_branch),
            session=AsyncMock(),
        )
        assert ctx.sucursal_uuid == new_branch

    @pytest.mark.asyncio
    async def test_revoked_branch_in_claim_is_rejected(
        self, monkeypatch
    ) -> None:
        """The mirror image: a branch still named in the claim but closed
        in the DB is refused.

        This is why the claim cannot be used as a positive cache with a
        DB fallback — that would leak access for up to one token lifetime
        after a revocation.
        """
        from parkos_core.auth.tenancy import get_tenant_ctx

        revoked = uuid_lib.UUID("00000000-0000-0000-0000-000000000a01")
        token = _issue(
            "admin",
            rol="admin",
            sucursales_permitidas=[str(revoked)],  # claim still names it
        )
        request = _build_request(token)
        self._patch_scope(monkeypatch, [])  # row closed (vigente_hasta set)

        with pytest.raises(HTTPException) as exc:
            await get_tenant_ctx(
                request=request,
                x_sucursal_context=str(revoked),
                session=AsyncMock(),
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


# ---------------------------------------------------------------------------
# requires_sucursal — endpoints that MUST have a branch selected
# ---------------------------------------------------------------------------


class TestRequiresSucursal:
    """``requires_sucursal`` raises 400 when ``ctx.sucursal_uuid is None``.

    Global endpoints (``/empresa/empresa``, ``/catalogos/*``) don't use this
    dependency — they accept ``sucursal_uuid=None``. Branch-scoped endpoints
    (``/empresa/tarifas-sucursal``, ``/empresa/cantidad-vehiculos-sucursal``)
    do use it, so a request without ``X-Sucursal-Context`` gets a clear 400
    instead of a cryptic downstream error.
    """

    async def test_global_mode_raises_400(self) -> None:
        """``requires_sucursal`` on a global-mode context => 400."""
        from parkos_core.auth.tenancy import TenantContext, requires_sucursal

        ctx = TenantContext(
            actor_uuid=uuid_lib.uuid4(),
            actor_rol="admin",
            issuer_prefix="admin-",
            sucursal_uuid=None,  # global mode
        )
        with pytest.raises(HTTPException) as exc:
            await requires_sucursal(ctx)
        assert exc.value.status_code == 400
        assert exc.value.detail["error"] == "missing_sucursal_context"

    async def test_branch_mode_passes_through(self) -> None:
        """``requires_sucursal`` on a branch-scoped context => returns ctx."""
        from parkos_core.auth.tenancy import TenantContext, requires_sucursal

        branch_uuid = uuid_lib.uuid4()
        ctx = TenantContext(
            actor_uuid=uuid_lib.uuid4(),
            actor_rol="admin",
            issuer_prefix="admin-",
            sucursal_uuid=branch_uuid,
        )
        result = await requires_sucursal(ctx)
        assert result is ctx
        assert result.sucursal_uuid == branch_uuid
