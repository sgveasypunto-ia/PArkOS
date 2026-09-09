"""
check_catalog_drift.py — CI guard for the declarative sync catalog (T-PR2-017).

REQ-OPS-003: re-derives catalog policy from source-of-truth artifacts and
fails the build on drift. Rules 1-4 shipped in PR2; rules 5-7
(`depends_on`/DAG/`priority`) are PR3's extension of this same script
(T-PR3-007, D18/ADR-003).

  1. name -> ORM class (every catalog entry's declared name matches its
     model_cls.__tablename__)
  2. exactly one catalog per table, exception-free
  3. counts: SYNC_CATALOG==46, LOCAL_ONLY_CATALOG==3, OUT_OF_CATALOG==5,
     46+3+5==54
  4. direction / broadcast_policy re-derived from modelo_datos_er.mmd
     (REQ-CAT-004), asserted against the declared value
  5. depends_on re-derived from modelo_datos_er.mmd's mandatory (NOT NULL),
     FK-tagged attributes — a nullable FK (or a polymorphic reference with
     no physical FK) in any depends_on fails the build (R22 guard)
  6. the depends_on graph (self-chain edges excluded) is a DAG (R19)
  7. `priority` is referenced nowhere in the dependency-ordering code path
     (AST check, R12)

Usage:
  python openspec/scripts/check_catalog_drift.py [SRC_ROOT] [ER_MMD_PATH]

  SRC_ROOT defaults to backend/packages/parkos_core/src
  ER_MMD_PATH defaults to modelo_datos_er.mmd (repo root)

  Exit codes:
    0 = no drift found
    1 = at least one violation found (printed as "rule N: detail")
    2 = SRC_ROOT / ER_MMD_PATH not found, or the source tree cannot be imported
"""
from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    default_src_root = repo_root / "backend" / "packages" / "parkos_core" / "src"
    src_root = Path(argv[1]) if len(argv) > 1 else default_src_root
    er_path = Path(argv[2]) if len(argv) > 2 else repo_root / "modelo_datos_er.mmd"

    if not src_root.is_dir():
        print(f"ERROR: source root not found: {src_root}", file=sys.stderr)
        return 2
    if not er_path.is_file():
        print(f"ERROR: ER file not found: {er_path}", file=sys.stderr)
        return 2

    sys.path.insert(0, str(src_root))
    try:
        from parkos_core.sync.catalog import LOCAL_ONLY_CATALOG, OUT_OF_CATALOG, SYNC_CATALOG
        from parkos_core.sync.catalog.validator import (
            check_rule_1_name_matches_model,
            check_rule_2_exactly_one_catalog,
            check_rule_3_counts,
            check_rule_4_direction_matches_er,
            check_rule_5_depends_on_matches_er,
            check_rule_6_graph_is_dag,
            check_rule_7_priority_absent_from_ordering,
            parse_er_entities,
        )
    except ImportError as exc:
        print(f"ERROR: could not import parkos_core.sync.catalog: {exc}", file=sys.stderr)
        return 2

    models_root = src_root / "parkos_core" / "models"
    er_entities = parse_er_entities(er_path)

    all_entries = list(SYNC_CATALOG) + list(LOCAL_ONLY_CATALOG)
    violations = []
    violations += check_rule_1_name_matches_model(all_entries)
    violations += check_rule_2_exactly_one_catalog(
        sync_names={e.name for e in SYNC_CATALOG},
        local_only_names={e.name for e in LOCAL_ONLY_CATALOG},
        out_of_catalog_names=OUT_OF_CATALOG,
        models_root=models_root,
    )
    violations += check_rule_3_counts(
        sync_catalog=list(SYNC_CATALOG),
        local_only_catalog=list(LOCAL_ONLY_CATALOG),
        out_of_catalog=OUT_OF_CATALOG,
    )
    violations += check_rule_4_direction_matches_er(
        sync_catalog=list(SYNC_CATALOG), er_entities=er_entities
    )
    violations += check_rule_5_depends_on_matches_er(
        sync_catalog=list(SYNC_CATALOG), mmd_path=er_path
    )
    violations += check_rule_6_graph_is_dag(sync_catalog=list(SYNC_CATALOG))
    violations += check_rule_7_priority_absent_from_ordering(src_root=src_root)

    print(f"Checked {len(SYNC_CATALOG)} SYNC_CATALOG + {len(LOCAL_ONLY_CATALOG)} "
          f"LOCAL_ONLY_CATALOG entries against {models_root} and {er_path}")
    print()

    if not violations:
        print("OK: no catalog drift found (rules 1-7).")
        return 0

    print(f"FAIL: {len(violations)} violation(s) found:")
    for v in violations:
        print(f"  {v}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
