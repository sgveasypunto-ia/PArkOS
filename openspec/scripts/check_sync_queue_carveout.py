"""
check_sync_queue_carveout.py — AST guard for the ``prod.sync_queue`` carve-out.

REQ-14-A-SYNC-FACADE / R-D3 / R8 / REQ-OPS-004: ``prod.sync_queue`` is the
one carved-out ``[A]`` table whose worker role (``rol_app``) keeps
UPDATE/DELETE grants (every other ``[A]`` table is append-only, enforced by
a DB-side ``REVOKE UPDATE, DELETE`` + trigger). The Python-side mirror of
that carve-out is: **only** ``parkos_core/repo/sync_queue.py`` may issue a
SQLAlchemy ``update(SyncQueue)`` / ``delete(SyncQueue)`` statement. Any other
module that does so has bypassed the column whitelist
(``ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS``, T-PR1-012) and the audit trail
``sync_queue.py`` centralizes.

This script AST-walks every ``.py`` file under the given source root
(default: ``backend/packages/parkos_core/src``) and flags the file
carve-out violation:

- a ``sqlalchemy.update(SyncQueue)`` or ``sqlalchemy.delete(SyncQueue)``
  call in any file other than ``repo/sync_queue.py``. Reads
  (``select(SyncQueue)``, plain attribute access) are allowed everywhere.

``ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS`` (T-PR1-012) is imported from
``parkos_core.repo.sync_queue`` — never hardcoded here — and reported in
the script's header output as the column whitelist this carve-out
protects; PR1 does not extend the AST check into a per-column enforcement
pass (that would touch ``repo/sync_queue.py``'s existing write paths,
which are out of PR1's scope). A future PR may tighten this into a
column-level check once that path is revisited.

Usage:
  python openspec/scripts/check_sync_queue_carveout.py [SRC_ROOT]

  Exit codes:
    0 = no violation found
    1 = at least one violation found (printed as ``file:line: reason``)
    2 = SRC_ROOT does not exist, or the source tree cannot be imported
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

CARVEOUT_FILE_SUFFIX = "repo/sync_queue.py"

_WRITE_FUNCS = {"update", "delete"}


@dataclass(frozen=True)
class Violation:
    path: Path
    lineno: int
    reason: str

    def __str__(self) -> str:
        return f"{self.path}:{self.lineno}: {self.reason}"


def _is_sync_queue_writer_call(node: ast.Call) -> bool:
    """True when ``node`` is ``update(SyncQueue)`` / ``delete(SyncQueue)``
    (bare name or ``sqlalchemy.update(SyncQueue)`` attribute-call form)."""
    func = node.func
    func_name: str | None = None
    if isinstance(func, ast.Name):
        func_name = func.id
    elif isinstance(func, ast.Attribute):
        func_name = func.attr
    if func_name not in _WRITE_FUNCS:
        return False
    if not node.args:
        return False
    first = node.args[0]
    return isinstance(first, ast.Name) and first.id == "SyncQueue"


def _is_carveout_file(path: Path) -> bool:
    return path.as_posix().endswith(CARVEOUT_FILE_SUFFIX)


def check_source(src_root: Path) -> list[Violation]:
    """Walk every ``.py`` file under ``src_root`` and return all violations."""
    violations: list[Violation] = []
    for path in sorted(src_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as e:
            violations.append(Violation(path, 1, f"failed to parse: {e}"))
            continue

        is_carveout = _is_carveout_file(path)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_sync_queue_writer_call(node) and not is_carveout:
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        "UPDATE/DELETE on SyncQueue outside repo/sync_queue.py "
                        "(carve-out violation, REQ-14-A-SYNC-FACADE)",
                    )
                )

    return violations


def _load_allowed_columns() -> frozenset[str]:
    """Import the real whitelist (T-PR1-012) — never a hardcoded duplicate here."""
    from parkos_core.repo.sync_queue import ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS

    return ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS


def main(argv: list[str]) -> int:
    src_root = Path(argv[1]) if len(argv) > 1 else Path("backend/packages/parkos_core/src")
    if not src_root.is_dir():
        print(f"ERROR: source root not found: {src_root}", file=sys.stderr)
        return 2

    try:
        allowed_columns = _load_allowed_columns()
    except ImportError as e:
        print(
            f"ERROR: could not import parkos_core.repo.sync_queue "
            f"(is parkos_core installed / on PYTHONPATH?): {e}",
            file=sys.stderr,
        )
        return 2

    print(f"Scanning {src_root} for prod.sync_queue carve-out violations...")
    print(f"Allowed UPDATE columns (from parkos_core.repo.sync_queue): {sorted(allowed_columns)}")
    print()

    violations = check_source(src_root)

    if not violations:
        print("OK: no sync_queue carve-out violations found.")
        return 0

    print(f"FAIL: {len(violations)} violation(s) found:")
    for v in violations:
        print(f"  {v}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
