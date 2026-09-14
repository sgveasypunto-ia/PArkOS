"""Append-only event recorder for ``[L-E]`` lifecycle event tables (REQ-30, REQ-33).

The ONLY allowed write path on ``[L-E]`` tables (e.g. ``ingreso``,
``facturas``, ``factura_electronica``) is this module's :func:`record_event`.
No UPDATE, no DELETE — events are point-in-time facts.

Defense in depth (design §3, AGENTS.md §3):

- **API layer**: no DELETE endpoint via ``make_router`` (REQ-33).
- **ORM layer**: this marker (``__record_only__``) is read by the AST test
  ``tests/static/test_no_raw_dml_on_le_tables.py`` (PR5-T13) which rejects
  ``session.execute(update/delete)`` against ``[L-E]`` classes outside this
  module.
- **DB layer**: defense handled by the read-only/single-purpose indexes
  on event tables + the no-DDL extension (PR2 wired REVOKE on ``[A]``
  tables only; ``[L-E]`` tables are read-write but logic-locked to
  insert-only at the application layer).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.base import LifecycleEventBase


class LifecycleEventWriteError(Exception):
    """Raised when a write against a ``[L-E]`` event table is rejected.

    Examples:
    - Attempting UPDATE on an event row (events are immutable).
    - Attempting DELETE on an event row (events are append-only).
    - Calling ``record_event`` on a non-``[L-E]`` class.
    """


# Marker string for the AST test (matches the error message it scans for).
LIFECYCLE_EVENT_FORBIDDEN_MSG = (
    "session.execute(update/delete) against [L-E] event table — use "
    "repo.event.record_event() instead."
)


def _now_naive() -> datetime:
    """Naive UTC ``datetime`` — matches ``VersionedMixin.vigente_desde`` style."""
    return datetime.now(UTC).replace(tzinfo=None)


async def record_event[T: LifecycleEventBase](
    session: AsyncSession,
    model_cls: type[T],
    *,
    actor_uuid: uuid_lib.UUID,
    new_attrs: dict[str, Any],
    log_tx: bool = True,
) -> T:
    """Append-only INSERT for ``[L-E]`` lifecycle event tables (REQ-30, REQ-33).

    Args:
        session: Active ``AsyncSession`` (caller commits).
        model_cls: The ``[L-E]`` ORM class (e.g. ``Ingreso``).
        actor_uuid: JWT subject (the writer of the event).
        new_attrs: Business-attribute mapping for the new event row.
            The caller supplies event-specific fields (``uuid_sucursal``,
            ``placa``, ``fecha_ingreso``, ``observaciones``, etc.).
            ``created_at`` and ``created_by`` are set server-side here.
        log_tx: Whether to also append a ``log_transaccional`` row in the
            same TX (default ``True``).

    Returns:
        The newly inserted event row. ``session.refresh()`` is the
        caller's responsibility.

    Raises:
        LifecycleEventWriteError: If ``model_cls`` is not a ``[L-E]``
            subclass (defense in depth — never reached from production
            code but guards against typos).
    """
    if not (isinstance(model_cls, type) and issubclass(model_cls, LifecycleEventBase)):
        raise LifecycleEventWriteError(
            f"record_event requires a LifecycleEventBase subclass; got {model_cls!r}"
        )

    now = _now_naive()

    new_row = model_cls(
        **new_attrs,
        created_at=now,
        created_by=actor_uuid,
    )
    session.add(new_row)

    if log_tx:
        # Lazily import to avoid module-load-time circulars (model +
        # hash_chain).
        from ..models.A.log_transaccional import LogTransaccional
        from . import hash_chain

        # Real defect confirmed live (qa-e2e audit session, 2026-09-10):
        # `uuid` is `server_default=func.gen_random_uuid()` (models/base.py)
        # — a DB-side default, never populated on `new_row` until a flush
        # round-trips it back. Reading `new_row.uuid` here without a prior
        # flush always returned `None`, so the very `log_transaccional` row
        # meant to prove which event this is (REQ-16 evidentiary trail,
        # hash-chained for tamper evidence) recorded
        # `uuid_registro_afectado = NULL` for every branch-originated
        # ``ingreso``/``facturas``/``factura_electronica`` — confirmed via a
        # real ``POST /api/v1/operacion/ingresos`` whose log row's FK
        # column came back empty. `versioned.close_and_insert` already
        # flushes before reading `new_row.uuid` for the same reason; this
        # mirrors that fix.
        await session.flush()

        # Extend the SHA-256 chain per ``uuid_sucursal`` (REQ-16, REQ-X4).
        # ``repo/hash_chain.append`` reads the prior chain head for the
        # tenant, computes the new ``hash_actual`` over the canonical
        # payload + prior hash, stamps both columns, and INSERTs the row
        # via ``session.add``. First call per tenant lands with
        # ``hash_anterior`` = the per-sucursal genesis hash; subsequent
        # calls link to the prior row's ``hash_actual``. PR11c -- Bug 2.
        log_attrs: dict[str, Any] = {
            "uuid_usuario": actor_uuid,
            "uuid_sucursal": new_attrs.get("uuid_sucursal"),
            "accion": "crear",
            "tabla_afectada": model_cls.__tablename__,
            "uuid_registro_afectado": getattr(new_row, "uuid", None),
            "timestamp_evento": now,
        }
        await hash_chain.append(
            session,
            LogTransaccional,
            log_attrs,
            actor_uuid=actor_uuid,
        )

    return new_row


__all__ = [
    "LIFECYCLE_EVENT_FORBIDDEN_MSG",
    "LifecycleEventWriteError",
    "record_event",
]
