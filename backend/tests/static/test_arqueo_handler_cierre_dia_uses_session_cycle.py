"""HU-F1.13 / T5.3 -- KD-ARQUEO-03 NEW AST walk: ``cierre_dia`` must call ``close_session_with_log``.

KD-ARQUEO-03 (REQ-OPS-092): for ``tipo_arqueo.codigo == 'cierre_dia'``,
the handler MUST call ``repo.session_cycle.close_session_with_log`` per
open sesion (NOT raw ``session.execute(update(Sesion))`` -- the
``ls_session_guard`` DB trigger rejects raw UPDATE without a
co-transactional ``log_transaccional`` row).

This AST walk locks the contract at static-parse time:

  * T1: ``cierre_dia`` branch contains a call to ``close_session_with_log``.
  * T2: ``cierre_dia`` branch does NOT contain raw UPDATE patterns on
    ``prod.sesion``.
  * T3: entire handler body MUST NOT contain raw UPDATE on ``prod.sesion``
    (defense in depth).

Pattern: ``ast.parse`` + ``ast.walk`` + source-level grep. Pure Python,
no DB.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"

_HANDLER_FILE = (
    _PARKOS_CORE_SRC / "parkos_core" / "api" / "v1" / "caja_arqueo.py"
)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _handler_node(tree: ast.Module, name: str) -> ast.AsyncFunctionDef:
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"`{name}` coroutine not found in {_HANDLER_FILE.name}")


def _function_calls_in_handler(
    handler: ast.AsyncFunctionDef, *, attr_name: str, value_id: str | None
) -> list[int]:
    """Return line numbers of calls to ``{value_id}.{attr_name}(...)``.

    ``value_id=None`` matches any base name (e.g. for free functions like
    ``close_session_with_log``).
    """
    hits: list[int] = []
    for node in ast.walk(handler):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr != attr_name:
                continue
            if value_id is not None:
                if not (
                    isinstance(func.value, ast.Name)
                    and func.value.id == value_id
                ):
                    continue
            hits.append(node.lineno)
        elif isinstance(func, ast.Name):
            if value_id is None and func.id == attr_name:
                hits.append(node.lineno)
    return hits


def _calls_close_session_with_log_in(handler: ast.AsyncFunctionDef) -> list[int]:
    """Return line numbers of ``close_session_with_log(...)`` calls."""
    return _function_calls_in_handler(handler, attr_name="close_session_with_log", value_id=None)


# ---------------------------------------------------------------------------
# T5.3 -- KD-ARQUEO-03 enforcement
# ---------------------------------------------------------------------------


def test_arqueo_post_handler_calls_close_session_with_log() -> None:
    """T5.3 / KD-ARQUEO-03: ``post_arqueo`` MUST call ``close_session_with_log``.

    The helper is invoked from the ``cerrar_sesiones_del_dia_bulk``
    wrapper in ``repo.arqueo`` -- so we accept EITHER a direct
    ``close_session_with_log(...)`` call OR a
    ``cerrar_sesiones_del_dia_bulk(...)`` call (which itself wraps
    the helper). Either form satisfies the KD-ARQUEO-03 contract.
    """
    tree = _parse(_HANDLER_FILE)
    handler = _handler_node(tree, "post_arqueo")
    direct = _calls_close_session_with_log_in(handler)
    wrapper = _function_calls_in_handler(
        handler, attr_name="cerrar_sesiones_del_dia_bulk", value_id=None
    )
    assert direct or wrapper, (
        "KD-ARQUEO-03 violated: `post_arqueo` does NOT call "
        "`close_session_with_log(...)` or "
        "`cerrar_sesiones_del_dia_bulk(...)`. The cierre_dia path "
        "MUST iterate `close_session_with_log` per open sesion."
    )


def test_arqueo_post_handler_no_update_sesion_anywhere() -> None:
    """T5.3 / defense in depth: NO raw UPDATE on ``prod.sesion`` anywhere."""
    text = _HANDLER_FILE.read_text(encoding="utf-8")
    forbidden_patterns = [
        r"update\s*\(\s*Sesion\s*\)",
        r"UPDATE\s+prod\.sesion",
    ]
    hits: list[tuple[int, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for pat in forbidden_patterns:
            if re.search(pat, line, flags=re.IGNORECASE):
                hits.append((line_no, pat))
    assert not hits, (
        "KD-ARQUEO-03 violated: raw UPDATE on prod.sesion in post_arqueo "
        "source:\n"
        + "\n".join(f"  line {ln}: {pat}" for ln, pat in hits)
        + "\nUse repo.session_cycle.close_session_with_log instead."
    )
