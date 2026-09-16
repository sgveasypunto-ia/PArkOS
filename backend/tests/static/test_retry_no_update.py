"""HU-F1.10 / T6.4 + T6.5 — AST walks for retry-handler invariants.

T6.4: ``POST /factura-electronica/{uuid}/reintentar`` MUST NOT contain
any ``session.execute(UPDATE ...)`` call. DEC-FE-07 — the chain IS the
audit trail; UPDATE on existing envio rows is forbidden. Retries are
appended as NEW rows with ``uuid_envio_padre=<tip.uuid>``.

T6.5: ``POST /factura-electronica/{uuid}/reintentar`` MUST commit
exactly once (KD-FE-01 single-commit invariant, same as the create
handler). The retry handler writes the new envio row only — no FE
row is touched — but the commit is still atomic.

Both walks parse the handler file with ``ast.parse`` and pattern-match
on the appropriate AST node shapes.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


_HANDLER_FILE = (
    _PARKOS_CORE_SRC
    / "parkos_core"
    / "api"
    / "v1"
    / "facturacion.py"
)


def _parse_handler() -> ast.Module:
    return ast.parse(_HANDLER_FILE.read_text(encoding="utf-8"))


def _retry_handler_node(tree: ast.Module) -> ast.AsyncFunctionDef:
    """Locate the ``retry_envio_dian`` coroutine in the parsed module."""
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "retry_envio_dian":
            return node
    raise AssertionError("`retry_envio_dian` coroutine not found in facturacion.py")


def test_retry_handler_does_not_execute_any_update_statement() -> None:
    """T6.4 / DEC-FE-07: no UPDATE on existing envio_dian rows.

    Walks every AST node inside ``retry_envio_dian`` looking for SQL
    UPDATE statements that mutate ``prod.envio_dian``. The retry
    handler MUST only INSERT new rows (``crear_envio_dian_reintento``
    inside the repo module) — never UPDATE existing ones, because the
    chain IS the audit trail.
    """
    tree = _parse_handler()
    handler = _retry_handler_node(tree)
    violations: list[tuple[int, str]] = []

    for node in ast.walk(handler):
        # Catch any string literal that resembles a SQL UPDATE statement.
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            upper = node.value.upper().lstrip()
            if upper.startswith("UPDATE "):
                violations.append((node.lineno, node.value[:80]))
        # Catch ``session.execute(text("UPDATE ..."))`` shape.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and node.args
        ):
            first = node.args[0]
            if (
                isinstance(first, ast.Call)
                and isinstance(first.func, ast.Name)
                and first.func.id == "text"
                and first.args
                and isinstance(first.args[0], ast.Constant)
                and isinstance(first.args[0].value, str)
            ):
                sql = first.args[0].value.upper().lstrip()
                if sql.startswith("UPDATE "):
                    violations.append((node.lineno, first.args[0].value[:80]))

    assert not violations, (
        f"DEC-FE-07 violated: retry_envio_dian contains {len(violations)} "
        f"UPDATE statements (lines: {[line for line, _ in violations]}); the "
        f"chain IS the audit trail. Use `crear_envio_dian_reintento` "
        f"(INSERT-only) instead."
    )


def test_retry_handler_commits_exactly_once() -> None:
    """T6.5 / KD-FE-01: the retry handler commits ONCE.

    Mirrors the T4.5 AST walk but targets ``retry_envio_dian`` instead
    of ``create_factura_electronica``.
    """
    tree = _parse_handler()
    handler = _retry_handler_node(tree)
    hits: list[int] = []
    for node in ast.walk(handler):
        if (
            isinstance(node, ast.Await)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "session"
            and node.value.func.attr == "commit"
        ):
            hits.append(node.lineno)

    assert len(hits) == 1, (
        f"KD-FE-01 violated: `retry_envio_dian` has {len(hits)} "
        f"`await session.commit()` calls (lines {hits}); the retry "
        f"INSERT must commit atomically in exactly one transaction."
    )


def test_retry_handler_uses_crear_envio_dian_reintento() -> None:
    """T6.5: the retry handler MUST call ``crear_envio_dian_reintento``.

    A future regression that swapped in ``crear_envio_dian_inicial`` or
    a direct ``session.add(EnvioDian(...))`` would break DEC-FE-02 (the
    retry row must carry ``uuid_envio_padre`` — the initial helper sets
    it to NULL). The walk pins the helper name so the audit trail
    invariant is enforced at the AST level.
    """
    tree = _parse_handler()
    handler = _retry_handler_node(tree)
    calls_retry_helper = False

    for node in ast.walk(handler):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "crear_envio_dian_reintento"
        ):
            calls_retry_helper = True
            break

    assert calls_retry_helper, (
        "DEC-FE-02 violated: `retry_envio_dian` does not call "
        "`crear_envio_dian_reintento`; the retry row would lose its "
        "`uuid_envio_padre` link to the chain tip."
    )
