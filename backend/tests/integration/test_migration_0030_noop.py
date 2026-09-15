"""HU-F1.12 / T7.3 -- MIGRATION 0030 module-contract test.

MIGRATION 0030 is a NO-OP audit trail (DEC-VENTA-08 WITHDRAWN):
pre-flight ``DO $$`` block verifies all 5 [V] tables exist + all 5
sync catalog entries registered, then ``upgrade()`` + ``downgrade()``
are empty callables.

Asserts:

  * T6.1 RED: module imports + ``revision`` +
    ``down_revision == "0029_reimpresion_siembra_and_permiso_anular"``.
  * T6.2 GREEN: ``upgrade()`` and ``downgrade()`` are callables.
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


def test_migration_0030_module_imports_with_canonical_revision() -> None:
    """T7.3 RED: module imports + revision metadata matches F1.11 head."""
    mod = importlib.import_module("0030_venta_suscripcion_optional")
    assert mod.revision == "0030_venta_suscripcion_optional", (
        f"unexpected revision id: {mod.revision!r}"
    )
    assert mod.down_revision == (
        "0029_reimpresion_siembra_and_permiso_anular"
    ), (
        "F1.12 migration must chain off the F1.11 head "
        "(0029_reimpresion_siembra_and_permiso_anular); got "
        f"{mod.down_revision!r}"
    )


def test_migration_0030_upgrade_and_downgrade_are_callable() -> None:
    """T7.3 GREEN: ``upgrade()`` + ``downgrade()`` are callables.

    Both are NO-OP bodies (MIGRATION 0030 is an audit trail only;
    no schema changes -- DEC-VENTA-08 WITHDRAWN). The module
    captures the alembic ``op`` module via global lookup, so we
    only assert the symbols exist + are callable.
    """
    mod = importlib.import_module("0030_venta_suscripcion_optional")
    assert callable(mod.upgrade), "MIGRATION 0030 upgrade() is not callable"
    assert callable(mod.downgrade), "MIGRATION 0030 downgrade() is not callable"