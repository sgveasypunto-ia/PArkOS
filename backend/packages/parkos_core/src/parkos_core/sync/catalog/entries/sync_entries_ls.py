"""catalog/entries/sync_entries_ls.py — 2 [L-S] catalog entries (T-PR2-010).

Both carry ``sync_strategy="grace_window"`` (D11) — the 24h JWT-overlap
default the dual-protocol cutover relies on.

**Bug found and fixed in PR7 (T-PR7-002).** ``sesion`` previously declared
``seq_strategy="max_timestamp_evento"``, but ``models/L_S/sesion.py`` has no
``timestamp_evento`` column (only ``timestamp_apertura`` / ``timestamp_cierre``
— unlike ``login``, which genuinely has ``timestamp_evento``).
``motor/read_local_seq.py::ReadLocalSeq`` dispatches ``max_timestamp_evento``
to ``SELECT MAX(timestamp_evento) FROM {table} WHERE uuid = :row_uuid``
(design.md §2 Issue #4), which would raise ``AttributeError`` for this spec.
Corrected to ``max_created_at`` — ``created_at`` is mandatory on every table
(``AuditMixin``, AGENTS.md §1). This fix is independent of
``resolve_conflict``'s own ``[L-S]`` grace-window branch (REQ-MOT-013),
which reads ``remote["timestamp_evento"]`` directly and never consults
``seq_strategy``.

**Separate, unfixed gap (documented, not corrected here — out of PR7
scope).** REQ-MOT-013 (``specs/sync-motor.md``) assumes every ``[L-S]``
remote payload carries a ``timestamp_evento`` key, but ``sesion`` has no
such column (only ``timestamp_apertura`` / ``timestamp_cierre``) and
nothing in this catalog or in ``repo/session_cycle.py`` maps one of those
onto a wire-level ``timestamp_evento`` key. ``motor/resolve_conflict.py``
handles a missing key defensively (``MANUAL``, not a crash) rather than
silently inventing a mapping; see that module's docstring and this PR's
apply report for the full note.
"""
from __future__ import annotations

from ....models.L_S.login import Login
from ....models.L_S.sesion import Sesion
from ..schema import SyncCatalogEntry

# 24h JWT overlap default (D11, R-D6).
GRACE_WINDOW_HOURS: int = 24

_LOGIN = SyncCatalogEntry(
    name="login",
    model_cls=Login,
    audit_class="L_S",
    sync_strategy="grace_window",
    direction="branch_to_cloud",
    broadcast_policy=None,  # single destination (cloud); no broadcast scope
    apply_strategy="session_cycle",
    depends_on=("usuarios", "sucursal"),
    has_uuid_sucursal=True,
    seq_strategy="max_timestamp_evento",
)

_SESION = SyncCatalogEntry(
    name="sesion",
    model_cls=Sesion,
    audit_class="L_S",
    sync_strategy="grace_window",
    direction="branch_to_cloud",
    broadcast_policy=None,  # single destination (cloud); no broadcast scope
    apply_strategy="session_cycle",
    depends_on=("sucursal", "usuarios"),
    has_uuid_sucursal=True,
    seq_strategy="max_created_at",
)

SYNC_ENTRIES_LS: tuple[SyncCatalogEntry, ...] = (_LOGIN, _SESION)

assert len(SYNC_ENTRIES_LS) == 2, f"expected 2 [L-S] entries, got {len(SYNC_ENTRIES_LS)}"

__all__ = ["GRACE_WINDOW_HOURS", "SYNC_ENTRIES_LS"]
