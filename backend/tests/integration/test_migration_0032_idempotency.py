"""HU-F1.14 / T1.1 -- MIGRATION 0032 pre-flight + module-contract tests.

Pre-flight on 2026-09-15 confirmed:

  * ``prod.alert_types`` exists with PK ``tipo_alerta`` +
    ``alert_types_inmutable`` trigger active + ``severity`` CHECK
    constraint accepting ``('info', 'warning', 'critical')``
    (migration 0013:21-22 + line 119).
  * ``prod.alert_types`` carries 9 seeded rows pre-F1.14: 8 técnicos
    (migration 0013) + 1 ``descuadre_critico`` (F1.13 MIGRATION 0031
    Op 2 lines 169-175).
  * ``prod.sync_log`` + ``prod.sync_queue`` exist (F1.14 endpoint
    reads both).
  * ``audit_read`` permission pre-seeded at
    ``0002_seed_permisos_canonicos.py:48`` (DEC-SYNC-03.B).

This module verifies the migration file metadata + the pre-flight state
(source-level + structure).

T1.1 RED: ``test_migration_0032_module_imports_with_canonical_revision``
asserts that the new migration module is importable + has the right
``revision`` + ``down_revision`` chain (F1.13 head = ``0031_...``).
Pre-implementation this raises ``ModuleNotFoundError`` -- that is the
RED state.
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


def test_migration_0032_module_imports_with_canonical_revision() -> None:
    """T1.1 RED/GREEN: module imports + revision metadata matches F1.13 head.

    MIGRATION 0032 chains off F1.13 head
    (``0031_arqueo_cierre_dia_and_gap_be_05``) and uses revision id
    ``0032_seed_alert_types_operativos``. Pre-implementation this raises
    ``ModuleNotFoundError`` -- that is the RED state.
    """
    mod = importlib.import_module("0032_seed_alert_types_operativos")
    assert mod.revision == "0032_seed_alert_types_operativos", (
        f"unexpected revision id: {mod.revision!r}"
    )
    assert mod.down_revision == "0031_arqueo_cierre_dia_and_gap_be_05", (
        "F1.14 migration must chain off the F1.13 head "
        "(0031_arqueo_cierre_dia_and_gap_be_05); got "
        f"{mod.down_revision!r}"
    )


def test_migration_0032_upgrade_and_downgrade_are_callable() -> None:
    """T1.1 GREEN: ``upgrade()`` + ``downgrade()`` are callables.

    MIGRATION 0032 is a REAL siembra (DEC-SYNC-05 + DEC-SYNC-06 +
    DEC-SYNC-07 + DEC-SYNC-10): pre-flight DO $$ block + Op 1 siembra
    11 alert_types codes (10 net new + idempotent re-attempt of
    ``descuadre_critico``) + Op 2 NO-DDL audit anchor for DEC-SYNC-03.B
    audit_read reuse. We assert the symbols exist and are callable (the
    DB layer is exercised in gated integration tests, not here).
    """
    mod = importlib.import_module("0032_seed_alert_types_operativos")
    assert callable(mod.upgrade), "MIGRATION 0032 upgrade() is not callable"
    assert callable(mod.downgrade), "MIGRATION 0032 downgrade() is not callable"


def test_migration_0032_seed_rows_canonical_11_codes() -> None:
    """T1.1 GREEN: ``_SEED_ROWS`` carries exactly the 11 plan.md line 1131 codes.

    ``DEC-SYNC-05``: 11 codes total = 10 net new + idempotent re-attempt
    of ``descuadre_critico`` (already seeded by F1.13 MIGRATION 0031
    Op 2 lines 169-175). ``DEC-SYNC-06``: severity mapping per plan.md
    line 1131 verbatim (alta -> critical, media -> warning, baja ->
    info). ``DEC-SYNC-10``: ``descripcion`` field per code.
    """
    mod = importlib.import_module("0032_seed_alert_types_operativos")
    seed_rows = mod._SEED_ROWS  # noqa: SLF001 -- source-level guard

    assert isinstance(seed_rows, tuple), f"_SEED_ROWS must be a tuple, got {type(seed_rows)}"
    assert len(seed_rows) == 11, f"expected 11 seed rows per plan.md line 1131, got {len(seed_rows)}"

    # Build the canonical (tipo_alerta, severity) tuples per plan.md line 1131.
    # Severity mapping: alta -> critical, media -> warning, baja -> info.
    canonical: dict[str, str] = {
        "sync_fallida": "critical",
        "capacidad_agotada": "warning",
        "capacidad_agotada_forzado": "warning",
        "evento_no_procesado": "critical",
        "impresora_caida": "critical",
        "fe_error_toppoint": "critical",
        "numeracion_toppoint_agotada": "critical",
        "cache_desactualizado": "info",
        "arqueo_pendiente_24h": "warning",
        "suscripcion_proxima_vencer": "warning",
        "descuadre_critico": "critical",
    }

    seen_codes: set[str] = set()
    for row in seed_rows:
        assert isinstance(row, tuple) and len(row) == 3, (
            f"each seed row must be a 3-tuple (tipo_alerta, severity, descripcion); got {row!r}"
        )
        tipo_alerta, severity, descripcion = row
        assert tipo_alerta not in seen_codes, (
            f"duplicate tipo_alerta in _SEED_ROWS: {tipo_alerta!r}"
        )
        seen_codes.add(tipo_alerta)
        assert tipo_alerta in canonical, (
            f"unexpected tipo_alerta {tipo_alerta!r} not in plan.md line 1131 list"
        )
        assert severity == canonical[tipo_alerta], (
            f"severity mismatch for {tipo_alerta!r}: expected {canonical[tipo_alerta]!r}, "
            f"got {severity!r} (DEC-SYNC-06)"
        )
        assert isinstance(descripcion, str) and len(descripcion) > 0, (
            f"descripcion must be a non-empty string for {tipo_alerta!r} (DEC-SYNC-10)"
        )

    missing = set(canonical) - seen_codes
    assert not missing, f"missing seed codes per plan.md line 1131: {sorted(missing)}"


def test_migration_0032_downgrade_preserves_descuadre_critico() -> None:
    """T1.3 REFACTOR: ``downgrade()`` excludes ``descuadre_critico``.

    F1.13 MIGRATION 0031 Op 2 lines 169-175 owns ``descuadre_critico``.
    F1.14's downgrade MUST NOT touch it (DEC-SYNC-05 + DEC-ARQUEO-09b).

    Verifies via runtime filter (the downgrade builds the DELETE list
    via a list comprehension at call time -- not via source-level
    string literals).
    """
    mod = importlib.import_module("0032_seed_alert_types_operativos")
    seed_rows = mod._SEED_ROWS  # noqa: SLF001

    # _SEED_ROWS MUST contain ``descuadre_critico`` (idempotent re-seed).
    code_set = {code for code, _, _ in seed_rows}
    assert "descuadre_critico" in code_set, (
        "F1.14 MUST re-seed descuadre_critico (idempotent via ON CONFLICT DO NOTHING) "
        "even though F1.13 already seeded it"
    )

    # The runtime filter that ``downgrade()`` uses MUST exclude
    # descuadre_critico and yield exactly 10 net new codes.
    net_new_codes = [code for code, _, _ in seed_rows if code != "descuadre_critico"]
    assert len(net_new_codes) == 10, (
        f"F1.14 must contribute 10 net new codes (DEC-SYNC-05); got {len(net_new_codes)}"
    )
    assert "descuadre_critico" not in net_new_codes, (
        "downgrade's filter MUST exclude descuadre_critico "
        "(owned by F1.13 MIGRATION 0031 Op 2)"
    )

    # Verify the SQL the downgrade actually emits. Mock ``op.execute``
    # to capture the DELETE statement and assert descuadre_critico is
    # NOT in the WHERE clause.
    from unittest.mock import patch

    executed_sqls: list[str] = []
    with patch.object(mod.op, "execute", side_effect=lambda sql: executed_sqls.append(sql)):
        mod.downgrade()

    delete_sqls = [s for s in executed_sqls if "DELETE FROM prod.alert_types" in s]
    assert len(delete_sqls) == 1, (
        f"downgrade() must emit exactly one DELETE against prod.alert_types; "
        f"got {len(delete_sqls)}"
    )
    delete_sql = delete_sqls[0]
    assert "descuadre_critico" not in delete_sql, (
        "downgrade() DELETE MUST NOT touch descuadre_critico "
        "(owned by F1.13 MIGRATION 0031 Op 2 lines 169-175)"
    )
    # All 10 net new codes MUST be in the WHERE IN (...) clause.
    for code in net_new_codes:
        assert f"'{code}'" in delete_sql, (
            f"downgrade() DELETE missing net new code {code!r} in WHERE clause"
        )


# ---------------------------------------------------------------------------
# T1.1.2 -- DEC-SYNC-03.B: audit_read permission pre-seeded at 0002:48
# ---------------------------------------------------------------------------


def test_audit_read_pre_seeded_in_0002_migration() -> None:
    """T1.1: ``audit_read`` permission is pre-seeded in ``0002_seed_permisos_canonicos.py``.

    DEC-SYNC-03.B resolved: no new permission seeded in MIGRATION 0032;
    the F1.14 endpoint reuses ``audit_read`` from the canonical
    permission list. This test asserts the source-level invariant.
    """
    p = (
        _BACKEND_ROOT
        / "packages"
        / "parkos_core"
        / "migrations"
        / "versions"
        / "0002_seed_permisos_canonicos.py"
    )
    assert p.is_file(), f"canonical migration missing: {p}"
    source = p.read_text(encoding="utf-8")
    assert '"audit_read"' in source or "'audit_read'" in source, (
        "0002_seed_permisos_canonicos.py must pre-seed the audit_read permission "
        "(DEC-SYNC-03.B)"
    )
