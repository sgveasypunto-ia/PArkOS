"""HU-F1.7 / DEC-SAL-01 + DEC-SUC-23-NEW -- AST walk for ``create_salida``.

Two defense-in-depth checks locked at AST level:

1. **No write verb after the salida INSERT.** Once
   ``crear_salida_evento`` runs (Step 8), the handler MUST NOT issue
   ``session.execute(update|delete|truncate|merge)`` against
   ``prod.salidas``. DEC-SAL-01: append-only; DDL revoke + trigger
   + partial unique index form the database side of the contract;
   the AST walk guarantees the handler cannot bypass them.

2. **No monto columns in ``new_attrs``.** The handler builds
   ``new_attrs`` before INSERT; it MUST NOT include ``valor``,
   ``subtotal``, ``iva``, ``total``, ``tarifa_uuid``, ``cobrar`` --
   those live in the snapshot (response body), never the row
   (DEC-SUC-23-NEW + DEC-SUC-21-NEW).

Pattern: F1.6 precedent (``test_no_write_after_insert.py`` + KD-S7).
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
    / "operacion.py"
)

_WRITE_VERBS = ("UPDATE", "DELETE", "TRUNCATE", "MERGE")

# DEC-SUC-23-NEW + DEC-SUC-21-NEW: never persist these on prod.salidas.
_FORBIDDEN_MONTO_KEYS = frozenset(
    {
        "valor",
        "subtotal",
        "iva",
        "total",
        "tarifa_uuid",
        "cobrar",
        "tipo_salida",  # DEC-SUC-21-NEW
    }
)


def _find_create_salida(tree: ast.Module) -> ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "create_salida"
        ):
            return node  # type: ignore[return-value]
    raise AssertionError(
        "create_salida not found in api/v1/operacion.py"
    )


def test_create_salida_no_tiene_update_delete_despues_de_insert() -> None:
    """AST walk: no UPDATE / DELETE / TRUNCATE / MERGE literal in
    ``create_salida`` body (string and identifier tokens, outside
    docstrings).
    """
    src = _HANDLER_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = _find_create_salida(tree)

    # Capture docstring value to exclude it.
    docstring_value: str | None = None
    if (
        fn.body
        and isinstance(fn.body[0], ast.Expr)
        and isinstance(fn.body[0].value, ast.Constant)
        and isinstance(fn.body[0].value.value, str)
    ):
        docstring_value = fn.body[0].value.value

    offenders: list[tuple[str, int]] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value == docstring_value:
                continue
            upper = node.value.upper()
            if any(kw in upper for kw in _WRITE_VERBS):
                offenders.append((node.value, node.lineno))
        elif isinstance(node, ast.Attribute):
            upper = node.attr.upper()
            if any(kw in upper for kw in _WRITE_VERBS):
                offenders.append((node.attr, node.lineno))

    if offenders:
        formatted = ", ".join(f"{name!r}@L{ln}" for name, ln in offenders)
        pytest.fail(
            f"create_salida contains forbidden write literals: {formatted}"
        )


def test_create_salida_new_attrs_no_contiene_monto_ni_tipo_salida() -> None:
    """AST walk: the ``new_attrs`` dict literal at Step 8 MUST NOT contain
    any of ``valor / subtotal / iva / total / tarifa_uuid / cobrar /
    tipo_salida``.

    DEC-SUC-23-NEW: monetary columns live in the snapshot, not the row.
    DEC-SUC-21-NEW: ``tipo_salida`` is server-derived, never persisted.
    """
    src = _HANDLER_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = _find_create_salida(tree)

    # Locate the Step 8 ``new_attrs = {...}`` dict.
    new_attrs_dict: ast.Dict | None = None
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "new_attrs"
                    and isinstance(node.value, ast.Dict)
                ):
                    new_attrs_dict = node.value
                    break
            if new_attrs_dict is not None:
                break

    assert new_attrs_dict is not None, (
        "Step 8 'new_attrs = {...}' dict literal not found in create_salida"
    )

    offending_keys: list[tuple[str, int]] = []
    for key_node in new_attrs_dict.keys:
        if not isinstance(key_node, ast.Constant):
            continue
        if not isinstance(key_node.value, str):
            continue
        if key_node.value in _FORBIDDEN_MONTO_KEYS:
            offending_keys.append((key_node.value, key_node.lineno))

    assert not offending_keys, (
        "DEC-SUC-23-NEW / DEC-SUC-21-NEW violated: "
        f"new_attrs contains forbidden keys: {offending_keys!r}"
    )


__all__ = [
    "test_create_salida_no_tiene_update_delete_despues_de_insert",
    "test_create_salida_new_attrs_no_contiene_monto_ni_tipo_salida",
]
