"""catalog/entries — per-audit-class ``SyncCatalogEntry`` declarations.

Split by audit class (design.md §3 Module Structure) so no single file
grows past what a reviewer can hold in context:

  - ``sync_entries_v.py``   — 26 ``[V]`` entries
  - ``sync_entries_le.py``  — 3 ``[L-E]`` entries
  - ``sync_entries_lw.py``  — 6 ``[L-W]`` entries
  - ``sync_entries_ls.py``  — 2 ``[L-S]`` entries
  - ``sync_entries_a.py``   — 9 ``[A]`` entries

``catalog/sync_catalog.py`` concatenates all five into the single
``SYNC_CATALOG`` tuple (46 entries, REQ-CAT-002).
"""
from __future__ import annotations
