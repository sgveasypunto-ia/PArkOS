"""A versioned ``resolucion_facturacion`` pulled by a branch applies cleanly.

THE DEFECT THIS PINS
--------------------
The cloud edited a DIAN resolution (closed version + new version carrying
``prefijo``/``rango_*``). The branch still held the OLD version open, so the
arriving NEW version diverged from it and ``identity_reconciler`` wrote an
informational ``sync_conflict`` whose JSONB payload contained
``datetime.date`` values (``fecha_resolucion`` ...). ``_json_safe`` only
handled ``datetime``/``UUID``/``Decimal``, so the bind raised
``TypeError: Object of type date is not JSON serializable`` wrapped in
``StatementError``: the row failed every cycle, the pull cursor stayed frozen
and the branch never received the prefix/range it needs to emit invoices.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

import pytest
from fastapi.encoders import jsonable_encoder
from parkos_core.models.A.sync_conflict import SyncConflict
from parkos_core.models.V.resolucion_facturacion import ResolucionFacturacion
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.runtime import engine_flag
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from parkos_core.sync.motor.sync_motor import SyncMotor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker


@pytest.fixture(autouse=True)
def _catalog_engine_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
    engine_flag._reset_cache_for_tests()


def _wire(row: ResolucionFacturacion) -> dict:
    """Cloud ``sync_queue`` payload: JSON-encoded, queue/audit metadata dropped."""
    skip = {"created_at", "created_by", "sync_status", "sync_attempts", "sync_timestamp"}
    cols = ResolucionFacturacion.__table__.columns
    return jsonable_encoder({c.name: getattr(row, c.name) for c in cols if c.name not in skip})


async def test_branch_applies_versioned_resolucion_and_keeps_only_new_open(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    spec = SYNC_CATALOG_BY_NAME["resolucion_facturacion"]
    numero = f"res-{uuid_lib.uuid4().hex[:12]}"
    t_old = datetime(2026, 10, 5, 1, 47, 21, 938729)
    t_new = datetime(2026, 10, 7, 0, 38, 55, 375991)

    async with Session() as session:
        sucursal = v_fixture_factory.build(Sucursal)
        session.add(sucursal)
        await session.commit()

        common = {
            "uuid_sucursal": sucursal.uuid,
            "numero_resolucion": numero,
            "fecha_resolucion": date(2026, 10, 4),
            "fecha_inicio_vigencia": date(2026, 10, 4),
            "fecha_fin_vigencia": date(2027, 4, 10),
        }
        # Branch state: ONLY the old version, open, without prefix/range.
        old_local = v_fixture_factory.build(
            ResolucionFacturacion, vigente_desde=t_old, **common
        )
        session.add(old_local)
        await session.commit()

        # What the cloud pull delivers: old version closed + new version open.
        old_wire = v_fixture_factory.build(
            ResolucionFacturacion,
            uuid=old_local.uuid,
            vigente_desde=t_old,
            vigente_hasta=t_new,
            estado="inactivo",
            **common,
        )
        new_wire = v_fixture_factory.build(
            ResolucionFacturacion,
            vigente_desde=t_new,
            prefijo="QA",
            rango_desde=1,
            rango_hasta=5000,
            **common,
        )
        rows = [(spec, _wire(old_wire)), (spec, _wire(new_wire))]

        motor = SyncMotor(engine=engine_flag.EngineMode.CATALOG_BRANCH)
        async with session.begin_nested():
            result = await motor.apply_batch(session, rows, actor_uuid=uuid_lib.uuid4())
        await session.commit()

        assert result.failed == [], result.failed_details
        assert result.failed_details == []

    async with Session() as session:
        versions = (
            await session.execute(
                select(ResolucionFacturacion)
                .where(ResolucionFacturacion.numero_resolucion == numero)
                .order_by(ResolucionFacturacion.vigente_desde)
            )
        ).scalars().all()
        open_rows = [v for v in versions if v.vigente_hasta is None]
        assert len(open_rows) == 1
        assert (open_rows[0].prefijo, open_rows[0].rango_desde, open_rows[0].rango_hasta) == (
            "QA",
            1,
            5000,
        )
        # Valid time travels intact: no gap, no overlap.
        assert open_rows[0].vigente_desde == t_new
        closed = [v for v in versions if v.vigente_hasta is not None]
        assert len(closed) == 1
        assert closed[0].uuid == old_local.uuid
        assert closed[0].vigente_hasta == open_rows[0].vigente_desde

        # The informational divergence conflict was stored with date values intact.
        conflict = (
            await session.execute(
                select(SyncConflict).where(
                    SyncConflict.tabla == "resolucion_facturacion",
                    SyncConflict.uuid_registro == old_local.uuid,
                )
            )
        ).scalars().first()
        assert conflict is not None
        assert conflict.datos_cloud["fecha_resolucion"] == "2026-10-04"
