"""sync/observability/ — metrics + logs + PII redaction + alerts (design §9).

PR12 (T-PR12-008) ships :mod:`metrics` with exactly the ONE gauge R-D8
needs (``catalog_backfill_complete``). PR13 (T-PR13-001) adds the
remaining counters/gauges (``sync_apply_total``, ``sync_dependency_wait``,
``catalog_rows_total``, ``sync_deferred_total``) plus ``logs.py``,
``pii_redaction.py``, and ``alerts.py`` per design.md §3/§9.
"""
from __future__ import annotations

__all__: list[str] = []
