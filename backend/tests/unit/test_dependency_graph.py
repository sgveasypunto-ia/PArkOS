"""test_dependency_graph.py — T-PR3-001/002 acceptance for catalog/dependency_graph.py.

Given the populated ``SYNC_CATALOG`` (PR2) with its ``depends_on`` fields
(D18), when the dependency graph is built, then:

  - ``test_depends_on_matches_er``: every entry's ``depends_on`` equals the
    ER's mandatory-FK parent set, re-derived mechanically from
    ``modelo_datos_er.mmd`` (ADR-003 Part 1).
  - ``test_nullable_fk_rejected``: R22's explicit worked example —
    ``"subscripciones_cliente" not in ingreso.depends_on`` (the FK is
    nullable: "NULL = estadía ocasional tarifada").
  - ``test_graph_is_dag_after_self_edges``: the 7 ``self_chain=True`` edges
    are excluded from the graph and the remainder is acyclic.
  - ``test_cycle_raises_at_import``: an injected 2-node cycle fixture raises
    ``DependencyGraphError`` at import time, not apply time (ADR-003
    rationale #5).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from parkos_core.sync.catalog import SYNC_CATALOG
from parkos_core.sync.catalog.validator import parse_er_mandatory_fk_parents

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ER_PATH = _REPO_ROOT / "modelo_datos_er.mmd"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_depends_on_matches_er() -> None:
    """Each SYNC_CATALOG entry's depends_on equals the ER's mandatory-FK parent set."""
    sync_names = {entry.name for entry in SYNC_CATALOG}
    expected_by_table = parse_er_mandatory_fk_parents(_ER_PATH, known_tables=sync_names)

    mismatches = []
    for entry in SYNC_CATALOG:
        expected = expected_by_table.get(entry.name, frozenset())
        actual = frozenset(entry.depends_on)
        if actual != expected:
            mismatches.append(
                f"{entry.name}: declared={sorted(actual)}, ER-derived={sorted(expected)}"
            )
    assert not mismatches, "\n".join(mismatches)


def test_nullable_fk_rejected() -> None:
    """R22 — a nullable FK must never appear in depends_on.

    ``ingreso.uuid_subscripcion_cliente`` is explicitly nullable in the ER
    ("NULL = estadía ocasional tarifada") — a subscribed vehicle presenting
    at a non-selling branch legitimately finds no subscription row, so this
    must never produce RETRY(parent_missing).
    """
    ingreso = next(entry for entry in SYNC_CATALOG if entry.name == "ingreso")
    assert "subscripciones_cliente" not in ingreso.depends_on


def test_graph_is_dag_after_self_edges() -> None:
    """The 7 self_chain=True edges are excluded; the remainder is acyclic."""
    from parkos_core.sync.catalog import dependency_graph

    self_chain_entries = [entry for entry in SYNC_CATALOG if entry.self_chain]
    assert len(self_chain_entries) == 7, [e.name for e in self_chain_entries]

    # No entry's depends_on ever references its own table name — self-chain
    # edges are resolved via parent_fk_column, never via depends_on.
    for entry in SYNC_CATALOG:
        assert entry.name not in entry.depends_on, (
            f"{entry.name}: self-chain edge leaked into depends_on"
        )

    # The module-level computation already ran at import time (above); every
    # SYNC_CATALOG table must have a resolved level, proving the graph is a DAG.
    assert set(dependency_graph.TOPOLOGICAL_LEVELS) == {entry.name for entry in SYNC_CATALOG}


def test_cycle_raises_at_import() -> None:
    """An injected 2-node cycle raises DependencyGraphError at import time.

    Loads a standalone fixture module (never inserted into ``sys.modules``,
    never touching the real ``SYNC_CATALOG``) that calls the REAL
    ``catalog.dependency_graph._topological_levels`` against a deliberately
    cyclic 2-node graph at module scope — the ``exec_module`` call below is
    exactly what "raises at import time" means (ADR-003 rationale #5: "a
    cycle is a programming error", caught by the build, not a runtime
    apply-time deadlock).
    """
    from parkos_core.sync.catalog.dependency_graph import DependencyGraphError

    fixture_path = _FIXTURES_DIR / "cyclic_dependency_graph_fixture.py"
    spec = importlib.util.spec_from_file_location(
        "cyclic_dependency_graph_fixture", fixture_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    with pytest.raises(DependencyGraphError):
        spec.loader.exec_module(module)
