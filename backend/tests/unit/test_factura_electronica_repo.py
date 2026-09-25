"""HU-F1.10 / T2.1 + T2.2 — repo/factura_electronica.py helpers.

T2.1 covers the read-side helpers:
  - buscar_resolucion_vigente_por_sucursal (REQ-OPS-073 / R2 mitigation)
  - buscar_factura_electronica_por_factura (V2)
  - buscar_factura_electronica_por_uuid (V1 GET + retry)
  - buscar_envio_dian_chain_tip (V2 chain tip)

T2.2 covers the write-side helpers:
  - crear_factura_electronica_inicial (Step 7 INSERT)
  - crear_envio_dian_inicial (Step 8 INSERT)
  - crear_envio_dian_reintento (Step 5 INSERT retry with uuid_envio_padre)

These tests use a real Postgres container (per F1.4/F1.5/F1.6/F1.7/F1.9
precedent — no mocked DB for paths that touch SELECT FOR UPDATE / the
partial UK race window).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, date, datetime
from pathlib import Path

# Ensure parkos_core importable
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest
from parkos_core.models.L_E.factura_electronica import FacturaElectronica
from parkos_core.models.L_E.facturas import Facturas
from parkos_core.models.L_W.envio_dian import EnvioDian
from parkos_core.models.V.resolucion_facturacion import ResolucionFacturacion
from parkos_core.repo.factura_electronica import (
    buscar_envio_dian_chain_tip,
    buscar_factura_electronica_por_factura,
    buscar_factura_electronica_por_uuid,
    buscar_factura_por_uuid,
    crear_envio_dian_inicial,
    crear_envio_dian_reintento,
    crear_factura_electronica_inicial,
)
from parkos_core.repo.resolucion_facturacion import (
    buscar_resolucion_vigente_por_sucursal,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seed_resolucion(
    pg_engine: AsyncEngine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    rango_desde: int = 1,
    rango_hasta: int = 5000,
    vigente_desde: datetime | None = None,
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
            vigente_desde=vigente_desde or _now(),
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


async def _seed_factura(
    pg_engine: AsyncEngine,
    *,
    uuid_sucursal: uuid_lib.UUID,
) -> uuid_lib.UUID:
    """Insert one ``prod.facturas`` row."""
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


@pytest.mark.asyncio
async def test_buscar_factura_por_uuid_returns_none_when_missing(
    pg_engine: AsyncEngine,
) -> None:
    """V1: missing ``facturas`` UUID → handler raises 404 (helper returns None)."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = await buscar_factura_por_uuid(session, uuid_factura=uuid_lib.uuid4())
    assert row is None


@pytest.mark.asyncio
async def test_buscar_resolucion_vigente_por_sucursal_returns_latest(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
) -> None:
    """R2 mitigation: when 2 vigentes exist, the latest is returned."""
    from datetime import timedelta
    earlier = _now() - timedelta(days=200)
    later = _now() - timedelta(days=10)
    await _seed_resolucion(
        pg_engine, uuid_sucursal=seeded_sucursal_uuid, vigente_desde=earlier
    )
    later_uuid = await _seed_resolucion(
        pg_engine, uuid_sucursal=seeded_sucursal_uuid, vigente_desde=later
    )

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = await buscar_resolucion_vigente_por_sucursal(
            session, uuid_sucursal=seeded_sucursal_uuid
        )
    assert row is not None
    assert row.uuid == later_uuid


@pytest.mark.asyncio
async def test_buscar_resolucion_vigente_por_sucursal_returns_none_when_no_vigent(
    pg_engine: AsyncEngine,
) -> None:
    """R2 mitigation: missing vigente → handler raises 409 (helper returns None)."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = await buscar_resolucion_vigente_por_sucursal(
            session, uuid_sucursal=uuid_lib.uuid4()
        )
    assert row is None


@pytest.mark.asyncio
async def test_buscar_factura_electronica_por_factura_returns_none_when_missing(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
) -> None:
    """V2: missing FE for uuid_factura → handler proceeds (helper returns None)."""
    factura_uuid = await _seed_factura(pg_engine, uuid_sucursal=seeded_sucursal_uuid)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = await buscar_factura_electronica_por_factura(
            session, uuid_factura=factura_uuid
        )
    assert row is None


@pytest.mark.asyncio
async def test_buscar_envio_dian_chain_tip_returns_latest(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
) -> None:
    """V2 chain tip: 3 envio rows; helper returns the latest by timestamp_evento DESC."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        fe = FacturaElectronica(
            uuid=uuid_lib.uuid4(),
            uuid_sucursal=seeded_sucursal_uuid,
            uuid_factura=None,
            uuid_resolucion_facturacion=None,
            prefijo="SETP",
            consecutivo=1,
            descuento=0,
            created_at=_now(),
            created_by=None,
        )
        session.add(fe)
        await session.flush()
        fe_uuid = fe.uuid
        for estado, ts_offset in (
            ("rechazado", -2),
            ("pendiente", -1),
            ("aceptado", 0),
        ):
            envio = EnvioDian(
                uuid=uuid_lib.uuid4(),
                uuid_sucursal=seeded_sucursal_uuid,
                uuid_factura_electronica=fe_uuid,
                uuid_resolucion_facturacion=None,
                payload={},
                respuesta_proveedor=None,
                cufe=None,
                uuid_envio_padre=None,
                timestamp_evento=(_now().replace(microsecond=0)).fromtimestamp(
                    (_now().replace(microsecond=0)).timestamp() + ts_offset
                ),
                estado=estado,
                vigente_desde=_now(),
                vigente_hasta=None,
                created_at=_now(),
                created_by=None,
            )
            session.add(envio)
        await session.commit()

    async with Session() as session:
        tip = await buscar_envio_dian_chain_tip(
            session, uuid_factura_electronica=fe_uuid
        )
    assert tip is not None
    assert tip.estado == "aceptado"


