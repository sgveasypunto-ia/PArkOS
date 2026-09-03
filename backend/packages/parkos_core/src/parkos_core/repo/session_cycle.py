"""Session lifecycle helpers for [L-S] tables (design §4.3).

PR1b ships the auth-domain helpers (login only — sesion + caja + arqueo
land in PR7). The ``record_login`` / ``close_login_with_log`` pair writes
rows to ``prod.login`` plus a co-transactional ``log_transaccional`` row
(satisfying the DB-layer session-guard trigger).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.L_S.login import Login


class SessionGuardError(Exception):
    """Raised when the DB-layer session guard trigger fires (LOG_TRANSACCIONAL_REQUIRED)."""


async def record_login(
    session: AsyncSession,
    *,
    usuario_uuid: uuid_lib.UUID,
    sucursal_uuid: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID | None = None,
    success: bool = True,
    motivo: str | None = None,
) -> Login:
    """REQ-42-S-LOGIN / REQ-43-S-LOGIN-FAILURE: INSERT a new ``login`` row.

    Args:
        session: Active ``AsyncSession`` (caller commits).
        usuario_uuid: The user attempting login.
        sucursal_uuid: The branch the login is against.
        actor_uuid: The audit actor. Defaults to ``usuario_uuid`` for self-service.
        success: ``True`` → ``estado='exitoso'``, ``False`` → ``estado='fallido'``.
        motivo: Optional failure reason (carried in the log row).

    Returns:
        The newly created :class:`Login` row (not yet committed).
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    estado = "exitoso" if success else "fallido"

    login_row = Login(
        uuid_usuario=usuario_uuid,
        uuid_sucursal=sucursal_uuid,
        timestamp_evento=now,
        timestamp_cierre=None,
        vigente_desde=now,
        vigente_hasta=None,
        estado=estado,
        created_at=now,
        created_by=actor_uuid or usuario_uuid,
        sync_status="pendiente",
    )
    session.add(login_row)

    # Co-transactional log row — required by the DB-layer session guard trigger.
    from ..models.A.log_transaccional import LogTransaccional

    log_row = LogTransaccional(
        uuid_usuario=actor_uuid or usuario_uuid,
        uuid_sucursal=sucursal_uuid,
        accion="login",
        tabla_afectada="login",
        timestamp_evento=now,
    )
    session.add(log_row)
    return login_row


async def close_login_with_log(
    session: AsyncSession,
    *,
    login_uuid: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID,
) -> Login:
    """REQ-45-S-LOGOUT skeleton: log row FIRST, then UPDATE ``login``.

    The full implementation lands in PR7 (with the timestamp_cierre +
    state-machine validation). PR1b ships this as a skeleton so the auth
    router's ``POST /auth/logout`` endpoint compiles.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 1. Read current row (for datos_anteriores snapshot)
    from sqlalchemy import select

    result = await session.execute(
        select(Login).where(Login.uuid == login_uuid)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise SessionGuardError(f"login {login_uuid} not found")

    # 2. Log row FIRST (so the DB-layer session-guard trigger accepts the UPDATE)
    from ..models.A.log_transaccional import LogTransaccional

    log_row = LogTransaccional(
        uuid_usuario=actor_uuid,
        uuid_sucursal=row.uuid_sucursal,
        accion="logout",
        tabla_afectada="login",
        uuid_registro_afectado=login_uuid,
        timestamp_evento=now,
    )
    session.add(log_row)
    await session.flush()  # ensure log row is visible to the trigger

    # 3. UPDATE the login row
    from sqlalchemy import update

    await session.execute(
        update(Login)
        .where(Login.uuid == login_uuid)
        .values(timestamp_cierre=now, estado="cerrado")
    )

    # Refresh the row so the caller sees the updated state
    await session.refresh(row)
    return row


__all__ = [
    "SessionGuardError",
    "record_login",
    "close_login_with_log",
]