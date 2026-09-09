"""Fixture module — an intentionally cyclic ``depends_on`` graph.

Not a test module itself (no ``test_*`` prefix — pytest never collects it).
Loaded via ``importlib.util`` by
``test_dependency_graph.py::test_cycle_raises_at_import`` to prove
``catalog/dependency_graph.py``'s cycle detection fires at import time, not
apply time (ADR-003 rationale #5). Calls the REAL production
``_topological_levels`` algorithm (not a reimplementation) against a
deliberately cyclic 2-node graph (``fixture_a -> fixture_b -> fixture_a``)
— the module-level assignment below is what "raises at import time" means.
"""
from __future__ import annotations

from parkos_core.sync.catalog.dependency_graph import _topological_levels

_CYCLIC_GRAPH: dict[str, frozenset[str]] = {
    "fixture_a": frozenset({"fixture_b"}),
    "fixture_b": frozenset({"fixture_a"}),
}

# Executes at import (module-exec) time — this call is the assertion under
# test. A real cycle here raises DependencyGraphError before this module
# finishes loading, exactly like a cyclic SYNC_CATALOG would.
TOPOLOGICAL_LEVELS = _topological_levels(_CYCLIC_GRAPH)
