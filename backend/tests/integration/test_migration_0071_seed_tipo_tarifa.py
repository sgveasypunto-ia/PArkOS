"""QA batch tarifas/cupos -- MIGRATION 0071 seed prod.tipo_tarifa.

Pre-flight found ``prod.tipo_tarifa`` empty in every environment (no
migration ever seeded it) while ``apps/web_admin/src/features/tarifas``
hardcodes 4 fixed UUIDs (hora/fraccion/plena/nocturna) to build the
CREATE/EDIT/HISTORIAL payloads and to group the flattened list. Without
a seed, the Tarifas module is broken out of the box on any fresh
install, not just this QA environment.

This migration seeds those exact 4 UUIDs (idempotent, fixed ``uuid``
instead of ``gen_random_uuid()`` so the frontend lookup keeps working
across re-runs/fresh installs) -- mirrors the 0040 tipo_arqueo siembra
pattern.

T1.1 RED: importing the module raises ``ModuleNotFoundError`` before
the migration file exists.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

sys.path.insert(
    0,
    str(_BACKEND_ROOT / "packages" / "parkos_core" / "migrations" / "versions"),
)

# Fixed UUIDs hardcoded by the frontend -- see
# apps/web_admin/src/features/tarifas/api/tarifaAgrupada.ts:43-46.
_FRONTEND_UUIDS = {
    "hora": "12e3886a-7059-47ee-bdb2-aa5fb1272bea",
    "fraccion": "c41b6602-f7b2-437d-bcfc-0462cd385eda",
    "plena": "d83ebff8-9546-43b3-91b1-bedffa57717f",
    "nocturna": "9f8ba4a9-6fd9-4da7-8ddb-97ce323a8600",
}


def test_migration_0071_module_imports_with_canonical_revision() -> None:
    mod = importlib.import_module("0071_seed_tipo_tarifa_modalidades")
    assert mod.revision == "0071_seed_tipo_tarifa_modalidades"
    assert mod.down_revision == "0070_grant_configuracion_caja_privileges"


def test_migration_0071_upgrade_and_downgrade_are_callable() -> None:
    mod = importlib.import_module("0071_seed_tipo_tarifa_modalidades")
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_migration_0071_seed_rows_match_frontend_hardcoded_uuids() -> None:
    """``_SEED_ROWS`` must carry the exact 4 (tipo, uuid) pairs the
    frontend hardcodes, or the Tarifas module stays broken after
    seeding with the wrong UUIDs."""
    mod = importlib.import_module("0071_seed_tipo_tarifa_modalidades")
    seed_rows = mod._SEED_ROWS  # noqa: SLF001

    assert isinstance(seed_rows, tuple)
    assert len(seed_rows) == 4

    seen: dict[str, str] = {}
    for row in seed_rows:
        assert isinstance(row, tuple) and len(row) == 2
        tipo, uuid_fijo = row
        assert tipo not in seen, f"duplicate tipo in _SEED_ROWS: {tipo!r}"
        seen[tipo] = uuid_fijo

    assert seen == _FRONTEND_UUIDS, (
        f"seeded (tipo -> uuid) must match the frontend hardcoded UUIDs exactly; "
        f"got {seen!r}, expected {_FRONTEND_UUIDS!r}"
    )
