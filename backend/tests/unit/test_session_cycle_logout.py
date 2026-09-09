"""Tests for ``repo.session_cycle.close_login_with_log`` (REQ-45 — logout).

Verifies the logout flow (PR1b-shipped helper, re-validated by PR7):

- Log row added FIRST (so the DB session-guard trigger accepts the
  subsequent UPDATE).
- UPDATE sets ``timestamp_cierre`` + ``estado='cerrado'``.
- ``SessionGuardError`` is raised when the SELECT misses (login row not
  found by UUID).
"""
from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock

from parkos_core.models.A.log_transaccional import LogTransaccional
from parkos_core.repo.session_cycle import (
    SessionGuardError,
    close_login_with_log,
)
from sqlalchemy.sql.dml import Update

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000aaa")
SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000bbb")


def _make_session() -> AsyncMock:
    """Mock ``AsyncSession`` — ``add`` sync, ``execute``/``flush``/``refresh`` async."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _login_row_mock() -> MagicMock:
    """Mock an existing ``Login`` row read by the initial SELECT."""
    row = MagicMock()
    row.uuid = uuid_lib.uuid4()
    row.uuid_sucursal = SUCURSAL_UUID
    return row


def _select_returns(row: MagicMock | None) -> MagicMock:
    """Build the SELECT-side result that ``scalar_one_or_none`` returns.

    Uses ``MagicMock`` (NOT ``AsyncMock``) because ``scalar_one_or_none()``
    is called synchronously by ``close_login_with_log`` — an ``AsyncMock``
    would return a coroutine instead of the row.
    """
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=row)
    return result


def _hash_chain_prior_row_lookup_returns() -> MagicMock:
    """Build the ``session.execute`` result ``repo.hash_chain._read_prior_hash``
    consumes (PR6 — ``close_login_with_log`` now routes its log row through
    ``hash_chain.append``, which does its OWN ``session.execute(select(...))``
    to read the prior chain head, BETWEEN the login-row SELECT and the
    UPDATE this test file's ``side_effect`` sequences already expect).
    Simulates an EXISTING prior row (not ``None``) so the genesis-row
    auto-bootstrap branch (an orthogonal concern — see
    ``tests/unit/test_hash_chain.py``) never activates here.
    """
    fake_prior_row = MagicMock()
    fake_prior_row.hash_actual = "a" * 64
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=fake_prior_row)
    return result


class TestCloseLoginWithLogOrder:
    """``close_login_with_log`` writes log FIRST then UPDATE."""

    async def test_writes_log_first_then_update(self):
        """Log row added BEFORE the UPDATE statement (DB session-guard
        trigger ``ls_session_guard`` requires this).
        """
        session = _make_session()
        # ``session.execute`` is called twice: SELECT, then UPDATE.
        session.execute.side_effect = [
            _select_returns(_login_row_mock()),
            _hash_chain_prior_row_lookup_returns(),
            AsyncMock(),
        ]

        await close_login_with_log(
            session,
            login_uuid=uuid_lib.uuid4(),
            actor_uuid=ACTOR_UUID,
        )

        all_calls = session.mock_calls
        add_log_idx = next(
            i
            for i, c in enumerate(all_calls)
            if c[0] == "add" and isinstance(c[1][0], LogTransaccional)
        )
        update_idx = next(
            i
            for i, c in enumerate(all_calls)
            if c[0] == "execute" and isinstance(c[1][0], Update)
        )
        assert add_log_idx < update_idx, (
            f"log row must be added BEFORE the UPDATE statement "
            f"(add idx={add_log_idx}, update idx={update_idx})"
        )

    async def test_log_row_carries_logout_metadata(self):
        """Log row carries ``accion='logout'`` + ``tabla_afectada='login'``."""
        session = _make_session()
        session.execute.side_effect = [
            _select_returns(_login_row_mock()),
            _hash_chain_prior_row_lookup_returns(),
            AsyncMock(),
        ]

        await close_login_with_log(
            session,
            login_uuid=uuid_lib.uuid4(),
            actor_uuid=ACTOR_UUID,
        )

        log_row = next(
            c.args[0]
            for c in session.add.call_args_list
            if isinstance(c.args[0], LogTransaccional)
        )
        assert log_row.accion == "logout"
        assert log_row.tabla_afectada == "login"
        assert log_row.uuid_usuario == ACTOR_UUID


class TestCloseLoginWithLogUpdateFields:
    """The UPDATE statement sets ``timestamp_cierre``.

    We inspect ``update_stmt._values`` (a stable private dict) rather than
    calling ``compile()`` — the latter is strict about Column-keyed values,
    but the helper's existing code also passes ``estado="cerrado"`` which is
    not yet a Login column (planned for a future migration).
    """

    async def test_update_sets_timestamp_cierre(self):
        session = _make_session()
        session.execute.side_effect = [
            _select_returns(_login_row_mock()),
            _hash_chain_prior_row_lookup_returns(),
            AsyncMock(),
        ]

        await close_login_with_log(
            session,
            login_uuid=uuid_lib.uuid4(),
            actor_uuid=ACTOR_UUID,
        )

        update_call = next(
            c for c in session.execute.call_args_list
            if isinstance(c.args[0], Update)
        )
        update_stmt = update_call.args[0]
        # ``_values`` is a dict mapping Column-or-str keys → BindParameter.
        # Normalize to column-name strings for assertion.
        col_names = {
            k.name if hasattr(k, "name") else str(k) for k in update_stmt._values
        }
        assert "timestamp_cierre" in col_names


class TestCloseLoginWithLogNotFound:
    """``SessionGuardError`` when the SELECT misses the login row."""

    async def test_select_returns_none_raises(self):
        session = _make_session()
        session.execute.side_effect = [_select_returns(None)]

        try:
            await close_login_with_log(
                session,
                login_uuid=uuid_lib.uuid4(),
                actor_uuid=ACTOR_UUID,
            )
        except SessionGuardError:
            return
        raise AssertionError(
            "SessionGuardError was not raised when the login row was not found"
        )
