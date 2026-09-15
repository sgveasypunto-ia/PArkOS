"""HU-F1.6 / migration 0025 — datos_nuevos JSONB column + capacidad_agotada_forzado alert type.

Pre-flight + round-trip + idempotency tests for the Alembic migration
``0025_add_alerta_datos_nuevos_and_alert_type``. Mirrors F1.5's
``test_migration_0024_mv.py`` pattern: ``DO $$`` pre-flight on
``prod.alerta`` exists, ``ALTER TABLE prod.alerta ADD COLUMN IF NOT
EXISTS datos_nuevos JSONB``, then ``INSERT ON CONFLICT DO NOTHING`` for
``capacidad_agotada_forzado`` (``alert_types_inmutable`` trigger blocks
non-superuser UPDATE/DELETE on ``prod.alert_types``).

Tests REQUIRE a live Postgres with ``pg_partman`` enabled; on the
default ``postgres:16-alpine`` image, the migration can't run (matches
F1.5 baseline — see conftest ``postgres_container`` fixture).

Lifecycle:
  - RED: migration does not exist (relationError: column ``datos_nuevos``
    does not exist; ``alert_types`` row missing for
    ``capacidad_agotada_forzado``).
  - GREEN (T0.1): migration lands; pre-flight NOTICE, ALTER COLUMN
    IF NOT EXISTS (idempotent), INSERT ON CONFLICT DO NOTHING (idempotent).
"""
from __future__ import annotations

import uuid as uuid_lib

import psycopg
import pytest

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# 0025 pre-flight: prod.alerta exists (KD-7 F1.5 pattern)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preflight_alerta_existe(pg_engine) -> None:
    """T1 (partial): ``prod.alerta`` table must exist pre-migration 0025.

    The migration's pre-flight ``DO $$`` block checks
    ``pg_catalog.pg_class WHERE relname='alerta'`` and aborts if missing.
    Asserting the row count today confirms the schema is in the F1.6
    starting state (post-0024 F1.5 chain head).
    """
    async with AsyncSession(pg_engine) as session:
        result = await session.execute(
            text(
                "SELECT count(*) FROM pg_catalog.pg_class "
                "WHERE relname='alerta' AND relnamespace='prod'::regnamespace"
            )
        )
        n = result.scalar_one()
    # The schema may have zero rows today (alerta is range-partitioned and
    # depends on default partitions), but the table MUST exist post-0001.
    assert n >= 1, "prod.alerta must exist for migration 0025 to apply"


@pytest.mark.asyncio
async def test_column_datos_nuevos_existe_post_upgrade(pg_engine) -> None:
    """T1: post-``alembic upgrade head``, ``prod.alerta.datos_nuevos JSONB``
    MUST exist.

    RED phase: column does not exist (UndefinedColumnError). GREEN phase
    (after 0025 migration lands): column exists, nullable, JSONB.
    """
    async with AsyncSession(pg_engine) as session:
        result = await session.execute(
            text(
                "SELECT data_type, is_nullable FROM information_schema.columns "
                "WHERE table_schema='prod' AND table_name='alerta' "
                "AND column_name='datos_nuevos'"
            )
        )
        row = result.first()
    assert row is not None, (
        "prod.alerta.datos_nuevos column MUST exist after 0025 upgrade. "
        "Migration 0025 must run ALTER TABLE prod.alerta "
        "ADD COLUMN IF NOT EXISTS datos_nuevos JSONB."
    )
    data_type, is_nullable = row
    assert data_type == "jsonb", f"datos_nuevos must be JSONB, got {data_type}"
    assert is_nullable == "YES", "datos_nuevos must be nullable"


@pytest.mark.asyncio
async def test_alert_type_capacidad_agotada_forzado_insertado(pg_engine) -> None:
    """T1: post-upgrade, ``prod.alert_types`` MUST contain a row
    ``tipo_alerta='capacidad_agotada_forzado'`` with severity='warning'.

    RED: row missing (filter ``WHERE tipo_alerta='capacidad_agotada_forzado'``
    returns 0). GREEN: row present, idempotent across re-applies (the
    ``INSERT … ON CONFLICT (tipo_alerta) DO NOTHING`` is the source of
    truth).
    """
    async with AsyncSession(pg_engine) as session:
        result = await session.execute(
            text(
                "SELECT severity, descripcion FROM prod.alert_types "
                "WHERE tipo_alerta='capacidad_agotada_forzado'"
            )
        )
        row = result.first()
    assert row is not None, (
        "prod.alert_types MUST contain tipo_alerta='capacidad_agotada_forzado' "
        "after migration 0025. Migration 0025 must INSERT this row with "
        "ON CONFLICT (tipo_alerta) DO NOTHING."
    )
    severity, descripcion = row
    assert severity == "warning", f"severity must be 'warning', got {severity}"
    assert descripcion is not None and "forzado" in descripcion.lower(), (
        f"descripcion must mention 'forzado', got {descripcion!r}"
    )


@pytest.mark.asyncio
async def test_alembic_head_includes_0025(pg_engine) -> None:
    """T1: alembic version table must show the migration head is
    ``0025_alerta_datos_nuevos`` after upgrade.

    Confirms the migration is part of the active chain (down_revision
    wired to 0024_mv_ocupacion_diaria, F1.5 chain head).
    """
    async with AsyncSession(pg_engine) as session:
        result = await session.execute(
            text("SELECT version_num FROM alembic_version")
        )
        row = result.first()
    assert row is not None, "alembic_version row missing"
    assert row[0] == "0025_alerta_datos_nuevos", (
        f"alembic head must be 0025_alerta_datos_nuevos, got {row[0]}"
    )


# ---------------------------------------------------------------------------
# T2 + T3: downgrade/upgrade round-trip + idempotency are integration-suite
# concerns owned by the conftest alembic_upgrade fixture (F1.5 precedent).
# Direct downgrade is destructive (DROP COLUMN) so we don't run it here.
# ---------------------------------------------------------------------------


__all__ = [
    "test_alembic_head_includes_0025",
    "test_alert_type_capacidad_agotada_forzado_insertado",
    "test_column_datos_nuevos_existe_post_upgrade",
    "test_preflight_alerta_existe",
]