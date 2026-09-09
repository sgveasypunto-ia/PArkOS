"""test_catalog_counts.py — T-PR2-016 (REQ-CAT-002, REQ-CAT-003, ADR-002).

Given the three collections are loaded, then ``len(SYNC_CATALOG)==46``,
``len(LOCAL_ONLY_CATALOG)==3``, ``len(OUT_OF_CATALOG)==5``, and
``46+3+5==54``.

Every assertion here recomputes the count from the loaded collections
themselves — no hardcoded literal is duplicated except the canon numbers
from proposal.md §6.5, which the test exists to guard.
"""
from __future__ import annotations

from parkos_core.sync.catalog import LOCAL_ONLY_CATALOG, OUT_OF_CATALOG, SYNC_CATALOG


def test_sync_catalog_has_46_entries() -> None:
    assert len(SYNC_CATALOG) == 46


def test_local_only_catalog_has_3_entries() -> None:
    assert len(LOCAL_ONLY_CATALOG) == 3


def test_out_of_catalog_has_5_names() -> None:
    assert len(OUT_OF_CATALOG) == 5


def test_catalog_coverage_totals_54() -> None:
    """46 + 3 + 5 = 54 — every prod table classified exactly once (proposal §6.5)."""
    assert len(SYNC_CATALOG) + len(LOCAL_ONLY_CATALOG) + len(OUT_OF_CATALOG) == 54


def test_sync_catalog_composition_by_audit_class() -> None:
    """26 [V] + 3 [L-E] + 6 [L-W] + 2 [L-S] + 9 [A] == 46 (REQ-CAT-002)."""
    counts: dict[str, int] = {}
    for entry in SYNC_CATALOG:
        counts[entry.audit_class] = counts.get(entry.audit_class, 0) + 1
    assert counts == {"V": 26, "L_E": 3, "L_W": 6, "L_S": 2, "A": 9}


def test_local_only_catalog_exact_names() -> None:
    names = {entry.name for entry in LOCAL_ONLY_CATALOG}
    assert names == {"idempotency_keys", "pairing_tokens", "revoked_sync_jwts"}


def test_local_only_catalog_all_local_only_and_both_role() -> None:
    for entry in LOCAL_ONLY_CATALOG:
        assert entry.sync_strategy == "local_only"
        assert entry.role_required == "both"


def test_out_of_catalog_exact_names() -> None:
    assert OUT_OF_CATALOG == frozenset(
        {"sync_queue", "sync_log", "sync_conflict", "sync_queue_lw_buffer", "alert_types"}
    )


def test_factura_electronica_and_revocacion_factura_single_catalog() -> None:
    """D6-rev: both resolve to SYNC_CATALOG only, never LocalOnlyCatalog."""
    sync_names = {entry.name for entry in SYNC_CATALOG}
    local_only_names = {entry.name for entry in LOCAL_ONLY_CATALOG}
    for name in ("factura_electronica", "revocacion_factura"):
        assert name in sync_names
        assert name not in local_only_names


def test_no_table_appears_in_more_than_one_catalog() -> None:
    """REQ-CAT-005: exactly one catalog per table, no exceptions."""
    sync_names = {entry.name for entry in SYNC_CATALOG}
    local_only_names = {entry.name for entry in LOCAL_ONLY_CATALOG}
    assert sync_names.isdisjoint(local_only_names)
    assert sync_names.isdisjoint(OUT_OF_CATALOG)
    assert local_only_names.isdisjoint(OUT_OF_CATALOG)
