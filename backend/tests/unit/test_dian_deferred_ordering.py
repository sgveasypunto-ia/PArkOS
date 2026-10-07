"""DD1 — a deferred DIAN dispatch must start only after the OUTERMOST commit.

SQLAlchemy fires ``after_commit`` for the release of a SAVEPOINT too. The
sync push applies every row inside ``session.begin_nested()``, so the
dispatch used to be spawned when the row's savepoint was released — before
the request-level ``session.commit()``. The detached task (own session)
could not see the not-yet-committed ``factura_electronica`` and failed with
``factura_electronica <id> not found``; every envio_dian stayed 'pendiente'.
"""
from __future__ import annotations

import uuid as uuid_lib
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from parkos_core.sync.hooks.impls import dian_dispatch_on_sync as hooks

KEY = ("fe", uuid_lib.UUID("00000000-0000-0000-0000-0000000000d1"))


@pytest.fixture
def sync_session():
    engine = create_engine("sqlite://")
    with Session(engine) as s:
        s.execute(text("select 1"))
        yield s
    engine.dispose()


@pytest.fixture
def spawned():
    """Capture what would be spawned instead of touching an event loop."""
    calls: list[list[object]] = []
    with patch.object(hooks, "_spawn", side_effect=lambda queued: calls.append(queued)):
        yield calls


async def _make(_session) -> None:  # pragma: no cover - never executed here
    return None


def _defer(sync_session, key=KEY):
    hooks.defer_dispatch(SimpleNamespace(sync_session=sync_session), _make, key=key)


def test_savepoint_release_does_not_spawn_before_the_outer_commit(sync_session, spawned) -> None:
    with sync_session.begin_nested():
        _defer(sync_session)
    assert spawned == [], "spawned at SAVEPOINT release: the row is not committed yet"
    sync_session.commit()
    assert len(spawned) == 1 and len(spawned[0]) == 1


def test_all_rows_of_the_batch_spawn_once_at_the_outer_commit(sync_session, spawned) -> None:
    for i in range(3):
        with sync_session.begin_nested():
            _defer(sync_session, key=("fe", uuid_lib.uuid4()))
    assert spawned == []
    sync_session.commit()
    assert [len(batch) for batch in spawned] == [3]


def test_failed_savepoint_drops_only_its_own_dispatches(sync_session, spawned) -> None:
    """A later poison row must not erase the dispatch of an earlier good row,
    and its own (rolled back) FE must never be dispatched."""
    with sync_session.begin_nested():
        _defer(sync_session, key=("fe", uuid_lib.UUID(int=1)))
    with pytest.raises(ValueError):
        with sync_session.begin_nested():
            _defer(sync_session, key=("fe", uuid_lib.UUID(int=2)))
            raise ValueError("row failed")
    sync_session.commit()
    keys = [q.key for batch in spawned for q in batch]
    assert keys == [("fe", uuid_lib.UUID(int=1))]


def test_root_rollback_drops_everything(sync_session, spawned) -> None:
    with sync_session.begin_nested():
        _defer(sync_session)
    sync_session.rollback()
    sync_session.commit()
    assert spawned == []


def test_plain_commit_without_savepoint_spawns(sync_session, spawned) -> None:
    _defer(sync_session)
    sync_session.commit()
    assert len(spawned) == 1


@pytest.mark.asyncio
async def test_sweep_pass_resumes_candidates_once_and_releases_the_snapshot() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from parkos_core.jobs.sync_cloud import SyncCloudWorker

    fe_a, fe_b = uuid_lib.uuid4(), uuid_lib.uuid4()
    session = MagicMock()
    session.rollback = AsyncMock()
    worker = SyncCloudWorker.__new__(SyncCloudWorker)
    worker.log = MagicMock()
    with (
        patch(
            "parkos_core.dian.cloud.sweep.find_stale_pendientes",
            new=AsyncMock(return_value=[fe_a, fe_b]),
        ),
        patch.object(hooks, "resume_factura_dispatch", side_effect=[True, False]) as resume,
    ):
        started = await worker._dian_sweep_once(session)
    assert started == 1
    assert [c.args[0] for c in resume.call_args_list] == [fe_a, fe_b]
    session.rollback.assert_awaited_once()
