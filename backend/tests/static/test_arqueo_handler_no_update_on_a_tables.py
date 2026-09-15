"""HU-F1.13 / T5.2 -- KD-ARQUEO-02 no UPDATE on [A] tables.

KD-ARQUEO-02 (DEC-ARQUEO-02): no UPDATE on user-meaningful fields of
``[A]`` tables (``prod.arqueo``, ``prod.alerta``, ``prod.factura_pagos``,
``prod.alert_types``, ``prod.log_transaccional``) outside the canonical
helpers. Only the bi-temporal ``vigente_hasta`` MAY be UPDATEd by
``VersionedBase`` superclass for ``[V]`` tables (the existing
``tests/static/test_no_raw_upsert_on_v_tables.py`` covers that path).

Pattern: source-level grep on the ``post_arqueo`` handler body. The
``[A]`` immutability contract is also enforced at the DB layer via
``fn_*_inmutable`` triggers -- this static check is defense in depth.
"""
from __future__ import annotations

import re
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"

_HANDLER_FILE = (
    _PARKOS_CORE_SRC / "parkos_core" / "api" / "v1" / "caja_arqueo.py"
)


_FORBIDDEN_UPDATE_PATTERNS = [
    r"update\s*\(\s*Arqueo\s*\)",
    r"update\s*\(\s*Alerta\s*\)",
    r"update\s*\(\s*FacturaPagos\s*\)",
    r"update\s*\(\s*AlertTypes\s*\)",
    r"update\s*\(\s*LogTransaccional\s*\)",
    r"UPDATE\s+prod\.arqueo",
    r"UPDATE\s+prod\.alerta",
    r"UPDATE\s+prod\.factura_pagos",
    r"UPDATE\s+prod\.alert_types",
    r"UPDATE\s+prod\.log_transaccional",
]


def _scan_source(path: Path, patterns: list[str]) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    hits: list[tuple[int, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for pat in patterns:
            if re.search(pat, line, flags=re.IGNORECASE):
                hits.append((line_no, pat))
    return hits


def test_arqueo_post_handler_no_update_on_a_tables() -> None:
    """T5.2 / KD-ARQUEO-02: no UPDATE on [A] tables in post_arqueo body."""
    hits = _scan_source(_HANDLER_FILE, _FORBIDDEN_UPDATE_PATTERNS)
    assert not hits, (
        "KD-ARQUEO-02 violated: raw UPDATE on [A] tables in "
        "post_arqueo source:\n"
        + "\n".join(f"  line {ln}: {pat}" for ln, pat in hits)
        + "\nUse repo.append_only.append_event / repo.workflow.append_transition "
        "instead."
    )
