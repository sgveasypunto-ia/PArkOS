"""HU-F1.12 / T6.3 -- no UPDATE on [V] tables in handler.

DEC-VENTA-05 deepens for F1.12: the handler MUST NOT issue any UPDATE
on the 5 [V] tables (``prod.clientes``, ``prod.vehiculos``,
``prod.subscripciones_cliente``, ``prod.subscripcion_vehiculos``,
``prod.tipo_subscripciones``). All state changes funnel through
``versioned.close_and_insert`` which only INSERTs.

Also rejects ``session.execute(text("UPDATE ...))`` calls (defense in
depth mirror of T6.2).

Pattern: F1.5 PR5-016 ``test_no_raw_upsert_on_v_tables.py``.
"""
from __future__ import annotations

import re
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"

_HANDLER_FILE = (
    _PARKOS_CORE_SRC / "parkos_core" / "api" / "v1" / "clientes_venta.py"
)

_V_TABLES = (
    "prod.clientes",
    "prod.vehiculos",
    "prod.subscripciones_cliente",
    "prod.subscripcion_vehiculos",
    "prod.tipo_subscripciones",
)

# Forbidden UPDATE patterns -- both raw SQL and ORM ``update()`` calls.
_FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = []
for _tbl in _V_TABLES:
    _FORBIDDEN_PATTERNS.append(
        (
            re.compile(rf"\bUPDATE\s+{re.escape(_tbl)}\b", re.IGNORECASE),
            f"raw UPDATE {_tbl} (must use close_and_insert)",
        )
    )

# ORM update() call patterns: ``update(prod.<table>...)`` or
# ``update(<TableClass>...)`` for the 5 model classes. We check the
# model attribute access patterns that the AST would see.
_ORM_UPDATE_FORBIDDEN = re.compile(
    r"\bupdate\s*\(\s*(?:prod\.)?(?:clientes|vehiculos|subscripciones_cliente|subscripcion_vehiculos|tipo_subscripciones)\b",
    re.IGNORECASE,
)


def test_venta_suscripcion_no_update_on_v_tables() -> None:
    """T6.3: handler emits NO UPDATE on the 5 [V] tables.

    Source-level grep on ``clientes_venta.py``. Both raw SQL ``UPDATE
    prod.<table>...`` and ORM ``update(prod.<table>...)`` are rejected.
    """
    source = _HANDLER_FILE.read_text(encoding="utf-8")
    lines = source.splitlines()
    hits: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(lines, start=1):
        for pattern, reason in _FORBIDDEN_PATTERNS:
            if pattern.search(line):
                hits.append((lineno, line.strip(), reason))
        if _ORM_UPDATE_FORBIDDEN.search(line):
            hits.append(
                (
                    lineno,
                    line.strip(),
                    "ORM update(...) call on a [V] table (must use close_and_insert)",
                )
            )
    assert not hits, (
        "DEC-VENTA-05 violated: handler emits UPDATE on [V] tables. "
        "All state changes must funnel through versioned.close_and_insert. "
        "Offending lines:\n"
        + "\n".join(f"  L{ln}: {ln_text}  // {reason}" for ln, ln_text, reason in hits)
    )
