"""HU-F1.11 / T1.1 + T2.1..T2.4 — repo/reimpresion_ticket.py helpers.

T1.1 — module import surface (RED→GREEN for the ``__all__`` skeleton).
T2.1..T2.4 — V1 helpers + V2 chain-tip guard + DEC-TKT-05 siembra lookup +
DEC-IDEM-01 idempotency wrapper.

All gated on ``PARKOS_DOCKER_TEST=1`` per F1.5/F1.7/F1.9/F1.10 precedent for
paths that touch SELECT FOR UPDATE / partial UK / versioned bi-temporal.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, datetime
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


# ---------------------------------------------------------------------------
# T1.1 — module import surface
# ---------------------------------------------------------------------------


def test_repo_reimpresion_ticket_module_imports() -> None:
    """T1.1: the module exists and exports the canonical 11 public names."""
    import parkos_core.repo.reimpresion_ticket as repo_reimpresion

    expected = {
        # Typed exceptions (5)
        "IngresoNoEncontradoError",
        "ReimpresionNotFoundError",
        "ReimpresionAlreadyPendingError",
        "AnulacionNoPermitidaError",
        "CostoServicioNoConfiguradoError",
        # V1 helpers (3)
        "buscar_ingreso_por_uuid",
        "buscar_reimpresion_por_uuid",
        "buscar_factura_por_uuid",
        # V2 chain-tip guard (1)
        "buscar_reimpresion_activa_por_ingreso",
        # DEC-TKT-05 siembra lookup (1)
        "buscar_costo_servicio_vigente_por_concepto",
        # DEC-IDEM-01 idempotency wrapper (1)
        "check_idempotency_key",
    }
    public = set(dir(repo_reimpresion))
    missing = expected - public
    assert not missing, (
        f"repo/reimpresion_ticket.py is missing {sorted(missing)} from "
        f"`__all__`; expected {sorted(expected)}."
    )


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# T2.1 — V1 helpers (factura, ingreso, reimpresion by uuid)
# ---------------------------------------------------------------------------


import pytest  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker  # noqa: E402


@pytest.mark.asyncio
async def test_buscar_ingreso_por_uuid_returns_orm_row_when_found(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
) -> None:
    """V1: ``prod.ingreso`` row found by PK → helper returns the row."""
    from parkos_core.models.L_E.ingreso import Ingreso
    from parkos_core.repo.reimpresion_ticket import buscar_ingreso_por_uuid

    ingreso_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = Ingreso(
            uuid=ingreso_uuid,
            uuid_sucursal=seeded_sucursal_uuid,
            placa="ABC123",
            uuid_usuario=None,
            created_at=_now(),
            created_by=None,
        )
        session.add(row)
        await session.commit()

    async with Session() as session:
        result = await buscar_ingreso_por_uuid(session, uuid_ingreso=ingreso_uuid)
    assert result is not None
    assert result.uuid == ingreso_uuid


@pytest.mark.asyncio
async def test_buscar_ingreso_por_uuid_returns_none_when_not_found(
    pg_engine: AsyncEngine,
) -> None:
    """V1: random uuid → helper returns ``None``."""
    from parkos_core.repo.reimpresion_ticket import buscar_ingreso_por_uuid

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        result = await buscar_ingreso_por_uuid(
            session, uuid_ingreso=uuid_lib.uuid4()
        )
    assert result is None


@pytest.mark.asyncio
async def test_buscar_reimpresion_por_uuid_returns_orm_row_when_found(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
) -> None:
    """V1 (anular): ``prod.reimpresion_ticket`` row found by uuid."""
    from parkos_core.models.L_W.reimpresion_ticket import ReimpresionTicket
    from parkos_core.repo.reimpresion_ticket import buscar_reimpresion_por_uuid

    reim_uuid = uuid_lib.uuid4()
    ingreso_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = ReimpresionTicket(
            uuid=reim_uuid,
            uuid_sucursal=seeded_sucursal_uuid,
            uuid_ingreso=ingreso_uuid,
            uuid_usuario=None,
            motivo="Cliente solicita reimpresion por deterioro",
            uuid_reimpresion_padre=None,
            timestamp_evento=_now(),
            estado="activo",
        )
        session.add(row)
        await session.commit()

    async with Session() as session:
        result = await buscar_reimpresion_por_uuid(session, uuid=reim_uuid)
    assert result is not None
    assert result.uuid == reim_uuid


@pytest.mark.asyncio
async def test_buscar_factura_por_uuid_returns_orm_row_when_found(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
) -> None:
    """V3 (DEC-TKT-04, optional): ``prod.facturas`` row found by uuid."""
    from parkos_core.models.L_E.facturas import Facturas
    from parkos_core.repo.reimpresion_ticket import buscar_factura_por_uuid

    factura_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = Facturas(
            uuid=factura_uuid,
            uuid_sucursal=seeded_sucursal_uuid,
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

    async with Session() as session:
        result = await buscar_factura_por_uuid(session, uuid_factura=factura_uuid)
    assert result is not None
    assert result.uuid == factura_uuid


# ---------------------------------------------------------------------------
# T2.2 — V2 chain-tip guard (DEC-TKT-02 + KD-TKT-02 SELECT FOR UPDATE)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buscar_reimpresion_activa_por_ingreso_returns_dict_when_found(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
) -> None:
    """V2: 2 rows for same uuid_ingreso → returns the LATEST by (timestamp, lex uuid)."""
    from parkos_core.models.L_W.reimpresion_ticket import ReimpresionTicket
    from parkos_core.repo.reimpresion_ticket import (
        buscar_reimpresion_activa_por_ingreso,
    )

    ingreso_uuid = uuid_lib.uuid4()
    earlier_uuid = uuid_lib.uuid4()
    later_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        for reim_uuid, ts_offset in (
            (earlier_uuid, -3600),
            (later_uuid, 0),
        ):
            ts = _now().fromtimestamp(_now().timestamp() + ts_offset)
            row = ReimpresionTicket(
                uuid=reim_uuid,
                uuid_sucursal=seeded_sucursal_uuid,
                uuid_ingreso=ingreso_uuid,
                uuid_usuario=None,
                motivo="Cliente solicita reimpresion",
                uuid_reimpresion_padre=None,
                timestamp_evento=ts,
                estado="activo",
            )
            session.add(row)
        await session.commit()

    async with Session() as session:
        result = await buscar_reimpresion_activa_por_ingreso(
            session, uuid_ingreso=ingreso_uuid
        )
    assert result is not None
    assert result["uuid"] == later_uuid
    assert result["workflow_estado"] == "autorizada"


@pytest.mark.asyncio
async def test_buscar_reimpresion_activa_por_ingreso_returns_none_when_no_active(
    pg_engine: AsyncEngine,
) -> None:
    """V2: no active row for uuid_ingreso → returns ``None``."""
    from parkos_core.repo.reimpresion_ticket import (
        buscar_reimpresion_activa_por_ingreso,
    )

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        result = await buscar_reimpresion_activa_por_ingreso(
            session, uuid_ingreso=uuid_lib.uuid4()
        )
    assert result is None


@pytest.mark.asyncio
async def test_buscar_reimpresion_activa_por_ingreso_uses_for_update(
    pg_engine: AsyncEngine,
) -> None:
    """KD-TKT-02: the SELECT must include ``with_for_update()`` (row lock).

    We verify by introspecting the compiled SQL — Postgres' FOR UPDATE
    clause is the audit trail.
    """
    import logging

    from parkos_core.repo.reimpresion_ticket import (
        buscar_reimpresion_activa_por_ingreso,
    )

    captured: list[str] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            msg = record.getMessage()
            if "FOR UPDATE" in msg or "reimpresion_ticket" in msg:
                captured.append(msg)

    sql_logger = logging.getLogger("sqlalchemy.engine")
    sql_logger.addHandler(_CaptureHandler())
    sql_logger.setLevel(logging.INFO)
    try:
        Session = async_sessionmaker(pg_engine, expire_on_commit=False)
        async with Session() as session:
            await buscar_reimpresion_activa_por_ingreso(
                session, uuid_ingreso=uuid_lib.uuid4()
            )
    finally:
        sql_logger.removeHandler(_CaptureHandler())

    assert any("FOR UPDATE" in m for m in captured), (
        f"KD-TKT-02 violated: ``buscar_reimpresion_activa_por_ingreso`` did "
        f"not emit a `FOR UPDATE` clause. Captured SQL log: {captured}"
    )


# ---------------------------------------------------------------------------
# T2.4 — DEC-TKT-05 siembra lookup + DEC-IDEM-01 idempotency wrapper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buscar_costo_servicio_vigente_por_concepto_returns_vigent_row(
    pg_engine: AsyncEngine,
) -> None:
    """DEC-TKT-05: vigente ``prod.costos_servicios`` row for concepto='reimpresion'."""
    from parkos_core.models.V.costos_servicios import CostosServicios
    from parkos_core.repo.reimpresion_ticket import (
        buscar_costo_servicio_vigente_por_concepto,
    )

    costo_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = CostosServicios(
            uuid=costo_uuid,
            concepto="reimpresion",
            costo=0,
            tipo_calculo="fijo",
            vigente_desde=_now(),
            vigente_hasta=None,
            estado="activo",
        )
        session.add(row)
        await session.commit()

    async with Session() as session:
        result = await buscar_costo_servicio_vigente_por_concepto(
            session, concepto="reimpresion"
        )
    assert result is not None
    assert result.uuid == costo_uuid


@pytest.mark.asyncio
async def test_buscar_costo_servicio_vigente_por_concepto_returns_none_when_no_vigent(
    pg_engine: AsyncEngine,
) -> None:
    """DEC-TKT-05: no vigente row for concepto='reimpresion' → ``None``."""
    from parkos_core.repo.reimpresion_ticket import (
        buscar_costo_servicio_vigente_por_concepto,
    )

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        result = await buscar_costo_servicio_vigente_por_concepto(
            session, concepto="reimpresion"
        )
    assert result is None


@pytest.mark.asyncio
async def test_check_idempotency_key_returns_none_when_key_absent(
    pg_engine: AsyncEngine,
) -> None:
    """DEC-IDEM-01: random key + endpoint → ``None`` (cache miss)."""
    from parkos_core.repo.reimpresion_ticket import check_idempotency_key

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        result = await check_idempotency_key(
            session,
            idempotency_key="00000000-0000-0000-0000-000000000000",
            endpoint="/api/v1/workflows/reimpresion-ticket",
        )
    # The thin wrapper returns None by design (F1.6 middleware owns the
    # cache lookup; the helper exists for testability + explicit
    # documentation of DEC-IDEM-01 reuse).
    assert result is None