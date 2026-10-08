"""HU-F1.6 / REQ-OPS-039 — subscripcion vigente (V6) + walk-in auditado.

Pure-async unit tests for
:func:`parkos_core.repo.subscripcion_activa.validar_subscripcion_vigente`.
Tests REQUIRE a live Postgres with bi-temporal fixture seeds.

Lifecycle:
  - RED: ``from parkos_core.repo.subscripcion_activa import
    validar_subscripcion_vigente`` raises ``ImportError``.
  - GREEN: helper returns ``SubscripcionValidationResult(vigente, subscripcion)``
    per the predicate:
        ``vigente_hasta IS NULL AND estado='activo' AND
        fecha_vencimiento >= NOW()`` (date arithmetic).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, date, datetime, timedelta

import pytest
from parkos_core.runtime.tiempo import hoy_bogota
from parkos_core.models.V.clientes import Clientes
from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.tipo_persona import TipoPersona
from parkos_core.models.V.tipo_subscripciones import TipoSubscripciones
from parkos_core.models.V.tipo_sucursal import TipoSucursal
from parkos_core.repo.subscripcion_activa import (
    SubscripcionValidationResult,
    validar_subscripcion_vigente,
)
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_parents(session: AsyncSession, v_fixture_factory) -> dict[str, uuid_lib.UUID]:
    """Insert the real FK parents of ``subscripciones_cliente``.

    ``uuid_cliente`` / ``uuid_sucursal`` / ``uuid_tipo_subscripcion`` carry
    real DB-level FKs, so a bare ``uuid4()`` no longer inserts.
    """
    uid = uuid_lib.uuid4().hex[:8]
    tipo_sucursal = v_fixture_factory.build(TipoSucursal, codigo=f"propia-{uid}")
    tipo_persona = v_fixture_factory.build(TipoPersona, tipo=f"natural-{uid}")
    tipo_subscripcion = v_fixture_factory.build(
        TipoSubscripciones, tipo=f"mensual-{uid}", cantidad_maxima_vehiculos=5
    )
    session.add_all([tipo_sucursal, tipo_persona, tipo_subscripcion])
    await session.flush()
    sucursal = v_fixture_factory.build(Sucursal, uuid_tipo_sucursal=tipo_sucursal.uuid)
    cliente = v_fixture_factory.build(
        Clientes,
        tipo_identificador="CC",
        numero_identificacion=uid,
        uuid_tipo_persona=tipo_persona.uuid,
    )
    session.add_all([sucursal, cliente])
    await session.flush()
    return {
        "uuid_cliente": cliente.uuid,
        "uuid_sucursal": sucursal.uuid,
        "uuid_tipo_subscripcion": tipo_subscripcion.uuid,
    }


def _seed_subscripcion(
    *,
    parents: dict[str, uuid_lib.UUID],
    vigente_hasta: datetime | None = None,
    estado: str = "activo",
    fecha_vencimiento: date | None = None,
) -> SubscripcionesCliente:
    """Build a SubscripcionesCliente row with safe defaults.

    ``vigente_desde`` defaults to ``NOW() - 1 day`` so the row is
    currently open; ``vigente_hasta`` carries the bi-temporal close
    semantics (None = open).
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    return SubscripcionesCliente(
        uuid=uuid_lib.uuid4(),
        uuid_cliente=parents["uuid_cliente"],
        uuid_sucursal=parents["uuid_sucursal"],
        uuid_tipo_subscripcion=parents["uuid_tipo_subscripcion"],
        fecha_inicio_cobertura=now.date(),
        fecha_vencimiento=fecha_vencimiento,
        created_at=now,
        created_by=uuid_lib.uuid4(),
        vigente_desde=now - timedelta(days=1),
        vigente_hasta=vigente_hasta,
        estado=estado,
        sync_status="pendiente",
        sync_timestamp=None,
        sync_attempts=0,
    )


