"""Unit tests for check (h3) of openspec/scripts/check_schema_match.py.

A fake cursor stands in for Postgres, so no Docker is needed. Regression for
two defects: ``to_regclass`` always returns one row (``(None,)`` when the
relation is missing), and migration 0018 names two DEFAULT partitions
``<parent>_p_default`` instead of ``<parent>_default``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "openspec" / "scripts" / "check_schema_match.py"
_spec = importlib.util.spec_from_file_location("check_schema_match_h3_under_test", _SCRIPT)
assert _spec is not None
assert _spec.loader is not None
csm = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = csm
_spec.loader.exec_module(csm)


class FakeCursor:
    """Answers ``to_regclass`` and ``count(*)`` from a {partition: rows} map."""

    def __init__(self, partitions: dict[str, int]) -> None:
        self._partitions = partitions
        self._row: tuple | None = None

    def execute(self, query: str, params: tuple | None = None) -> None:
        if "to_regclass" in query:
            assert params is not None
            name = params[0].split(".", 1)[1]
            self._row = (f"prod.{name}" if name in self._partitions else None,)
        else:
            name = query.split('"."')[1].rstrip('"')
            self._row = (self._partitions[name],)

    def fetchone(self) -> tuple | None:
        return self._row


PARENTS = [
    ("pairing_tokens", "fecha_retencion_hasta"),
    ("revoked_sync_jwts", "fecha_retencion_hasta"),
]


def _run(partitions: dict[str, int]):
    diff = csm.Diff()
    csm.check_default_partitions(FakeCursor(partitions), "prod", PARENTS, diff)
    return diff


def test_missing_default_partitions_do_not_crash_nor_fail() -> None:
    assert _run({}).ok


def test_empty_p_default_partitions_pass() -> None:
    assert _run({"pairing_tokens_p_default": 0, "revoked_sync_jwts_p_default": 0}).ok


def test_rows_in_p_default_are_detected_and_named() -> None:
    diff = _run({"pairing_tokens_p_default": 0, "revoked_sync_jwts_p_default": 3})
    assert not diff.ok
    assert len(diff.issues) == 1
    assert "revoked_sync_jwts_p_default" in diff.issues[0]


def test_rows_in_plain_default_are_detected() -> None:
    diff = _run({"revoked_sync_jwts_default": 1})
    assert not diff.ok
    assert "revoked_sync_jwts_default" in diff.issues[0]


def test_allowlisted_legacy_default_passes() -> None:
    assert _run({"pairing_tokens_default": 8}).ok


def test_p_default_is_never_allowlisted() -> None:
    assert "pairing_tokens_p_default" not in csm.DEFAULT_PARTITION_LEGACY
    assert not _run({"pairing_tokens_p_default": 1}).ok


@pytest.mark.parametrize("parent", ["salidas", "pairing_tokens"])
def test_candidates_cover_both_suffixes(parent: str) -> None:
    assert csm.default_partition_candidates(parent) == (f"{parent}_default", f"{parent}_p_default")
