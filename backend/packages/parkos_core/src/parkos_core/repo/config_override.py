"""Config override resolution helper (REQ-OP-12, SC-OP-06, SC-03-V-CONFIG-OVERRIDE).

Per-branch override pattern for ``configuracion_seguridad`` and
``configuracion_tolerancias``: per-branch row wins; falls back to global
default (``uuid_sucursal IS NULL``).

Used by the ``GET /configuracion-seguridad/efectiva`` endpoint (PR4) and
by other resolution code paths (PR7 sync + PR8 pairing).
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.configuracion_seguridad import ConfiguracionSeguridad


async def resolve_efectiva_seguridad(
    session: AsyncSession,
    uuid_sucursal: uuid_lib.UUID,
) -> ConfiguracionSeguridad | None:
    """Resolve the effective ``configuracion_seguridad`` for a branch.

    Priority:
    1. Per-branch row (``vigente_hasta IS NULL AND uuid_sucursal = :requested``)
    2. Global default (``vigente_hasta IS NULL AND uuid_sucursal IS NULL``)
    3. ``None`` if neither exists (caller raises 404).

    Args:
        session: Active ``AsyncSession``.
        uuid_sucursal: Branch UUID to resolve for.

    Returns:
        The matching ORM row, or ``None`` if neither per-branch nor global
        default is configured.
    """
    # 1. Per-branch row first.
    stmt_branch = (
        select(ConfiguracionSeguridad)
        .where(
            ConfiguracionSeguridad.uuid_sucursal == uuid_sucursal,
            ConfiguracionSeguridad.vigente_hasta.is_(None),
        )
        .limit(1)
    )
    row = (await session.execute(stmt_branch)).scalar_one_or_none()
    if row is not None:
        return row

    # 2. Fall back to global default.
    stmt_global = (
        select(ConfiguracionSeguridad)
        .where(
            ConfiguracionSeguridad.uuid_sucursal.is_(None),
            ConfiguracionSeguridad.vigente_hasta.is_(None),
        )
        .limit(1)
    )
    return (await session.execute(stmt_global)).scalar_one_or_none()


__all__ = ["resolve_efectiva_seguridad"]