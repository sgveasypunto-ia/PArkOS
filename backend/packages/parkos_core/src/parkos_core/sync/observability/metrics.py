"""sync/observability/metrics.py — ``prometheus_client`` counters/gauges
(T-PR12-008, T-PR13-001).

REQ-OPS-006, design.md §9 (D10). PR12 shipped exactly the ONE gauge R-D8
needs; PR13 (T-PR13-001) adds the remaining counters/gauges design.md §9
enumerates: ``sync_apply_total`` (Counter), ``sync_dependency_wait``
(Gauge), ``catalog_rows_total`` (Gauge), ``sync_deferred_total`` (Counter).

**PII guarantee (REQ-OPS-006, cross-PR constraint).** Every label on every
metric in this module is a STRUCTURAL identifier only — a status enum
value, a table name, a branch uuid, an ``audit_class`` literal, or a parent
table name. None of them ever carries row/payload content (e-mail, phone,
name, etc.). ``tests/unit/test_observability_metrics.py`` asserts this
explicitly against the module's exposed label names.

``catalog_backfill_complete{uuid_sucursal}`` — 1 once EVERY
``cloud_to_branch``/``bidirectional`` catalog entry has completed its
initial topological backfill with ZERO unresolved (buffered) parents for
that branch (R-D8); 0 otherwise, including while backfill is in progress or
any single level still has an unresolved parent.

``sync_apply_total{status, tabla, uuid_sucursal, audit_class}`` — one
increment per ``apply_row`` outcome (``status`` mirrors
``motor.apply_result.ApplyStatus``: ``APPLIED`` / ``CONFLICT`` / ``RETRY``).

``sync_dependency_wait{tabla, tabla_padre}`` — gauge of rows currently
buffered in ``prod.sync_queue_lw_buffer`` waiting on a missing parent (D18).

``catalog_rows_total{tabla, uuid_sucursal}`` — current row count per
catalog table/branch (R18 — the trigger for the deferred volume-bounded
``clientes`` broadcast).

``sync_deferred_total{tabla, tabla_padre}`` — counter of
``RETRY(parent_missing)`` outcomes, deliberately *not* counted as failures
(design.md §9: "deliberately *not* counted as failures").

Exposition (a real ``/metrics`` scrape endpoint) is a deploy-pipeline
concern out of this PR's scope, same carve-out precedent as T-PR11-004
(``check_drain.py``)/``dual_protocol.py`` (``PARKOS_CATALOG_REVISION``
wiring) — the module still uses the real ``prometheus_client`` types (not a
hand-rolled stand-in) so a future exposition endpoint only needs to import
this module, not rewrite it.
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge

catalog_backfill_complete = Gauge(
    "catalog_backfill_complete",
    "1 once every cloud_to_branch/bidirectional catalog entry has completed "
    "its initial topological backfill with zero unresolved parents for this "
    "branch (R-D8); 0 otherwise.",
    ["uuid_sucursal"],
)

sync_apply_total = Counter(
    "sync_apply_total",
    "Count of apply_row outcomes by status, table, branch, and audit class. "
    "Labels are structural identifiers only — never payload content.",
    ["status", "tabla", "uuid_sucursal", "audit_class"],
)

sync_dependency_wait = Gauge(
    "sync_dependency_wait",
    "Rows currently buffered in prod.sync_queue_lw_buffer waiting on a "
    "missing parent (D18), by table and parent table.",
    ["tabla", "tabla_padre"],
)

catalog_rows_total = Gauge(
    "catalog_rows_total",
    "Current row count per catalog table and branch (R18) — the trigger "
    "for the deferred volume-bounded clientes broadcast.",
    ["tabla", "uuid_sucursal"],
)

sync_deferred_total = Counter(
    "sync_deferred_total",
    "Count of RETRY(parent_missing) outcomes by table and parent table — "
    "deliberately not counted as failures.",
    ["tabla", "tabla_padre"],
)

__all__ = [
    "catalog_backfill_complete",
    "catalog_rows_total",
    "sync_apply_total",
    "sync_deferred_total",
    "sync_dependency_wait",
]
