"""motor/dependency_orderer.py — topological sort within a selected batch (D18, T-PR3-006).

Orders an **already-selected** batch of ``SyncQueue`` rows by each row's
table's ``depends_on`` topological level (:mod:`catalog.dependency_graph`),
via a stable sort. Composition with batch selection is intentionally
one-directional and exact, per ADR-003 Part 1 / design.md Issue #7:

  1. **Select** — ``repo/sync_queue.py::list_pending`` — unchanged, not one
     line (``prioridad DESC, intentos ASC, created_at ASC``, ``LIMIT 100``).
  2. **Order within the selected batch** — this module, topological sort
     over ``depends_on``.
  3. **Buffer** — any row whose declared parent is neither local nor earlier
     in the same batch (PR8, ``motor/dependency_buffer.py`` — out of PR3
     scope).

``priority`` (``prioridad``) is never read here. It already did its job in
step 1: ``list_pending`` returns rows pre-ordered by priority, and a
**stable** sort by topological level alone preserves that relative order
between rows that land in the same level — which is exactly what "priority
survives only as a FIFO tie-break within one topological level" (ADR-003
Part 1, R12) means in code. Re-reading ``row.prioridad`` here to break ties
explicitly would be redundant at best and, per the same ADR, a forbidden
second cross-table ordering signal — ``check_catalog_drift.py`` rule 7
asserts ``priority`` is never referenced anywhere in this module.

Self-chain edges (``self_chain=True``, resolved via ``parent_fk_column``,
e.g. the ``uuid_padre`` family) never enter ``depends_on`` in the first
place (see ``catalog/dependency_graph.py``), so they play no part in this
ordering either — nothing in this module needs to special-case them.
"""
from __future__ import annotations

from typing import Protocol

from ..catalog.dependency_graph import TOPOLOGICAL_LEVELS


class QueueRowLike(Protocol):
    """The minimal shape ``order_batch`` needs from a queue row.

    Matches ``models.A.sync_queue.SyncQueue.tabla`` — the source table name
    the row was enqueued for. No other field is read.
    """

    tabla: str


def order_batch(rows: list[QueueRowLike]) -> list[QueueRowLike]:
    """Stable-sort an already-selected batch by topological level.

    ``rows`` MUST already come from ``repo/sync_queue.py::list_pending``
    (or an equivalent ``prioridad DESC, intentos ASC, created_at ASC``
    selection) — this function only reorders *between* dependency levels;
    the relative order *within* one level is exactly whatever ``rows``
    already had when it arrived (the FIFO tie-break, R12).

    A row whose ``tabla`` is not a known ``SYNC_CATALOG`` table (e.g. an
    out-of-catalog table slipping through, which should not happen per
    ``check_catalog_drift.py`` rule 2) sorts after every known table,
    grouped with any other unknown table — it never blocks a known table's
    ordering.
    """
    unknown_level = len(TOPOLOGICAL_LEVELS)
    return sorted(rows, key=lambda row: TOPOLOGICAL_LEVELS.get(row.tabla, unknown_level))


__all__ = ["QueueRowLike", "order_batch"]
