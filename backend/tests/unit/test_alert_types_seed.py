"""HU-F1.14 / T4.2 -- MIGRATION 0032 alert_types siembra unit tests.

Four unit tests covering the canonical 11-code seed rowset, the
``DEC-SYNC-05`` (10 net new) invariant, the ``DEC-SYNC-06`` severity
mapping, and the ``ON CONFLICT (tipo_alerta) DO NOTHING`` idempotency
pattern.

Source-level + AST-light approach -- no real DB. The seed rowset is
exposed as ``_SEED_ROWS`` at module top-level so the assertions can
inspect the canonical tuple directly (mirrors F1.13 ``_SEED_ROWS`` in
``0031_arqueo_cierre_dia_and_gap_be_05.py``).
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(
    0,
    str(_BACKEND_ROOT / "packages" / "parkos_core" / "migrations" / "versions"),
)

_MIGRATION_FILE = (
    _BACKEND_ROOT
    / "packages"
    / "parkos_core"
    / "migrations"
    / "versions"
    / "0032_seed_alert_types_operativos.py"
)


def _load_m0032():
    return importlib.import_module("0032_seed_alert_types_operativos")


# ---------------------------------------------------------------------------
# T4.2.1 -- canonical 11 codes + DEC-SYNC-05 (10 net new)
# ---------------------------------------------------------------------------


def test_seed_rows_canonical_11_codes_with_one_idempotent() -> None:
    """T4.2.1 / DEC-SYNC-05: _SEED_ROWS has exactly 11 codes (10 net new + descuadre_critico)."""
    m0032 = _load_m0032()
    seed_rows = m0032._SEED_ROWS  # noqa: SLF001

    assert len(seed_rows) == 11, (
        f"DEC-SYNC-05 violated: expected 11 alert_types codes, "
        f"got {len(seed_rows)}"
    )

    codes = [row[0] for row in seed_rows]
    assert "descuadre_critico" in codes, (
        "DEC-SYNC-05 violated: _SEED_ROWS MUST include descuadre_critico "
        "(F1.13 idempotent re-attempt via ON CONFLICT DO NOTHING)"
    )

    net_new = [c for c in codes if c != "descuadre_critico"]
    assert len(net_new) == 10, (
        f"DEC-SYNC-05 violated: expected 10 NET NEW alert_types codes, "
        f"got {len(net_new)} ({net_new!r})"
    )


# ---------------------------------------------------------------------------
# T4.2.2 -- DEC-SYNC-06 severity mapping (alta=critical, media=warning, baja=info)
# ---------------------------------------------------------------------------


def test_seed_rows_severity_mapping_per_dec_sync_06() -> None:
    """T4.2.2 / DEC-SYNC-06: severity MUST be in {'critical', 'warning', 'info'}."""
    m0032 = _load_m0032()
    seed_rows = m0032._SEED_ROWS  # noqa: SLF001

    allowed = {"critical", "warning", "info"}
    bad: list[tuple[str, str]] = []
    for tipo_alerta, severity, _desc in seed_rows:
        if severity not in allowed:
            bad.append((tipo_alerta, severity))
    assert not bad, (
        f"DEC-SYNC-06 violated: invalid severity in _SEED_ROWS: {bad!r}. "
        f"Allowed values per prod.alert_types CHECK constraint "
        f"(migration 0013 line 119): {sorted(allowed)!r}"
    )


def test_seed_rows_severity_distribution_per_plan_md_1131() -> None:
    """T4.2.2 / DEC-SYNC-06: severity distribution matches plan.md line 1131.

    Per plan.md line 1131 the canonical 11 codes split as:

      * 5 critical: sync_fallida, evento_no_procesado, impresora_caida,
        fe_error_toppoint, numeracion_toppoint_agotada
      * 1 critical (idempotent): descuadre_critico
      * 4 warning: capacidad_agotada, capacidad_agotada_forzado,
        arqueo_pendiente_24h, suscripcion_proxima_vencer
      * 1 info: cache_desactualizado

    Total critical = 6, warning = 4, info = 1 (11 codes).
    """
    m0032 = _load_m0032()
    seed_rows = m0032._SEED_ROWS  # noqa: SLF001

    counts = {"critical": 0, "warning": 0, "info": 0}
    for _tipo_alerta, severity, _desc in seed_rows:
        counts[severity] += 1
    assert counts == {"critical": 6, "warning": 4, "info": 1}, (
        f"DEC-SYNC-06 violated: severity distribution is {counts!r}, "
        f"expected {{'critical': 6, 'warning': 4, 'info': 1}}"
    )


# ---------------------------------------------------------------------------
# T4.2.3 -- ON CONFLICT (tipo_alerta) DO NOTHING idempotency pattern
# ---------------------------------------------------------------------------


def test_upgrade_emits_on_conflict_do_nothing_for_idempotency() -> None:
    """T4.2.3 / DEC-SYNC-05: upgrade() emits ``ON CONFLICT (tipo_alerta) DO NOTHING``.

    Source-level scan: the upgrade body MUST contain the
    ``ON CONFLICT (tipo_alerta) DO NOTHING`` literal so a second
    ``alembic upgrade head`` is a no-op (idempotency). The
    ``alert_types_inmutable`` trigger (migration 0013:21-22) blocks
    UPDATE/DELETE only -- INSERT with ON CONFLICT is allowed.
    """
    text = _MIGRATION_FILE.read_text(encoding="utf-8")
    # Extract upgrade() body roughly -- between def upgrade and def downgrade
    upgrade_match = re.search(
        r"def\s+upgrade\s*\(\s*\)\s*->\s*None\s*:\s*(.*?)(?=\n\ndef\s+downgrade)",
        text,
        flags=re.DOTALL,
    )
    assert upgrade_match is not None, (
        "Cannot locate upgrade() body in MIGRATION 0032 source"
    )
    upgrade_body = upgrade_match.group(1)

    assert "ON CONFLICT (tipo_alerta) DO NOTHING" in upgrade_body, (
        "DEC-SYNC-05 violated: upgrade() MUST emit "
        "`ON CONFLICT (tipo_alerta) DO NOTHING` for idempotency. "
        "A second alembic upgrade head must be a no-op."
    )


def test_downgrade_delete_sql_excludes_descuadre_critico() -> None:
    """T4.2.3 / DEC-SYNC-05: downgrade's DELETE SQL excludes descuadre_critico.

    Runtime check via mocked ``op.execute`` (mirrors F1.13
    ``test_migration_0032_downgrade_preserves_descuadre_critico``).
    Captures every SQL the downgrade emits and verifies the
    ``DELETE FROM prod.alert_types`` statement does NOT contain
    ``descuadre_critico`` in its WHERE IN clause.
    """
    from unittest.mock import patch

    m0032 = _load_m0032()
    seed_rows = m0032._SEED_ROWS  # noqa: SLF001

    executed_sqls: list[str] = []
    with patch.object(
        m0032.op,
        "execute",
        side_effect=lambda sql: executed_sqls.append(sql),
    ):
        m0032.downgrade()

    delete_sqls = [s for s in executed_sqls if "DELETE FROM prod.alert_types" in s]
    assert len(delete_sqls) == 1, (
        f"downgrade() must emit exactly one DELETE against prod.alert_types; "
        f"got {len(delete_sqls)}"
    )
    delete_sql = delete_sqls[0]
    assert "descuadre_critico" not in delete_sql, (
        "DEC-SYNC-05 violated: downgrade() DELETE MUST NOT touch "
        "descuadre_critico (F1.13-owned)."
    )
    # All 10 net new codes MUST be in the WHERE IN clause.
    net_new_codes = [code for code, _, _ in seed_rows if code != "descuadre_critico"]
    for code in net_new_codes:
        assert f"'{code}'" in delete_sql, (
            f"downgrade() DELETE missing net new code {code!r} in WHERE clause"
        )
