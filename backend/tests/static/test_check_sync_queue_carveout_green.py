"""test_check_sync_queue_carveout_green.py — T-PR1-011.

Green-path test: ``openspec/scripts/check_sync_queue_carveout.py`` must
exit 0 against the current ``parkos_core`` source tree. A companion test
proves the checker actually detects a violation (not a vacuous pass) by
running it against an injected fixture file in an isolated temp tree.

The script lives outside the ``parkos_core`` package (it is a repo-wide
OpenSpec tooling script, not shipped in the wheel), so it is loaded here
via ``importlib`` from its file path rather than a normal package import.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_PATH = _REPO_ROOT / "openspec" / "scripts" / "check_sync_queue_carveout.py"
_REAL_SRC_ROOT = _REPO_ROOT / "backend" / "packages" / "parkos_core" / "src"


def _load_checker_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_sync_queue_carveout", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker() -> ModuleType:
    return _load_checker_module()


def test_carveout_check_exits_0_against_real_source(checker: ModuleType) -> None:
    """The real ``parkos_core`` source tree carries zero carve-out violations."""
    assert _REAL_SRC_ROOT.is_dir(), f"expected real src root at {_REAL_SRC_ROOT}"
    violations = checker.check_source(_REAL_SRC_ROOT)
    assert violations == [], f"unexpected carve-out violations: {violations}"


def test_carveout_check_flags_injected_violation(checker: ModuleType, tmp_path: Path) -> None:
    """A ``delete(SyncQueue)`` call outside ``repo/sync_queue.py`` must be flagged
    with a ``file:line`` violation."""
    offending_dir = tmp_path / "jobs"
    offending_dir.mkdir()
    offending_file = offending_dir / "rogue_worker.py"
    offending_file.write_text(
        textwrap.dedent(
            """\
            from sqlalchemy import delete
            from ..models.A.sync_queue import SyncQueue


            async def purge_stale(session):
                await session.execute(delete(SyncQueue).where(SyncQueue.estado == "fallido"))
            """
        ),
        encoding="utf-8",
    )

    # A carve-out-file sibling must NOT be flagged, proving the check is
    # scoped by path, not by "any delete(SyncQueue) anywhere".
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "sync_queue.py").write_text(
        textwrap.dedent(
            """\
            from sqlalchemy import delete
            from ..models.A.sync_queue import SyncQueue


            async def _purge(session):
                await session.execute(delete(SyncQueue))
            """
        ),
        encoding="utf-8",
    )

    violations = checker.check_source(tmp_path)

    assert len(violations) == 1
    (violation,) = violations
    assert violation.path == offending_file
    assert violation.lineno == 6
    assert "carve-out violation" in violation.reason
