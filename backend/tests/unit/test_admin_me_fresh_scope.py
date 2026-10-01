"""Regression tests for ``GET /api/v1/admin/me`` branch scope.

Bug (2026-09-29): the BranchSelector showed a stale branch list. The
previous fix (``db36751``) made ``list_sucursales`` read
``prod.usuarios_sucursal`` fresh, but ``admin_me`` kept returning the
JWT claim. Since ``/admin/me`` is what ``useAdminAuth`` feeds into the
client-side ``allowedPickerOptions`` filter, the stale claim
re-introduced the exact same symptom: an admin who created a branch saw
it in the Administrar table (unscoped read) but never in the picker
until re-login.

These are handler-level tests with a mocked session -- no DB, no
testcontainer. They lock three properties:

1. The scope comes from the DB helper, not the claim.
2. A branch present only in the claim is dropped (revocation is
   immediate, fail-closed -- a stale token must not widen access).
3. The claim is still required to identify the actor (``sub``), so the
   fix did not accidentally make the endpoint unauthenticated.
"""

from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from parkos_core.api.v1 import admin_views

ADMIN = uuid_lib.UUID("00000000-0000-0000-0000-00000000ad01")
SUC_EN_CLAIM = uuid_lib.UUID("00000000-0000-0000-0000-00000000aa01")
SUC_SOLO_EN_DB = uuid_lib.UUID("00000000-0000-0000-0000-00000000bb01")


def _session_mock(*, email: str | None = "admin@parkos.local", rol: str = "admin"):
    """Mock session returning ``usuario`` then ``permissions``.

    ``admin_me`` issues two ``session.execute`` calls before delegating
    the scope to the helper: the ``Usuarios`` lookup (``.first()``) and
    the ``Permisos`` join (``.all()``). ``side_effect`` replays them in
    that order.
    """
    usuario = MagicMock()
    usuario.email = email
    usuario.rol = rol

    usuario_result = MagicMock()
    usuario_scalars = MagicMock()
    usuario_scalars.first = MagicMock(return_value=usuario)
    usuario_result.scalars = MagicMock(return_value=usuario_scalars)

    permisos_result = MagicMock()
    permisos_scalars = MagicMock()
    permisos_scalars.all = MagicMock(return_value=["config_catalogo", "audit_read"])
    permisos_result.scalars = MagicMock(return_value=permisos_scalars)

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[usuario_result, permisos_result])
    return session


def _patch_fresh(monkeypatch: pytest.MonkeyPatch, value: list[uuid_lib.UUID]) -> AsyncMock:
    """Replace the module-level helper with a stub returning ``value``."""
    stub = AsyncMock(return_value=value)
    monkeypatch.setattr(admin_views, "extract_sucursales_permitidas_fresh", stub, raising=True)
    return stub


def _claims(**overrides) -> dict:
    base = {
        "sub": str(ADMIN),
        "iss": "admin-test",
        "rol": "admin",
        "sucursales_permitidas": [str(SUC_EN_CLAIM)],
    }
    base.update(overrides)
    return base


async def test_scope_comes_from_db_not_jwt_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A branch auto-assigned in the DB is reported even when the JWT
    claim predates it. This is the reported bug: create a branch, expect
    it in the picker, no re-login.
    """
    session = _session_mock()
    stub = _patch_fresh(monkeypatch, [SUC_EN_CLAIM, SUC_SOLO_EN_DB])

    response = await admin_views.admin_me(session=session, claims=_claims())

    assert SUC_SOLO_EN_DB in response.sucursales_permitidas
    assert stub.await_count == 1
    # The helper is called with the actor from ``sub``, not from the claim list.
    assert stub.await_args.kwargs["actor_uuid"] == ADMIN


async def test_claim_only_branch_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A branch present in the claim but NOT open in the DB is excluded.

    The claim is a login-time snapshot, so it can only ever be a
    superset (or a subset) of current truth. Trusting it would leak
    access for up to one token lifetime after a revocation -- the exact
    leak the fresh read was introduced to close.
    """
    session = _session_mock()
    _patch_fresh(monkeypatch, [SUC_SOLO_EN_DB])

    response = await admin_views.admin_me(session=session, claims=_claims())

    assert response.sucursales_permitidas == [SUC_SOLO_EN_DB]
    assert SUC_EN_CLAIM not in response.sucursales_permitidas


async def test_no_open_assignments_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty DB assignments -> empty list, never a fallback to the claim.

    ``/sucursales`` fails closed the same way, so the two endpoints agree
    and the client-side ``sucursalUuids.length === 0`` branch cannot be
    reached by a stale-token admin.
    """
    session = _session_mock()
    _patch_fresh(monkeypatch, [])

    response = await admin_views.admin_me(session=session, claims=_claims())

    assert response.sucursales_permitidas == []


async def test_identity_still_comes_from_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``actor_uuid``/``email``/``rol``/``permissions`` are unchanged --
    only the branch scope moved to the DB. Guards against a refactor
    that returns DB scope but drops the identity fields.
    """
    session = _session_mock(email="root@parkos.local", rol="admin")
    _patch_fresh(monkeypatch, [SUC_SOLO_EN_DB])

    response = await admin_views.admin_me(session=session, claims=_claims())

    assert response.actor_uuid == ADMIN
    assert response.email == "root@parkos.local"
    assert response.rol == "admin"
    assert response.permissions == ["audit_read", "config_catalogo"]


@pytest.mark.parametrize("bad_sub", ["not-a-uuid", "", None])
async def test_malformed_sub_still_401(monkeypatch: pytest.MonkeyPatch, bad_sub) -> None:
    """The ``sub`` claim remains the identity proof: a malformed one
    still 401s before the DB is touched.
    """
    session = _session_mock()
    stub = _patch_fresh(monkeypatch, [SUC_SOLO_EN_DB])

    with pytest.raises(HTTPException) as excinfo:
        await admin_views.admin_me(session=session, claims=_claims(sub=bad_sub))

    assert excinfo.value.status_code == 401
    assert stub.await_count == 0


__all__ = [
    "test_claim_only_branch_is_dropped",
    "test_identity_still_comes_from_token",
    "test_malformed_sub_still_401",
    "test_no_open_assignments_fails_closed",
    "test_scope_comes_from_db_not_jwt_claim",
]
