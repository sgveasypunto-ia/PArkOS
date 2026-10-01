"""Unit tests for entry_seed.py's argument-resolution fallback.

Security fix under test: `--database-url` is no longer a required CLI flag
(a DSN carries the Postgres superuser password in plain text, and a
required CLI argument puts it in the process argv, visible to Windows
Event ID 4688/Sysmon/EDR). It now falls back to the `DATABASE_URL`
environment variable - same pattern `installer/parkos-installer.ps1`'s
`Invoke-MigrationsAndSeed` already uses for `migrate.exe`.

No prior test coverage exists for `entry_seed.py` (it is a minimal
PyInstaller entry-point shim); this file is deliberately narrow - it only
covers the new argument-resolution fallback, loading the module directly
from its path since it lives outside the `parkos_core` package tree and
its top-level imports (only `argparse`/`os`/`sys`/`uuid`/`httpx`) are all
safe to import without a running Postgres/API.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ENTRY_SEED_PATH = Path(__file__).parent / "entry_seed.py"
_spec = importlib.util.spec_from_file_location("entry_seed", _ENTRY_SEED_PATH)
assert _spec is not None and _spec.loader is not None
entry_seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entry_seed)


def test_resolve_database_url_prefers_the_cli_flag_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://from-env")
    assert entry_seed._resolve_database_url("postgresql://from-cli") == "postgresql://from-cli"


def test_resolve_database_url_falls_back_to_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://from-env")
    assert entry_seed._resolve_database_url(None) == "postgresql://from-env"


def test_resolve_database_url_returns_none_when_neither_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert entry_seed._resolve_database_url(None) is None
