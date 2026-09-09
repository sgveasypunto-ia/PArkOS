"""catalog/out_of_catalog.py — OUT_OF_CATALOG exemption list (T-PR2-015).

Exactly 5 names (REQ-CAT-006, D6-rev): sync infrastructure plus the
deploy-seeded ``alert_types`` registry. None of these are ``SyncCatalog`` or
``LocalOnlyCatalog`` entries — the cloud worker MUST **skip** (not
``mark_failed(unknown_table)``) any row whose table is one of these five
(D21, REQ-OPS-014).

Declared as bare table-name strings, not ``SyncCatalogEntry`` instances:
``sync_queue_lw_buffer`` and ``alert_types`` are new ``[A]`` tables that do
not exist yet — their ORM models and migrations ship in PR8 (dependency
buffer) and PR10/PR8 (alert registry) respectively (design.md §4 Data Model
Changes, migrations ``0009``/``0010``). A ``SyncCatalogEntry`` requires a
real ``model_cls`` (REQ-CAT-001), so this exemption list intentionally stays
a plain name set until those PRs land the ORM classes; drift-checking
(``check_catalog_drift.py`` rule 2 / REQ-OPS-003) still resolves every
*existing* ORM class in ``models/{V,L_E,L_W,L_S,A}/`` against
``SYNC_CATALOG | LOCAL_ONLY_CATALOG | OUT_OF_CATALOG`` and does not require
these two not-yet-existing tables to have a model.
"""
from __future__ import annotations

OUT_OF_CATALOG: frozenset[str] = frozenset(
    {
        "sync_queue",
        "sync_log",
        "sync_conflict",
        "sync_queue_lw_buffer",
        "alert_types",
    }
)

assert len(OUT_OF_CATALOG) == 5, f"expected 5 out-of-catalog names, got {len(OUT_OF_CATALOG)}"

__all__ = ["OUT_OF_CATALOG"]