@pytest.mark.asyncio
async def test_subscripcion_vigente_procede_sin_forzado(pg_engine, v_fixture_factory) -> None:
    """T1: vigente_hasta IS NULL + estado='activo' + fecha_vencimiento >= today
    → ``SubscripcionValidationResult(vigente=True, subscripcion=row)``."""
    today = hoy_bogota()  # the repo compares against the Bogota calendar day
    async with AsyncSession(pg_engine, expire_on_commit=False) as session:
        parents = await _seed_parents(session, v_fixture_factory)
        seed = _seed_subscripcion(
            parents=parents,
            fecha_vencimiento=today + timedelta(days=30),  # future
            estado="activo",
            vigente_hasta=None,
        )
        session.add(seed)
        await session.commit()
        result = await validar_subscripcion_vigente(
            session, uuid_subscripcion_cliente=seed.uuid, forzado=False
        )
    assert isinstance(result, SubscripcionValidationResult)
    assert result.vigente is True
    assert result.subscripcion is not None
    assert result.subscripcion.uuid == seed.uuid


@pytest.mark.asyncio
async def test_subscripcion_vencida_sin_forzado_returns_false(pg_engine, v_fixture_factory) -> None:
    """T2: fecha_vencimiento < today → ``SubscripcionValidationResult(vigente=False)``
    with forzado=False."""
    today = hoy_bogota()  # the repo compares against the Bogota calendar day
    async with AsyncSession(pg_engine, expire_on_commit=False) as session:
        parents = await _seed_parents(session, v_fixture_factory)
        seed = _seed_subscripcion(
            parents=parents,
            fecha_vencimiento=today - timedelta(days=1),  # past
            estado="activo",
            vigente_hasta=None,
        )
        session.add(seed)
        await session.commit()
        result = await validar_subscripcion_vigente(
            session, uuid_subscripcion_cliente=seed.uuid, forzado=False
        )
    assert result.vigente is False
    assert result.subscripcion is None


@pytest.mark.asyncio
async def test_subscripcion_vencida_con_forzado_walk_in(pg_engine, v_fixture_factory) -> None:
    """T3: misma T2 state con forzado=True → ``vigente=False``
    (walk-in auditado; caller procede)."""
    today = hoy_bogota()  # the repo compares against the Bogota calendar day
    async with AsyncSession(pg_engine, expire_on_commit=False) as session:
        parents = await _seed_parents(session, v_fixture_factory)
        seed = _seed_subscripcion(
            parents=parents,
            fecha_vencimiento=today - timedelta(days=1),
            estado="activo",
            vigente_hasta=None,
        )
        session.add(seed)
        await session.commit()
        result = await validar_subscripcion_vigente(
            session, uuid_subscripcion_cliente=seed.uuid, forzado=True
        )
    # forzado=True on vencida → walk-in auditado, vigente=False, subscripcion=None
    assert result.vigente is False
    assert result.subscripcion is None


@pytest.mark.asyncio
async def test_subscripcion_inactiva_sin_forzado_returns_false(pg_engine, v_fixture_factory) -> None:
    """T4: estado='inactivo' (vigente en fechas) → ``SubscripcionValidationResult(vigente=False)``."""
    today = hoy_bogota()  # the repo compares against the Bogota calendar day
    async with AsyncSession(pg_engine, expire_on_commit=False) as session:
        parents = await _seed_parents(session, v_fixture_factory)
        seed = _seed_subscripcion(
            parents=parents,
            fecha_vencimiento=today + timedelta(days=30),
            estado="inactivo",  # explicit inactiva
            vigente_hasta=None,
        )
        session.add(seed)
        await session.commit()
        result = await validar_subscripcion_vigente(
            session, uuid_subscripcion_cliente=seed.uuid, forzado=False
        )
    assert result.vigente is False
    assert result.subscripcion is None


@pytest.mark.asyncio
async def test_subscripcion_no_existe_returns_false(pg_engine) -> None:
    """T-aux: uuid_subscripcion_cliente does not exist in DB → vigente=False."""
    fake_uuid = uuid_lib.uuid4()
    async with AsyncSession(pg_engine) as session:
        result = await validar_subscripcion_vigente(
            session, uuid_subscripcion_cliente=fake_uuid, forzado=False
        )
    assert result.vigente is False
    assert result.subscripcion is None


__all__ = [
    "test_subscripcion_inactiva_sin_forzado_returns_false",
    "test_subscripcion_no_existe_returns_false",
    "test_subscripcion_vencida_con_forzado_walk_in",
    "test_subscripcion_vencida_sin_forzado_returns_false",
    "test_subscripcion_vigente_procede_sin_forzado",
]