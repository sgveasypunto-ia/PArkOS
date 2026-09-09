"""repo/alert_types.py — ``validate`` against ``prod.alert_types`` (T-PR8-005).

REQ-CAT-021, design.md §2 Issue #6: raises :class:`UnknownAlertTypeError` for
any ``tipo_alerta`` outside the deploy-seeded registry. Wired into the
alert-writing path via :mod:`parkos_core.sync.hooks.impls.alert_emitter`
(``AlertEmitter``, design.md §6's 8th registry callable) — the sole
production call site this PR wires. Two OTHER pre-existing alert-writing
call sites (``dian/cloud/dispatcher.py::_write_alerta``,
``jobs/sync_cloud.py::_handle_chain_break``) predate ``prod.alert_types``
entirely and already write literal identifiers that ARE in the seeded
registry (``dian_rechazada``/``dian_timeout``/``dian_error``,
``hash_chain_anomaly``) — retrofitting them to call :func:`validate` too is
a documented, explicitly out-of-scope follow-up for whichever PR next
touches those modules (see this PR's apply report for the full rationale).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.alert_types import AlertTypes


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


__all__ = ["UnknownAlertTypeError", "validate"]
