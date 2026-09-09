"""test_identity_nk_indexes_schema.py — T-PR5-007 acceptance for migration
``0008_add_identity_nk_indexes.py`` (D17).

Verifies the 3 non-unique functional partial indexes exist after
``alembic upgrade head``, are scoped to the currently-open version
(``WHERE vigente_hasta IS NULL``), and use the SAME functional
expressions ``catalog/normalizers.py`` computes in Python
(``regexp_replace`` / ``upper(regexp_replace(...))``) — both are
``IMMUTABLE`` (deterministic, no catalog/locale lookups), which is a
precondition for a functional index to even be creatable; the migration
itself already proves this (a non-``IMMUTABLE`` expression would have
failed ``CREATE INDEX`` at apply time).
"""
from __future__ import annotations

from sqlalchemy import text


async def test_three_identity_indexes_exist(pg_engine, alembic_upgrade) -> None:
    async with pg_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'prod' "
                    "AND indexname IN ("
                    "'ix_clientes_nk_open', 'ix_clientes_b2b_nk_open', "
                    "'ix_vehiculos_nk_open')"
                )
            )
        ).scalars().all()

    assert set(rows) == {
        "ix_clientes_nk_open",
        "ix_clientes_b2b_nk_open",
        "ix_vehiculos_nk_open",
    }


async def test_indexes_are_partial_on_open_version(pg_engine, alembic_upgrade) -> None:
    async with pg_engine.connect() as conn:
        for index_name in (
            "ix_clientes_nk_open",
            "ix_clientes_b2b_nk_open",
            "ix_vehiculos_nk_open",
        ):
            definition = (
                await conn.execute(
                    text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
                    {"name": index_name},
                )
            ).scalar_one()
            assert "vigente_hasta IS NULL" in definition


async def test_clientes_and_vehiculos_indexes_use_normalizer_expressions(
    pg_engine, alembic_upgrade
) -> None:
    async with pg_engine.connect() as conn:
        clientes_def = (
            await conn.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_clientes_nk_open'")
            )
        ).scalar_one()
        vehiculos_def = (
            await conn.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_vehiculos_nk_open'")
            )
        ).scalar_one()

    assert "regexp_replace" in clientes_def
    assert "tipo_identificador" in clientes_def

    assert "regexp_replace" in vehiculos_def
    assert "upper(" in vehiculos_def
