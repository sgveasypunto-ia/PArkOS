"""test_no_sync_back_event_literals.py — T-PR9-007.

D1-rev (design.md §0 amendment log #1) dropped ``prod.sync_back_events``,
``SyncBackEventEmitter``, and the ``operacion='sync_back_event'`` protocol
in full. Nothing in ``dian/cloud/dispatcher.py`` or ``jobs/sync_cloud.py``
may reference these withdrawn concepts, or the withdrawn D1-original
numbering vocabulary (``numero_temporal`` / ``numero_oficial`` /
``preliminar``) — not in code, not in comments/docstrings (a stray
docstring mention is exactly how a withdrawn design silently survives a
refactor).

R21 (early check; PR14 T-PR14-004 is the full repo-wide gate).
"""
from __future__ import annotations

from pathlib import Path

import pytest

_PARKOS_CORE_SRC = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "parkos_core"
    / "src"
    / "parkos_core"
)

_FORBIDDEN_LITERALS: tuple[str, ...] = (
    "sync_back_event",
    "SyncBackEvent",
    "numero_temporal",
    "numero_oficial",
    "preliminar",
)

_CHECKED_FILES: tuple[Path, ...] = (
    _PARKOS_CORE_SRC / "dian" / "cloud" / "dispatcher.py",
    _PARKOS_CORE_SRC / "jobs" / "sync_cloud.py",
)


@pytest.mark.parametrize("path", _CHECKED_FILES, ids=lambda p: p.name)
@pytest.mark.parametrize("literal", _FORBIDDEN_LITERALS)
def test_no_forbidden_literal(path: Path, literal: str) -> None:
    assert path.is_file(), f"expected file not found: {path}"
    source = path.read_text(encoding="utf-8")
    assert literal not in source, (
        f"{path.name} contains the withdrawn D1-original literal {literal!r} "
        "(design.md §0 amendment #1 — D1-rev dropped this in full)"
    )
