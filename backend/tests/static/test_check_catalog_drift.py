"""test_check_catalog_drift.py — T-PR2-017 acceptance for check_catalog_drift.py.

  - Script exits 0 against the populated catalog from T-PR2-002..015.
  - Script exits 1 naming the offending table on an injected direction
    mismatch fixture.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _REPO_ROOT / "openspec" / "scripts"

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_catalog_drift  # noqa: E402
from parkos_core.sync.catalog import SYNC_CATALOG  # noqa: E402
from parkos_core.sync.catalog.validator import (  # noqa: E402
    check_rule_4_direction_matches_er,
    parse_er_entities,
)


def test_check_catalog_drift_exits_0_against_real_catalog() -> None:
    """Green path: the populated catalog matches the ER (T-PR2-002..015)."""
    exit_code = check_catalog_drift.main(["check_catalog_drift.py"])
    assert exit_code == 0


def test_rule_4_flags_injected_direction_mismatch() -> None:
    """An entry with a deliberately wrong direction is flagged, by name."""
    er_entities = parse_er_entities(_REPO_ROOT / "modelo_datos_er.mmd")

    real_usuarios = next(e for e in SYNC_CATALOG if e.name == "usuarios")
    # usuarios is ER-derived as cloud_to_branch/all_branches; flip it.
    from dataclasses import replace

    tampered = replace(real_usuarios, direction="branch_to_cloud")
    fixture_catalog = [tampered if e.name == "usuarios" else e for e in SYNC_CATALOG]

    violations = check_rule_4_direction_matches_er(
        sync_catalog=fixture_catalog, er_entities=er_entities
    )
    messages = [str(v) for v in violations]
    assert any("usuarios" in m for m in messages), messages
