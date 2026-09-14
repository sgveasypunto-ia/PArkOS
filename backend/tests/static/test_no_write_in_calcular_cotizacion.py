"""test_no_write_in_calcular_cotizacion.py -- HU-F1.8 / REQ-OPS-025.

TDD AST guard for the PL/pgSQL function ``prod.calcular_cotizacion``
introduced by Alembic migration ``0022_create_calcular_cotizacion.py``.
Enforces the core invariant of REQ-OPS-025: the function body MUST
NOT contain any of the SQL mutation keywords ``INSERT``, ``UPDATE``,
``DELETE``, ``TRUNCATE``, or ``MERGE`` -- case-insensitive, outside
string literals and SQL comments. This is the defense-in-depth
contract: a future dev cannot silently make the function stateful.

**Volatility classification (apply-time correction, design.md §4 /
KD-1).** The original REQ-OPS-025 letter required ``STABLE``. The
apply phase discovered that Postgres refuses ``SELECT ... FOR SHARE``
from inside a ``STABLE`` function (see ``FeatureNotSupportedError:
SELECT FOR SHARE is not allowed in a non-volatile function``), and
KD-1 mandates the lock. The function is therefore declared
``VOLATILE`` -- a documented deviation in the migration docstring.
This guard accepts both ``STABLE`` and ``VOLATILE``; the read-only
contract is enforced by the no-DML check below, not by the volatility
keyword.

The invariants are checked by parsing the migration file as Python
(``ast`` module) and walking the ``op.execute(...)`` triple-quoted
string literal that carries the ``CREATE OR REPLACE FUNCTION`` body.
Token matching uses a word-boundary regex to avoid false positives
(e.g. a column named ``inserted_at`` would NOT trigger the
``INSERT`` rejection).

Lifecycle:

  - Before the migration exists, ``ast.parse`` raises ``FileNotFoundError``
    on the migration file (the test does not catch it; pytest reports
    a collection error). RED phase starts here.
  - Once the migration lands (T-HU-F1.8-5, GREEN), this test MUST
    pass without any mutation in the function body.
  - Any future PR that introduces a mutation in the function body
    MUST also update this test's allowlist (none today).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "parkos_core"
    / "migrations"
    / "versions"
    / "0022_create_calcular_cotizacion.py"
)

# SQL mutation keywords we forbid inside the function body. Kept in
# one place so the test failure message names them explicitly.
_FORBIDDEN_DML_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "MERGE")

# Word-boundary pattern — case-insensitive. Matches the keyword as a
# standalone token (not a substring of an identifier like
# ``inserted_at`` or ``update_count``).
_DML_WORD_RE = re.compile(
    r"\b(?:" + "|".join(_FORBIDDEN_DML_KEYWORDS) + r")\b",
    flags=re.IGNORECASE,
)


def _extract_op_execute_sql(source: str) -> str:
    """Parse ``source`` as Python and return the first triple-quoted
    string literal passed to ``op.execute(...)``.

    The migration declares exactly one ``op.execute(...)`` triple-quoted
    call that carries the ``CREATE OR REPLACE FUNCTION ... GRANT EXECUTE``
    body. If the migration ever splits this across multiple
    ``op.execute`` calls, this helper would need to be extended to
    concatenate them -- for now, ONE call is the contract.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "execute"):
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
            continue
        return first_arg.value
    raise AssertionError(
        "0022_create_calcular_cotizacion.py does not contain any "
        "op.execute(\"...\") string literal — the AST guard cannot run."
    )


def _strip_sql_comments_and_strings(body: str) -> str:
    """Remove SQL line comments (``-- ...``), block comments
    (``/* ... */``), and string literals (``'...'`` and ``\"...\"``)
    from the body so DML keywords inside them don't trigger the
    guard. Token matching runs on the stripped text only.
    """
    # Block comments /* ... */ — non-greedy across newlines.
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.DOTALL)
    # Line comments -- to end-of-line. PostgreSQL accepts ``--`` and
    # ``/* */``; ``#`` is not a SQL comment so we don't strip it.
    body = re.sub(r"--[^\n]*", " ", body)
    # Single-quoted strings — naive (no escaped quote handling).
    # Good enough for the migration body, which carries no escaped
    # quotes inside string literals.
    body = re.sub(r"'(?:''|[^'])*'", "''", body)
    # Double-quoted identifiers — keep them (no DML keyword hiding
    # in our identifiers, but stay defensive).
    body = re.sub(r'"(?:[^"])*"', '""', body)
    return body


