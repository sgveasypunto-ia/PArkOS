"""sync/catalog — the declarative sync policy surface (PR2).

Re-exports the three classification sets every table resolves to exactly
one of (D6-rev, REQ-CAT-002/003/006):

  - :data:`SYNC_CATALOG` — 46 entries
  - :data:`LOCAL_ONLY_CATALOG` — 3 entries
  - :data:`OUT_OF_CATALOG` — 5 names

46 + 3 + 5 = 54 physical prod tables, each classified exactly once
(proposal.md §6.5).
"""
from __future__ import annotations

from .local_only_catalog import LOCAL_ONLY_CATALOG
from .out_of_catalog import OUT_OF_CATALOG
from .schema import SyncCatalogEntry
from .sync_catalog import SYNC_CATALOG, SYNC_CATALOG_BY_NAME

__all__ = [
    "LOCAL_ONLY_CATALOG",
    "OUT_OF_CATALOG",
    "SYNC_CATALOG",
    "SYNC_CATALOG_BY_NAME",
    "SyncCatalogEntry",
]
