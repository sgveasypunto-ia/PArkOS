"""Tests for ``record_login_failure`` + ``clear_login_failures`` (REQ-OP-11).

Both helpers are BEST-EFFORT no-ops until the ``Usuarios.intentos_fallo``
column lands. They MUST:

- NOT raise when the column is missing on the ORM.
- NOT write to the session (``session.add`` is silent).

When the column lands in a future PR, these tests become canaries: they
will start failing and must be replaced with real lockout-enforcement
tests (3 failures within 15 min lock the user out for 30 min — REQ-43,
SC-41).
"""
from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock

from parkos_core.models.V.usuarios import Usuarios
from parkos_core.repo.session_cycle import (
    clear_login_failures,
    record_login_failure,
)

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000aaa")
USUARIO_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000bbb")


def _make_session() -> AsyncMock:
    """Mock ``AsyncSession`` — defensive in case the helpers grow new calls."""
    session = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    return session


def test_precondition_usuarios_lacks_intentos_fallo():
    """Sanity check — ``Usuarios.intentos_fallo`` MUST NOT exist yet.

    If this test fails in the future, the ``intentos_fallo`` column has
    landed on the ORM. The two helpers below will then need real
    lockout-enforcement tests (3 failures / 15 min → 30 min lockout).
    """
    assert not hasattr(Usuarios, "intentos_fallo"), (
        "Pre-condition violated: Usuarios.intentos_fallo exists; "
        "PR7 ships record_login_failure / clear_login_failures as "
        "best-effort no-ops. Replace these tests with real lockout tests."
    )


class TestRecordLoginFailureNoColumn:
    """``record_login_failure`` is a no-op when the column is missing."""

    async def test_does_not_raise(self):
        session = _make_session()
        # MUST NOT raise — column-missing is the documented skip path.
        await record_login_failure(
            session,
            actor_uuid=ACTOR_UUID,
            uuid_usuario=USUARIO_UUID,
            ip_origen="127.0.0.1",
        )

    async def test_session_add_is_not_called(self):
        """No log row, no counter row — nothing added to the session."""
        session = _make_session()
        await record_login_failure(
            session,
            actor_uuid=ACTOR_UUID,
            uuid_usuario=USUARIO_UUID,
        )
        session.add.assert_not_called()

    async def test_session_execute_is_not_called(self):
        """No UPDATE attempt — column missing means we never touch the DB."""
        session = _make_session()
        await record_login_failure(
            session,
            actor_uuid=ACTOR_UUID,
            uuid_usuario=USUARIO_UUID,
        )
        session.execute.assert_not_called()


class TestClearLoginFailuresNoColumn:
    """``clear_login_failures`` is a no-op when the column is missing."""

    async def test_does_not_raise(self):
        session = _make_session()
        await clear_login_failures(
            session,
            actor_uuid=ACTOR_UUID,
            uuid_usuario=USUARIO_UUID,
        )

    async def test_session_add_is_not_called(self):
        """No log row, no counter reset — nothing added to the session."""
        session = _make_session()
        await clear_login_failures(
            session,
            actor_uuid=ACTOR_UUID,
            uuid_usuario=USUARIO_UUID,
        )
        session.add.assert_not_called()

    async def test_session_execute_is_not_called(self):
        """No UPDATE attempt — column missing means we never touch the DB."""
        session = _make_session()
        await clear_login_failures(
            session,
            actor_uuid=ACTOR_UUID,
            uuid_usuario=USUARIO_UUID,
        )
        session.execute.assert_not_called()
