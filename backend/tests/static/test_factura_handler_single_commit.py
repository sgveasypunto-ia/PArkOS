"""HU-F1.9 / KD-FACT-01 / T6.1 -- AST walk: single-commit invariant.

Defense in depth (KD-FACT-01). The handler
``api/v1/facturacion.py::create_factura`` MUST materialize
``prod.facturas`` + ``prod.factura_detalle`` + ``prod.factura_impuestos`` +
``prod.factura_pagos`` atomically in exactly ONE ``await
session.commit()``. Multiple commits or partial commits break the
4-table atomic guarantee.

Lock continuity (KD-FACT-02): the FOR SHARE lock on ``prod.tarifas_sucursal``
acquired in Step 7 is held through Step 10 INSERTs. Released at
``session.commit()`` in Step 11. NO sub-transactions, NO SAVEPOINT.

Pattern: F1.6 ``test_kd_forzado_in_handler.py`` precedent (AST-walk
defense in depth) + F1.7 ``test_salida_handler_step_order.py`` (rec DFS).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_HANDLER_FILE = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "parkos_core"
    / "src"
    / "parkos_core"
    / "api"
    / "v1"
    / "facturacion.py"
)


def _get_handler_function(tree: ast.Module, name: str) -> ast.AsyncFunctionDef:
    """Return the ``async def`` named ``name`` from ``tree``.

    Raises ``pytest.fail`` with a clear message if not found.
    """
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    pytest.fail(f"async def {name} not found in {_HANDLER_FILE}")


def _count_session_commits(fn: ast.AsyncFunctionDef) -> int:
    """Count ``await session.commit()`` calls in ``fn`` body.

    Recursive DFS so nested control flow (if/else inside the function)
    is visited in source order. Dedupes by ``(lineno)`` since each call
    site is unique.
    """
    count = 0
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Await)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "commit"
        ):
            count += 1
    return count


def _has_no_savepoint(fn: ast.AsyncFunctionDef) -> bool:
    """Return True iff NO ``SAVEPOINT`` / ``begin_nested`` / ``RELEASE``
    string literal or function call appears in ``fn`` body.

    KD-FACT-02 invariant: no nested transactions, no SAVEPOINT
    (lock continuity).
    """
    for node in ast.walk(fn):
        # String literal ``"SAVEPOINT"`` or ``"begin_nested"``
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.upper() in ("SAVEPOINT", "BEGIN_NESTED"):
                return False
        # ``await session.begin_nested()`` call
        elif (
            isinstance(node, ast.Await)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "begin_nested"
        ):
            return False
    return True


def test_create_factura_handler_invokes_session_commit_exactly_once() -> None:
    """KD-FACT-01: ``create_factura`` MUST commit exactly once."""
    src = _HANDLER_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = _get_handler_function(tree, "create_factura")

    commit_count = _count_session_commits(fn)
    assert commit_count == 1, (
        f"KD-FACT-01 invariant violated: create_factura has "
        f"{commit_count} session.commit() calls; expected exactly 1."
    )


def test_create_factura_handler_has_no_savepoint_or_nested_tx() -> None:
    """KD-FACT-02 invariant: NO SAVEPOINT / begin_nested in create_factura.

    A nested transaction would release the FOR SHARE lock acquired in
    Step 7 prematurely, breaking KD-FACT-02 lock continuity.
    """
    src = _HANDLER_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = _get_handler_function(tree, "create_factura")

    assert _has_no_savepoint(fn), (
        "KD-FACT-02 invariant violated: create_factura contains "
        "SAVEPOINT / begin_nested / nested transaction. "
        "This would release the FOR SHARE lock prematurely."
    )


def test_create_factura_pago_handler_invokes_session_commit_exactly_once() -> None:
    """KD-FACT-01: ``create_factura_pago`` MUST commit exactly once."""
    src = _HANDLER_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = _get_handler_function(tree, "create_factura_pago")

    commit_count = _count_session_commits(fn)
    assert commit_count == 1, (
        f"KD-FACT-01 invariant violated: create_factura_pago has "
        f"{commit_count} session.commit() calls; expected exactly 1."
    )
