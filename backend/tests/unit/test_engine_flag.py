"""test_engine_flag.py — T-PR1-007 (RED), ADR-001 Validation, D22.

Covers the ``PARKOS_SYNC_ENGINE`` 5-value parser contract ratified by D22 /
ADR-001 (service-flavoured enum, amendment 2026-09-08):

    legacy | catalog_admin | catalog_dian | catalog | catalog_branch

The behaviour-flavoured enum (``catalog_read``, ``catalog_dual``,
``catalog_only``, ``catalog_lite``) was withdrawn by the ADR-001 amendment
and must never parse successfully.

Note on ``test_legacy_is_kill_switch``: ADR-001's Validation section
describes this case in terms of ``SyncMotor.apply_row`` returning the
legacy outcome — that dispatch does not exist until PR4
(``motor/sync_motor.py::SyncMotor``). PR1 only ships the parser
(``runtime/engine_flag.py``), so this test is scoped to what PR1 owns:
``EngineMode.LEGACY`` parses correctly and is exposed as the value every
future dispatcher (PR4+) keys its kill-switch branch on.
"""

from __future__ import annotations

import pytest
from parkos_core.runtime.engine_flag import (
    EngineMode,
    InvalidEngineModeError,
    get_engine,
)


@pytest.fixture(autouse=True)
def _isolated_engine_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets a clean env var + a reset cache (60s TTL would leak otherwise)."""
    monkeypatch.delenv("PARKOS_SYNC_ENGINE", raising=False)
    from parkos_core.runtime import engine_flag

    engine_flag._reset_cache_for_tests()
    yield
    engine_flag._reset_cache_for_tests()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("legacy", EngineMode.LEGACY),
        ("catalog_admin", EngineMode.CATALOG_ADMIN),
        ("catalog_dian", EngineMode.CATALOG_DIAN),
        ("catalog", EngineMode.CATALOG),
        ("catalog_branch", EngineMode.CATALOG_BRANCH),
    ],
)
def test_parse_all_5_values(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: EngineMode
) -> None:
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", raw)
    assert get_engine() == expected


@pytest.mark.parametrize(
    "withdrawn",
    ["catalog_read", "catalog_dual", "catalog_only", "catalog_lite"],
)
def test_rejects_withdrawn_values(monkeypatch: pytest.MonkeyPatch, withdrawn: str) -> None:
    """The behaviour-flavoured enum was withdrawn by the ADR-001 amendment."""
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", withdrawn)
    with pytest.raises(InvalidEngineModeError):
        get_engine()


def test_exact_match_not_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """``catalog`` must not swallow ``catalog_admin``/``catalog_dian``/``catalog_branch``,
    and an unknown near-miss (``catalogue``) must be rejected outright."""
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog_admin")
    assert get_engine() != EngineMode.CATALOG
    assert get_engine() == EngineMode.CATALOG_ADMIN

    from parkos_core.runtime import engine_flag

    engine_flag._reset_cache_for_tests()
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalogue")
    with pytest.raises(InvalidEngineModeError):
        get_engine()


def test_legacy_is_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """``legacy`` parses to a distinct, dedicated value (D12 kill switch).

    Scoped to the parser (PR1); PR4's ``SyncMotor`` is the actual consumer
    that dispatches ``EngineMode.LEGACY`` to the legacy applier unchanged.
    """
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "legacy")
    mode = get_engine()
    assert mode is EngineMode.LEGACY
    assert mode.value == "legacy"
    # The kill switch must be reachable independent of every other mode.
    assert mode not in (
        EngineMode.CATALOG_ADMIN,
        EngineMode.CATALOG_DIAN,
        EngineMode.CATALOG,
        EngineMode.CATALOG_BRANCH,
    )


def test_unset_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unset ``PARKOS_SYNC_ENGINE`` is a fail-fast configuration error, not a silent default."""
    monkeypatch.delenv("PARKOS_SYNC_ENGINE", raising=False)
    with pytest.raises(InvalidEngineModeError):
        get_engine()
