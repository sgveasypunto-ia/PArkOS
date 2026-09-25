"""ORM model for ``prod.sync_cursor`` (CU-07 — per-branch pull cursor).

Operational, never-replicated table that makes the branch's cloud pull
delivery-incremental (plan.md CU-07): the worker persists ``next_seq``
(the cloud's epoch-ms ``created_at`` high-water mark from ``/sync/pull``)
here after each applied batch and re-pulls from it next cycle instead of
``since_seq=0`` every time.

Defense in depth mirrors :class:`parkos_core.models.A.
ingreso_consecutivo_contador.IngresoConsecutivoContador` (migration
0042's carved-out ``[A]`` pattern):

  * ``REVOKE UPDATE, DELETE`` from ``rol_app`` — migration 0051.
  * ``BEFORE UPDATE OR DELETE`` trigger carve-out that only permits
    UPDATE on ``(ultimo_seq, sync_status, sync_timestamp,
    sync_attempts)`` — every other column is byte-identical to OLD on
    UPDATE; DELETE is unconditionally rejected.

One row per ``uuid_sucursal`` (UK ``(uuid_sucursal)``): the cursor is
branch-local — the worker never pushes it, and it is deliberately absent
from every sync catalog collection so no enqueue trigger is attached
(the same local-only convention as ``ingreso_consecutivo_contador``).

The cursor is a single monotonic high-water mark, never a multi-version
history, so it carries no ``vigente_*`` columns — a stale cursor is
detected and overwritten by :func:`parkos_core.repo.sync_cursor.set_seq`
(monotonic guard), not by bi-temporal close+insert.

NOT partitioned: bounded at ``O(branches)`` single-digit rows per branch
DB; ``pg_partman`` would add overhead for no gain.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class SyncCursor(AppendOnlyBase):
    """[A] Per-``uuid_sucursal`` pull high-water mark (epoch-ms of created_at)."""

    __tablename__ = "sync_cursor"

    # --- Business columns ---
    uuid_sucursal: Mapped[uuid_lib.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )
    # Cloud's ``next_seq`` — epoch-ms of the last applied row's
    # ``created_at`` (see ``api/v1/sync_router.py::_row_seq``). Monotonic;
    # ``set_seq`` refuses to move it backwards (defense against a cloudy
    # clock rewind delivering a stale ``next_seq``).
    ultimo_seq: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )

    __table_args__ = (
        # UK ``UNIQUE (uuid_sucursal)`` lives at the DB layer (migration
        # 0051), not here — same migration-side-UK precedent as
        # ``ingreso_consecutivo_contador`` and ``idempotency_keys``.
        {"schema": "prod", "extend_existing": True},
    )


__all__ = ["SyncCursor"]