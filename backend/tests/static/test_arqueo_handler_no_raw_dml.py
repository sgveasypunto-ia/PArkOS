"""HU-F1.13 / T5.2 -- no raw DML on [A]/[V] tables outside helpers (DEC-ARQUEO-02 + DEC-ARQUEO-05).

Pattern (F1.5 PR5-016 + F1.12 T6.2): source-level grep on the
``post_arqueo`` handler body. Rejects raw INSERT/UPDATE/DELETE on
[A] / [V] tables outside the canonical helpers (``repo.append_only``,
``repo.workflow``, ``repo.session_cycle``, ``repo.arqueo``).

Defense in depth:

  * ``insert(Arqueo)`` / ``update(Arqueo)`` -- ``[A]`` append-only,
    raw INSERT outside :func:`repo.append_only.append_event` blocks.
  * ``insert(Alerta)`` -- ``[L-W]`` workflow, raw INSERT outside
    :func:`repo.workflow.append_transition` blocks.
  * ``update(Sesion)`` -- ``[L-S]`` lifecycle, raw UPDATE outside
    :func:`repo.session_cycle.close_session_with_log` blocks (KD-ARQUEO-03).
  * ``INSERT INTO prod.tipo_arqueo`` -- ``[V]`` versioning, raw
    INSERT outside :func:`repo.versioned.close_and_insert` blocks.

These checks are static-only; the runtime [A] immutability triggers
enforce the same contract at the DB layer.
"""
from __future__ import annotations

import re
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"

_HANDLER_FILE = (
    _PARKOS_CORE_SRC / "parkos_core" / "api" / "v1" / "caja_arqueo.py"
)

# Patterns rejected in the handler source. Each pattern is a substring
# match (case-insensitive); if any appears in the file outside the
# module-level docstring, the test fails.
_FORBIDDEN_PATTERNS_A = [
    # Raw INSERT/UPDATE/DELETE on [A] tables
    r"insert\s*\(\s*Arqueo\s*\)",
    r"insert\s*\(\s*Alerta\s*\)",
    r"insert\s*\(\s*FacturaPagos\s*\)",
    r"insert\s*\(\s*LogTransaccional\s*\)",
    r"insert\s*\(\s*AlertTypes\s*\)",
    r"update\s*\(\s*Arqueo\s*\)",
    r"update\s*\(\s*Alerta\s*\)",
    r"update\s*\(\s*FacturaPagos\s*\)",
    r"update\s*\(\s*AlertTypes\s*\)",
    # Raw SQL strings (defense in depth)
    r"INSERT\s+INTO\s+prod\.arqueo",
    r"UPDATE\s+prod\.arqueo",
    r"DELETE\s+FROM\s+prod\.arqueo",
    r"INSERT\s+INTO\s+prod\.alerta",
    r"UPDATE\s+prod\.alerta",
    r"DELETE\s+FROM\s+prod\.alerta",
]

_FORBIDDEN_PATTERNS_V = [
    # [V] versioning -- no raw INSERT/UPDATE/DELETE outside repo.versioned
    r"INSERT\s+INTO\s+prod\.tipo_arqueo",
    r"UPDATE\s+prod\.tipo_arqueo",
    r"DELETE\s+FROM\s+prod\.tipo_arqueo",
    r"INSERT\s+INTO\s+prod\.configuracion_tolerancias",
    r"UPDATE\s+prod\.configuracion_tolerancias",
    r"DELETE\s+FROM\s+prod\.configuracion_tolerancias",
]


def _scan_handler_source(path: Path, patterns: list[str]) -> list[tuple[int, str]]:
    """Return (line_no, matched_text) for any forbidden pattern."""
    text = path.read_text(encoding="utf-8")
    hits: list[tuple[int, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        # Skip docstring-only lines (no executable code).
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for pat in patterns:
            if re.search(pat, line, flags=re.IGNORECASE):
                hits.append((line_no, pat))
    return hits


def test_arqueo_post_handler_no_raw_dml_on_a_tables() -> None:
    """T5.2 / DEC-ARQUEO-02 + DEC-ARQUEO-05: no raw DML on [A] tables."""
    hits = _scan_handler_source(_HANDLER_FILE, _FORBIDDEN_PATTERNS_A)
    assert not hits, (
        "DEC-ARQUEO-02 + DEC-ARQUEO-05 violated: raw DML on [A] tables "
        "in post_arqueo source:\n"
        + "\n".join(f"  line {ln}: {pat}" for ln, pat in hits)
    )


def test_arqueo_post_handler_no_raw_dml_on_v_tables() -> None:
    """T5.2: no raw DML on [V] tables (``tipo_arqueo``, ``configuracion_tolerancias``)."""
    hits = _scan_handler_source(_HANDLER_FILE, _FORBIDDEN_PATTERNS_V)
    assert not hits, (
        "DEC-ARQUEO-02 violated: raw DML on [V] tables in post_arqueo source:\n"
        + "\n".join(f"  line {ln}: {pat}" for ln, pat in hits)
    )
