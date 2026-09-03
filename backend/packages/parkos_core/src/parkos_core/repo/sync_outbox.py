"""No-op facade that documents the sync outbox contract (design §12).

REQ-X6 + SC-X5: the ``AFTER INSERT`` trigger ``prod.fn_enqueue_sync()``
on every replicated ``[A]`` table is the **canonical** outbox path. The
trigger guarantees:

  - **Atomicity**: the ``sync_queue`` row is inserted in the same TX as
    the source row — there are no orphan inserts.
  - **Consistency**: the trigger's ``IF TG_TABLE_NAME = 'sync_queue'
    RETURN NULL`` guard prevents recursion.
  - **Per-table priority**: ``factura_electronica`` / ``revocacion_factura``
    get priority 10; ``ingreso`` / ``salidas`` / ``factura_pagos`` get 5;
    everything else gets 1.

If you ever feel tempted to enqueue a ``sync_queue`` row from Python,
**DON'T.** This module is the design-enforced fence that makes the
contract visible: ``enqueue_sync_row`` always raises.

The legitimate way to write ``sync_queue`` rows from Python is through
:func:`parkos_core.repo.sync_queue.enqueue` — for tests, batch imports,
or other escape hatches where the DB trigger cannot fire. The production
hot path uses the trigger; this module exists to keep callers honest.
"""
from __future__ import annotations

from typing import Any


def enqueue_sync_row(*args: Any, **kwargs: Any) -> None:
    """Always raises :class:`RuntimeError`.

    Documents the design contract. The DB trigger
    ``prod.fn_enqueue_sync()`` is the canonical sync enqueue path; this
    Python function exists only as a no-op fence that fails loudly if
    a caller accidentally reaches for it.

    For legitimate programmatic enqueue (tests, batch imports), use
    :func:`parkos_core.repo.sync_queue.enqueue` directly.
    """
    raise RuntimeError(
        "parkos_core.repo.sync_outbox.enqueue_sync_row is a no-op by design. "
        "The DB trigger prod.fn_enqueue_sync() handles enqueue. "
        "For programmatic enqueue, use parkos_core.repo.sync_queue.enqueue "
        "(tests + batch imports only). See design.md §12 (Sync triggers and outbox)."
    )


__all__ = ["enqueue_sync_row"]