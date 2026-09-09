"""test_consecutivo_assignment.py — T-PR9-001 (RED) / T-PR9-002 (GREEN).

``repo.resolucion_facturacion.assign_consecutivo`` is the branch-local
DIAN numbering allocator (D1-rev, design.md §2 Issue #9). Exercised
against a REAL Postgres container (rule: no mocked DB for this path —
the row lock + ``MAX()`` scoping is exactly the part a mock would hide).

Covers, per T-PR9-001's acceptance:

  1. Sequential, no-gap assignment across distinct source events.
  2. Idempotent per source event: a retry of the SAME event never mints
     a second number.
  3. If the persisting transaction never commits, no number is
     considered consumed — the next call recomputes the SAME value.
  4. Range exhaustion raises once ``rango_hasta`` would be exceeded.

``factura_electronica.uuid_factura`` carries a real FK to ``facturas``
(``fk_factura_electronica_uuid_factura``), so each "source event" in
these tests is a real seeded ``facturas`` row — the natural 1:1 business
event a DIAN invoice numbers.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, date, datetime

import pytest
from parkos_core.models.L_E.factura_electronica import FacturaElectronica
from parkos_core.models.L_E.facturas import Facturas
from parkos_core.models.V.clientes import Clientes
from parkos_core.models.V.resolucion_facturacion import ResolucionFacturacion
from parkos_core.repo.resolucion_facturacion import (
    ConsecutivoRangeExhaustedError,
    ResolucionFacturacionNotFoundError,
    assign_consecutivo,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seed_resolucion(
    pg_engine: AsyncEngine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    rango_desde: int,
    rango_hasta: int,
) -> uuid_lib.UUID:
    """Insert one open ``resolucion_facturacion`` version row."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = ResolucionFacturacion(
            uuid=uuid_lib.uuid4(),
            uuid_sucursal=uuid_sucursal,
            numero_resolucion=f"RES-{uuid_lib.uuid4().hex[:8]}",
            prefijo="SETP",
            rango_desde=rango_desde,
            rango_hasta=rango_hasta,
            fecha_resolucion=date.today(),
            fecha_inicio_vigencia=date.today(),
            fecha_fin_vigencia=None,
            vigente_desde=_now(),
            vigente_hasta=None,
            estado="activo",
            created_at=_now(),
            created_by=None,
            sync_status="pendiente",
            sync_timestamp=None,
            sync_attempts=0,
        )
        session.add(row)
        await session.commit()
        return row.uuid


async def _seed_facturas(pg_engine: AsyncEngine, *, uuid_sucursal: uuid_lib.UUID) -> uuid_lib.UUID:
    """Insert one ``facturas`` row (the commercial event a DIAN invoice numbers).

    ``uuid_ingreso`` / ``uuid_salida`` stay ``NULL`` — both FKs are
    nullable, so this seed needs no ``ingreso``/``salidas`` parent.
    """
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = Facturas(
            uuid=uuid_lib.uuid4(),
            uuid_sucursal=uuid_sucursal,
            subtotal=10000,
            descuento=0,
            total=10000,
            uuid_ingreso=None,
            uuid_salida=None,
            created_at=_now(),
            created_by=None,
        )
        session.add(row)
        await session.commit()
        return row.uuid


