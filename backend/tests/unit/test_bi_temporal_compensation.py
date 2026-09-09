"""test_bi_temporal_compensation.py — T-PR5-015 acceptance for
``hooks/impls/bi_temporal_compensation.py`` (REQ-HOOK-007).

Real Postgres throughout — the compensating ``log_transaccional`` row and
its hash-chain extension are asserted against actual persisted rows.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

from parkos_core.models.A.factura_pagos import FacturaPagos
from parkos_core.models.A.log_transaccional import LogTransaccional
from parkos_core.sync.hooks.impls.bi_temporal_compensation import bi_temporal_compensation
from parkos_core.sync.motor.apply_row import apply_row
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000aa")


async def _seed_factura(session, uuid_sucursal) -> uuid_lib.UUID:
    """Seed a minimal ``prod.facturas`` row for ``factura_pagos.uuid_factura``'s FK.

    Pre-existing bug discovered here (out of PR5 scope — see the PR5 apply
    report's "Issues Found" section, same class of defect as
    ``factura_electronica``'s in ``tests/migrations/
    test_derived_read_views_schema.py``): migration 0001 attaches the
    ``fn_set_vigente_inicial`` trigger to ``prod.facturas``, an ``[L-E]``
    table with NO ``vigente_desde``/``estado`` columns — any insert raises
    ``UndefinedColumnError``. ``session_replication_role=replica`` disables
    triggers for this one seed insert.
    """
    factura_uuid = uuid_lib.uuid4()
    await session.execute(text("SET session_replication_role = replica"))
    await session.execute(
        text(
            "INSERT INTO prod.facturas (uuid, uuid_sucursal, subtotal, total) "
            "VALUES (:uuid, :uuid_sucursal, 1000, 1000)"
        ),
        {"uuid": factura_uuid, "uuid_sucursal": uuid_sucursal},
    )
    await session.execute(text("SET session_replication_role = origin"))
    await session.commit()
    return factura_uuid


async def _seed_genesis_for_sucursal(session, uuid_sucursal) -> None:
    """Bootstrap the hash-chain genesis anchor for one uuid_sucursal.

    ``prod.fn_extend_hash_chain()`` (0001_initial_schema.py) requires a
    prior row to exist for a given ``uuid_sucursal`` before accepting any
    insert — see the escape hatch it provides (``accion='inicialización'``,
    ``hash_anterior = hash_actual``), already exercised by the EXISTING
    (xfail, deferred to PR6) ``tests/migrations/test_hash_chain_genesis.py``.
    Scoped to a per-test, per-branch ``uuid_sucursal`` here (never the
    shared ``NULL`` partition), so it cannot interact with that xfail test.
    """
    anchor = "1" * 64
    session.add(
        LogTransaccional(
            uuid_usuario=None,
            uuid_sucursal=uuid_sucursal,
            accion="inicialización",
            tabla_afectada="log_transaccional",
            uuid_registro_afectado=None,
            timestamp_evento=datetime.now(UTC).replace(tzinfo=None),
            hash_anterior=anchor,
            hash_actual=anchor,
        )
    )
    await session.commit()


async def test_reverso_emits_compensating_log_transaccional_row(
    pg_engine, alembic_upgrade, make_spec, seeded_sucursal_uuid
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await _seed_genesis_for_sucursal(session, seeded_sucursal_uuid)
        factura_uuid = await _seed_factura(session, seeded_sucursal_uuid)

        original_uuid = uuid_lib.uuid4()

        spec = make_spec("factura_pagos", hook_post_insert=bi_temporal_compensation)
        payload = {
            "uuid_sucursal": seeded_sucursal_uuid,
            "uuid_factura": factura_uuid,
            "medio_pago": "efectivo",
            "valor": 1000,
            "tipo_movimiento": "reverso",
            "uuid_pago_revertido": original_uuid,
            "timestamp_evento": datetime.now(UTC).replace(tzinfo=None),
        }

        result = await apply_row(
            session, spec, payload, actor_uuid=ACTOR_UUID, log_tx=False
        )
        await session.commit()

        assert result.status == "APPLIED"
        assert result.metrics["hook_post_insert"] is True

        # The original factura_pagos row was never touched (it was never
        # even inserted here — this hook is invoked on the REVERSO row
        # itself; the point is that it does not attempt an UPDATE on
        # anything).
        original_rows = (
            await session.execute(
                select(FacturaPagos).where(FacturaPagos.uuid == original_uuid)
            )
        ).scalars().all()
        assert original_rows == []

        compensating = (
            await session.execute(
                select(LogTransaccional).where(
                    LogTransaccional.tabla_afectada == "factura_pagos",
                    LogTransaccional.uuid_registro_afectado == original_uuid,
                )
            )
        ).scalar_one()
        assert compensating.accion == "compensar"
        assert compensating.datos_nuevos["compensacion_para"] == str(original_uuid)
        # Hash chain extended — hash_anterior/hash_actual populated (not the
        # raw-INSERT-then-trigger-fills-in-NULL path; append_event(chain_
        # hash=True) computes them explicitly in Python).
        assert compensating.hash_anterior is not None
        assert compensating.hash_actual is not None
        assert compensating.hash_anterior != compensating.hash_actual


async def test_pago_does_not_emit_compensation(
    pg_engine, alembic_upgrade, make_spec, seeded_sucursal_uuid
) -> None:
    """A tipo_movimiento='pago' row (not a reverso) triggers no compensation."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        factura_uuid = await _seed_factura(session, seeded_sucursal_uuid)

        before_count = (
            await session.execute(
                select(func.count())
                .select_from(LogTransaccional)
                .where(LogTransaccional.tabla_afectada == "factura_pagos")
            )
        ).scalar_one()

        spec = make_spec("factura_pagos", hook_post_insert=bi_temporal_compensation)
        payload = {
            "uuid_sucursal": seeded_sucursal_uuid,
            "uuid_factura": factura_uuid,
            "medio_pago": "efectivo",
            "valor": 1000,
            "tipo_movimiento": "pago",
            "timestamp_evento": datetime.now(UTC).replace(tzinfo=None),
        }

        result = await apply_row(
            session, spec, payload, actor_uuid=ACTOR_UUID, log_tx=False
        )
        await session.commit()

        assert result.status == "APPLIED"

        after_count = (
            await session.execute(
                select(func.count())
                .select_from(LogTransaccional)
                .where(LogTransaccional.tabla_afectada == "factura_pagos")
            )
        ).scalar_one()
        assert after_count == before_count
