"""DIAN1 - nothing in the DIAN dispatch path may UPDATE ``prod.envio_dian``.

``envio_dian`` is append-only for ``rol_app`` (``REVOKE UPDATE, DELETE``; the
chain is the audit trail and the last row is the state). The dispatcher once
did ``envio.estado = ...; await session.commit()`` on a loaded ORM row; the
database rejected it (``permission denied for table envio_dian``) and no
terminal outcome was ever stored. Unit tests with a session double and DB tests
running as the superuser cannot see that, so this static gate forbids the
shapes that lead to it. The behavioural proof runs as ``rol_app`` in
``tests/integration/test_dian_append_only_chain_db.py``.
"""
from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "packages" / "parkos_core" / "src" / "parkos_core"

_SCANNED = [
    *sorted((_SRC / "dian").rglob("*.py")),
    _SRC / "sync" / "hooks" / "impls" / "dian_dispatch_on_sync.py",
]

# Columns of EnvioDian a dispatcher could be tempted to edit in place.
_ENVIO_COLUMNS = {
    "estado",
    "respuesta_proveedor",
    "cufe",
    "payload",
    "fecha_retencion_hasta",
    "timestamp_evento",
    "vigente_hasta",
    "vigente_desde",
    "uuid_envio_padre",
    "uuid_factura_electronica",
    "uuid_sucursal",
}


def _scan(source: str, rel: object) -> list[str]:
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr in _ENVIO_COLUMNS
                and not (isinstance(target.value, ast.Name) and target.value.id == "self")
            ):
                found.append(
                    f"{rel}:{node.lineno} assigns attribute '{target.attr}' of an object "
                    "(an ORM row of an append-only table must be INSERTed, not edited)"
                )
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = " ".join(node.value.upper().split())
            if text.startswith("UPDATE ") and "ENVIO_DIAN" in text:
                found.append(f"{rel}:{node.lineno} raw UPDATE of envio_dian")
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in {"update", "delete"} and any(
                isinstance(a, ast.Name) and a.id == "EnvioDian" for a in node.args
            ):
                found.append(f"{rel}:{node.lineno} {name}(EnvioDian) statement")
    return found


def test_scanned_files_exist() -> None:
    assert len(_SCANNED) >= 4 and all(p.exists() for p in _SCANNED)
    assert (_SRC / "dian" / "cloud" / "dispatcher.py") in _SCANNED


def test_dian_dispatch_path_never_updates_envio_dian() -> None:
    violations = [
        v
        for path in _SCANNED
        for v in _scan(path.read_text(encoding="utf-8"), path.relative_to(_SRC))
    ]
    assert violations == [], "envio_dian is append-only:\n" + "\n".join(violations)


def test_gate_detects_the_original_defect() -> None:
    """The scanner must catch the exact shapes that shipped the bug."""
    bad = (
        "async def f(envio, session):\n"
        "    envio.estado = 'timeout'\n"
        "    envio.respuesta_proveedor = {}\n"
        "    await session.execute(text('UPDATE prod.envio_dian SET estado = 1'))\n"
        "    await session.execute(update(EnvioDian).values(estado='x'))\n"
        "    await session.commit()\n"
    )
    assert len(_scan(bad, "probe.py")) == 4
    assert _scan("def f(self):\n    self.estado = 1\n", "probe.py") == []
