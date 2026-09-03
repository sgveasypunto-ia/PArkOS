"""Bi-temporal close+insert helper for [V] tables (design §4.1).

REQ-04, REQ-05:
1. UPDATE current SET vigente_hasta = NOW(), estado = 'inactivo' WHERE uuid = :cu
2. INSERT new row with vigente_desde = NOW(), vigente_hasta = NULL, estado = 'activo'
3. (PR2) Write a ``log_transaccional`` row in the same TX

Both operations happen in the same transaction. The caller is responsible for
``session.commit()``.

NOTE: This module is the ONLY allowed UPDATE writer on [V] tables. The AST
test ``tests/static/test_no_raw_upsert_on_v_tables.py`` rejects
``session.execute(update(...))`` against [V] classes outside this module.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime, timezone
from typing import Any, TypeVar

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.base import VersionedBase

T = TypeVar("T", bound=VersionedBase)


class VersioningError(Exception):
    """Base class for versioned-table operation failures."""


class RowNotFoundError(VersioningError):
    """Raised when ``current_uuid`` does not match any row."""


async def close_and_insert(
    session: AsyncSession,
    model_cls: type[T],
    *,
    current_uuid: uuid_lib.UUID | None,
    new_attrs: dict[str, Any],
    actor_uuid: uuid_lib.UUID,
    log_tx: bool = True,
) -> T:
    """Bi-temporal Actualización: close current version, insert new version.

    Args:
        session: Active ``AsyncSession`` (caller commits).
        model_cls: The [V] ORM class to operate on (e.g. ``Usuarios``).
        current_uuid: UUID of the row to close. If ``None``, performs INSERT
            only (no close step) — used for the POST ``/<resource>`` path.
        new_attrs: Column-name → value mapping for the new row. The caller
            supplies business attributes (e.g. ``nombre``, ``email``);
            ``vigente_desde``, ``vigente_hasta``, ``estado``, ``created_at``,
            ``created_by`` are set server-side here.
        actor_uuid: JWT subject (the writer of the change).
        log_tx: Whether to write a ``log_transaccional`` row in the same TX
            (default ``True``). PR2 ships the helper; PR1b accepts the
            parameter but the actual log row is a no-op stub.

    Returns:
        The newly inserted row instance. ``session.refresh()`` is the
        caller's responsibility (we don't refresh here to keep the helper
        composable inside larger TX).

    Raises:
        RowNotFoundError: ``current_uuid`` doesn't match any row.
        VersioningError: On any other invariant violation (e.g. attempting
            to close a row whose ``vigente_hasta`` is already set — the
            UPDATE returns 0 rows and we raise).
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 1. Close the current version (if any)
    if current_uuid is not None:
        result = await session.execute(
            update(model_cls)
            .where(
                model_cls.uuid == current_uuid,
                model_cls.vigente_hasta.is_(None),
            )
            .values(
                vigente_hasta=now,
                estado="inactivo",
            )
        )
        if result.rowcount == 0:
            raise RowNotFoundError(
                f"no active row in {model_cls.__tablename__} for uuid={current_uuid}"
            )

    # 2. Build the new row
    payload: dict[str, Any] = {
        "vigente_desde": now,
        "vigente_hasta": None,
        "estado": "activo",
        "created_at": now,
        "created_by": actor_uuid,
        **new_attrs,
    }
    new_row = model_cls(**payload)
    session.add(new_row)

    # 3. Log row stub (PR2: append_only.append_event for log_transaccional)
    if log_tx:
        # Lazily import to avoid module-load-time circulars.
        from ..models.A.log_transaccional import LogTransaccional

        log_row = LogTransaccional(
            uuid_usuario=actor_uuid,
            uuid_sucursal=new_attrs.get("uuid_sucursal"),
            accion="actualizar" if current_uuid is not None else "crear",
            tabla_afectada=model_cls.__tablename__,
            uuid_registro_afectado=getattr(new_row, "uuid", None),
            timestamp_evento=now,
        )
        session.add(log_row)

    return new_row


async def current_version(
    session: AsyncSession,
    model_cls: type[T],
    uuid: uuid_lib.UUID,
) -> T | None:
    """Return the active row for ``uuid`` (vigente_hasta IS NULL), or None."""
    result = await session.execute(
        select(model_cls).where(
            model_cls.uuid == uuid,
            model_cls.vigente_hasta.is_(None),
        )
    )
    return result.scalar_one_or_none()


__all__ = [
    "VersioningError",
    "RowNotFoundError",
    "close_and_insert",
    "current_version",
]