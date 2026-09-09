"""sync/observability/metrics.py — ``prometheus_client`` gauges (T-PR12-008).

REQ-OPS-006, design.md §9 (D10). PR12 ships exactly the ONE gauge R-D8
needs; PR13 (T-PR13-001) adds the remaining counters/gauges design.md §9
enumerates (``sync_apply_total``, ``sync_dependency_wait``,
``catalog_rows_total``, ``sync_deferred_total``) — this module is created
here, not there, only because R-D8's branch-cutover gate needs
``catalog_backfill_complete`` NOW.

``catalog_backfill_complete{uuid_sucursal}`` — 1 once EVERY
``cloud_to_branch``/``bidirectional`` catalog entry has completed its
initial topological backfill with ZERO unresolved (buffered) parents for
that branch (R-D8); 0 otherwise, including while backfill is in progress or
any single level still has an unresolved parent. Exposition (a real
``/metrics`` scrape endpoint) is a deploy-pipeline concern out of this PR's
scope, same carve-out precedent as T-PR11-004 (``check_drain.py``)/
``dual_protocol.py`` (``PARKOS_CATALOG_REVISION`` wiring) — the module
still uses the real ``prometheus_client.Gauge`` (not a hand-rolled stand-in)
so a future exposition endpoint only needs to import this module, not
rewrite it.
"""
from __future__ import annotations

from prometheus_client import Gauge

catalog_backfill_complete = Gauge(
    "catalog_backfill_complete",
    "1 once every cloud_to_branch/bidirectional catalog entry has completed "
    "its initial topological backfill with zero unresolved parents for this "
    "branch (R-D8); 0 otherwise.",
    ["uuid_sucursal"],
)

__all__ = ["catalog_backfill_complete"]
