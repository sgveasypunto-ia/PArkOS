"""test_check_drain_green.py — T-PR11-004 acceptance (REQ-OPS-013, REQ-CUT-002).

``openspec/scripts/check_drain.py`` — the stage-4 drain gate — exits 0 when
``prod.sync_queue`` has zero ``estado='pendiente'`` rows, exits 1 (printing
the count + elapsed seconds) otherwise, and exits 2 on a usage/connection
error. Loaded via ``importlib`` from its file path (same precedent as
``test_check_sync_queue_carveout_green.py`` — the script lives outside the
``parkos_core`` package).

Mock-based tests pin ``main()``'s exit-code contract deterministically;
the real-DB test proves ``count_pending`` executes the documented SQL
against a genuine Postgres container without asserting an exact ambient
count (the session-scoped test DB, ``tests/conftest.py``, may carry pending
rows left by unrelated tests in the same session).
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_PATH = _REPO_ROOT / "openspec" / "scripts" / "check_drain.py"


def _load_checker_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_drain", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker() -> ModuleType:
    return _load_checker_module()


def _fake_conn(count: int) -> MagicMock:
    """A ``psycopg.connect(...)`` context-manager double returning ``count``."""
    cursor = MagicMock()
    cursor.fetchone.return_value = (count,)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn


class TestCheckDrainExitCodes:
    def test_exits_0_when_zero_pending(
        self, checker: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        monkeypatch.setattr(
            checker.psycopg, "connect", MagicMock(return_value=_fake_conn(0))
        )
        exit_code = checker.main(["--database-url", "postgresql://fake/db"])
        assert exit_code == 0
        assert "OK" in capsys.readouterr().out

    def test_exits_1_with_count_and_elapsed_when_pending(
        self, checker: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        monkeypatch.setattr(
            checker.psycopg, "connect", MagicMock(return_value=_fake_conn(42))
        )
        started_at = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
        exit_code = checker.main(
            ["--database-url", "postgresql://fake/db", "--since", started_at]
        )
        assert exit_code == 1
        out = capsys.readouterr().out
        assert "FAIL" in out
        assert "42" in out
        assert "elapsed=" in out

    def test_exits_2_when_no_dsn_available(
        self, checker: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        exit_code = checker.main([])
        assert exit_code == 2

    def test_exits_2_on_connection_failure(
        self, checker: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*args: object, **kwargs: object) -> None:
            raise checker.psycopg.OperationalError("connection refused")

        monkeypatch.setattr(checker.psycopg, "connect", _raise)
        exit_code = checker.main(["--database-url", "postgresql://fake/db"])
        assert exit_code == 2


def test_count_pending_matches_real_postgres(
    pg_dsn: str, alembic_upgrade, checker: ModuleType
) -> None:
    """The script's SQL executes cleanly against a real container and its
    result matches an independent, hand-written count query."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn:
        script_count = checker.count_pending(conn)

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM prod.sync_queue WHERE estado='pendiente'")
        (independent_count,) = cur.fetchone()

    assert script_count == independent_count
