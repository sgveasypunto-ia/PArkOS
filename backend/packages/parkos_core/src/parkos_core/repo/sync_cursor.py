"""Per-``uuid_sucursal`` cloud-pull high-water mark (CU-07).

Persistence for the branch worker's delivery cursor: the branch no longer
re-snapshots the whole cloud catalog from ``since_seq=0`` on every cycle;
instead it reads the last APPLIED ``next_seq`` here and re-pulls from it
(effective, per :func:`api.v1.sync_router`'s READ delivery model, as
``seq > watermark``). Mirrors :func:`repo.ingreso_consecutivo.
assign_ingreso_consecutivo`'s proven recipe (T-PR9-002 held verbatim):
idempotency-check, ``SELECT ... FOR UPDATE``, INSERT-then-UPDATE on the
carve-out columns.

``[A]`` audit class: ``REVOKE UPDATE, DELETE`` on ``rol_app`` and a
``BEFORE UPDATE OR DELETE`` trigger in migration 0051 enforce this at the
DB layer; the trigger carve-out allows UPDATE only on
``(ultimo_seq, sync_status, sync_timestamp, sync_attempts)`` -- exactly
what :func:`set_seq` mutates.

Monotonicity is a hard invariant (a clock rewind on the cloud must not
move the watermark backwards and re-deliver history). ``set_seq`` guards
``new_seq > current`` before persisting; the row can then only move
forward.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.sync_cursor import SyncCursor


async def get_seq(session: AsyncSession, *, uuid_sucursal: uuid_lib.UUID) -> int:
    """Return the branch's last-applied pull watermark (``0`` if never set).

    Reads the single cursor row for ``uuid_sucursal`` (UK
    ``(uuid_sucursal)``). No lock: the calling worker owns the cursor and
    only writes from :func:`set_seq` inside the same ``session`` as its
    pull batch, so a plain read cannot race itself.
    """
    row = (
        await session.execute(
            select(SyncCursor).where(SyncCursor.uuid_sucursal == uuid_sucursal)
        )
    ).scalar_one_or_none()
    return int(row.ultimo_seq) if row is not None else 0


async def set_seq(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    ultimo_seq: int,
) -> int:
    """Persist ``ultimo_seq`` for ``uuid_sucursal``, never moving backwards.

    Monotonic guard: computes ``new = max(current, ultimo_seq)`` and only
    writes when ``new > current``. The row is created on first call
    (INSERT; trigger permits it). Subsequent calls take ``SELECT ... FOR
    UPDATE`` and flip only the carve-out column ``ultimo_seq``.

    Returns the persisted value (draws are no-ops returning ``current``).

    The caller commits together with its applied pull batch; a rollback of
    the batch also rolls the cursor back, so the next cycle re-delivers
    the unapplied rows (``api/v1/sync_router._fetch_pull_rows`` filters
    ``seq > since``, and :func:`apply_guard.row_already_present` makes
    re-delivery of already-applied rows a no-op).
    """
    row = (
        await session.execute(
            select(SyncCursor)
            .where(SyncCursor.uuid_sucursal == uuid_sucursal)
            .with_for_update()
        )
    ).scalar_one_or_none()

    if row is None:
        new_row = SyncCursor(uuid_sucursal=uuid_sucursal, ultimo_seq=ultimo_seq)
        session.add(new_row)
        await session.flush()
        return int(ultimo_seq)

    current = int(row.ultimo_seq)
    if ultimo_seq <= current:
        return current
    row.ultimo_seq = ultimo_seq
    # SQLAlchemy ORM-level mutation; on flush() the carve-out trigger
    # allows the UPDATE because only (ultimo_seq) changed.
    await session.flush()
    return int(ultimo_seq)


__all__ = ["get_seq", "set_seq"]