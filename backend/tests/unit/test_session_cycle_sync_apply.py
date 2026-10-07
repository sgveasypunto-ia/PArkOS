"""SS1: ``open_session`` / ``close_session_with_log`` as used by the sync apply path.

The cloud applies the branch's open/close EVENTS with the origin's facts and
idempotently. Mock-session unit coverage (the DB behaviour is pinned by
``tests/integration/test_sync_sesion_cierre.py``).
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.repo.session_cycle import (
    SessionNotFoundError,
    close_session_with_log,
    open_session,
)

ORIGIN_CLOSE = datetime(2026, 10, 6, 21, 30, 0)
ORIGIN_OPEN = datetime(2026, 10, 6, 13, 0, 0)


def _session(row: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    update_result = MagicMock()
    update_result.rowcount = 1
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[result, update_result, update_result])
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _row(cierre: datetime | None) -> MagicMock:
    row = MagicMock()
    row.uuid = uuid_lib.uuid4()
    row.valor_inicial_efectivo = 1000
    row.valor_inicial_datafono = 0
    row.uuid_sucursal = uuid_lib.uuid4()
    row.timestamp_cierre = cierre
    return row


async def test_close_uses_the_origin_closing_time_and_user() -> None:
    row = _row(None)
    session = _session(row)
    closer = uuid_lib.uuid4()
    await close_session_with_log(
        session,
        actor_uuid=uuid_lib.uuid4(),
        sesion_uuid=row.uuid,
        timestamp_cierre=ORIGIN_CLOSE,
        uuid_usuario_cierre=closer,
        idempotent=True,
    )
    log_row = session.add.call_args.args[0]
    assert log_row.timestamp_evento == ORIGIN_CLOSE
    values = session.execute.await_args_list[1].args[0].compile().params
    assert values["timestamp_cierre"] == ORIGIN_CLOSE
    assert values["uuid_usuario_cierre"] == closer
    assert values["estado"] == "cerrado"


async def test_idempotent_close_of_an_already_closed_sesion_is_a_noop() -> None:
    row = _row(ORIGIN_CLOSE)
    session = _session(row)
    out = await close_session_with_log(
        session, actor_uuid=uuid_lib.uuid4(), sesion_uuid=row.uuid, idempotent=True
    )
    assert out is row
    session.add.assert_not_called()  # no log row
    assert session.execute.await_count == 1  # only the SELECT, no UPDATE


async def test_non_idempotent_double_close_keeps_raising() -> None:
    """The operator-facing path is unchanged: closing twice is an error."""
    row = _row(ORIGIN_CLOSE)
    found = MagicMock()
    found.scalar_one_or_none.return_value = row
    lost_race = MagicMock()
    lost_race.rowcount = 0  # ``timestamp_cierre IS NULL`` no longer matches
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[found, lost_race])
    session.add = MagicMock()
    session.flush = AsyncMock()
    with pytest.raises(SessionNotFoundError):
        await close_session_with_log(session, actor_uuid=uuid_lib.uuid4(), sesion_uuid=row.uuid)


async def test_idempotent_close_of_a_missing_sesion_still_raises_so_it_is_retried() -> None:
    session = _session(None)
    with pytest.raises(SessionNotFoundError):
        await close_session_with_log(
            session, actor_uuid=uuid_lib.uuid4(), sesion_uuid=uuid_lib.uuid4(), idempotent=True
        )


async def test_idempotent_open_returns_the_existing_sesion_without_inserting() -> None:
    existing = _row(None)
    session = _session(existing)
    out = await open_session(
        session,
        actor_uuid=uuid_lib.uuid4(),
        uuid_sucursal=existing.uuid_sucursal,
        valor_inicial_efectivo=1,
        valor_inicial_datafono=0,
        uuid_usuario=uuid_lib.uuid4(),
        uuid=existing.uuid,
        idempotent=True,
    )
    assert out is existing
    session.add.assert_not_called()


async def test_open_keeps_the_origin_opening_time() -> None:
    session = _session(None)
    out = await open_session(
        session,
        actor_uuid=uuid_lib.uuid4(),
        uuid_sucursal=uuid_lib.uuid4(),
        valor_inicial_efectivo=1,
        valor_inicial_datafono=0,
        uuid_usuario=uuid_lib.uuid4(),
        uuid=uuid_lib.uuid4(),
        timestamp_apertura=ORIGIN_OPEN,
        idempotent=True,
    )
    assert out.timestamp_apertura == ORIGIN_OPEN
