"""test_check_catalog_drift.py — T-PR2-017 / T-PR3-007 acceptance for check_catalog_drift.py.

  - Script exits 0 against the populated catalog from T-PR2-002..015 with
    rules 1-7 active (T-PR3-007 extends this same script).
  - Script exits 1 naming the offending table on an injected direction
    mismatch fixture (rule 4).
  - Script exits 1 when a fixture nullable FK is injected into depends_on
    (rule 5, R22 guard).
  - Script exits 1 when priority is referenced in a fixture ordering
    function (rule 7, AST check).
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _REPO_ROOT / "openspec" / "scripts"

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_catalog_drift  # noqa: E402
from parkos_core.sync.catalog import SYNC_CATALOG  # noqa: E402
from parkos_core.sync.catalog.validator import (  # noqa: E402
    check_rule_4_direction_matches_er,
    check_rule_5_depends_on_matches_er,
    check_rule_7_priority_absent_from_ordering,
    parse_er_entities,
)


def test_check_catalog_drift_exits_0_against_real_catalog() -> None:
    """Green path: the populated catalog matches the ER.

    Rules 1-7 active (PR2 T-PR2-002..015, PR3 T-PR3-001..007).
    """
    exit_code = check_catalog_drift.main(["check_catalog_drift.py"])
    assert exit_code == 0


def test_rule_4_flags_injected_direction_mismatch() -> None:
    """An entry with a deliberately wrong direction is flagged, by name."""
    er_entities = parse_er_entities(_REPO_ROOT / "modelo_datos_er.mmd")

    real_usuarios = next(e for e in SYNC_CATALOG if e.name == "usuarios")
    # usuarios is ER-derived as cloud_to_branch/all_branches; flip it.
    tampered = replace(real_usuarios, direction="branch_to_cloud")
    fixture_catalog = [tampered if e.name == "usuarios" else e for e in SYNC_CATALOG]

    violations = check_rule_4_direction_matches_er(
        sync_catalog=fixture_catalog, er_entities=er_entities
    )
    messages = [str(v) for v in violations]
    assert any("usuarios" in m for m in messages), messages


def test_rule_5_flags_injected_nullable_fk_in_depends_on() -> None:
    """A nullable FK injected into depends_on is rejected — R22 guard (T-PR3-007).

    ``subscripciones_cliente`` is a nullable FK on ``ingreso`` (R22); forcing
    it into ``depends_on`` must be flagged by name, exactly like the real
    bug this rule exists to catch.
    """
    real_ingreso = next(e for e in SYNC_CATALOG if e.name == "ingreso")
    tampered = replace(
        real_ingreso, depends_on=(*real_ingreso.depends_on, "subscripciones_cliente")
    )
    fixture_catalog = [tampered if e.name == "ingreso" else e for e in SYNC_CATALOG]

    violations = check_rule_5_depends_on_matches_er(
        sync_catalog=fixture_catalog, mmd_path=_REPO_ROOT / "modelo_datos_er.mmd"
    )
    messages = [str(v) for v in violations]
    assert any("ingreso" in m for m in messages), messages


def test_rule_7_flags_priority_in_fixture_ordering_function(tmp_path: Path) -> None:
    """`priority` referenced in a fixture ordering module is rejected (AST check, T-PR3-007)."""
    fixture_dir = tmp_path / "parkos_core" / "sync" / "motor"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "dependency_orderer.py").write_text(
        "def order_batch(rows):\n"
        "    return sorted(rows, key=lambda r: r.priority)\n",
        encoding="utf-8",
    )

    violations = check_rule_7_priority_absent_from_ordering(
        src_root=tmp_path,
        relative_paths=("parkos_core/sync/motor/dependency_orderer.py",),
    )
    messages = [str(v) for v in violations]
    assert any("priority" in m for m in messages), messages
