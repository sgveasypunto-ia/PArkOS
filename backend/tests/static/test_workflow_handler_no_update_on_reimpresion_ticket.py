"""HU-F1.11 / T7.1 + T7.2 — AST walks enforcing the INSERT-only invariant on
``prod.reimpresion_ticket``.

T7.1: ``create_reimpresion_ticket`` + ``anular_reimpresion_ticket``
       MUST NOT contain any raw ``UPDATE prod.reimpresion_ticket``
       statement. DEC-TKT-02 + DEC-TKT-03 + REQ-OPS-077 + REQ-OPS-XR4
       all converge on the same invariant: the chain IS the audit
       trail, mutations are appended as NEW rows via
       ``repo.workflow.append_transition``.

T7.2: Extends F1.5 PR5-016's ``test_no_raw_dml_on_lw_tables.py`` walk
       to confirm NO future F1.11 handler emits a raw
       ``UPDATE prod.reimpresion_ticket`` or
       ``DELETE FROM prod.reimpresion_ticket`` pattern from any of the
       touched files (``repo/reimpresion_ticket.py`` +
       ``api/v1/workflows_reimpresion.py``). Allowed patterns:
       ``INSERT INTO prod.reimpresion_ticket`` via
       ``append_transition``, ``SELECT ... FROM prod.reimpresion_ticket``.

Pattern: parse the handler file with ``ast.parse``, walk every AST node
inside the two handler bodies, collect UPDATE/DELETE statements and
report any violation. Pure Python, no DB.
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
    / "workflows_reimpresion.py"
)
_REPO_FILE = (
    _PARKOS_CORE_SRC
    / "parkos_core"
    / "repo"
    / "reimpresion_ticket.py"
)


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


def _collect_sql_violations(handler: ast.AsyncFunctionDef) -> list[tuple[int, str]]:
    """Walk the handler body collecting any UPDATE/DELETE SQL strings."""
    violations: list[tuple[int, str]] = []

    for node in ast.walk(handler):
        # Catch any string literal that looks like UPDATE/DELETE on reimpresion_ticket.
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            upper = node.value.upper().lstrip()
            if upper.startswith(("UPDATE ", "DELETE ")) and "REIMPRESION_TICKET" in upper:
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
                if sql.startswith(("UPDATE ", "DELETE ")) and "REIMPRESION_TICKET" in sql:
                    violations.append((node.lineno, first.args[0].value[:80]))

        # Catch SQLAlchemy 2.0 ``update(ReimpresionTicket)`` / ``delete(...)`` shapes.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id not in {"update", "delete"}:
                continue
            args = node.args
            if not args:
                continue
            target = args[0]
            target_id: str | None = None
            if isinstance(target, ast.Name):
                target_id = target.id
            elif isinstance(target, ast.Attribute):
                target_id = target.attr
            if target_id == "ReimpresionTicket":
                violations.append((node.lineno, ast.unparse(node)[:80]))

    return violations


# ---------------------------------------------------------------------------
# T7.1 — no UPDATE/DELETE on reimpresion_ticket from either handler
# ---------------------------------------------------------------------------


def test_create_reimpresion_ticket_handler_no_update_on_reimpresion_ticket() -> None:
    """T7.1 / DEC-TKT-02: ``create_reimpresion_ticket`` never UPDATEs reimpresion_ticket.

    Walks every AST node inside the create handler looking for SQL
    UPDATE/DELETE statements that mutate ``prod.reimpresion_ticket``.
    The handler MUST only INSERT a new chain root via
    ``repo.workflow.append_transition`` — never UPDATE existing rows.
    """
    tree = _parse(_HANDLER_FILE)
    handler = _handler_node(tree, "create_reimpresion_ticket")
    violations = _collect_sql_violations(handler)

    assert not violations, (
        f"DEC-TKT-02 violated: `create_reimpresion_ticket` contains "
        f"{len(violations)} UPDATE/DELETE statements on reimpresion_ticket "
        f"(lines: {[line for line, _ in violations]}); the chain IS the "
        f"audit trail. Use `repo.workflow.append_transition` (INSERT-only) "
        f"instead."
    )


def test_anular_reimpresion_ticket_handler_no_update_on_reimpresion_ticket() -> None:
    """T7.1 / DEC-TKT-03: ``anular_reimpresion_ticket`` never UPDATEs reimpresion_ticket.

    The anulacion closes a chain via a NEW ``rechazada`` row linked
    through ``uuid_reimpresion_padre=<tip.uuid>``. The original chain
    tip row MUST NEVER be mutated (DEC-TKT-03).
    """
    tree = _parse(_HANDLER_FILE)
    handler = _handler_node(tree, "anular_reimpresion_ticket")
    violations = _collect_sql_violations(handler)

    assert not violations, (
        f"DEC-TKT-03 violated: `anular_reimpresion_ticket` contains "
        f"{len(violations)} UPDATE/DELETE statements on reimpresion_ticket "
        f"(lines: {[line for line, _ in violations]}); the original chain "
        f"tip MUST NEVER be mutated. Insert a NEW row with "
        f"`uuid_reimpresion_padre=<tip.uuid>` via "
        f"`repo.workflow.append_transition` instead."
    )


# ---------------------------------------------------------------------------
# T7.2 — extended grep across the F1.11 source files
# ---------------------------------------------------------------------------


def test_repo_layer_no_raw_dml_on_reimpresion_ticket() -> None:
    """T7.2: NO raw UPDATE/DELETE on ``prod.reimpresion_ticket`` from any F1.11 source.

    Greps both ``repo/reimpresion_ticket.py`` and
    ``api/v1/workflows_reimpresion.py`` for raw ``UPDATE
    prod.reimpresion_ticket`` or ``DELETE FROM prod.reimpresion_ticket``
    string literals. Allowed patterns: ``INSERT INTO
    prod.reimpresion_ticket`` via ``append_transition``, ``SELECT ...
    FROM prod.reimpresion_ticket``.
    """
    offenders: list[tuple[Path, int, str]] = []
    for path in (_REPO_FILE, _HANDLER_FILE):
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for idx, line in enumerate(lines, start=1):
            upper = line.upper().lstrip()
            if "REIMPRESION_TICKET" not in upper:
                continue
            if upper.startswith(("UPDATE ", "DELETE ")):
                offenders.append((path, idx, line.strip()))

    assert not offenders, (
        "REQ-OPS-XR4 violated: raw UPDATE/DELETE on prod.reimpresion_ticket "
        "found outside the canonical write path:\n"
        + "\n".join(
            f"  {p.relative_to(_PARKOS_CORE_SRC)}:{ln}: {s}"
            for p, ln, s in offenders
        )
    )