@pytest.mark.asyncio
async def test_crear_factura_electronica_inicial_inserts_row(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
) -> None:
    """Step 7 INSERT: helper creates a row with the snapshotted prefijo + consecutivo."""
    factura_uuid = await _seed_factura(pg_engine, uuid_sucursal=seeded_sucursal_uuid)
    resolucion_uuid = await _seed_resolucion(pg_engine, uuid_sucursal=seeded_sucursal_uuid)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        fe = await crear_factura_electronica_inicial(
            session,
            actor_uuid=uuid_lib.uuid4(),
            uuid_sucursal=seeded_sucursal_uuid,
            uuid_factura=factura_uuid,
            uuid_resolucion_facturacion=resolucion_uuid,
            prefijo="SETP",
            consecutivo=42,
        )
        await session.commit()
    assert fe.prefijo == "SETP"
    assert fe.consecutivo == 42
    assert fe.uuid_factura == factura_uuid
    assert fe.descuento == 0, "default descuento stays Decimal(0) for ordinary facturas"


@pytest.mark.asyncio
async def test_crear_factura_electronica_inicial_persiste_descuento_real(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
) -> None:
    """2026-09-24 (salida-mensualidad factura): the DIAN document mirrors
    the internal factura's real ``descuento`` -- NOT a silent Decimal(0).
    The caller (``api/v1/facturacion.py``'s FE handler) passes ``factura.
    descuento`` fetched at V1; this test pins the repo function's own
    contract (accepts + persists the value verbatim)."""
    from decimal import Decimal

    factura_uuid = await _seed_factura(pg_engine, uuid_sucursal=seeded_sucursal_uuid)
    resolucion_uuid = await _seed_resolucion(pg_engine, uuid_sucursal=seeded_sucursal_uuid)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        fe = await crear_factura_electronica_inicial(
            session,
            actor_uuid=uuid_lib.uuid4(),
            uuid_sucursal=seeded_sucursal_uuid,
            uuid_factura=factura_uuid,
            uuid_resolucion_facturacion=resolucion_uuid,
            prefijo="SETP",
            consecutivo=43,
            descuento=Decimal("10000.00"),
        )
        await session.commit()
    assert fe.descuento == Decimal("10000.00")


@pytest.mark.asyncio
async def test_crear_envio_dian_inicial_sets_uuid_envio_padre_null(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
) -> None:
    """Step 8 INSERT: initial envio has ``uuid_envio_padre IS NULL`` + ``estado='pendiente'``."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        envio = await crear_envio_dian_inicial(
            session,
            actor_uuid=uuid_lib.uuid4(),
            uuid_sucursal=seeded_sucursal_uuid,
            uuid_factura_electronica=uuid_lib.uuid4(),
            uuid_resolucion_facturacion=uuid_lib.uuid4(),
            payload={"prefijo": "SETP", "consecutivo": 42, "uuid_factura": "x"},
        )
        await session.commit()
    assert envio.uuid_envio_padre is None
    assert envio.estado == "pendiente"
    assert envio.cufe is None


@pytest.mark.asyncio
async def test_crear_envio_dian_reintento_sets_uuid_envio_padre_to_tip(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
) -> None:
    """Step 5 INSERT: retry envio has ``uuid_envio_padre=<tip.uuid>`` (DEC-FE-02)."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        fe = FacturaElectronica(
            uuid=uuid_lib.uuid4(),
            uuid_sucursal=seeded_sucursal_uuid,
            uuid_factura=None,
            uuid_resolucion_facturacion=None,
            prefijo="SETP",
            consecutivo=1,
            descuento=0,
            created_at=_now(),
            created_by=None,
        )
        session.add(fe)
        await session.flush()
        fe_uuid = fe.uuid
        initial = await crear_envio_dian_inicial(
            session,
            actor_uuid=uuid_lib.uuid4(),
            uuid_sucursal=seeded_sucursal_uuid,
            uuid_factura_electronica=fe_uuid,
            uuid_resolucion_facturacion=uuid_lib.uuid4(),
            payload={},
        )
        await session.flush()
        retry = await crear_envio_dian_reintento(
            session,
            actor_uuid=uuid_lib.uuid4(),
            uuid_sucursal=seeded_sucursal_uuid,
            uuid_factura_electronica=fe_uuid,
            uuid_resolucion_facturacion=uuid_lib.uuid4(),
            payload={},
            uuid_envio_padre=initial.uuid,
        )
        await session.commit()
    assert retry.uuid_envio_padre == initial.uuid
    assert retry.estado == "pendiente"
