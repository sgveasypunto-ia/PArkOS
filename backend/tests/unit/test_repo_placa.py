"""HU-F1.6 / REQ-OPS-038 — regex placa Colombia server-side.

Pure-async unit tests for :func:`parkos_core.repo.placa.detectar_tipo_vehiculo`
with real `pg_engine` seed fixtures. The 6 parametrized cases mirror the
regex constants:

  - FORMATO_AUTO = ``^[A-Z]{3}[0-9]{3}$`` (e.g. ``ABC123``)
  - FORMATO_MOTO = ``^[A-Z]{3}[0-9]{2}[A-Z]$`` (e.g. ``ABC12D``)

DEC-SUC-22: regex estricta, sin tolerancia O<->0 / I<->1.

Lifecycle:
  - RED: ``from parkos_core.repo.placa import detectar_tipo_vehiculo``
    raises ``ModuleNotFoundError`` (repo/placa.py does not exist).
  - GREEN: helper returns the UUID of the vigente row in
    ``prod.tipos_vehiculo`` keyed by ``tipo`` ('Auto' or 'Moto').
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from parkos_core.repo.placa import detectar_tipo_vehiculo
from sqlalchemy.ext.asyncio import AsyncSession

from backend.tests.conftest import VFixtureFactory  # noqa: F401


@pytest.fixture
async def seed_tipos_vehiculo(pg_engine):
    """Insert two vigente rows: ``tipo='Auto'`` and ``tipo='Moto'``.

    Returns ``(uuid_auto, uuid_moto)``.
    """
    async with AsyncSession(pg_engine) as session:
        tv_auto = VFixtureFactory.build(TiposVehiculo, tipo="Auto")
        tv_moto = VFixtureFactory.build(TiposVehiculo, tipo="Moto")
        session.add_all([tv_auto, tv_moto])
        await session.commit()
        return (tv_auto.uuid, tv_moto.uuid)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("placa", "expected_tipo"),
    [
        ("ABC123", "Auto"),
        ("XYZ789", "Auto"),
        ("JKL456", "Auto"),
    ],
)
async def test_detectar_tipo_vehiculo_auto_devuelve_uuid(
    seed_tipos_vehiculo, pg_engine, placa, expected_tipo
) -> None:
    """T1/T2: ``ABC123`` regex matches FORMATO_AUTO; helper returns
    the UUID of the vigente ``tipo='Auto'`` row."""
    uuid_auto, _uuid_moto = seed_tipos_vehiculo
    async with AsyncSession(pg_engine) as session:
        result = await detectar_tipo_vehiculo(session, placa)
    assert result == uuid_auto, (
        f"placa={placa!r} expected UUID of tipo={expected_tipo!r}, "
        f"got {result}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("placa", "expected_tipo"),
    [
        ("ABC12D", "Moto"),
        ("XYZ99Z", "Moto"),
        ("JKL77M", "Moto"),
    ],
)
async def test_detectar_tipo_vehiculo_moto_devuelve_uuid(
    seed_tipos_vehiculo, pg_engine, placa, expected_tipo
) -> None:
    """T2: ``ABC12D`` regex matches FORMATO_MOTO; helper returns
    the UUID of the vigente ``tipo='Moto'`` row."""
    _uuid_auto, uuid_moto = seed_tipos_vehiculo
    async with AsyncSession(pg_engine) as session:
        result = await detectar_tipo_vehiculo(session, placa)
    assert result == uuid_moto


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "placa",
    [
        "AB12",       # 4 chars, no match
        "AB1234",     # 3 letters + 4 digits (no ABC pattern)
        "ABC-123",    # with hyphen
        "ABC1234",    # 3 letters + 4 digits, no pattern
        "123ABC",     # reversed order
        "ABC12",      # 5 chars, incomplete
    ],
)
async def test_detectar_tipo_vehiculo_devuelve_none_regex_mismatch(
    pg_engine, placa
) -> None:
    """T3/T5/T6: regex mismatch returns ``None`` (no regex matched)."""
    async with AsyncSession(pg_engine) as session:
        result = await detectar_tipo_vehiculo(session, placa)
    assert result is None, (
        f"placa={placa!r} should not match FORMATO_AUTO or FORMATO_MOTO; "
        f"got {result}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "placa",
    [
        "abc123",     # lowercase (DEC-SUC-22 strict)
        "abc12d",     # lowercase moto
        "AbC123",     # mixed case
        "ABC12d",     # mixed case moto
    ],
)
async def test_detectar_tipo_vehiculo_lowercase_devuelve_none(
    pg_engine, placa
) -> None:
    """T4: lowercase or mixed-case placa does NOT match either regex
    (DEC-SUC-22: regex estricta, sin tolerancia O<->0 / I<->1)."""
    async with AsyncSession(pg_engine) as session:
        result = await detectar_tipo_vehiculo(session, placa)
    assert result is None


@pytest.mark.asyncio
async def test_detectar_tipo_vehiculo_none_devuelve_none(pg_engine) -> None:
    """T-null: ``placa=None`` returns ``None`` (no regex match)."""
    async with AsyncSession(pg_engine) as session:
        result = await detectar_tipo_vehiculo(session, None)
    assert result is None


@pytest.mark.asyncio
async def test_detectar_tipo_vehiculo_catalog_missing_devuelve_none(
    pg_engine,
) -> None:
    """T-catalog-missing: regex matches ``ABC123`` but no vigente
    ``tipo='Auto'`` row exists; helper returns ``None`` (the catalog
    defect surfaces as V4 ``tipo_vehiculo_invalido`` in the handler)."""
    async with AsyncSession(pg_engine) as session:
        result = await detectar_tipo_vehiculo(session, "ABC123")
    assert result is None, (
        "with no vigente row in prod.tipos_vehiculo for tipo='Auto', "
        "helper must return None (V4 catalog defect)"
    )


__all__ = [
    "test_detectar_tipo_vehiculo_auto_devuelve_uuid",
    "test_detectar_tipo_vehiculo_catalog_missing_devuelve_none",
    "test_detectar_tipo_vehiculo_devuelve_none_regex_mismatch",
    "test_detectar_tipo_vehiculo_lowercase_devuelve_none",
    "test_detectar_tipo_vehiculo_moto_devuelve_uuid",
    "test_detectar_tipo_vehiculo_none_devuelve_none",
]