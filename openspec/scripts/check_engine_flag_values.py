"""
check_engine_flag_values.py — engine flag enum + withdrawn-literal guard
(T-PR14-005, ADR-001 Validation, design.md §2 Issue #3).

  1. ``parkos_core.runtime.engine_flag.EngineMode``'s literal values equal
     EXACTLY the 5 ratified D22 values: ``legacy``, ``catalog_admin``,
     ``catalog_dian``, ``catalog``, ``catalog_branch`` — no more, no fewer,
     no different spelling.
  2. The 4 withdrawn behaviour-flavoured literals (``catalog_read``,
     ``catalog_dual``, ``catalog_only``, ``catalog_lite``) appear NOWHERE
     under ``backend/`` or ``openspec/scripts/`` — except the 2 files that
     already legitimately test them as REJECTED values since PR1
     (``runtime/engine_flag.py``'s own ``_WITHDRAWN_VALUES`` frozenset, and
     ``tests/unit/test_engine_flag.py``'s parametrized rejection test).

Usage:
  python openspec/scripts/check_engine_flag_values.py [SRC_ROOT] [SCAN_ROOT]

  SRC_ROOT defaults to backend/packages/parkos_core/src (where
  ``engine_flag.py`` is imported from).
  SCAN_ROOT defaults to the repo root; the scan itself is always restricted
  to the ``backend/`` and ``openspec/scripts/`` subtrees under it (matching
  the requirement's exact scope) — passing a narrower SCAN_ROOT only
  shrinks, never widens, what gets scanned.

Exit codes:
  0 = enum matches exactly the 5 ratified values; zero unexpected
      withdrawn-literal hits
  1 = enum mismatch, or a withdrawn literal found outside the 2 allowed
      files
  2 = SRC_ROOT not found, or ``parkos_core.runtime.engine_flag`` cannot be
      imported
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_RATIFIED_VALUES: frozenset[str] = frozenset(
    {"legacy", "catalog_admin", "catalog_dian", "catalog", "catalog_branch"}
)

_WITHDRAWN_LITERALS: tuple[str, ...] = (
    "catalog_read",
    "catalog_dual",
    "catalog_only",
    "catalog_lite",
)

# Files that legitimately reference the withdrawn literals as either
# REJECTED values (PR1's own guard) or as this script's/its test's own
# search DATA (the exact tautological trap a scanner-writing agent must
# self-exclude from, or it flags its own docstring/fixture) — relative to
# the repo root, POSIX separators.
_ALLOWED_RELATIVE_PATHS: frozenset[str] = frozenset(
    {
        "backend/packages/parkos_core/src/parkos_core/runtime/engine_flag.py",
        "backend/tests/unit/test_engine_flag.py",
        "openspec/scripts/check_engine_flag_values.py",
        "backend/tests/static/test_engine_flag_no_withdrawn_literals.py",
    }
)

_SCAN_SUBTREES: tuple[str, ...] = ("backend", "openspec/scripts")

_EXCLUDED_DIR_NAMES: frozenset[str] = frozenset(
    {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
)


def _check_enum_values(src_root: Path) -> list[str]:
    """Rule 1 — the enum's literal value set matches the 5 ratified D22 values exactly."""
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    try:
        from parkos_core.runtime.engine_flag import EngineMode
    except ImportError as exc:
        return [f"could not import parkos_core.runtime.engine_flag: {exc}"]

    actual = frozenset(m.value for m in EngineMode)
    if actual != _RATIFIED_VALUES:
        detail = []
        missing = _RATIFIED_VALUES - actual
        extra = actual - _RATIFIED_VALUES
        if missing:
            detail.append(f"missing ratified value(s): {sorted(missing)}")
        if extra:
            detail.append(f"unexpected value(s): {sorted(extra)}")
        return [f"EngineMode enum mismatch — {'; '.join(detail)}"]
    return []


def _iter_scan_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for subtree in _SCAN_SUBTREES:
        root = repo_root / subtree
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIR_NAMES]
            for fname in filenames:
                if fname.endswith(".py"):
                    files.append(Path(dirpath) / fname)
    return files


def _check_withdrawn_literals(repo_root: Path) -> list[str]:
    """Rule 2 — zero withdrawn-literal hits under backend/ or openspec/scripts/,
    outside the allowed files."""
    violations: list[str] = []
    for path in _iter_scan_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        if rel in _ALLOWED_RELATIVE_PATHS:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(source.splitlines(), start=1):
            for literal in _WITHDRAWN_LITERALS:
                if literal in line:
                    violations.append(f"{rel}:{lineno}: contains withdrawn literal {literal!r}")
    return violations


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    default_src_root = repo_root / "backend" / "packages" / "parkos_core" / "src"
    src_root = Path(argv[1]) if len(argv) > 1 else default_src_root
    scan_root = Path(argv[2]) if len(argv) > 2 else repo_root

    if not src_root.is_dir():
        print(f"ERROR: source root not found: {src_root}", file=sys.stderr)
        return 2

    enum_violations = _check_enum_values(src_root)
    if enum_violations and enum_violations[0].startswith("could not import"):
        print(f"ERROR: {enum_violations[0]}", file=sys.stderr)
        return 2

    violations = enum_violations + _check_withdrawn_literals(scan_root)

    if not violations:
        print(
            "OK: EngineMode enum matches the 5 ratified D22 values; "
            "no withdrawn literals found under backend/ or openspec/scripts/."
        )
        return 0

    print(f"FAIL: {len(violations)} violation(s) found:")
    for v in violations:
        print(f"  {v}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
