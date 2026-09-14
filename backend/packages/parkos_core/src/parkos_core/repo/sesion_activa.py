"""Helper to fetch the active cash session for an actor (HU-F1.3).

The partial unique index ``prod.uq_prod_sesion_one_active_per_user``
(created by migration 0023) guarantees at most ONE row in
``prod.sesion`` with ``timestamp_cierre IS NULL`` per
``uuid_usuario`` — defense in depth, KD-3. The ``ORDER BY
timestamp_apertura DESC NULLS LAST LIMIT 1`` here is a defensive
secondary sort in case the DB invariant is ever lost
(index drop during an emergency); on a healthy index it returns the
unique row.

Called from ``api/v1/caja_sesion.py::get_my_sesion``. Has NO HTTP
coupling — testable in isolation against a real ``AsyncSession``.
"""

from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.L_S.sesion import Sesion


async def get_sesion_activa(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
) -> Sesion | None:
    """Resolve the unique active ``Sesion`` for ``actor_uuid``.

    Returns ``None`` when no row satisfies the predicate (the handler
    maps this to HTTP 404 ``sesion_no_active``). On a healthy partial
    unique index the SELECT yields 0 or 1 row; the ``LIMIT 1`` is
    defensive against future erosion of the invariant.
    """
    stmt = (
        select(Sesion)
        .where(Sesion.uuid_usuario == actor_uuid)
        .where(Sesion.timestamp_cierre.is_(None))
        .order_by(Sesion.timestamp_apertura.desc().nulls_last())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


__all__ = ["get_sesion_activa"]
