"""test_natural_key_normalizer_parity.py — T-PR5-006 acceptance.

Asserts the Python normalizer (``catalog/normalizers.py``) and the SQL
functional index expression (migration ``0008_add_identity_nk_indexes.py``
— ``regexp_replace(...)`` / ``upper(regexp_replace(...))``) agree over a
shared fixture set. A divergence here would make the lookup index miss and
silently reintroduce the D17 duplicate-version bug — see
``catalog/normalizers.py``'s module docstring.

Real Postgres (``pg_engine``): the SQL side of the comparison must run
through the actual server, not a Python re-implementation of
``regexp_replace`` semantics.
"""
from __future__ import annotations

import pytest
from parkos_core.sync.catalog.normalizers import (
    normalize_numero_identificacion,
    normalize_placa,
)
from sqlalchemy import text

NUMERO_IDENTIFICACION_FIXTURES = [
    "1020",
    "10-20",
    "10.20",
    "10 20",
    "  1020  ",
    "ABC-123-456",
    "900.123.456-7",
]

PLACA_FIXTURES = [
    "ABC123",
    "ABC-123",
    "abc123",
    "abc-123",
    "  ABC 123  ",
    "xyz.999",
]


@pytest.mark.parametrize("value", NUMERO_IDENTIFICACION_FIXTURES)
async def test_numero_identificacion_normalizer_matches_sql(
    pg_engine, alembic_upgrade, value: str
) -> None:
    python_result = normalize_numero_identificacion(value)

    async with pg_engine.connect() as conn:
        sql_result = (
            await conn.execute(
                text("SELECT regexp_replace(:v, '[^0-9A-Za-z]', '', 'g')"),
                {"v": value},
            )
        ).scalar_one()

    assert python_result == sql_result


@pytest.mark.parametrize("value", PLACA_FIXTURES)
async def test_placa_normalizer_matches_sql(pg_engine, alembic_upgrade, value: str) -> None:
    python_result = normalize_placa(value)

    async with pg_engine.connect() as conn:
        sql_result = (
            await conn.execute(
                text("SELECT upper(regexp_replace(:v, '[^0-9A-Za-z]', '', 'g'))"),
                {"v": value},
            )
        ).scalar_one()

    assert python_result == sql_result


async def test_abc_dash_123_and_abc123_normalize_identically(pg_engine, alembic_upgrade) -> None:
    """T-PR5-006's explicit acceptance line: ``ABC-123`` and ``ABC123``
    normalize to the same key in both Python and SQL."""
    assert normalize_placa("ABC-123") == normalize_placa("ABC123") == "ABC123"

    async with pg_engine.connect() as conn:
        dash_result = (
            await conn.execute(
                text("SELECT upper(regexp_replace(:v, '[^0-9A-Za-z]', '', 'g'))"),
                {"v": "ABC-123"},
            )
        ).scalar_one()
        plain_result = (
            await conn.execute(
                text("SELECT upper(regexp_replace(:v, '[^0-9A-Za-z]', '', 'g'))"),
                {"v": "ABC123"},
            )
        ).scalar_one()

    assert dash_result == plain_result == "ABC123"
