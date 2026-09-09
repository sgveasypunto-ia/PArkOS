"""catalog/sync_catalog.py — SYNC_CATALOG aggregator (REQ-CAT-002).

Concatenates the five per-audit-class entry tuples
(``entries/sync_entries_{v,le,lw,ls,a}.py``) into the single 46-entry
``SYNC_CATALOG`` design.md's Module Structure (§3) describes. Not an
explicit tasks.md file entry on its own — implied by T-PR2-002..015's
per-group files plus T-PR2-016's ``Given the three collections are
loaded, ...`` acceptance clause, which needs somewhere to import
``SYNC_CATALOG`` from.
"""
from __future__ import annotations

from .entries.sync_entries_a import SYNC_ENTRIES_A
from .entries.sync_entries_le import SYNC_ENTRIES_LE
from .entries.sync_entries_lw import SYNC_ENTRIES_LW
from .entries.sync_entries_ls import SYNC_ENTRIES_LS
from .entries.sync_entries_v import SYNC_ENTRIES_V
from .schema import SyncCatalogEntry

SYNC_CATALOG: tuple[SyncCatalogEntry, ...] = (
    SYNC_ENTRIES_V
    + SYNC_ENTRIES_LE
    + SYNC_ENTRIES_LW
    + SYNC_ENTRIES_LS
    + SYNC_ENTRIES_A
)

assert len(SYNC_CATALOG) == 46, f"expected 46 SYNC_CATALOG entries, got {len(SYNC_CATALOG)}"

# name -> entry lookup, used by check_catalog_drift.py and (from PR4 on) the
# motor's dispatch path.
SYNC_CATALOG_BY_NAME: dict[str, SyncCatalogEntry] = {entry.name: entry for entry in SYNC_CATALOG}

assert len(SYNC_CATALOG_BY_NAME) == len(SYNC_CATALOG), "duplicate entry name in SYNC_CATALOG"

__all__ = ["SYNC_CATALOG", "SYNC_CATALOG_BY_NAME"]