def _check_volatility_declaration(sql: str) -> str | None:
    """Return an error message if the function declaration does NOT
    declare a recognized volatility (``STABLE`` or ``VOLATILE``).

    Both classifications are accepted (the original REQ-OPS-025 letter
    mandated ``STABLE``; the apply phase relaxed this to permit
    ``VOLATILE`` because KD-1's ``SELECT ... FOR SHARE`` requires it --
    see module docstring). The header may carry the keyword on its
    own line OR inline with ``LANGUAGE plpgsql``.
    """
    header_end = sql.find("$$")
    if header_end == -1:
        return (
            "could not locate the opening ``$$`` of the CREATE FUNCTION "
            "body — the AST guard cannot verify the volatility declaration."
        )
    header = sql[:header_end]
    has_stable = re.search(r"\bSTABLE\b", header, flags=re.IGNORECASE) is not None
    has_volatile = re.search(r"\bVOLATILE\b", header, flags=re.IGNORECASE) is not None
    if not (has_stable or has_volatile):
        return (
            "the CREATE FUNCTION declaration MUST declare a recognized "
            "volatility (``STABLE`` or ``VOLATILE``). Without an explicit "
            "declaration, Postgres defaults to ``VOLATILE``, which is "
            "permissible but should be made explicit for the contract. "
            f"Found:\n{header.strip()}"
        )
    if has_stable and has_volatile:
        return (
            "the CREATE FUNCTION declaration declares BOTH ``STABLE`` and "
            "``VOLATILE``; pick exactly one. "
            f"Found:\n{header.strip()}"
        )
    return None


def _find_dml_offenses(body: str) -> list[tuple[str, int]]:
    """Scan ``body`` (post-comment/string strip) for SQL DML keywords
    outside string literals and SQL comments. Returns a list of
    ``(keyword, line_number)`` tuples — one per offending line.
    """
    stripped = _strip_sql_comments_and_strings(body)
    # Track the original line numbers: split stripped by newline
    # boundaries that match the source body.
    offenses: list[tuple[str, int]] = []
    for line_no, line in enumerate(stripped.splitlines(), start=1):
        match = _DML_WORD_RE.search(line)
        if match is None:
            continue
        offenses.append((match.group(0).upper(), line_no))
    return offenses


def test_migracion_0022_declara_volatility_y_no_contiene_dml() -> None:
    """The migration ``0022_create_calcular_cotizacion.py`` MUST declare
    a recognized volatility (``STABLE`` or ``VOLATILE``) and MUST NOT
    contain any of ``INSERT|UPDATE|DELETE|TRUNCATE|MERGE`` inside the
    function body.

    RED phase: the migration file does not exist yet, so this test
    errors out with ``FileNotFoundError`` during module collection.
    GREEN phase (T-HU-F1.8-5 lands): the migration exists, the
    function declares its volatility, and the body has no DML keyword.
    """
    source = _MIGRATION_PATH.read_text(encoding="utf-8")
    sql = _extract_op_execute_sql(source)

    volatility_error = _check_volatility_declaration(sql)
    assert volatility_error is None, volatility_error

    # Locate the function body: between the first ``$$ ... $$`` block.
    body_start = sql.find("$$")
    body_end = sql.find("$$", body_start + 2) if body_start != -1 else -1
    assert body_start != -1 and body_end != -1, (
        "could not locate the ``$$ ... $$`` body of the CREATE FUNCTION "
        "block in the migration — the AST guard cannot run."
    )
    body = sql[body_start + 2 : body_end]

    offenses = _find_dml_offenses(body)
    assert not offenses, (
        "prod.calcular_cotizacion MUST NOT mutate any state (REQ-OPS-025 "
        "+ KD-IVA read-only contract). Found forbidden DML keywords in "
        f"the function body: {offenses!r}. Any INSERT/UPDATE/DELETE/"
        "TRUNCATE/MERGE would silently break idempotency."
    )


__all__ = ["test_migracion_0022_declara_volatility_y_no_contiene_dml"]
