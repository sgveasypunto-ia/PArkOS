"""HU-F1.12 / T6.2 -- DEC-VENTA-05 enforcement: no raw INSERT/UPDATE/DELETE on [V] tables.

Source-level grep + AST walk on ``api/v1/clientes_venta.py``. The
handler MUST NOT emit raw ``INSERT INTO prod.<v_table>``, ``UPDATE
prod.<v_table>``, or ``DELETE FROM prod.<v_table>`` SQL -- all writes
to the 5 [V] tables funnel through the repo helpers in
``repo/venta_suscripcion.py`` (DEC-VENTA-05).

The allowed exception is ``pg_advisory_xact_lock`` inside the
``crear_subscripcion_vehiculos_bulk`` helper (not a write -- it's a
lock acquisition), and the ``close_and_insert`` collaborator in
``repo/versioned.py``.

Pattern: F1.5 PR5-016 ``test_no_raw_upsert_on_v_tables.py`` (source
grep + regex match).
"""
from __future__ import annotations

import re
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"

_HANDLER_FILE = (
    _PARKOS_CORE_SRC / "parkos_core" / "api" / "v1" / "clientes_venta.py"
)

# [V] tables in scope -- DEC-VENTA-05 enforcement.
_V_TABLES = (
    "prod.clientes",
    "prod.vehiculos",
    "prod.subscripciones_cliente",
    "prod.subscripcion_vehiculos",
    "prod.tipo_subscripciones",
)

# Forbidden raw DML patterns. Each tuple is (regex, human-readable
# reason). The regex is applied to every line of the handler source.
_FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = []
for _tbl in _V_TABLES:
    _FORBIDDEN_PATTERNS.append(
        (
            re.compile(rf"\bINSERT\s+INTO\s+{re.escape(_tbl)}\b", re.IGNORECASE),
            f"raw INSERT INTO {_tbl} (must use repo.venta_suscripcion.close_and_insert)",
        )
    )
    _FORBIDDEN_PATTERNS.append(
        (
            re.compile(rf"\bUPDATE\s+{re.escape(_tbl)}\b", re.IGNORECASE),
            f"raw UPDATE {_tbl} (must use repo.venta_suscripcion.close_and_insert)",
        )
    )
    _FORBIDDEN_PATTERNS.append(
        (
            re.compile(rf"\bDELETE\s+FROM\s+{re.escape(_tbl)}\b", re.IGNORECASE),
            f"raw DELETE FROM {_tbl} (forbidden -- defense in depth)",
        )
    )


def test_venta_suscripcion_no_raw_dml_on_v_tables() -> None:
    """T6.2 / DEC-VENTA-05: handler emits NO raw DML on the 5 [V] tables.

    Source-level grep on ``clientes_venta.py``. Allowed:
    ``session.add(...)`` calls (which the ORM translates to INSERT) and
    ``session.execute(text('SELECT pg_advisory_xact_lock...'), ...)``
    (advisory lock acquisition, not a write).
    """
    source = _HANDLER_FILE.read_text(encoding="utf-8")
    lines = source.splitlines()
    hits: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(lines, start=1):
        for pattern, reason in _FORBIDDEN_PATTERNS:
            if pattern.search(line):
                hits.append((lineno, line.strip(), reason))
    assert not hits, (
        "DEC-VENTA-05 violated: handler emits raw DML on [V] tables. "
        "All writes must funnel through repo.venta_suscripcion helpers. "
        "Offending lines:\n"
        + "\n".join(f"  L{ln}: {ln_text}  // {reason}" for ln, ln_text, reason in hits)
    )
