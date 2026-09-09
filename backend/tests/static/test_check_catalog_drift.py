"""test_check_catalog_drift.py — T-PR2-017 / T-PR3-007 / T-PR11-005 acceptance
for check_catalog_drift.py.

  - Script exits 0 against the populated catalog from T-PR2-002..015 (and
    the amended, non-stub ``modelo_datos_er.mmd``) with rules 1-7 active
    (T-PR3-007 extends this same script).
  - Script exits 1 naming the offending table on an injected direction
    mismatch fixture (rule 4).
  - Script exits 1 when a fixture nullable FK is injected into depends_on
    (rule 5, R22 guard).
  - Script exits 1 when priority is referenced in a fixture ordering
    function (rule 7, AST check).

**T-PR11-005 rule-count finding.** ``tasks.md``'s T-PR11-005 wording assumes
"the full 11-rule drift check" without having verified the number against
the actual script. Counted directly from ``validator.py``'s exported
``check_rule_N_*`` functions (and from this script's own ``main()`` call
list): the script implements exactly **7** rules, not 11.
``design.md``'s §11 amended list enumerates 11 numbered properties, but 4
of them (its own #4 "exemption list" — folded into rules 2/3's counts here;
#8 "``never_propagated`` set by exactly one table"; #9 "direction/
broadcast_policy disjoint enums"; #10 "``natural_key`` non-empty for
exactly 3 tables") are enforced elsewhere — at ``SyncCatalogEntry``
construction time in ``catalog/schema.py``'s ``__post_init__`` and its
module-level ``assert`` — not by this AST/CI script; and design's own #11
("priority absent from the ordering path") is this script's rule 7 under a
different number. ``operations.md``'s REQ-OPS-003 (the actual normative
spec text) and the CI pipeline order comment in the same file both already
say "rules 1-6" / "rules 1-6" — this script additionally ships rule 7
(R12, priority-absence AST check), for **7** rules total. See
``test_exactly_seven_rules_are_wired`` below for the executable proof.
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
from parkos_core.sync.catalog import validator as catalog_validator  # noqa: E402
from parkos_core.sync.catalog.validator import (  # noqa: E402
    check_rule_4_direction_matches_er,
    check_rule_5_depends_on_matches_er,
    check_rule_7_priority_absent_from_ordering,
    parse_er_entities,
)


def test_check_catalog_drift_exits_0_against_real_catalog() -> None:
    """Green path: the populated catalog matches the ER.

    Rules 1-7 active (PR2 T-PR2-002..015, PR3 T-PR3-001..007), run against
    the real, now-populated catalog and the amended (non-stub)
    ``modelo_datos_er.mmd`` — closes the PR1 placeholder (T-PR11-005).
    """
    exit_code = check_catalog_drift.main(["check_catalog_drift.py"])
    assert exit_code == 0


def test_exactly_seven_rules_are_wired() -> None:
    """T-PR11-005: the script implements exactly 7 rules today, not 11.

    Counts the ``check_rule_N_*`` functions ``validator.py`` actually
    exports (the source of truth this test refuses to hardcode past) and
    cross-checks against the fixed set 1-7. A future rule addition (or
    removal) MUST update this test deliberately rather than let the
    "11 rules" claim from ``tasks.md``/``design.md`` silently drift back
    into an unverified assumption.
    """
    rule_numbers = sorted(
        int(name.removeprefix("check_rule_").split("_", 1)[0])
        for name in catalog_validator.__all__
        if name.startswith("check_rule_")
    )
    assert rule_numbers == [1, 2, 3, 4, 5, 6, 7]


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
