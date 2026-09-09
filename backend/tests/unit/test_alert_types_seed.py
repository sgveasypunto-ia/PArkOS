"""test_alert_types_seed.py — T-PR8-004, REQ-OPS-016 (addendum #5).

Grep-based CI guard: the third-party DIAN provider's literal name must
never appear in any ``alert_types`` seed row, source file, log format
string, or DB row (design.md §2 Issue #6's "Amended — seed values use
generic identifiers only").

**Scope decision (documented, not a whole-tree scan).** REQ-OPS-016's
"Given" clause names ``prod.alert_types`` seed data and "every ``tipo_alerta``
string literal in ``parkos_core/``" — i.e. the alert-type identifier
surface, not literally every byte under ``parkos_core/``. A whole-tree scan
would immediately false-positive against
``dian/cloud/dian_providers/factus.py`` (T-PR11-04, an already-shipped,
out-of-PR8-scope adapter that legitimately names the real DIAN provider it
integrates with — the vendor's actual API contract). This test therefore
scans the well-defined set of files this PR's ``alert_types`` feature
actually owns, plus the seeded DB rows, which is the surface REQ-OPS-016 is
actually protecting.
"""
from __future__ import annotations

from pathlib import Path

import pytest

# The third-party DIAN provider's literal name (lowercase for a
# case-insensitive check) — the ONE identifier this test exists to keep out
# of the alert_types surface. Deliberately held as data, not a docstring
# mention elsewhere in this file, to keep the grep target unambiguous.
_BANNED_VENDOR_NAME = "factus"

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = _REPO_ROOT / "backend"
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src" / "parkos_core"

# Every file this PR's alert_types feature owns (T-PR8-001..009). NOT a
# whole-``parkos_core/`` scan — see module docstring.
_ALERT_TYPES_OWNED_FILES: tuple[Path, ...] = (
    _PARKOS_CORE_SRC / "repo" / "alert_types.py",
    _PARKOS_CORE_SRC / "models" / "A" / "alert_types.py",
    _PARKOS_CORE_SRC / "sync" / "hooks" / "impls" / "alert_emitter.py",
    _PARKOS_CORE_SRC / "sync" / "motor" / "dependency_buffer.py",
    _BACKEND_ROOT
    / "packages" / "parkos_core" / "migrations" / "versions" / "0013_add_alert_types.py",
    _REPO_ROOT / "infra" / "scripts" / "seed_alert_types.py",
)


@pytest.mark.parametrize("path", _ALERT_TYPES_OWNED_FILES, ids=lambda p: p.name)
def test_no_vendor_name_in_alert_types_owned_file(path: Path) -> None:
    assert path.is_file(), f"expected file does not exist: {path}"
    content = path.read_text(encoding="utf-8").lower()
    assert _BANNED_VENDOR_NAME not in content, (
        f"{path}: contains the banned third-party DIAN provider name "
        f"(REQ-OPS-016, addendum #5) — use a generic identifier instead"
    )


def test_no_vendor_name_in_seed_row_constants() -> None:
    """The in-memory seed constants (both the migration's and the standalone
    script's) never carry the vendor name in any field."""
    import sys

    sys.path.insert(0, str(_REPO_ROOT / "infra" / "scripts"))
    from seed_alert_types import SEED_ROWS  # type: ignore[import-not-found]

    for tipo_alerta, descripcion, severity in SEED_ROWS:
        for field in (tipo_alerta, descripcion, severity):
            assert _BANNED_VENDOR_NAME not in field.lower(), (
                f"seed row {tipo_alerta!r} contains the banned vendor name in {field!r}"
            )


async def test_no_vendor_name_in_alert_types_db_rows(pg_engine, alembic_upgrade) -> None:
    """No persisted ``prod.alert_types`` row carries the vendor name."""
    from sqlalchemy import text

    async with pg_engine.connect() as conn:
        rows = (
            await conn.execute(text("SELECT tipo_alerta, descripcion FROM prod.alert_types"))
        ).all()

    for tipo_alerta, descripcion in rows:
        assert _BANNED_VENDOR_NAME not in tipo_alerta.lower()
        if descripcion:
            assert _BANNED_VENDOR_NAME not in descripcion.lower()
