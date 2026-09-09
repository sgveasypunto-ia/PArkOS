"""test_v_fixture_factory.py — T-PR2-018 acceptance for ``VFixtureFactory``.

Coverage report must show all 26 ``[V]`` classes exercised through the
factory (T-PR2-018's acceptance criterion) — this test parametrizes over
every ``SYNC_ENTRIES_V`` model class rather than a hand-picked subset.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.sync.catalog.entries.sync_entries_v import SYNC_ENTRIES_V

_V_MODEL_CLASSES = [entry.model_cls for entry in SYNC_ENTRIES_V]

assert len(_V_MODEL_CLASSES) == 26


@pytest.mark.parametrize(
    "model_cls", _V_MODEL_CLASSES, ids=[c.__tablename__ for c in _V_MODEL_CLASSES]
)
def test_factory_defaults_vigente_hasta_none(v_fixture_factory, model_cls) -> None:
    """Every [V] class builds with vigente_hasta=None (open version) by default."""
    row = v_fixture_factory.build(model_cls)
    assert row.vigente_hasta is None
    assert row.uuid is not None
    assert row.estado == "activo"


@pytest.mark.parametrize(
    "model_cls", _V_MODEL_CLASSES, ids=[c.__tablename__ for c in _V_MODEL_CLASSES]
)
def test_factory_accepts_overrides(v_fixture_factory, model_cls) -> None:
    """Explicit overrides win over the factory's defaults."""
    row = v_fixture_factory.build(model_cls, estado="inactivo")
    assert row.estado == "inactivo"


def test_factory_override_can_close_a_version(v_fixture_factory) -> None:
    """A caller can build an already-closed historical version."""
    closed_at = datetime.now(UTC).replace(tzinfo=None)
    row = v_fixture_factory.build(Usuarios, vigente_hasta=closed_at)
    assert row.vigente_hasta == closed_at
