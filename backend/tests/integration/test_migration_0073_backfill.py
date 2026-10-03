"""MIGRATION 0073 -- backfill ``prod.factura_pagos.uuid_sucursal``.

Static-analysis tests (no DB needed), same style as
``test_migration_0027_idempotent.py``.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

MIGRATION_PATH = Path(
    "packages/parkos_core/migrations/versions/"
    "0073_backfill_factura_pagos_uuid_sucursal.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("mig_0073", str(MIGRATION_PATH))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_0073_file_exists() -> None:
    assert MIGRATION_PATH.is_file(), f"MIGRATION 0073 file missing at {MIGRATION_PATH}."


def test_migration_0073_revision_and_chain() -> None:
    module = _load_module()
    assert module.revision == "0073_backfill_factura_pagos_uuid_sucursal"
    assert module.down_revision == "0072_grant_v_factura_electronica_acuse_select"


def test_migration_0073_has_upgrade_and_downgrade() -> None:
    module = _load_module()
    assert callable(getattr(module, "upgrade", None))
    assert callable(getattr(module, "downgrade", None))


def test_migration_0073_backfill_is_idempotent_and_scoped() -> None:
    """The UPDATE must only touch NULL rows and join through facturas."""
    src = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "UPDATE prod.factura_pagos" in src
    assert "fp.uuid_sucursal IS NULL" in src
    assert "prod.facturas" in src
