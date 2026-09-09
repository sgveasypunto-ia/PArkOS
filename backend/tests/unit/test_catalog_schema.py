"""test_catalog_schema.py — T-PR2-001 acceptance for ``SyncCatalogEntry``.

Given the dataclass is constructed, when a field is mutated, then it
raises (``frozen=True``); when ``broadcast_policy`` receives a ``direction``
literal (e.g. ``"bidirectional"``), then a static assertion fails — the two
enums are disjoint string-literal sets.
"""
from __future__ import annotations

import dataclasses

import pytest
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.sync.catalog.schema import (
    _BROADCAST_POLICY_VALUES,
    _DIRECTION_VALUES,
    SyncCatalogEntry,
    SyncCatalogEntrySchemaError,
)


def _valid_entry(**overrides: object) -> SyncCatalogEntry:
    kwargs: dict[str, object] = {
        "name": "usuarios",
        "model_cls": Usuarios,
        "audit_class": "V",
        "sync_strategy": "append",
        "direction": "cloud_to_branch",
        "broadcast_policy": "all_branches",
        "apply_strategy": "close_and_insert",
        "seq_strategy": "max_created_at",
    }
    kwargs.update(overrides)
    return SyncCatalogEntry(**kwargs)  # type: ignore[arg-type]


def test_entry_is_frozen() -> None:
    """Mutating any field after construction raises."""
    entry = _valid_entry()
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.direction = "branch_to_cloud"  # type: ignore[misc]


def test_direction_and_broadcast_policy_enums_are_disjoint() -> None:
    """REQ-CAT-001: broadcast_policy must never accept a direction value."""
    assert _DIRECTION_VALUES.isdisjoint(_BROADCAST_POLICY_VALUES)
    # "bidirectional" is a direction literal; it must not be a valid
    # broadcast_policy value.
    assert "bidirectional" not in _BROADCAST_POLICY_VALUES


def test_removed_fields_are_absent() -> None:
    """cloud_only, sync_back_event, direction_proposed were removed by this amendment."""
    field_names = {f.name for f in dataclasses.fields(SyncCatalogEntry)}
    assert "cloud_only" not in field_names
    assert "sync_back_event" not in field_names
    assert "direction_proposed" not in field_names


def test_added_fields_are_present() -> None:
    """depends_on, parent_fk_column, self_chain, natural_key,
    natural_key_normalizer, originating_role, snapshot_columns,
    justification were added by this amendment."""
    field_names = {f.name for f in dataclasses.fields(SyncCatalogEntry)}
    for expected in (
        "depends_on",
        "parent_fk_column",
        "self_chain",
        "natural_key",
        "natural_key_normalizer",
        "originating_role",
        "snapshot_columns",
        "justification",
    ):
        assert expected in field_names, f"missing added field: {expected}"


def test_never_propagated_requires_none_direction() -> None:
    """sync_strategy='never_propagated' with a non-None direction raises."""
    with pytest.raises(SyncCatalogEntrySchemaError, match="never_propagated"):
        _valid_entry(
            sync_strategy="never_propagated",
            direction="cloud_to_branch",
            justification="test",
        )


def test_never_propagated_requires_justification() -> None:
    """sync_strategy='never_propagated' without a justification raises."""
    with pytest.raises(SyncCatalogEntrySchemaError, match="justification"):
        _valid_entry(sync_strategy="never_propagated", direction=None, justification=None)


def test_never_propagated_valid_construction() -> None:
    """A well-formed never_propagated entry constructs cleanly."""
    entry = _valid_entry(
        sync_strategy="never_propagated",
        direction=None,
        broadcast_policy=None,
        apply_strategy=None,
        seq_strategy="none",
        justification="ER CLOUD-ONLY, no branch-side need",
    )
    assert entry.direction is None
    assert entry.justification


def test_non_never_propagated_requires_direction() -> None:
    """A non-never_propagated, non-local_only entry with direction=None raises."""
    with pytest.raises(SyncCatalogEntrySchemaError, match="direction=None"):
        _valid_entry(sync_strategy="append", direction=None)


def test_name_must_match_model_tablename() -> None:
    """entry.name must equal model_cls.__tablename__."""
    with pytest.raises(SyncCatalogEntrySchemaError, match="__tablename__"):
        _valid_entry(name="not_usuarios")


def test_self_chain_requires_parent_fk_column() -> None:
    """self_chain=True without parent_fk_column raises."""
    with pytest.raises(SyncCatalogEntrySchemaError, match="parent_fk_column"):
        _valid_entry(self_chain=True, parent_fk_column=None)
