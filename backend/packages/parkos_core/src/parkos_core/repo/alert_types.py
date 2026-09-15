"""repo/alert_types.py — ``validate`` + ``AlertaFactory`` against ``prod.alert_types`` (T-PR8-005, HU-F1.10).

REQ-CAT-021, design.md §2 Issue #6: raises :class:`UnknownAlertTypeError` for
any ``tipo_alerta`` outside the deploy-seeded registry.

HU-F1.10 / DEC-FE-03 adds :class:`AlertaFactory` — the canonical
fire-an-alert call site for branch-initiated alert emission (initial
range-exhaustion alert from the ``create_factura_electronica`` handler,
plus the same pattern available for any future branch-side alert).
The factory writes the row, leaves commit to the caller (R5 mitigation:
alerta commits atomically with the originating TX, exactly like
``insertar_alerta_forzado`` for F1.6 REQ-OPS-041.C).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.alert_types import AlertTypes
from ..models.L_W.alerta import Alerta


class UnknownAlertTypeError(Exception):
    """Raised when ``tipo_alerta`` is not a row in ``prod.alert_types``."""


async def validate(session: AsyncSession, tipo_alerta: str) -> None:
    """Raise :class:`UnknownAlertTypeError` if ``tipo_alerta`` is unregistered.

    Args:
        session: Active ``AsyncSession``.
        tipo_alerta: The identifier to check against ``prod.alert_types``.

    Raises:
        UnknownAlertTypeError: ``tipo_alerta`` has no matching seeded row.
    """
    row = (
        await session.execute(
            select(AlertTypes.tipo_alerta).where(AlertTypes.tipo_alerta == tipo_alerta)
        )
    ).scalar_one_or_none()
    if row is None:
        raise UnknownAlertTypeError(
            f"{tipo_alerta!r} is not a registered prod.alert_types identifier"
        )


class AlertaFactory:
    """Branch-initiated alerta INSERT helper (HU-F1.10 / DEC-FE-03).

    The factory writes a single ``prod.alerta`` row in the caller's TX;
    the caller commits (so the alerta materializes atomically with the
    originating transaction — KD-FE-01 single-commit invariant).
    """

    def __init__(self, session: AsyncSession, ctx: object) -> None:
        self._session = session
        self._ctx = ctx

    async def fire(
        self,
        tipo_alerta: str,
        *,
        motivo: str,
        uuid_sucursal: uuid_lib.UUID | None = None,
    ) -> Alerta:
        """Insert one ``prod.alerta`` row with the given ``tipo_alerta``.

        Args:
            tipo_alerta: must be a seeded ``prod.alert_types`` row
                (validated via :func:`validate`).
            motivo: human-readable context (stored in ``datos_nuevos``).
            uuid_sucursal: optional sucursal FK; defaults to ``ctx.sucursal_uuid``
                when the bound context exposes one.

        Returns:
            The newly constructed (not-yet-committed) :class:`Alerta` row.
            The caller is responsible for ``await session.commit()``.
        """
        await validate(self._session, tipo_alerta)
        actor_uuid = getattr(self._ctx, "actor_uuid", None)
        resolved_sucursal = uuid_sucursal or getattr(self._ctx, "sucursal_uuid", None)
        alerta = Alerta(
            uuid_sucursal=resolved_sucursal,
            uuid_usuario=actor_uuid,
            tipo_alerta=tipo_alerta,
            estado="abierta",
            timestamp_evento=datetime.now(UTC).replace(tzinfo=None),
            uuid_arqueo=None,
            datos_nuevos={"motivo": motivo},
        )
        self._session.add(alerta)
        await self._session.flush()
        return alerta


__all__ = ["AlertaFactory", "UnknownAlertTypeError", "validate"]

