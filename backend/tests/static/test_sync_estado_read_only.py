"""HU-F1.14 / T4.1 -- KD-SYNC-01 SELECT-only + KD-SYNC-02 read-only AST walks.

KD-SYNC-01 (SELECT-only invariant): the ``get_sync_estado`` handler MUST
NOT contain UPDATE/INSERT/DELETE on ``[A]`` tables ``prod.sync_log`` or
``prod.sync_queue`` outside the canonical helpers. KD-SYNC-02 extends
this to a source-level read-only AST walk:

  * NO ``update(SyncLog)``, ``update(SyncQueue)``, ``delete(SyncLog)``,
    ``delete(SyncQueue)`` calls anywhere in the handler body.
  * NO ``text("UPDATE prod.sync_log ...")`` or
    ``text("DELETE FROM prod.sync_queue ...")`` raw SQL.
  * NO ``await session.commit()`` -- the handler is purely read-only;
    the audit log (``prod.log_operaciones``) is never written from
    this endpoint (DEC-SYNC-09 + DEC-SYNC-06).

Pattern: source-level grep (mirrors F1.13
``test_arqueo_handler_no_update_on_a_tables.py``) + a focused AST walk
on ``await session.commit()`` (mirrors F1.13
``test_arqueo_handler_single_commit.py``).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"

_HANDLER_FILE = (
    _PARKOS_CORE_SRC / "parkos_core" / "api" / "v1" / "sync_estado.py"
)


# KD-SYNC-02: forbidden DML tokens (case-insensitive source-level scan).
# Source-level grep catches both ORM calls AND raw SQL literals.
_FORBIDDEN_DML_PATTERNS = [
    r"update\s*\(\s*SyncLog\s*\)",
    r"update\s*\(\s*SyncQueue\s*\)",
    r"delete\s*\(\s*SyncLog\s*\)",
    r"delete\s*\(\s*SyncQueue\s*\)",
    r"text\s*\(\s*['\"]UPDATE\s+prod\.sync_log",
    r"text\s*\(\s*['\"]UPDATE\s+prod\.sync_queue",
    r"text\s*\(\s*['\"]DELETE\s+FROM\s+prod\.sync_log",
    r"text\s*\(\s*['\"]DELETE\s+FROM\s+prod\.sync_queue",
    r"text\s*\(\s*['\"]INSERT\s+INTO\s+prod\.sync_log",
    r"text\s*\(\s*['\"]INSERT\s+INTO\s+prod\.sync_queue",
]


def _scan_source(path: Path, patterns: list[str]) -> list[tuple[int, str]]:
    """Return (line_no, pattern) hits, ignoring comments."""
    text = path.read_text(encoding="utf-8")
    hits: list[tuple[int, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for pat in patterns:
            if re.search(pat, line, flags=re.IGNORECASE):
                hits.append((line_no, pat))
    return hits


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _handler_node(tree: ast.Module, name: str) -> ast.AsyncFunctionDef:
    """Locate ``name`` coroutine in the parsed module."""
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(
        f"`{name}` coroutine not found in {_HANDLER_FILE.name}"
    )


def _collect_commit_lines(handler: ast.AsyncFunctionDef) -> list[int]:
    """Return 1-indexed line numbers of every ``await session.commit()``."""
    hits: list[int] = []
    for node in ast.walk(handler):
        if not isinstance(node, ast.Await):
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        func = value.func
        if not isinstance(func, ast.Attribute):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "session"):
            continue
        if func.attr != "commit":
            continue
        hits.append(node.lineno)
    return hits


# ---------------------------------------------------------------------------
# T4.1.1 -- KD-SYNC-01 SELECT-only (source-level grep)
# ---------------------------------------------------------------------------


def test_get_sync_estado_has_no_dml_on_sync_tables() -> None:
    """T4.1.1 / KD-SYNC-01: no UPDATE/DELETE/INSERT on sync_log or sync_queue.

    Source-level grep across the handler source. ORM calls
    (``update(SyncLog)``) AND raw SQL literals
    (``text("UPDATE prod.sync_log ...")``) are both rejected.
    The handler is purely read-only -- the only DB ops are the two
    SELECT helpers from :mod:`repo.sync_estado`.
    """
    hits = _scan_source(_HANDLER_FILE, _FORBIDDEN_DML_PATTERNS)
    assert not hits, (
        "KD-SYNC-01 violated: raw DML on [A] sync_log or sync_queue "
        "tables in get_sync_estado source:\n"
        + "\n".join(f"  line {ln}: {pat}" for ln, pat in hits)
        + "\nUse SELECT helpers from repo.sync_estado instead."
    )


# ---------------------------------------------------------------------------
# T4.1.2 -- KD-SYNC-02 read-only AST walk (no commit)
# ---------------------------------------------------------------------------


def test_get_sync_estado_does_not_commit_session() -> None:
    """T4.1.2 / KD-SYNC-02: ``get_sync_estado`` MUST NOT commit the session.

    The handler is purely read-only; ``await session.commit()`` is
    forbidden. The audit log (``prod.log_operaciones``) is never
    written from this endpoint (DEC-SYNC-06).
    """
    tree = _parse(_HANDLER_FILE)
    handler = _handler_node(tree, "get_sync_estado")
    hits = _collect_commit_lines(handler)
    assert not hits, (
        f"KD-SYNC-02 violated: `get_sync_estado` calls "
        f"`await session.commit()` at lines {hits}; the handler is "
        f"read-only and MUST NOT commit (DEC-SYNC-06)."
    )


# ---------------------------------------------------------------------------
# T4.1.3 -- KD-SYNC-02 defense in depth (no raw UPDATE/DELETE SQL literals)
# ---------------------------------------------------------------------------


def test_get_sync_estado_has_no_raw_update_delete_sql() -> None:
    """T4.1.3 / KD-SYNC-02: no raw ``UPDATE`` or ``DELETE`` SQL literals.

    Defense in depth: even if the handler were to use
    ``session.execute(text(...))``, the source-level grep on
    ``UPDATE prod.sync_*`` and ``DELETE FROM prod.sync_*`` catches
    it. SELECT statements ARE allowed (e.g. ``text("SELECT MAX(...)")``).
    """
    hits = _scan_source(
        _HANDLER_FILE,
        [
            r"text\s*\(\s*['\"]UPDATE\s+prod\.sync_",
            r"text\s*\(\s*['\"]DELETE\s+FROM\s+prod\.sync_",
            r"execute\s*\(\s*text\s*\(\s*['\"]UPDATE\s+prod\.sync_",
            r"execute\s*\(\s*text\s*\(\s*['\"]DELETE\s+FROM\s+prod\.sync_",
        ],
    )
    assert not hits, (
        "KD-SYNC-02 violated: raw UPDATE/DELETE SQL on sync_log or "
        "sync_queue in get_sync_estado source:\n"
        + "\n".join(f"  line {ln}: {pat}" for ln, pat in hits)
        + "\nUse repo.sync_estado typed SELECT helpers instead."
    )
