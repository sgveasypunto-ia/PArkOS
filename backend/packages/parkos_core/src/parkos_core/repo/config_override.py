"""Config override resolution helper (REQ-OP-12, SC-OP-06, SC-03-V-CONFIG-OVERRIDE).

Per-branch override pattern for ``configuracion_seguridad``,
``configuracion_tolerancias`` and ``configuracion_caja`` (HU-F13.3):
per-branch row wins; falls back to global default (``uuid_sucursal IS NULL``).

Used by the ``GET /configuracion-seguridad/efectiva`` endpoint (PR4),
the ``GET /configuracion-caja/efectiva`` endpoint (HU-F13.3), and
by other resolution code paths (PR7 sync + PR8 pairing).
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.tenancy import suspend_tenant_context
from ..models.V.configuracion_caja import ConfiguracionCaja
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
    # Real defect confirmed via live QA (2026-10-02): this resolver takes an
    # explicit ``uuid_sucursal`` target, which may legitimately differ from
    # the ADMIN'S currently active branch (``X-Sucursal-Context``). Without
    # suspending tenant auto-scoping here, the ``do_orm_execute`` listener
    # appends ``AND uuid_sucursal = <active ctx>`` to BOTH statements below:
    # the per-branch lookup then only ever matches when the requested branch
    # happens to equal the active one, and the global-default fallback
    # (``uuid_sucursal IS NULL``) never matches a bound, non-null ctx at
    # all -- so a branch with no override (the "falls back to global" case
    # this function exists for) incorrectly 404s instead of resolving.
    with suspend_tenant_context():
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


async def resolve_efectiva_caja(
    session: AsyncSession,
    uuid_sucursal: uuid_lib.UUID,
) -> ConfiguracionCaja | None:
    """Resolve the effective ``configuracion_caja`` for a branch (HU-F13.3).

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
    # Same tenant-scoping defect as ``resolve_efectiva_seguridad`` above --
    # see that function's comment.
    with suspend_tenant_context():
        # 1. Per-branch row first.
        stmt_branch = (
            select(ConfiguracionCaja)
            .where(
                ConfiguracionCaja.uuid_sucursal == uuid_sucursal,
                ConfiguracionCaja.vigente_hasta.is_(None),
            )
            .limit(1)
        )
        row = (await session.execute(stmt_branch)).scalar_one_or_none()
        if row is not None:
            return row

        # 2. Fall back to global default.
        stmt_global = (
            select(ConfiguracionCaja)
            .where(
                ConfiguracionCaja.uuid_sucursal.is_(None),
                ConfiguracionCaja.vigente_hasta.is_(None),
            )
            .limit(1)
        )
        return (await session.execute(stmt_global)).scalar_one_or_none()


__all__ = ["resolve_efectiva_caja", "resolve_efectiva_seguridad"]