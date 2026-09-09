"""parkos_core.sync.cutover — cutover-mechanics helpers (design.md §8).

Public surface:

- :mod:`parkos_core.sync.cutover.dual_protocol` — the ``/sync/hello``
  dual-protocol handshake response builder (T-PR11-003, REQ-CUT-003/004).
- :mod:`parkos_core.sync.cutover.backfill` — topological, paginated initial
  backfill for a freshly paired branch (T-PR12-001/002, R-D8).
"""

from __future__ import annotations

__all__: list[str] = []
