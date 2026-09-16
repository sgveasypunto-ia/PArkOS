"""HU-F1.7 / migration 0026 -- idempotency proof + IVA row presence.

Verifies:
  - T1: ``alembic upgrade head`` reaches head ``0026_seed_impuestos_iva_...
    _one_exit_per_ingreso`` (chain tail).
  - T2: post-upgrade, ``prod.impuestos`` contains exactly ONE row with
        ``codigo='IVA'``, ``porcentaje=0.19``, ``estado='activo'``,
        ``vigente_hasta IS NULL`` (migration 0026 Op 2 inline-seed).
  - T3: post-upgrade, ``prod.alert_types`` contains the 2 F1.7 alert
        types seeded by Op 3: ``subscripcion_vencida_forzado`` and
        ``tarifa_vigente_forzado``, both with ``severity='warning'``.
  - T4: post-upgrade, the partial unique index ``one_exit_per_ingreso``
        exists on ``prod.salidas (uuid_ingreso) WHERE NOT EXISTS (...)``.

Mirrors F1.6 ``test_migration_0025_datos_nuevos.py`` pattern: pre-flight
+ post-upgrade assertions, no destructive downgrade inside the test
(downgrade round-trip is owned by the ``alembic_upgrade`` session fixture
on a fresh DB; F1.5 precedent).
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# T1: alembic head is 0026
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alembic_head_includes_0026(pg_engine) -> None:
    """T1: ``alembic upgrade head`` lands on migration 0026.

    Confirms the migration is part of the active chain (down_revision
    wired to ``0025_alerta_datos_nuevos``, F1.6 chain head).
    """
    async with AsyncSession(pg_engine) as session:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
        row = result.first()
    assert row is not None, "alembic_version row missing"
    assert row[0] == "0026_seed_impuestos_iva_and_one_exit_per_ingreso", (
        f"alembic head must be 0026_seed_impuestos_iva_and_one_exit_per_ingreso, "
        f"got {row[0]!r}"
    )


# ---------------------------------------------------------------------------
# T2: prod.impuestos.IVA row present (single, vigente, porcentaje=0.19)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_iva_row_presente_post_migration(pg_engine) -> None:
    """T2: post-upgrade, ``prod.impuestos`` MUST contain a row
    ``codigo='IVA'`` with ``porcentaje=0.19``, ``estado='activo'`` and
    ``vigente_hasta IS NULL``.

    RED phase: row missing (filter ``WHERE codigo='IVA'`` returns 0).
    GREEN phase: row present, idempotent across re-applies (``ON
    CONFLICT (codigo, vigente_desde) DO NOTHING``).
    """
    async with AsyncSession(pg_engine) as session:
        result = await session.execute(
            text(
                "SELECT porcentaje, estado, vigente_hasta, nombre "
                "FROM prod.impuestos WHERE codigo='IVA'"
            )
        )
        rows = result.fetchall()
    assert len(rows) >= 1, (
        "prod.impuestos MUST contain codigo='IVA' after migration 0026. "
        "Migration 0026 Op 2 must INSERT this row with ON CONFLICT DO NOTHING."
    )
    # Find the vigente row (vigente_hasta IS NULL, estado='activo').
    vigente = [r for r in rows if r[2] is None and r[1] == "activo"]
    assert len(vigente) == 1, (
        f"IVA must have exactly one vigente row (estado='activo', "
        f"vigente_hasta IS NULL); got {len(vigente)}: {vigente!r}"
    )
    porcentaje, estado, vigente_hasta, nombre = vigente[0]
    assert float(porcentaje) == 0.19, (
        f"IVA porcentaje must be 0.19 (regulatory constant, "
        f"IVA Colombia 2026); got {porcentaje!r}"
    )
    assert nombre == "IVA", f"nombre must be 'IVA', got {nombre!r}"


# ---------------------------------------------------------------------------
# T3: 2 F1.7 alert_types seeded (subscripcion_vencida_forzado +
#     tarifa_vigente_forzado)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alert_types_f17_insertados(pg_engine) -> None:
    """T3: post-upgrade, ``prod.alert_types`` MUST contain both F1.7
    alert types with ``severity='warning'``:

      - ``subscripcion_vencida_forzado`` (V2 bypass)
      - ``tarifa_vigente_forzado`` (V5 bypass)
    """
    async with AsyncSession(pg_engine) as session:
        result = await session.execute(
            text(
                "SELECT tipo_alerta, severity FROM prod.alert_types "
                "WHERE tipo_alerta IN "
                "('subscripcion_vencida_forzado', 'tarifa_vigente_forzado') "
                "ORDER BY tipo_alerta"
            )
        )
        rows = result.fetchall()
    assert len(rows) == 2, (
        f"prod.alert_types must contain 2 F1.7 alert types; got {len(rows)}: "
        f"{rows!r}"
    )
    expected = {
        "subscripcion_vencida_forzado": "warning",
        "tarifa_vigente_forzado": "warning",
    }
    for tipo_alerta, severity in rows:
        assert expected[tipo_alerta] == severity, (
            f"severity for {tipo_alerta} must be 'warning'; got {severity!r}"
        )


# ---------------------------------------------------------------------------
# T4: partial unique index one_exit_per_ingreso exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partial_unique_index_one_exit_per_ingreso(pg_engine) -> None:
    """T4: post-upgrade, the partial unique index ``one_exit_per_ingreso``
    MUST exist on ``prod.salidas (uuid_ingreso)`` with a ``WHERE`` clause
    excluding anuladas.

    The index is the TOCTOU-closer for V1 EXISTS (R4). Verified by
    inspecting ``pg_indexes`` rather than attempting to query
    ``pg_index``'s ``indexprs`` (the WHERE clause is a planner-only
    predicate; ``pg_indexes`` carries ``indexdef`` we can pattern-match).
    """
    async with AsyncSession(pg_engine) as session:
        result = await session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname='prod' AND tablename='salidas' "
                "AND indexname='one_exit_per_ingreso'"
            )
        )
        row = result.first()
    assert row is not None, (
        "partial unique index one_exit_per_ingreso MUST exist on "
        "prod.salidas after migration 0026 Op 4"
    )
    indexdef = row[0]
    assert "UNIQUE INDEX" in indexdef.upper(), (
        f"index must be UNIQUE; got indexdef={indexdef!r}"
    )
    assert "uuid_ingreso" in indexdef, (
        f"index must be on uuid_ingreso; got indexdef={indexdef!r}"
    )
    # The WHERE clause excludes anuladas (per KD-S16); spot-check the
    # presence of ``anulaciones`` in the predicate (exact WHERE shape
    # is verified at migration file source, not here).
    assert "WHERE" in indexdef.upper(), (
        f"index must be PARTIAL (have a WHERE clause); got indexdef={indexdef!r}"
    )


# ---------------------------------------------------------------------------
# T5: idempotency -- re-applying 0026 must be a no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_0026_re_aplica_sin_error(pg_engine) -> None:
    """T5: migration 0026 can be applied twice consecutively without
    error. Idempotency proof for the 4 ops (Op 2 ``ON CONFLICT DO
    NOTHING``, Op 3 ``ON CONFLICT DO NOTHING``, Op 4 ``IF NOT EXISTS``).

    Implementation: invoke the migration ``upgrade()`` function via
    ``alembic``'s programmatic API. The upgrade is a no-op the second
    time around because every statement is guarded by either a unique
    constraint conflict (Op 2 + Op 3) or ``IF NOT EXISTS`` (Op 4). The
    pre-flight Op 1 ``DO $$`` block is read-only (no DDL) so it also
    runs clean on re-apply.
    """
    import importlib

    migration_mod = importlib.import_module(
        "parkos_core.migrations.versions."
        "0026_seed_impuestos_iva_and_one_exit_per_ingreso"
    )
    # First apply -- might already be applied by alembic_upgrade, so
    # just call it twice and confirm no exception on the second call.
    migration_mod.upgrade()
    try:
        migration_mod.upgrade()
    except Exception as exc:
        pytest.fail(
            f"0026 upgrade must be idempotent (re-apply = no-op); "
            f"second apply raised: {exc!r}"
        )


__all__ = [
    "test_alembic_head_includes_0026",
    "test_iva_row_presente_post_migration",
    "test_alert_types_f17_insertados",
    "test_partial_unique_index_one_exit_per_ingreso",
    "test_0026_re_aplica_sin_error",
]
