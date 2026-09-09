"""dian/backoff.py — DIAN-specific retry curve (T-PR9-004, design.md §2 Issue #9).

Declares :data:`DIAN_BACKOFF_SCHEDULE` **once**, so both legs of one legal
operation (the ``factura_electronica`` / ``revocacion_factura`` catalog
entries' ``backoff_schedule`` override, wired in ``repo/sync_queue.py::
mark_failed`` — T-PR9-005/006 — and the cloud-side DIAN dispatcher's own
provider round-trip retry, T-PR9-008) import the SAME tuple instead of two
independently-drifting copies.

**Distinct from the general curve.** ``repo/sync_queue.py::BACKOFF_SCHEDULE``
(1m → 5m → 30m → 2h → 12h → 24h, cap) governs ordinary replication retries
for every other catalog entry. The DIAN curve is shorter at the front
(15 minutes instead of 30) and terminal after exactly **6** failed attempts
with a loud, critical alert (``fe_provider_error`` / ``fe_numbering_exhausted``
— ``repo/alert_types.py``, T-PR8-002) rather than a quiet
``FALLIDO_PERMANENTE``. Rationale (design.md §2 Issue #9): a
``factura_electronica`` row already holds a consumed, sequential,
no-gap ``consecutivo`` the moment it is emitted — silently abandoning the
retry after the general curve's ~14h-to-5th-attempt window would leave that
number permanently un-acknowledged by DIAN with no alarm.

**Not cloud-only.** Unlike ``dian/cloud/*`` (Layer 2 import guard, REQ-X3),
this module lives directly under ``dian/`` and carries NO
``PARKOS_DEPLOY=branch`` guard — it is plain data (a tuple of
``timedelta``), never a DIAN-provider call, and it MUST import cleanly on
BOTH deploys because the sync catalog (``sync/catalog/entries/
sync_entries_le.py`` / ``sync_entries_a.py``) is shared code loaded by both
the cloud and the branch process. ``infra/docker/Dockerfile.branch`` only
excludes ``**/dian/cloud/**`` from the branch image (NOT the whole
``dian/`` package), so this file is physically present there too.
"""
from __future__ import annotations

from datetime import timedelta

# 1m -> 5m -> 15m -> 1h -> 6h -> 24h. Index i is the delay AFTER the
# (i+1)-th failed attempt (same convention as
# ``repo/sync_queue.py::next_retry_delay`` / ``BACKOFF_SCHEDULE``).
DIAN_BACKOFF_SCHEDULE: tuple[timedelta, ...] = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=6),
    timedelta(hours=24),
)

# Terminal after 6 failed attempts (design.md §2 Issue #9) — matches
# ``len(DIAN_BACKOFF_SCHEDULE)``; exposed as a named constant so callers
# never hardcode the magic number ``6`` independently of the schedule.
DIAN_MAX_RETRIES: int = len(DIAN_BACKOFF_SCHEDULE)

__all__ = ["DIAN_BACKOFF_SCHEDULE", "DIAN_MAX_RETRIES"]
