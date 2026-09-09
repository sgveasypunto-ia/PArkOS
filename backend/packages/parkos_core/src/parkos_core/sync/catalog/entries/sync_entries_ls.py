"""catalog/entries/sync_entries_ls.py — 2 [L-S] catalog entries (T-PR2-010).

Both carry ``sync_strategy="grace_window"`` (D11) — the 24h JWT-overlap
default the dual-protocol cutover relies on.
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
    seq_strategy="max_timestamp_evento",
)

SYNC_ENTRIES_LS: tuple[SyncCatalogEntry, ...] = (_LOGIN, _SESION)

assert len(SYNC_ENTRIES_LS) == 2, f"expected 2 [L-S] entries, got {len(SYNC_ENTRIES_LS)}"

__all__ = ["GRACE_WINDOW_HOURS", "SYNC_ENTRIES_LS"]
