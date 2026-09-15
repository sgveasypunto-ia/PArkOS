"""HU-F1.7 / D-HU-F1.7-20 -- AST walk: ``api/v1/operacion.py::create_salida``.

Defense in depth (D-HU-F1.7-20, design §7). The 12-step validation chain
MUST be invoked in canonical order; reordering would silently break the
discriminator precedence contract (KD-3 → V1 → V2 → V3 → KD-FORZADO → V5 →
INSERT → alerta → single commit → derivar tipo → response).

KD-S7 lock continuity: the ``cotizar_para_salida`` call (Step 7) acquires
``SELECT ... FOR SHARE`` on ``tarifas_sucursal`` and MUST run BEFORE
``crear_salida_evento`` (Step 8). The single ``session.commit()`` (Step 9)
is the only place the lock is released.

Pattern: F1.6 precedent (``test_kd_forzado_in_handler.py``).
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

# Canonical chain per D-HU-F1.7-20. Matched by short basename only.
_EXPECTED_CHAIN: list[str] = [
    "buscar_ingreso_activo_por_uuid",   # Step 2 V1
    "validar_subscripcion_vigente",     # Step 4 V2
    "detectar_tipo_vehiculo",           # Step 5 V3 (x2 in handler)
    "validar_kd_forzado",               # Step 6 KD-FORZADO-01
    "cotizar_para_salida",              # Step 7 V5 (PL/pgSQL)
    "crear_salida_evento",              # Step 8 INSERT [A]
    "insertar_alerta_salida_forzado",   # Step 9 alerta same-TX
]


def _extract_call_chain(fn: ast.AsyncFunctionDef) -> list[str]:
    """Return, in source order, the short name of every awaited helper
    in ``fn`` whose name matches :data:`_EXPECTED_CHAIN`.

    Uses recursive DFS (NOT ``ast.walk`` -- which is BFS and reorders nodes
    across depths). Each call-site is recorded once, deduped by
    ``(name, lineno)``.
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

    _visit(fn, None)
    return chain


def _find_create_salida(tree: ast.Module) -> ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "create_salida"
        ):
            return node  # type: ignore[return-value]
    raise AssertionError(
        "create_salida not found in api/v1/operacion.py -- F1.7 owns this "
        "handler"
    )


def test_create_salida_invoca_helpers_en_orden_canónico() -> None:
    """The 12-step chain MUST be invoked in D-HU-F1.7-20 canonical order.

    KD-S7 invariant: ``cotizar_para_salida`` (Step 7) MUST come BEFORE
    ``crear_salida_evento`` (Step 8) -- the lock acquired by the former
    is held across the latter and released at ``session.commit()``.
    """
    src = _HANDLER_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = _find_create_salida(tree)
    chain = _extract_call_chain(fn)

    # Locate cotizar_para_salida and crear_salida_evento positions.
    try:
        i_cot = chain.index("cotizar_para_salida")
    except ValueError:
        pytest.fail("create_salida does NOT call cotizar_para_salida -- KD-S7 broken")
    try:
        i_cre = chain.index("crear_salida_evento")
    except ValueError:
        pytest.fail("create_salida does NOT call crear_salida_evento -- Step 8 missing")

    assert i_cot < i_cre, (
        f"KD-S7 violated: cotizar_para_salida@{i_cot} must come BEFORE "
        f"crear_salida_evento@{i_cre}; chain={chain!r}"
    )


def test_create_salida_cadena_completa_en_orden() -> None:
    """Project the call chain to the canonical subsequence; allow extra
    unknown calls in between, but the EXPECTED order must be strictly
    preserved.
    """
    src = _HANDLER_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = _find_create_salida(tree)
    chain = _extract_call_chain(fn)
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
            "create_salida calls the validation chain out of order. "
            f"Expected next: {missing!r} but got order: {chain!r}"
        )


def test_create_salida_no_tiene_segundo_commit() -> None:
    """KD-S7 invariant: a single ``session.commit()`` after the alerta
    INSERT -- NO second commit anywhere else in the handler.

    Defense in depth: another commit would silently release the
    ``SELECT ... FOR SHARE`` lock acquired in ``cotizar_para_salida``
    (F1.8 / KD-S7). Detected via ``ast.walk`` counting ``session.commit``
    references in the function body.
    """
    src = _HANDLER_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = _find_create_salida(tree)

    commits: list[int] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            # Detect ``session.commit()`` attribute call.
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "commit"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "session"
            ):
                commits.append(node.lineno)

    assert len(commits) == 1, (
        f"KD-S7 violated: create_salida has {len(commits)} session.commit() "
        f"calls at lines {commits!r}; exactly ONE is required."
    )


__all__ = [
    "test_create_salida_invoca_helpers_en_orden_canónico",
    "test_create_salida_cadena_completa_en_orden",
    "test_create_salida_no_tiene_segundo_commit",
]
