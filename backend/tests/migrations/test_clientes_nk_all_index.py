"""Migration 0084: full (non-partial) natural-key index on ``prod.clientes``.

The derived pull scope of ``clientes_b2b`` compares the natural key of closed
cliente versions too, which the partial ``ix_clientes_nk_open`` cannot serve.
"""
from __future__ import annotations

from sqlalchemy import text


async def test_full_natural_key_index_exists_and_is_not_partial(pg_engine, alembic_upgrade) -> None:
    async with pg_engine.connect() as conn:
        definition = (
            await conn.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_clientes_nk'")
            )
        ).scalar_one()

    assert "tipo_identificador" in definition
    assert "regexp_replace(" in definition
    assert "vigente_hasta" not in definition