async def _seed_cliente(pg_engine: AsyncEngine) -> uuid_lib.UUID:
    """Insert one ``clientes`` row — no FK constraint at the SQL level."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = Clientes(
            uuid=uuid_lib.uuid4(),
            tipo_identificador="CC",
            numero_identificacion=str(uuid_lib.uuid4().int)[:10],
            nombre="Cliente",
            apellido="De Prueba",
            vigente_desde=_now(),
            vigente_hasta=None,
            estado="activo",
            created_at=_now(),
            created_by=None,
            sync_status="pendiente",
            sync_timestamp=None,
            sync_attempts=0,
        )
        session.add(row)
        await session.commit()
        return row.uuid


async def _insert_factura_electronica(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_resolucion_facturacion: uuid_lib.UUID,
    uuid_factura: uuid_lib.UUID,
    uuid_cliente: uuid_lib.UUID,
    consecutivo: int,
) -> FacturaElectronica:
    row = FacturaElectronica(
        uuid=uuid_lib.uuid4(),
        uuid_sucursal=uuid_sucursal,
        uuid_factura=uuid_factura,
        uuid_cliente=uuid_cliente,
        uuid_resolucion_facturacion=uuid_resolucion_facturacion,
        prefijo="SETP",
        consecutivo=consecutivo,
        descuento=0,
        created_at=_now(),
        created_by=None,
    )
    session.add(row)
    return row


@pytest.fixture
async def seeded_cliente_uuid(pg_engine: AsyncEngine) -> uuid_lib.UUID:
    return await _seed_cliente(pg_engine)


@pytest.mark.asyncio
async def test_sequential_no_gap_per_branch_resolution(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
    seeded_cliente_uuid: uuid_lib.UUID,
) -> None:
    """Distinct source events get sequential, no-gap numbers from rango_desde."""
    resolucion_uuid = await _seed_resolucion(
        pg_engine,
        uuid_sucursal=seeded_sucursal_uuid,
        rango_desde=1000,
        rango_hasta=1010,
    )
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    assigned: list[int] = []
    for _ in range(3):
        source_event = await _seed_facturas(pg_engine, uuid_sucursal=seeded_sucursal_uuid)
        async with Session() as session:
            number = await assign_consecutivo(session, resolucion_uuid, source_event)
            assigned.append(number)
            await _insert_factura_electronica(
                session,
                uuid_sucursal=seeded_sucursal_uuid,
                uuid_resolucion_facturacion=resolucion_uuid,
                uuid_factura=source_event,
                uuid_cliente=seeded_cliente_uuid,
                consecutivo=number,
            )
            await session.commit()

    assert assigned == [1000, 1001, 1002]


@pytest.mark.asyncio
async def test_retry_of_same_source_event_reuses_the_same_number(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
    seeded_cliente_uuid: uuid_lib.UUID,
) -> None:
    """A retry of the SAME event never mints, discards, then re-mints a number."""
    resolucion_uuid = await _seed_resolucion(
        pg_engine,
        uuid_sucursal=seeded_sucursal_uuid,
        rango_desde=2000,
        rango_hasta=2010,
    )
    source_event = await _seed_facturas(pg_engine, uuid_sucursal=seeded_sucursal_uuid)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    # First (successful) attempt — assign + insert + commit.
    async with Session() as session:
        first = await assign_consecutivo(session, resolucion_uuid, source_event)
        await _insert_factura_electronica(
            session,
            uuid_sucursal=seeded_sucursal_uuid,
            uuid_resolucion_facturacion=resolucion_uuid,
            uuid_factura=source_event,
            uuid_cliente=seeded_cliente_uuid,
            consecutivo=first,
        )
        await session.commit()

    # A DIFFERENT event in between must NOT shift the retried number.
    other_event = await _seed_facturas(pg_engine, uuid_sucursal=seeded_sucursal_uuid)
    async with Session() as session:
        other_number = await assign_consecutivo(session, resolucion_uuid, other_event)
        await _insert_factura_electronica(
            session,
            uuid_sucursal=seeded_sucursal_uuid,
            uuid_resolucion_facturacion=resolucion_uuid,
            uuid_factura=other_event,
            uuid_cliente=seeded_cliente_uuid,
            consecutivo=other_number,
        )
        await session.commit()
    assert other_number == first + 1

    # Retry of the ORIGINAL event — must return the SAME number, not a
    # new one (and must NOT collide with `other_number`).
    async with Session() as session:
        retried = await assign_consecutivo(session, resolucion_uuid, source_event)

    assert retried == first
    assert retried != other_number


@pytest.mark.asyncio
async def test_failed_persisting_transaction_consumes_no_number(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
    seeded_cliente_uuid: uuid_lib.UUID,
) -> None:
    """A rollback after assignment leaves nothing consumed — same number next time."""
    resolucion_uuid = await _seed_resolucion(
        pg_engine,
        uuid_sucursal=seeded_sucursal_uuid,
        rango_desde=3000,
        rango_hasta=3010,
    )
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    # Attempt 1: assign, then the persisting transaction ROLLS BACK
    # (never inserts factura_electronica, never commits).
    doomed_event = await _seed_facturas(pg_engine, uuid_sucursal=seeded_sucursal_uuid)
    async with Session() as session:
        doomed_number = await assign_consecutivo(session, resolucion_uuid, doomed_event)
        await _insert_factura_electronica(
            session,
            uuid_sucursal=seeded_sucursal_uuid,
            uuid_resolucion_facturacion=resolucion_uuid,
            uuid_factura=doomed_event,
            uuid_cliente=seeded_cliente_uuid,
            consecutivo=doomed_number,
        )
        await session.rollback()  # simulate a crash before commit

    # Attempt 2: a fresh event, in a fresh transaction — since nothing
    # from attempt 1 was ever committed, MAX() is unaffected and the
    # exact same number is handed out again (no gap, nothing "consumed").
    fresh_event = await _seed_facturas(pg_engine, uuid_sucursal=seeded_sucursal_uuid)
    async with Session() as session:
        fresh_number = await assign_consecutivo(session, resolucion_uuid, fresh_event)
        await _insert_factura_electronica(
            session,
            uuid_sucursal=seeded_sucursal_uuid,
            uuid_resolucion_facturacion=resolucion_uuid,
            uuid_factura=fresh_event,
            uuid_cliente=seeded_cliente_uuid,
            consecutivo=fresh_number,
        )
        await session.commit()

    assert fresh_number == doomed_number == 3000


@pytest.mark.asyncio
async def test_range_exhaustion_raises(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
    seeded_cliente_uuid: uuid_lib.UUID,
) -> None:
    """Once rango_hasta is reached, the next assignment raises (no silent overflow)."""
    resolucion_uuid = await _seed_resolucion(
        pg_engine,
        uuid_sucursal=seeded_sucursal_uuid,
        rango_desde=4000,
        rango_hasta=4000,  # a single-number range
    )
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    source_event = await _seed_facturas(pg_engine, uuid_sucursal=seeded_sucursal_uuid)
    async with Session() as session:
        number = await assign_consecutivo(session, resolucion_uuid, source_event)
        assert number == 4000
        await _insert_factura_electronica(
            session,
            uuid_sucursal=seeded_sucursal_uuid,
            uuid_resolucion_facturacion=resolucion_uuid,
            uuid_factura=source_event,
            uuid_cliente=seeded_cliente_uuid,
            consecutivo=number,
        )
        await session.commit()

    overflow_event = await _seed_facturas(pg_engine, uuid_sucursal=seeded_sucursal_uuid)
    async with Session() as session:
        with pytest.raises(ConsecutivoRangeExhaustedError):
            await assign_consecutivo(session, resolucion_uuid, overflow_event)


@pytest.mark.asyncio
async def test_unknown_resolucion_raises_not_found(pg_engine: AsyncEngine) -> None:
    """A resolucion_uuid with no local row raises, rather than assigning garbage."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        with pytest.raises(ResolucionFacturacionNotFoundError):
            await assign_consecutivo(session, uuid_lib.uuid4(), uuid_lib.uuid4())
