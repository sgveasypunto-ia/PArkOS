"""Append-only repository helpers for [A]-class tables (design §4.4).

REQ-10-A-INSERCION: every state-changing operation on an ``[A]`` table
goes through one of the helpers in this module. The DB layer enforces
inmutability (``REVOKE UPDATE, DELETE`` + ``BEFORE UPDATE OR DELETE``
trigger per ``[A]`` table), but defense in depth (AGENTS.md §1 + §3)
demands the ORM layer also refuse mutations.

What lives here:

  - :func:`append_event` — single-row INSERT into any ``[A]`` model.
    Optionally extends the SHA-256 chain (for ``log_transaccional`` and
    ``revocacion_factura`` — the only two hash-chain carriers).
  - :func:`compensate` — generic reverso pattern (REQ-15-A-COMPENSATION).
    Reads the original row, inserts a new compensating row whose
    ``uuid_pago_revertido`` points at the original. The original row
    itself is left untouched per the [A] inmutability contract — derived
    views (``V_FACTURA_PAGOS_NETOS``) subtract reversos from pagos.

What does NOT live here:

  - ``sync_queue`` state updates (``mark_dispatched``, ``mark_failed``,
    ``schedule_retry``). Those live in :mod:`parkos_core.repo.sync_queue`
    because ``sync_queue`` is the carved-out [A] table (design §12).
  - The DB-side outbox enqueue — that's the ``AFTER INSERT`` trigger
    ``prod.fn_enqueue_sync()``, NOT a Python call. See
    :mod:`parkos_core.repo.sync_outbox` for the no-op facade.

AST tests in ``tests/static/test_no_raw_dml_on_a_tables.py`` reject
``session.execute(update/delete)`` against [A] class names outside this
module + ``repo.sync_queue``.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.base import AppendOnlyBase

T = TypeVar("T", bound=AppendOnlyBase)


class AppendOnlyError(Exception):
    """Base class for [A]-table append/compensate failures."""


class DuplicateCompensationError(AppendOnlyError):
    """Raised when a reverso row already exists for the original row.

    Maps to HTTP 409 in router code. The DB enforces this via the partial
    unique index ``uq_factura_pagos_reverso`` (PR6 migration); this is
    the Python-side mirror.
    """


class OriginalNotFoundError(AppendOnlyError):
    """Raised when ``compensate`` cannot locate the original row."""


async def append_event(  # noqa: UP047 (TypeVar style — matches repo/versioned.py)
    session: AsyncSession,
    model_cls: type[T],
    attrs: dict[str, Any],
    *,
    actor_uuid: uuid_lib.UUID | None = None,
    chain_hash: bool = False,
) -> T:
    """REQ-10-A-INSERCION: insert a single row into any ``[A]`` table.

    The DB trigger ``prod.fn_<table>_inmutable()`` blocks any later
    UPDATE/DELETE on this row (sync_queue is the carve-out). For DIAN
    tables the migration also sets ``fecha_retencion_hasta`` automatically
    via the retention worker — the caller does NOT set it here.

    Args:
        session: Active ``AsyncSession`` (caller commits).
        model_cls: The [A] ORM class (e.g. ``LogTransaccional``,
            ``SyncQueue``, ``RevocacionFactura``).
        attrs: Column-name → value mapping for the new row. The caller
            supplies business attributes; ``created_at`` / ``created_by``
            are filled server-side.
        actor_uuid: JWT subject (the writer of the event). Defaults to
            ``None`` (e.g. for trigger-originated ``sync_queue`` inserts).
        chain_hash: When ``True`` AND the target table carries
            ``HashChainMixin``, the SHA-256 chain is extended before the
            INSERT — :func:`repo.hash_chain.append` is invoked and the
            resulting ``hash_anterior`` / ``hash_actual`` are stamped onto
            the row.

    Returns:
        The newly created :class:`AppendOnlyBase` instance (not yet
        committed). The caller MUST commit the session.

    Raises:
        AppendOnlyError: On any [A] invariant violation surfaced by the
            DB (e.g. partial UK violation).
    """
    # Build the payload — created_at + created_by are server-computed.
    payload: dict[str, Any] = {
        "created_at": datetime.now(UTC).replace(tzinfo=None),
        "created_by": actor_uuid,
        **attrs,
    }

    # Hash chain extension (REQ-16, REQ-X4). Delegated to the
    # specialized helper so it can read the prior chain head in one
    # SELECT and compute the new hash before the INSERT.
    if chain_hash and _has_hash_chain(model_cls):
        from .hash_chain import append as chain_append

        return await chain_append(
            session,
            model_cls,
            attrs,
            actor_uuid=actor_uuid or uuid_lib.uuid4(),
        )

    new_row = model_cls(**payload)
    session.add(new_row)
    return new_row


async def compensate(  # noqa: UP047 (TypeVar style — matches repo/versioned.py)
    session: AsyncSession,
    model_cls: type[T],
    original_uuid: uuid_lib.UUID,
    attrs: dict[str, Any],
    *,
    actor_uuid: uuid_lib.UUID | None = None,
) -> T:
    """REQ-15-A-COMPENSATION: insert a reverso row whose
    ``uuid_pago_revertido`` points at ``original_uuid``.

    Used by the ``factura_pagos`` reverso flow (PR6 wires the model
    in). Generic enough to work with any [A] model that exposes
    ``tipo_movimiento`` and ``uuid_pago_revertido`` columns.

    Per the [A] inmutability contract, the ORIGINAL row is NOT mutated.
    The reverso row is the "compensation record"; the derived view
    (``V_FACTURA_PAGOS_NETOS``) subtracts reversos from pagos for net
    reporting. Re-attempting the compensation raises
    :class:`DuplicateCompensationError` at the DB layer (partial UK
    ``uq_factura_pagos_reverso``).

    Args:
        session: Active ``AsyncSession``.
        model_cls: The [A] ORM class carrying ``tipo_movimiento`` /
            ``uuid_pago_revertido`` (e.g. ``FacturaPagos``).
        original_uuid: UUID of the original ``pago`` row to reverse.
        attrs: Business columns for the new reverso row. The caller
            supplies business attributes; the helper stamps
            ``tipo_movimiento='reverso'`` and
            ``uuid_pago_revertido=original_uuid`` server-side.
        actor_uuid: JWT subject for the audit trail.

    Returns:
        The newly inserted reverso row (not yet committed).

    Raises:
        OriginalNotFoundError: ``original_uuid`` does not match any row.
        DuplicateCompensationError: A reverso row already exists for the
            original (DB partial UK violation).
    """
    # 1. Read the original row — must exist, must be 'pago', must be
    #    unreversed (uuid_pago_revertido IS NULL).
    if not hasattr(model_cls, "tipo_movimiento") or not hasattr(
        model_cls, "uuid_pago_revertido"
    ):
        raise AppendOnlyError(
            f"{model_cls.__name__} does not expose tipo_movimiento / "
            f"uuid_pago_revertido — cannot use compensate()"
        )

    original = (
        await session.execute(
            select(model_cls).where(model_cls.uuid == original_uuid)
        )
    ).scalar_one_or_none()
    if original is None:
        raise OriginalNotFoundError(
            f"original row {original_uuid} not found in {model_cls.__name__}"
        )
    if getattr(original, "tipo_movimiento", None) != "pago":
        raise AppendOnlyError(
            f"original row {original_uuid} has tipo_movimiento="
            f"{getattr(original, 'tipo_movimiento', None)!r}, expected 'pago'"
        )
    if getattr(original, "uuid_pago_revertido", None) is not None:
        raise DuplicateCompensationError(
            f"original row {original_uuid} already has uuid_pago_revertido="
            f"{getattr(original, 'uuid_pago_revertido', None)!r}"
        )

    # 2. Stamp server-side columns on the new row.
    reverso_attrs: dict[str, Any] = {
        **attrs,
        "tipo_movimiento": "reverso",
        "uuid_pago_revertido": original_uuid,
    }

    # 3. Insert. We do NOT mutate the original — per the [A] contract.
    return await append_event(
        session,
        model_cls,
        reverso_attrs,
        actor_uuid=actor_uuid,
    )


def _has_hash_chain(model_cls: type[AppendOnlyBase]) -> bool:
    """Return True if ``model_cls`` carries ``HashChainMixin``."""
    from ..models.base import HashChainMixin

    return HashChainMixin in model_cls.__mro__


__all__ = [
    "AppendOnlyError",
    "DuplicateCompensationError",
    "OriginalNotFoundError",
    "append_event",
    "compensate",
]