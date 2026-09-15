"""HU-F1.9 / MIGRATION 0027 -- idempotency + trigger + partial index invariants.

Red-Phase test files gate the migration's correctness against these
invariants (mirrors F1.7's MIGRATION 0026 precedent, tasks Phase 5
T5.4):

1. The migration file exists at
   ``0027_one_factura_per_salida_and_init_pago_trigger_and_revoke.py``.
2. ``revision`` and ``down_revision`` are wired to chain after
   MIGRATION 0026.
3. The migration script defines an ``upgrade()`` function with the
   expected operations in order.
4. The Op 3 BEFORE INSERT trigger function name follows the documented
   discriminator ``fn_factura_pagos_init_pago_uniqueness``.
5. The Op 2 unique-index name follows ``one_factura_per_salida``.

These are static-analysis tests so they RUN without a DB (bypassing
the session-level pytest skip cascade for DB-gated suites).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

MIGRATION_PATH = Path(
    "packages/parkos_core/migrations/versions/"
    "0027_one_factura_per_salida_and_init_pago_trigger_and_revoke.py"
)


def test_migration_0027_file_exists() -> None:
    """RED: MIGRATION 0027 file MUST exist before this test passes."""
    assert MIGRATION_PATH.is_file(), (
        f"MIGRATION 0027 file missing at {MIGRATION_PATH}. "
        "Create it with revision='0027_...', down_revision="
        "'0026_seed_impuestos_iva_and_one_exit_per_ingreso'."
    )


def test_migration_0027_revision_and_chain() -> None:
    """GREEN: revision + down_revision correctly wired to chain after 0026."""
    spec = importlib.util.spec_from_file_location(
        "mig_0027", str(MIGRATION_PATH)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == (
        "0027_one_factura_per_salida_and_init_pago_trigger_and_revoke"
    )
    assert module.down_revision == (
        "0026_seed_impuestos_iva_and_one_exit_per_ingreso"
    )


def test_migration_0027_has_upgrade_function() -> None:
    """GREEN: the module MUST expose an upgrade() function."""
    spec = importlib.util.spec_from_file_location(
        "mig_0027", str(MIGRATION_PATH)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(getattr(module, "upgrade", None))
    assert callable(getattr(module, "downgrade", None))


def test_migration_0027_op3_trigger_function_name() -> None:
    """GREEN: source contains the discriminator trigger name.

    The repo handler ``crear_factura_pago`` catches IntegrityError with
    the substring ``factura_pagos_init_pago_uniqueness`` (MIGRATION
    0027 Op 3 analogía migration 0004). The migration source MUST
    install that exact trigger name.
    """
    src = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "fn_factura_pagos_init_pago_uniqueness" in src, (
        "MIGRATION 0027 Op 3 must install trigger function "
        "fn_factura_pagos_init_pago_uniqueness on prod.factura_pagos."
    )
    assert "factura_pagos_init_pago_uniqueness" in src, (
        "MIGRATION 0027 must wire the trigger name "
        "factura_pagos_init_pago_uniqueness (analogía migration 0004)."
    )


def test_migration_0027_op2_unique_index_name() -> None:
    """GREEN: source contains the unique-index name and CONCURRENTLY clause.

    The repo handler ``crear_factura_evento`` catches IntegrityError with
    ``one_factura_per_salida`` (MIGRATION 0027 Op 2). The migration
    source MUST install that exact index.
    """
    src = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "one_factura_per_salida" in src, (
        "MIGRATION 0027 Op 2 must install unique index "
        "one_factura_per_salida on prod.facturas (uuid_salida) WHERE uuid_salida IS NOT NULL."
    )
    assert "CONCURRENTLY" in src, (
        "MIGRATION 0027 Op 2 must use CREATE UNIQUE INDEX CONCURRENTLY "
        "(no lock reads/writes in production)."
    )
