"""catalog/dependency_graph.py — ``depends_on`` -> DAG; topological levels (D18, T-PR3-003).

Builds a directed graph from every ``SYNC_CATALOG`` entry's ``depends_on``
(edge: parent -> child) and precomputes each table's topological level once,
at import time — the graph is static (design.md Issue #7: "the graph is
static, computed once at import from depends_on"). ``depends_on`` never
contains an entry's own table name (self-references are resolved separately
via ``parent_fk_column`` / ``self_chain``, see ``check_catalog_drift.py``
rules 5-6 and ADR-003 Part 1), so self-chain edges are structurally absent
from this graph already; ``_build_graph`` still filters them out defensively.

A cycle in the graph is a **programming error** in a catalog entry's
``depends_on`` declaration (ADR-003 rationale #5), not a condition the sync
motor can resolve at apply time. This module therefore raises
:class:`DependencyGraphError` (an ``ImportError`` subclass) as soon as the
module-level computation below runs — i.e. at import time, turning a
would-be production deadlock into a failed build.
"""
from __future__ import annotations

from .sync_catalog import SYNC_CATALOG


class DependencyGraphError(ImportError):
    """Raised when the ``depends_on`` graph contains a cycle.

    Subclasses ``ImportError`` (per T-PR3-003 / design.md Issue #7: "raises
    an ImportError-class exception on a cycle") — importing this module (or
    anything that transitively imports it) fails outright for a cyclic
    catalog, rather than deferring detection to a runtime apply cycle.
    """


def _build_graph(catalog: tuple = SYNC_CATALOG) -> dict[str, frozenset[str]]:
    """Return ``{table_name: frozenset(parent_table_names)}`` for ``catalog``.

    Self-references (``parent == table``) are excluded — they never appear
    in a well-formed entry's ``depends_on`` (self-chains are resolved via
    ``parent_fk_column`` instead, see ``check_catalog_drift.py`` rule 5/6),
    but the filter is defensive: a self-reference must never be able to
    manufacture a trivial 1-node cycle here.
    """
    return {
        entry.name: frozenset(parent for parent in entry.depends_on if parent != entry.name)
        for entry in catalog
    }


def _topological_levels(graph: dict[str, frozenset[str]]) -> dict[str, int]:
    """Compute each node's topological level via Kahn's algorithm (BFS layering).

    Level 0 is every root (no parents in ``graph``); level *n* is every node
    whose parents are all in levels ``< n``. Nodes with no interdependency
    share the same level, which is exactly what lets
    ``motor/dependency_orderer.py`` stable-sort a batch by level alone and
    have ``priority`` survive, unbothered, as the FIFO tie-break within one
    level (ADR-003 Part 1, R12).

    Raises :class:`DependencyGraphError` if any node remains unresolved
    after every currently-ready node (in-degree 0) has been peeled off —
    the remaining set is, by construction, part of a cycle.
    """
    remaining: dict[str, set[str]] = {name: set(parents) for name, parents in graph.items()}
    levels: dict[str, int] = {}
    level = 0
    while remaining:
        ready = sorted(name for name, parents in remaining.items() if not parents)
        if not ready:
            cyclic = ", ".join(sorted(remaining))
            raise DependencyGraphError(
                "SYNC_CATALOG depends_on graph contains a cycle involving: "
                f"{cyclic} — a cycle is a programming error (ADR-003 rationale #5); "
                "fix the offending entry's depends_on, do not resolve it at apply time"
            )
        for name in ready:
            levels[name] = level
            del remaining[name]
        for parents in remaining.values():
            parents.difference_update(ready)
        level += 1
    return levels


def topological_level(table_name: str) -> int:
    """Return the precomputed topological level for a ``SYNC_CATALOG`` table name.

    Raises ``KeyError`` for a name outside ``SYNC_CATALOG`` — this module
    only orders tables that are themselves catalog entries (ADR-003: "that
    is itself a SyncCatalog entry").
    """
    return TOPOLOGICAL_LEVELS[table_name]


# Computed once, at import time (design.md Issue #7). A cyclic catalog fails
# right here, not at apply time.
GRAPH: dict[str, frozenset[str]] = _build_graph()
TOPOLOGICAL_LEVELS: dict[str, int] = _topological_levels(GRAPH)


__all__ = [
    "GRAPH",
    "TOPOLOGICAL_LEVELS",
    "DependencyGraphError",
    "topological_level",
]
