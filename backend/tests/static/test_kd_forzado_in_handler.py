"""HU-F1.6 / R7 -- AST walk: ``api/v1/operacion.py::create_ingreso``.

Defense in depth (R7, D-HU-F1.6-11). The 11-step validation chain
(KD-3 → V5 → V4 → KD-FORZADO → V1+V2 → V3 → V6 → V8 → INSERT →
alerta → V9) MUST be invoked in the canonical order; reordering would
silently break a discriminator's precedence guarantee.

Pattern: F1.5 precedent (similar AST walks in
``tests/static/test_no_write_in_ocupacion.py``).
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

# Canonical chain per D-HU-F1.6-11. Steps are matched by basename only;
# ``repo.X.Y`` lookups also resolve to a single token sequence.
_EXPECTED_CHAIN: list[str] = [
    # KD-3 chain: tenant validation happens in handler prelude.
    # (preceded by ``target = payload.uuid_sucursal or ctx.sucursal_uuid``)
    "detectar_tipo_vehiculo",       # V5 regex lookup
    "validar_tipo_vehiculo_vigente", # V4 catalog check
    "validar_kd_forzado",            # KD-FORZADO-01 prefix
    "validar_cupo_disponible",       # V1 + V2 (cupo no config / agotado)
    "validar_tarifa_vigente",        # V3 bi-temporal predicate
    "validar_subscripcion_vigente",  # V6
    "existe_ingreso_activo",         # V8 no-duplicate
    "crear_ingreso_evento",          # INSERT (record_event)
    "insertar_alerta_forzado",       # KD-FORZADO-01.alerta (same TX)
]


def _extract_call_chain(fn: ast.FunctionDef) -> list[str]:
    """Return, in source order, the short name of every awaited/called helper
    in ``fn`` that matches a name in :data:`_EXPECTED_CHAIN`.

    Uses recursive DFS (NOT ``ast.walk`` -- which is BFS and reorders nodes
    across depths). Each call-site is recorded once, deduped by
    ``(name, lineno)`` so ``ast.walk``-style double-visits inside Await
    don't double-count.
    """
    chain: list[str] = []
    expected = set(_EXPECTED_CHAIN)
    seen: set[tuple[str, int]] = set()

    def _func_name(call: ast.Call) -> str | None:
        if isinstance(call.func, ast.Name):
            return call.func.id
        if isinstance(call.func, ast.Attribute):
            return call.func.attr
        return None

    def _visit(node: ast.AST, parent: ast.AST | None) -> None:
        # Awaited call -> record the function name once.
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
            name = _func_name(node.value)
            if name in expected:
                key = (name, node.lineno)
                if key not in seen:
                    seen.add(key)
                    chain.append(name)
            # Descend into the Call children too in case the helper arg
            # tree contains another matched helper (unlikely but cheap).
            for child in ast.iter_child_nodes(node):
                _visit(child, node)
            return
        # Sync top-level Call (not nested in an Await).
        if isinstance(node, ast.Call) and not isinstance(parent, ast.Await):
            name = _func_name(node)
            if name in expected:
                key = (name, node.lineno)
                if key not in seen:
                    seen.add(key)
                    chain.append(name)
        # Recurse into children (DFS, source-order via iter_child_nodes).
        for child in ast.iter_child_nodes(node):
            _visit(child, node)

    _visit(fn, None)
    return chain


def _find_create_ingreso(tree: ast.Module) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "create_ingreso"
        ):
            return node  # type: ignore[return-value]
    raise AssertionError(
        "create_ingreso not found in api/v1/operacion.py -- F1.6 owns this "
        "handler replacement"
    )


def test_create_ingreso_handler_invoca_helpers_en_orden_correcto() -> None:
    """The validation chain MUST appear in D-HU-F1.6-11 order."""
    src = _HANDLER_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = _find_create_ingreso(tree)
    chain = _extract_call_chain(fn)
    # Project the chain to the canonical subsequence; allow extra unknown
    # calls in between, but the EXPECTED order must be strictly preserved.
    expected_index = 0
    expected = _EXPECTED_CHAIN
    for step in chain:
        if expected_index >= len(expected):
            break
        if step == expected[expected_index]:
            expected_index += 1
    if expected_index != len(expected):
        missing = expected[expected_index:]
        pytest.fail(
            "create_ingreso calls the validation chain out of order. "
            f"Expected next: {missing!r} but got order: {chain!r}"
        )


__all__ = ["test_create_ingreso_handler_invoca_helpers_en_orden_correcto"]
