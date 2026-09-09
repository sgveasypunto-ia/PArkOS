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

import re

from .entries.sync_entries_a import SYNC_ENTRIES_A
from .entries.sync_entries_le import SYNC_ENTRIES_LE
from .entries.sync_entries_ls import SYNC_ENTRIES_LS
from .entries.sync_entries_lw import SYNC_ENTRIES_LW
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

# ---------------------------------------------------------------------------
# pg_partman child-partition name normalization (found wiring the post-PR14
# full-catalog-sync closing exercise's real trigger-driven sync_queue rows).
# ---------------------------------------------------------------------------
#
# ``0001_initial_schema.py`` registers 8 high-volume tables with
# ``partman.create_parent()`` (``salidas``, ``factura_detalle``,
# ``factura_pagos``, ``log_transaccional``, ``sync_log``, ``sync_queue``,
# ``caja``, ``arqueo``) and clones each parent's own ``AFTER INSERT ...
# fn_enqueue_sync()``/``fn_enqueue_sync_catalog()`` trigger onto every child
# partition — genuine PostgreSQL behavior for a row-level trigger inherited
# by a declarative-partitioned table: the trigger fires with ``TG_TABLE_NAME``
# bound to the PARTITION the row physically landed in (e.g.
# ``log_transaccional_p_current``, the migration's own single premade
# current-month partition; a future ``partman.run_maintenance()``-created
# dated partition would follow the same ``_p<YYYYMMDD>`` convention), never
# the LOGICAL parent name. ``SYNC_CATALOG_BY_NAME`` is keyed by the parent
# name only — a raw ``sync_queue.tabla`` lookup for any of these 8 tables
# therefore ALWAYS misses, and every job that guards an unrecognized
# ``tabla`` with ``mark_failed(..., "unknown_table")`` (D21/REQ-CUT-015)
# silently, permanently fails to sync every row from these 8 tables — found
# concretely via ``log_transaccional`` and ``revocacion_factura``-adjacent
# rows never reaching the destination in this session's closing exercise.
_PARTMAN_SUFFIX_RE = re.compile(r"_p(?:_current|_default|\d{8})$")


def resolve_catalog_name(tabla: str) -> str:
    """Strip a pg_partman child-partition suffix, if present.

    Returns ``tabla`` unchanged when it carries no recognized partition
    suffix (the overwhelming majority of tables — only the 8 named above
    are ever partitioned). Callers ONLY need this before a
    ``SYNC_CATALOG_BY_NAME``/``OUT_OF_CATALOG`` lookup keyed on a raw
    ``sync_queue.tabla`` (or DB-trigger-sourced) value; a value already
    known to be a logical catalog/infra name never needs it.
    """
    return _PARTMAN_SUFFIX_RE.sub("", tabla)


__all__ = ["SYNC_CATALOG", "SYNC_CATALOG_BY_NAME", "resolve_catalog_name"]
