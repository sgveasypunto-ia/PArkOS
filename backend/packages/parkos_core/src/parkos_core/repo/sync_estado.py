"""HU-F1.14 / KD-SYNC-01 + KD-SYNC-02 -- ``repo/sync_estado.py``.

Read-only SELECT helpers consumed by :mod:`parkos_core.api.v1.sync_estado`.
All three helpers execute exactly one SELECT against the respective
``[A]`` table and return scalar values. They NEVER call
``await session.commit()`` and NEVER issue UPDATE/INSERT/DELETE.

KD-SYNC-01 (SELECT-only invariant): the helpers' bodies contain
ONLY ``await session.execute(select(...))`` calls. No write path is
reachable from this module.

KD-SYNC-02 (read-only AST walk): ``tests/static/test_sync_estado_read_only.py``
asserts that ``api/v1/sync_estado.py::get_sync_estado`` does NOT contain
``update(SyncLog)``, ``update(SyncQueue)``, ``delete(SyncLog)``,
``delete(SyncQueue)``, ``text("UPDATE prod.sync_log")``,
``text("DELETE FROM prod.sync_queue")``, or ``await session.commit()``.

DEC-SYNC-01..10 reference: the design decisions are recorded in
``openspec/changes/hu-f1-14-sync-estado/design.md``.

Helpers:

* :func:`get_ultima_sync_at` -- ``SELECT MAX(timestamp_evento) FROM
  prod.sync_log WHERE uuid_sucursal = :s`` -> ``datetime | None``
  (None when no rows, DEC-SYNC-08).
* :func:`calcular_lag_seg` -- pure math, ``int((now - ultima_sync_at)
  .total_seconds())``. Returns ``None`` when ``ultima_sync_at IS NULL``
  (DEC-SYNC-08). No DB / no IO.
* :func:`count_pendientes_sync_queue` -- ``SELECT count(*) FROM
  prod.sync_queue WHERE uuid_sucursal = :s AND estado='pendiente'`` ->
  ``int >= 0`` (DEC-SYNC-09).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.sync_log import SyncLog
from ..models.A.sync_queue import SyncQueue

# Estado filter used by count_pendientes_sync_queue (REQ-OPS-004 carve-out
# whitelist: pending is one of the 5 estados enum'd on prod.sync_queue).
_PENDIENTE_ESTADO: Final[str] = "pendiente"


async def get_ultima_sync_at(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
) -> datetime | None:
    """Return the MAX(timestamp_evento) for the given branch, or ``None``.

    KD-SYNC-01: SELECT-only. NO UPDATE/DELETE/INSERT. NO commit.
    DEC-SYNC-08: returns ``None`` when no rows exist (empty branch
    contract, NOT 0, NOT inf).
    """
    stmt = (
        select(func.max(SyncLog.timestamp_evento))
        .where(SyncLog.uuid_sucursal == uuid_sucursal)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def calcular_lag_seg(
    ultima_sync_at: datetime | None,
    now: datetime,
) -> int | None:
    """Return ``int((now - ultima_sync_at).total_seconds())`` or ``None``.

    Pure math helper (no DB, no IO). DEC-SYNC-08: when
    ``ultima_sync_at IS None`` the function returns ``None`` -- the
    handler MUST render this as the NEVER SYNCED banner state (NOT
    verde, NOT 0).
    """
    if ultima_sync_at is None:
        return None
    delta = (now - ultima_sync_at).total_seconds()
    return int(delta)


async def count_pendientes_sync_queue(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
) -> int:
    """Return the count of pending sync_queue rows for the given branch.

    KD-SYNC-01: SELECT-only. NO UPDATE/DELETE/INSERT. NO commit.
    DEC-SYNC-09: ALWAYS returns ``int >= 0`` (count(*) semantics --
    NEVER null, NEVER negative).
    """
    stmt = (
        select(func.count())
        .select_from(SyncQueue)
        .where(SyncQueue.uuid_sucursal == uuid_sucursal)
        .where(SyncQueue.estado == _PENDIENTE_ESTADO)
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


__all__ = [
    "calcular_lag_seg",
    "count_pendientes_sync_queue",
    "get_ultima_sync_at",
]
