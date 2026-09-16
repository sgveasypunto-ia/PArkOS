"""HU-F1.13 / T-GAP-BE-05 -- permission-string fix.

GAP-BE-05: two factory-mounted routers were tagged with the wrong
``permission_required`` string at F1.7 (both used ``emitir_factura``
which is reserved for the F1.11 venta chain). HU-F1.13 bundle fixes
them to the correct tokens:

  * ``api/v1/caja.py:53``         ``emitir_factura`` -> ``realizar_arqueo``
  * ``api/v1/caja_sesion.py:257`` ``emitir_factura`` -> ``abrir_cerrar_caja``

This is a static guard: assert the literal permission string passed to
``make_router(..., permission_required=...)`` is the corrected token.
A future regression that re-introduces ``emitir_factura`` in either
file will fail this test.
"""
from __future__ import annotations

import re
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"

_CAJA_FILE = _PARKOS_CORE_SRC / "parkos_core" / "api" / "v1" / "caja.py"
_CAJA_SESION_FILE = _PARKOS_CORE_SRC / "parkos_core" / "api" / "v1" / "caja_sesion.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_permission_literal(source: str) -> str:
    """Return the ``permission_required="..."`` literal in the source.

    Asserts there is exactly one such literal and it is the corrected
    GAP-BE-05 token.
    """
    pattern = re.compile(r'permission_required\s*=\s*"([^"]+)"')
    matches = pattern.findall(source)
    assert len(matches) == 1, (
        f"expected exactly 1 `permission_required=\"...\"` literal, "
        f"found {len(matches)}: {matches}"
    )
    return matches[0]


def test_gap_be_05_caja_permission_is_realizar_arqueo() -> None:
    """GAP-BE-05 site #1: api/v1/caja.py -- permission_required='realizar_arqueo'."""
    source = _read(_CAJA_FILE)
    literal = _extract_permission_literal(source)
    assert literal == "realizar_arqueo", (
        f"GAP-BE-05 site #1 violated: api/v1/caja.py uses "
        f"permission_required={literal!r}; expected 'realizar_arqueo'."
    )


def test_gap_be_05_caja_sesion_permission_is_abrir_cerrar_caja() -> None:
    """GAP-BE-05 site #2: api/v1/caja_sesion.py -- permission_required='abrir_cerrar_caja'."""
    source = _read(_CAJA_SESION_FILE)
    literal = _extract_permission_literal(source)
    assert literal == "abrir_cerrar_caja", (
        f"GAP-BE-05 site #2 violated: api/v1/caja_sesion.py uses "
        f"permission_required={literal!r}; expected 'abrir_cerrar_caja'."
    )
