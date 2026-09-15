"""HU-F1.13 / T1.1 -- MIGRATION 0031 pre-flight + module-contract tests.

Pre-flight on 2026-09-15 confirmed:

  * 7 required tables exist in ``prod`` (tipo_arqueo, alert_types,
    arqueo, sesion, alerta, configuracion_tolerancias, factura_pagos).
  * ``prod.tipo_arqueo.cierre_dia`` is NOT yet seeded (A-07 gap).
  * ``prod.alert_types.descuadre_critico`` is NOT yet seeded (DEC-ARQUEO-09b gap).
  * GAP-BE-05 sites #1 + #2 still carry ``permission_required="emitir_factura"``
    at ``api/v1/caja.py:53`` + ``api/v1/caja_sesion.py:257``.

This module verifies the migration file metadata + the pre-flight state
(source-level + structure).
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

# Parkos-core versions directory on PYTHONPATH so the module can be imported.
sys.path.insert(
    0,
    str(_BACKEND_ROOT / "packages" / "parkos_core" / "migrations" / "versions"),
)

# ---------------------------------------------------------------------------
# T1.1.1 -- migration file metadata
# ---------------------------------------------------------------------------


def test_migration_0031_module_imports_with_canonical_revision() -> None:
    """T1.1 RED/GREEN: module imports + revision metadata matches F1.12 head."""
    mod = importlib.import_module("0031_arqueo_cierre_dia_and_gap_be_05")
    assert mod.revision == "0031_arqueo_cierre_dia_and_gap_be_05", (
        f"unexpected revision id: {mod.revision!r}"
    )
    assert mod.down_revision == "0030_venta_suscripcion_optional", (
        "F1.13 migration must chain off the F1.12 head "
        "(0030_venta_suscripcion_optional); got "
        f"{mod.down_revision!r}"
    )


def test_migration_0031_upgrade_and_downgrade_are_callable() -> None:
    """T1.1 GREEN: ``upgrade()`` + ``downgrade()`` are callables.

    MIGRATION 0031 is a REAL siembra (DEC-ARQUEO-09): pre-flight DO $$
    + Op 1 siembra cierre_dia + Op 2 siembra descuadre_critico +
    Op 3 NO-DDL anchor for GAP-BE-05. We assert the symbols exist
    and are callable (the DB layer is exercised in gated integration
    tests, not here).
    """
    mod = importlib.import_module("0031_arqueo_cierre_dia_and_gap_be_05")
    assert callable(mod.upgrade), "MIGRATION 0031 upgrade() is not callable"
    assert callable(mod.downgrade), "MIGRATION 0031 downgrade() is not callable"


# ---------------------------------------------------------------------------
# T1.1.4/T1.1.5 -- GAP-BE-05 source-level confirmation
# ---------------------------------------------------------------------------


def test_gap_be_05_site_1_caja_py_emits_factura_pre_fix() -> None:
    """GAP-BE-05 site #1: ``api/v1/caja.py:53`` -- pre-fix still emits.

    The actual fix lands in T-GAP-BE-05 (commit 9). This test confirms
    the pre-fix state exists at the source-level so the T-GAP test has
    a clean baseline to assert against (defensive readback).
    """
    caja_py = (
        _BACKEND_ROOT
        / "packages"
        / "parkos_core"
        / "src"
        / "parkos_core"
        / "api"
        / "v1"
        / "caja.py"
    )
    assert caja_py.is_file(), f"missing {caja_py}"
    text = caja_py.read_text(encoding="utf-8")
    # Pre-fix: permission_required="emitir_factura" appears in caja.py
    # (either as the GAP-BE-05 site #1 itself OR as a different read-
    # only mount — both forms satisfy the search; the T-GAP test
    # confirms the FIX is the one in the arqueo factory).
    assert "emitir_factura" in text, (
        "GAP-BE-05 site #1 expected to carry emitir_factura pre-fix; "
        "if this fails the GAP has already been applied (skip this test)."
    )


def test_gap_be_05_site_2_caja_sesion_py_emits_factura_pre_fix() -> None:
    """GAP-BE-05 site #2: ``api/v1/caja_sesion.py:257`` -- pre-fix still emits."""
    caja_sesion_py = (
        _BACKEND_ROOT
        / "packages"
        / "parkos_core"
        / "src"
        / "parkos_core"
        / "api"
        / "v1"
        / "caja_sesion.py"
    )
    assert caja_sesion_py.is_file(), f"missing {caja_sesion_py}"
    text = caja_sesion_py.read_text(encoding="utf-8")
    assert "emitir_factura" in text, (
        "GAP-BE-05 site #2 expected to carry emitir_factura pre-fix."
    )
