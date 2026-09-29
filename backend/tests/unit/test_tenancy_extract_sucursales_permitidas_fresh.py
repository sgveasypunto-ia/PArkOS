"""Unit tests for ``extract_sucursales_permitidas_fresh`` -- the DB-side
counterpart to ``extract_sucursales_permitidas`` (which reads the JWT
claim).

The full behavior is covered by the integration test suite in CI;
this file covers the Python-level contract (the SQL it issues, the
list shape returned) without spinning up a testcontainer.

Why this helper exists: the JWT claim ``sucursales_permitidas`` is
captured at login time. An admin who creates a branch in the same
session won't see it in the picker until re-login because the server
filters the DB query against the stale claim. This helper reads the
assignment table fresh on every request so the picker reflects
mutations immediately.
"""
from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.db.tenancy import extract_sucursales_permitidas_fresh

ADMIN = uuid_lib.UUID("00000000-0000-0000-0000-00000000ad01")
SUC_A = uuid_lib.UUID("00000000-0000-0000-0000-00000000aa01")
SUC_B = uuid_lib.UUID("00000000-0000-0000-0000-00000000bb01")
SUC_C = uuid_lib.UUID("00000000-0000-0000-0000-00000000cc01")


async def test_returns_uuid_list_from_session_execute() -> None:
    """``session.execute(stmt).scalars().all()`` returns UUID rows;
    the helper returns them as a plain list.
    """
    session = AsyncMock()
    fake_scalars = AsyncMock()
    fake_scalars.all = MagicMock(return_value=[SUC_A, SUC_B, SUC_C])
    fake_result = MagicMock()
    fake_result.scalars = MagicMock(return_value=fake_scalars)
    session.execute = AsyncMock(return_value=fake_result)

    out = await extract_sucursales_permitidas_fresh(
        session, actor_uuid=ADMIN
    )

    assert out == [SUC_A, SUC_B, SUC_C]


async def test_returns_empty_list_when_no_open_assignments() -> None:
    """If the admin has no open ``usuarios_sucursal`` rows, return
    an empty list (which the caller maps to ``items=[]`` -- fail-closed,
    not "show everything").
    """
    session = AsyncMock()
    fake_scalars = AsyncMock()
    fake_scalars.all = MagicMock(return_value=[])
    fake_result = MagicMock()
    fake_result.scalars = MagicMock(return_value=fake_scalars)
    session.execute = AsyncMock(return_value=fake_result)

    out = await extract_sucursales_permitidas_fresh(
        session, actor_uuid=ADMIN
    )

    assert out == []


async def test_issues_select_against_usuarios_sucursal_filtered_by_admin_and_open() -> None:
    """The SQL must filter on ``uuid_usuario = :actor`` AND
    ``vigente_hasta IS NULL`` -- the canonical "open assignment" shape.
    Lock the contract here so a future refactor of the WHERE clause
    doesn't accidentally widen the scope.
    """
    session = AsyncMock()
    fake_scalars = AsyncMock()
    fake_scalars.all = MagicMock(return_value=[])
    fake_result = MagicMock()
    fake_result.scalars = MagicMock(return_value=fake_scalars)
    session.execute = AsyncMock(return_value=fake_result)

    await extract_sucursales_permitidas_fresh(session, actor_uuid=ADMIN)

    assert session.execute.await_count == 1
    stmt = session.execute.await_args.args[0]
    # Lock the WHERE clause contract: it must reference the right
    # entities and column names so a future refactor doesn't widen the
    # scope. We don't bind the actor uuid through ``execute(..., {'actor': ...})``
    # here -- it's a positional parameter (session.execute takes one
    # stmt arg + optional bind params); the actor is bound later when
    # SQLAlchemy executes. What we DO verify is the statement shape.
    stmt_str = str(stmt)
    assert "uuid_usuario" in stmt_str
    assert "vigente_hasta" in stmt_str
    assert "usuarios_sucursal" in stmt_str


@pytest.mark.parametrize(
    "actor_uuid",
    [ADMIN, uuid_lib.UUID("11111111-2222-3333-4444-555555555555")],
    ids=["admin-fixture", "fresh-uuid"],
)
async def test_returns_whatever_session_provided(actor_uuid: uuid_lib.UUID) -> None:
    """The helper is a thin pass-through: it returns whatever the
    SELECT produced, in the order it came. No filtering, no sorting,
    no deduplication on the Python side. The DB handles ordering and
    filtering (vigente_hasta IS NULL, uuid_usuario = :actor).
    """
    session = AsyncMock()
    fake_scalars = AsyncMock()
    fake_scalars.all = MagicMock(return_value=[SUC_C, SUC_A])  # not sorted
    fake_result = MagicMock()
    fake_result.scalars = MagicMock(return_value=fake_scalars)
    session.execute = AsyncMock(return_value=fake_result)

    out = await extract_sucursales_permitidas_fresh(
        session, actor_uuid=actor_uuid
    )

    # Order preserved verbatim from the DB result.
    assert out == [SUC_C, SUC_A]
