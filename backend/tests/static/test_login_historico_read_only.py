"""HU-F1.15 / T4.1 -- KD-LOGIN-01 + KD-LOGIN-02 read-only AST walks.

KD-LOGIN-01 (SELECT-only invariant): the ``get_login_historico``
handler MUST NOT contain UPDATE/INSERT/DELETE on ``prod.login`` (an
[L-S] table) outside the canonical helpers. KD-LOGIN-02 extends this
to a source-level read-only AST walk:

  * NO ``update(Login)``, ``delete(Login)``, ``session.execute(update
    (Login))``, ``session.execute(delete(Login))`` calls anywhere in
    the handler body.
  * NO ``text("UPDATE prod.login ...")`` or ``text("DELETE FROM prod
    .login ...")`` raw SQL.
  * NO ``await session.commit()`` -- the handler is purely read-only;
    the audit log (``prod.log_operaciones``) is never written from
    this endpoint.

Pattern: source-level grep (mirrors F1.5 PR5-016
``test_no_raw_dml_on_a_tables.py`` + F1.14
``test_sync_estado_read_only.py``) + a focused AST walk on
``await session.commit()`` (mirrors F1.13
``test_arqueo_handler_single_commit.py`` + F1.14
``test_get_sync_estado_does_not_commit_session``).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"

_HANDLER_FILE = (
    _PARKOS_CORE_SRC / "parkos_core" / "api" / "v1" / "usuarios_login.py"
)


# KD-LOGIN-01 + KD-LOGIN-02: forbidden DML tokens (case-insensitive
# source-level scan). Source-level grep catches both ORM calls AND raw
# SQL literals -- belt-and-suspenders for the SELECT-only invariant.
_FORBIDDEN_DML_PATTERNS = [
    r"update\s*\(\s*Login\s*\)",
    r"delete\s*\(\s*Login\s*\)",
    r"text\s*\(\s*['\"]UPDATE\s+prod\.login",
    r"text\s*\(\s*['\"]DELETE\s+FROM\s+prod\.login",
    r"text\s*\(\s*['\"]INSERT\s+INTO\s+prod\.login",
    r"text\s*\(\s*['\"]TRUNCATE\s+prod\.login",
    r"text\s*\(\s*['\"]MERGE\s+INTO\s+prod\.login",
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
# T4.1.1 -- KD-LOGIN-01 SELECT-only (source-level grep)
# ---------------------------------------------------------------------------


def test_get_login_historico_has_no_dml_on_login() -> None:
    """T4.1.1 / KD-LOGIN-01: no UPDATE/DELETE/INSERT on ``prod.login``.

    Source-level grep across the handler source. ORM calls
    (``update(Login)``) AND raw SQL literals
    (``text("UPDATE prod.login ...")``) are both rejected. The
    handler is purely read-only -- the only DB op is the single
    SELECT helper from :mod:`repo.login_historico`.
    """
    hits = _scan_source(_HANDLER_FILE, _FORBIDDEN_DML_PATTERNS)
    assert not hits, (
        "KD-LOGIN-01 violated: raw DML on prod.login in "
        "get_login_historico source:\n"
        + "\n".join(f"  line {ln}: {pat}" for ln, pat in hits)
        + "\nUse the SELECT helper from repo.login_historico instead."
    )


# ---------------------------------------------------------------------------
# T4.1.2 -- KD-LOGIN-02 read-only AST walk (no commit)
# ---------------------------------------------------------------------------


def test_get_login_historico_does_not_commit_session() -> None:
    """T4.1.2 / KD-LOGIN-02: ``get_login_historico`` MUST NOT commit the session.

    The handler is purely read-only; ``await session.commit()`` is
    forbidden. The audit log (``prod.log_operaciones``) is never
    written from this endpoint (DEC-LOGIN-05 + DEC-LOGIN-09).
    """
    tree = _parse(_HANDLER_FILE)
    handler = _handler_node(tree, "get_login_historico")
    hits = _collect_commit_lines(handler)
    assert not hits, (
        f"KD-LOGIN-02 violated: `get_login_historico` calls "
        f"`await session.commit()` at lines {hits}; the handler is "
        f"read-only and MUST NOT commit."
    )


# ---------------------------------------------------------------------------
# T4.1.3 -- KD-LOGIN-01 defense in depth (no raw UPDATE/DELETE SQL literals)
# ---------------------------------------------------------------------------


def test_get_login_historico_has_no_raw_update_delete_sql() -> None:
    """T4.1.3 / KD-LOGIN-01: no raw ``UPDATE`` / ``DELETE`` / ``INSERT`` SQL literals.

    Defense in depth: even if the handler were to use
    ``session.execute(text(...))``, the source-level grep on
    ``UPDATE prod.login``, ``DELETE FROM prod.login``, and
    ``INSERT INTO prod.login`` catches it. SELECT statements ARE
    allowed (e.g. ``text("SELECT MAX(...)")``) but the handler
    delegates all DB access to :mod:`repo.login_historico` anyway.
    """
    hits = _scan_source(
        _HANDLER_FILE,
        [
            r"text\s*\(\s*['\"]UPDATE\s+prod\.login",
            r"text\s*\(\s*['\"]DELETE\s+FROM\s+prod\.login",
            r"text\s*\(\s*['\"]INSERT\s+INTO\s+prod\.login",
        ],
    )
    assert not hits, (
        "KD-LOGIN-01 violated: raw UPDATE/DELETE/INSERT SQL on "
        "prod.login in get_login_historico source:\n"
        + "\n".join(f"  line {ln}: {pat}" for ln, pat in hits)
        + "\nUse repo.login_historico typed SELECT helpers instead."
    )
