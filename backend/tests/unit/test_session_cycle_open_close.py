"""Tests for ``repo.session_cycle.open_session`` + ``close_session_with_log``.

Verifies REQ-40, REQ-41, SC-40, SC-42:

- ``open_session`` writes a ``Sesion`` row + co-transactional
  ``log_transaccional`` row.
- Server-side fields (``created_at``, ``created_by``, ``timestamp_apertura``)
  are populated; ``timestamp_cierre`` starts ``None``.
- ``close_session_with_log`` writes the log row FIRST (so the DB
  session-guard trigger ``ls_session_guard`` accepts the subsequent UPDATE).
- The closing UPDATE sets ``timestamp_cierre`` + ``uuid_usuario_cierre``.
- ``SessionNotFoundError`` is raised when the SELECT misses OR when the
  UPDATE returns ``rowcount=0``.
"""
from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock

from parkos_core.models.A.log_transaccional import LogTransaccional
from parkos_core.models.L_S.sesion import Sesion
from parkos_core.repo.session_cycle import (
    SessionNotFoundError,
    close_session_with_log,
    open_session,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Update

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000aaa")
SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000bbb")
USUARIO_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000ccc")


def _make_session() -> AsyncMock:
    """Mock ``AsyncSession`` — ``add`` is sync, ``execute``/``flush``/``refresh`` async."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _sesion_row_mock() -> MagicMock:
    """Build a mock that mimics an existing ``Sesion`` row read by SELECT."""
    row = MagicMock()
    row.uuid = uuid_lib.uuid4()
    row.uuid_sucursal = SUCURSAL_UUID
    row.valor_inicial_efectivo = 100.0
    row.valor_inicial_datafono = 50.0
    return row


def _select_returns(row: MagicMock | None) -> MagicMock:
    """Build the SELECT-side result that ``scalar_one_or_none`` returns.

    Uses ``MagicMock`` (NOT ``AsyncMock``) because ``scalar_one_or_none()``
    is called synchronously by the helper — an ``AsyncMock`` would return
    a coroutine instead of the row.
    """
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=row)
    return result


def _update_returns(rowcount: int) -> MagicMock:
    """Build the UPDATE-side result whose ``rowcount`` matches.

    ``.rowcount`` is read as a regular attribute, so a ``MagicMock`` is
    the right shape (no async semantics needed).
    """
    result = MagicMock()
    result.rowcount = rowcount
    return result


class TestOpenSession:
    """``open_session`` writes a fresh ``Sesion`` + log row."""

    async def test_writes_log_and_session(self):
        session = _make_session()
        await open_session(
            session,
            actor_uuid=ACTOR_UUID,
            uuid_sucursal=SUCURSAL_UUID,
            valor_inicial_efectivo=100.0,
            valor_inicial_datafono=50.0,
            uuid_usuario=USUARIO_UUID,
        )
        # Two adds: Sesion row + LogTransaccional row
        assert session.add.call_count == 2
        added_types = [type(c.args[0]).__name__ for c in session.add.call_args_list]
        assert "Sesion" in added_types
        assert "LogTransaccional" in added_types

    async def test_sets_server_side_fields(self):
        """``created_at``, ``created_by``, ``timestamp_apertura`` populated;
        ``timestamp_cierre`` + ``uuid_usuario_cierre`` start ``None``."""
        session = _make_session()
        await open_session(
            session,
            actor_uuid=ACTOR_UUID,
            uuid_sucursal=SUCURSAL_UUID,
            valor_inicial_efectivo=200.0,
            valor_inicial_datafono=0.0,
            uuid_usuario=USUARIO_UUID,
        )
        sesion_row = next(
            c.args[0] for c in session.add.call_args_list
            if isinstance(c.args[0], Sesion)
        )
        assert sesion_row.created_at is not None
        assert sesion_row.created_by == ACTOR_UUID
        assert sesion_row.timestamp_apertura is not None
        assert sesion_row.timestamp_cierre is None
        assert sesion_row.uuid_usuario_cierre is None
        # Business attrs propagated
        assert sesion_row.uuid_sucursal == SUCURSAL_UUID
        assert sesion_row.uuid_usuario == USUARIO_UUID

    async def test_log_tx_false_skips_log_row(self):
        """``log_tx=False`` writes only the ``Sesion`` row."""
        session = _make_session()
        await open_session(
            session,
            actor_uuid=ACTOR_UUID,
            uuid_sucursal=SUCURSAL_UUID,
            valor_inicial_efectivo=100.0,
            valor_inicial_datafono=0.0,
            uuid_usuario=USUARIO_UUID,
            log_tx=False,
        )
        assert session.add.call_count == 1
        assert isinstance(session.add.call_args.args[0], Sesion)


class TestCloseSessionOrder:
    """``close_session_with_log`` writes the log row BEFORE the UPDATE."""

    async def test_writes_log_first_then_update(self):
        """DB trigger ``ls_session_guard`` requires the log row to be in the
        same TX before the UPDATE — verify ``session.add(LogTransaccional)``
        is called BEFORE ``session.execute(Update(...))``.
        """
        session = _make_session()
        session.execute.side_effect = [
            _select_returns(_sesion_row_mock()),
            _update_returns(rowcount=1),
        ]

        await close_session_with_log(
            session,
            actor_uuid=ACTOR_UUID,
            sesion_uuid=uuid_lib.uuid4(),
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

    async def test_log_row_carries_close_metadata(self):
        """Log row carries ``accion='cerrar'`` + ``tabla_afectada='sesion'``."""
        session = _make_session()
        session.execute.side_effect = [
            _select_returns(_sesion_row_mock()),
            _update_returns(rowcount=1),
        ]

        await close_session_with_log(
            session,
            actor_uuid=ACTOR_UUID,
            sesion_uuid=uuid_lib.uuid4(),
            valor_final_efectivo=150.0,
            valor_final_datafono=75.0,
        )

        log_row = next(
            c.args[0]
            for c in session.add.call_args_list
            if isinstance(c.args[0], LogTransaccional)
        )
        assert log_row.accion == "cerrar"
        assert log_row.tabla_afectada == "sesion"
        assert log_row.uuid_usuario == ACTOR_UUID


class TestCloseSessionUpdateFields:
    """The closing UPDATE sets the right columns."""

    async def test_update_sets_timestamp_cierre_and_usuario_cierre(self):
        session = _make_session()
        session.execute.side_effect = [
            _select_returns(_sesion_row_mock()),
            _update_returns(rowcount=1),
        ]

        await close_session_with_log(
            session,
            actor_uuid=ACTOR_UUID,
            sesion_uuid=uuid_lib.uuid4(),
        )

        update_call = next(
            c for c in session.execute.call_args_list
            if isinstance(c.args[0], Update)
        )
        update_stmt = update_call.args[0]
        # Compile to SQL to inspect the SET clause column names. ``update_stmt.values``
        # is a bound method (not the dict), so we use the public ``compile`` API.
        compiled_sql = str(update_stmt.compile(dialect=postgresql.dialect()))
        assert "timestamp_cierre" in compiled_sql
        assert "uuid_usuario_cierre" in compiled_sql


class TestCloseSessionNotFound:
    """``SessionNotFoundError`` when the SELECT misses OR UPDATE returns 0 rows."""

    async def test_select_returns_none_raises(self):
        """SELECT miss → ``SessionNotFoundError`` (raised before the UPDATE)."""
        session = _make_session()
        session.execute.side_effect = [_select_returns(None)]

        try:
            await close_session_with_log(
                session,
                actor_uuid=ACTOR_UUID,
                sesion_uuid=uuid_lib.uuid4(),
            )
        except SessionNotFoundError:
            return
        raise AssertionError("SessionNotFoundError was not raised on SELECT miss")

    async def test_update_returns_zero_rows_raises(self):
        """SELECT hits a row but UPDATE finds ``timestamp_cierre`` already set
        (``rowcount=0``) → ``SessionNotFoundError``."""
        session = _make_session()
        session.execute.side_effect = [
            _select_returns(_sesion_row_mock()),
            _update_returns(rowcount=0),
        ]

        try:
            await close_session_with_log(
                session,
                actor_uuid=ACTOR_UUID,
                sesion_uuid=uuid_lib.uuid4(),
            )
        except SessionNotFoundError:
            return
        raise AssertionError(
            "SessionNotFoundError was not raised when UPDATE rowcount=0"
        )
