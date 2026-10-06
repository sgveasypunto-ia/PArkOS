"""Static gate: no catalog entry may reach ``POST /sync/pull`` without a decided scope.

T5.1 every pull-eligible entry has a pull-scope rule AND a class in the shared
      ``EXPECTED_SCOPE`` (and the two agree).
T5.2 only an explicit allowlist of reference catalogs may stay ``all_branches``.

Known leak point NOT covered here: ``sync/cutover/backfill.py`` has no branch
scoping and no production caller today. If it is ever wired to a real path it
must apply the same predicates (``pull_scope.build_scope_predicate``).
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG
from parkos_core.sync.motor.pull_scope import _DERIVED_RULES, build_scope_predicate

from tests.pull_scope_expected import (
    ALL_BRANCHES_ALLOWLIST,
    EXPECTED_SCOPE,
    POLICY_OF_CLASS,
    PULL_DIRECTION_WITHOUT_POLICY,
)

_PULL_DIRECTIONS = {"cloud_to_branch", "bidirectional"}
_PERSONAL_DATA = {"usuarios", "permisos_usuario", "clientes", "clientes_b2b", "vehiculos"}

_ELIGIBLE = [
    s for s in SYNC_CATALOG if s.direction in _PULL_DIRECTIONS and s.broadcast_policy is not None
]


def test_pull_direction_without_policy_is_only_the_documented_exception() -> None:
    unscoped = {
        s.name
        for s in SYNC_CATALOG
        if s.direction in _PULL_DIRECTIONS and s.broadcast_policy is None
    }
    assert unscoped == PULL_DIRECTION_WITHOUT_POLICY, (
        "a pull-direction entry has no broadcast_policy: decide its scope or document the exception"
    )


@pytest.mark.parametrize("spec", _ELIGIBLE, ids=lambda s: s.name)
def test_every_pull_eligible_entry_has_a_scope_rule(spec) -> None:
    # Raises ValueError for an unsupported policy or a derived/transitive entry
    # with no registered rule.
    build_scope_predicate(spec, uuid_lib.uuid4())
    if spec.broadcast_policy == "derived":
        assert spec.name in _DERIVED_RULES


@pytest.mark.parametrize("spec", _ELIGIBLE, ids=lambda s: s.name)
def test_every_pull_eligible_entry_is_in_expected_scope_and_agrees(spec) -> None:
    assert spec.name in EXPECTED_SCOPE, f"{spec.name}: no decided scope in EXPECTED_SCOPE"
    assert POLICY_OF_CLASS[EXPECTED_SCOPE[spec.name]] == spec.broadcast_policy, (
        f"{spec.name}: catalog says {spec.broadcast_policy!r}, EXPECTED_SCOPE says "
        f"{EXPECTED_SCOPE[spec.name]!r}"
    )


def test_expected_scope_names_only_pull_eligible_entries() -> None:
    assert set(EXPECTED_SCOPE) == {s.name for s in _ELIGIBLE}


def test_derived_rules_are_all_used() -> None:
    derived = {s.name for s in _ELIGIBLE if s.broadcast_policy == "derived"}
    assert set(_DERIVED_RULES) == derived, "a derived rule is registered for a non-derived entry"


def test_all_branches_only_for_allowlisted_reference_catalogs() -> None:
    all_branches = {s.name for s in _ELIGIBLE if s.broadcast_policy == "all_branches"}
    assert all_branches <= ALL_BRANCHES_ALLOWLIST, (
        f"{sorted(all_branches - ALL_BRANCHES_ALLOWLIST)} broadcast to every branch without being "
        "an allowlisted reference catalog"
    )


def test_personal_data_entries_are_never_all_branches() -> None:
    by_name = {s.name: s for s in _ELIGIBLE}
    for name in _PERSONAL_DATA:
        assert by_name[name].broadcast_policy != "all_branches", f"{name} leaks to every branch"
    assert not (_PERSONAL_DATA & ALL_BRANCHES_ALLOWLIST)
