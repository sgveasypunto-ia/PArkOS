"""HU-F1.9 / D-HU-F1.9-11 / T6.3 -- AST walk: 12-step chain order.

Defense in depth (D-HU-F1.9-11). The ``create_factura`` handler
MUST invoke the helpers in canonical order:

  Step 2 V1 salida            -> repo_factura.buscar_salida_facturable
  Step 4 V2 cliente           -> repo_factura.buscar_o_crear_cliente_por_nit
  Step 5 V3 IVA               -> obtener_iva_vigente  (verify-report C3 fix;
                                  was ``validar_iva_configurado`` pre-fix)
  Step 6 V4 detalle           -> repo_factura.validar_items
  Step 7 KD-FACT-02 lock      -> repo_factura.lock_tarifas_sucursal_para_items
  Step 8 V6 total             -> repo_factura.compute_total
  Step 9 INSERT               -> repo_factura.crear_factura_evento
  Step 10a detalle bulk       -> crear_factura_detalle_bulk
  Step 10b IVA snapshot       -> repo_factura.crear_factura_impuesto_iva
  Step 10c init pago          -> repo_factura.crear_factura_pago
  Step 11 single commit       -> session.commit

Reordering would silently break:
- Lock continuity (KD-FACT-02): Step 7 BEFORE Step 8 keeps the FOR SHARE
  lock held through Steps 9-10.
- Discriminator precedence (D-HU-F1.9-12): V1 before tenant scope avoids
  info leak; V4 before V6 ensures items validated before total recompute.

Pattern: F1.7 ``test_salida_handler_step_order.py`` (recursive DFS).
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

# Canonical chain per D-HU-F1.9-11. Matched by short basename only.
# ``buscar_o_crear_cliente_por_nit`` is conditional on fe_con_datos
# (Step 4 may be skipped in tests where fe_con_datos=False), so the
# AST walk uses ``issubset`` rather than strict equality.
#
# verify-report C3: Step 5 V3 is now ``obtener_iva_vigente`` (returns
# Decimal | None) instead of ``validar_iva_configurado`` (returns bool).
# The helper change is required by DEC-FACT-03 — the handler MUST pass
# the DB-derived IVA percentage to both ``compute_total`` (Step 8) and
# ``crear_factura_impuesto_iva`` (Step 10b), not a hardcoded 0.19.
_EXPECTED_CHAIN: list[str] = [
    "buscar_salida_facturable",          # Step 2 V1
    "buscar_o_crear_cliente_por_nit",    # Step 4 V2 (conditional)
    "obtener_iva_vigente",               # Step 5 V3 (C3 fix: was validar_iva_configurado)
    "validar_items",                     # Step 6 V4
    "lock_tarifas_sucursal_para_items",  # Step 7 KD-FACT-02
    "compute_total",                     # Step 8 V6
    "crear_factura_evento",              # Step 9 INSERT
    "crear_factura_detalle_bulk",        # Step 10a detalle bulk
    "crear_factura_impuesto_iva",        # Step 10b IVA snapshot
    "crear_factura_pago",                # Step 10c init pago
]


def _get_handler_function(tree: ast.Module, name: str) -> ast.AsyncFunctionDef:
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    pytest.fail(f"async def {name} not found in {_HANDLER_FILE}")


def _extract_call_chain(fn: ast.AsyncFunctionDef) -> list[str]:
    """Return, in source order, the short name of every awaited/called helper
    in ``fn`` whose name matches :data:`_EXPECTED_CHAIN`.

    Uses recursive DFS so nested control flow (if/else inside the function)
    is visited in source order. Dedupes by ``(name, lineno)``.
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
            for child in ast.iter_child_nodes(node):
                _visit(child, node)
            return
        for child in ast.iter_child_nodes(node):
            _visit(child, node)

    for stmt in fn.body:
        _visit(stmt, None)
    return chain


def test_create_factura_handler_invoca_helpers_en_orden_correcto() -> None:
    """D-HU-F1.9-11: 12-step chain MUST be invoked in canonical order."""
    src = _HANDLER_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = _get_handler_function(tree, "create_factura")

    chain = _extract_call_chain(fn)
    # The chain MUST be a superset of the expected ordered pattern.
    # We check each expected step appears in order, skipping conditional
    # ones (buscar_o_crear_cliente_por_nit) when not called.
    filtered_chain = [n for n in chain if n in _EXPECTED_CHAIN]

    # The unconditional chain (excluding the conditional Step 4) must
    # match the expected ordered pattern exactly.
    unconditional = [
        "buscar_salida_facturable",          # Step 2
        "obtener_iva_vigente",               # Step 5 (C3 fix)
        "validar_items",                     # Step 6
        "lock_tarifas_sucursal_para_items",  # Step 7
        "compute_total",                     # Step 8
        "crear_factura_evento",              # Step 9
        "crear_factura_detalle_bulk",        # Step 10a
        "crear_factura_impuesto_iva",        # Step 10b
        "crear_factura_pago",                # Step 10c
    ]

    # Find each expected step in the chain (in order)
    last_idx = -1
    for step in unconditional:
        try:
            idx = filtered_chain.index(step, last_idx + 1)
        except ValueError:
            pytest.fail(
                f"D-HU-F1.9-11 invariant violated: step {step!r} not "
                f"found in order. Chain was: {filtered_chain}"
            )
        last_idx = idx

    # Also: Step 7 MUST come before Step 8 (lock continuity, KD-FACT-02).
    step7_idx = filtered_chain.index("lock_tarifas_sucursal_para_items")
    step8_idx = filtered_chain.index("compute_total")
    assert step7_idx < step8_idx, (
        f"KD-FACT-02 invariant violated: lock_tarifas_sucursal_para_items "
        f"(Step 7, idx={step7_idx}) MUST come before compute_total "
        f"(Step 8, idx={step8_idx}) to keep the FOR SHARE lock held "
        f"through the total recompute."
    )

    # Step 9 INSERT MUST come after Step 8 (V6) — V6 catches total
    # mismatch BEFORE any INSERT.
    step9_idx = filtered_chain.index("crear_factura_evento")
    assert step8_idx < step9_idx, (
        "D-HU-F1.9-12 invariant violated: V6 total check (Step 8) "
        "MUST come before INSERT (Step 9)."
    )


def test_create_factura_handler_step_markers_are_present() -> None:
    """Defense in depth: source has all 12 step comment markers in order."""
    src = _HANDLER_FILE.read_text(encoding="utf-8")
    # Find positions of each Step marker in source order
    positions: list[tuple[int, str]] = []
    for i in range(1, 13):
        marker = f"# --- Step {i}:"
        pos = src.find(marker)
        assert pos != -1, f"step marker missing: {marker!r}"
        positions.append((pos, marker))

    # Verify monotonic order
    for i in range(1, len(positions)):
        assert positions[i - 1][0] < positions[i][0], (
            f"step markers out of order: {positions[i - 1][1]} comes "
            f"after {positions[i][1]}"
        )
