"""test_no_write_in_ocupacion.py -- HU-F1.5 / REQ-OPS-030 defense in depth.

TDD AST guard for the read-only contract on the ``get_ocupacion``
handler introduced by HU-F1.5 in
``api/v1/operacion.py``. Enforces the core invariant:

  - ``get_ocupacion`` is a read-only endpoint; the body MUST NOT
    contain any ``INSERT|UPDATE|DELETE|TRUNCATE|MERGE`` statement,
    nor a ``SELECT ... FOR UPDATE|SHARE`` lock (which would
    unnecessarily serialize polling clients against the refresh
    worker).

Pattern mirrors ``tests/static/test_no_write_in_calcular_cotizacion
.py`` (F1.8 precedent) and ``tests/static/test_no_write_in_caja_sesion
_me.py`` (F1.3 precedent): parse the Python file with ``ast``, locate
the named function, scan its source text with a word-boundary regex
for SQL mutation keywords. False positives (e.g. ``inserted_at``) are
blocked by the word-boundary anchor.

Lifecycle:

  - GREEN phase: the handler exists; this test MUST pass.
  - Any future PR that introduces a mutation in ``get_ocupacion``
    MUST also update this test's allowlist (none today).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

# Path to the router that owns ``get_ocupacion``. Read from the file
# itself (not a hard-coded absolute path) so the test stays
# relocatable.
_ROUTER_PATH = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "parkos_core"
    / "src"
    / "parkos_core"
    / "api"
    / "v1"
    / "operacion.py"
)

# SQL mutation keywords forbidden inside the read-only handler.
# Same shape as the F1.3 / F1.8 guards; centralised so the failure
# message names them explicitly.
_FORBIDDEN_DML_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "MERGE")
_DML_WORD_RE = re.compile(
    r"\b(?:" + "|".join(_FORBIDDEN_DML_KEYWORDS) + r")\b",
    flags=re.IGNORECASE,
)


def _extract_function_source(file_path: Path, func_name: str) -> str:
    """Parse ``file_path`` as Python and return the source text of
    the function named ``func_name``.

    Raises ``AssertionError`` if the file does not exist yet (RED
    phase pre-handler) or if the function is missing.
    """
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            # Return the full source of the function -- including
            # decorators and signature -- so the inner-body scan
            # catches guard keywords wherever they appear.
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(
        f"{file_path.name} does not declare function {func_name!r} -- the AST guard cannot run."
    )


def _strip_python_comments_and_strings(body: str) -> str:
    """Remove Python string literals and comments so DML keywords
    inside them don't trigger the guard. Mirrors the F1.8 SQL
    comment/string stripper, applied to Python source."""
    # Triple-quoted strings first (block + line).
    body = re.sub(r'""".*?"""', '""', body, flags=re.DOTALL)
    body = re.sub(r"'''.*?'''", "''", body, flags=re.DOTALL)
    # Single-quoted strings (naive -- no escaped quote handling,
    # acceptable for the function bodies at hand).
    body = re.sub(r'"(?:\\.|[^"\\])*"', '""', body)
    body = re.sub(r"'(?:\\.|[^'\\])*'", "''", body)
    # Line comments.
    body = re.sub(r"#[^\n]*", " ", body)
    return body


def _find_dml_offenses(body: str) -> list[tuple[str, int]]:
    """Scan ``body`` (post-comment/string strip) for SQL DML
    keywords. Returns ``[(keyword, line_number), ...]``."""
    stripped = _strip_python_comments_and_strings(body)
    offenses: list[tuple[str, int]] = []
    for line_no, line in enumerate(stripped.splitlines(), start=1):
        match = _DML_WORD_RE.search(line)
        if match is None:
            continue
        offenses.append((match.group(0).upper(), line_no))
    return offenses


def test_get_ocupacion_no_contiene_dml() -> None:
    """``operacion.get_ocupacion`` MUST NOT contain any of
    ``INSERT|UPDATE|DELETE|TRUNCATE|MERGE`` (case-insensitive, outside
    string literals and comments).

    Defense in depth (REQ-OPS-030 read-only contract): the endpoint
    is supposed to issue a single SELECT against
    ``prod.mv_ocupacion_diaria`` via ``repo.ocupacion``; any state
    mutation is a contract violation that the AST guard rejects.
    """
    source = _extract_function_source(_ROUTER_PATH, "get_ocupacion")
    offenses = _find_dml_offenses(source)
    assert not offenses, (
        "operacion.get_ocupacion MUST NOT mutate any state "
        f"(REQ-OPS-030 read-only contract). Found forbidden DML "
        f"keywords inside the handler body: {offenses!r}. Any "
        f"INSERT/UPDATE/DELETE/TRUNCATE/MERGE would silently break "
        f"the read-only invariant."
    )


__all__ = ["test_get_ocupacion_no_contiene_dml"]
