"""test_engine_flag_no_withdrawn_literals.py — T-PR14-005 acceptance for
``check_engine_flag_values.py`` (ADR-001 Validation).

  - Script exits 0 against the real repo (5 ratified values, zero
    unexpected withdrawn-literal hits).
  - ``EngineMode``'s value set matches the 5 ratified D22 values exactly.
  - A withdrawn literal in a fixture file OUTSIDE the 2 allowed paths is
    flagged.
  - The 2 real, pre-existing PR1 files that legitimately reference the
    withdrawn literals (as REJECTED values) are not flagged.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _REPO_ROOT / "openspec" / "scripts"

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_engine_flag_values  # noqa: E402


def test_check_engine_flag_values_exits_0_against_real_repo() -> None:
    exit_code = check_engine_flag_values.main(["check_engine_flag_values.py"])
    assert exit_code == 0


def test_enum_values_match_ratified_set_exactly() -> None:
    from parkos_core.runtime.engine_flag import EngineMode

    assert frozenset(m.value for m in EngineMode) == frozenset(
        {"legacy", "catalog_admin", "catalog_dian", "catalog", "catalog_branch"}
    )


def test_flags_withdrawn_literal_in_fixture_file(tmp_path: Path) -> None:
    """A fixture tree containing a withdrawn literal outside the allowed files is flagged."""
    fixture_pkg = tmp_path / "backend" / "packages" / "somepkg"
    fixture_pkg.mkdir(parents=True)
    (fixture_pkg / "bad.py").write_text("MODE = 'catalog_read'\n", encoding="utf-8")

    violations = check_engine_flag_values._check_withdrawn_literals(tmp_path)
    assert any("catalog_read" in v for v in violations), violations


def test_allowed_files_are_not_flagged() -> None:
    """engine_flag.py's own withdrawal list, test_engine_flag.py's rejection
    test, and this checker script + its own test (which legitimately use
    the literals as search DATA) are never flagged."""
    violations = check_engine_flag_values._check_withdrawn_literals(_REPO_ROOT)
    assert violations == [], violations
