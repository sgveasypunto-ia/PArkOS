"""test_sync_pull_scope_dependency_order.py -- T3.10: apply order of what the derived
scope delivers.

The branch applies a pull batch through ``SyncMotor.apply_batch``: rows are sorted
topologically over ``depends_on`` and each one runs in its own SAVEPOINT. These tests
fix what actually happens when a subscription (and its vehicle link) arrives before,
or without, the cliente / vehiculo the derived scope also selects.

Finding pinned here: ``hook_validate_parent`` is the registry no-op for every real
entry (no ``ValidateParentChain`` exists), so ``RETRY(parent_missing)`` -- the only
trigger of ``sync_queue_lw_buffer`` / ``dependency_buffer`` -- never fires on the pull
path. A child whose parent is not present hits the FK instead: the row is reported in
``result.failed`` (not buffered) and the branch worker leaves the pull cursor where it
is, so the child is retried on the next cycle until its parent lands.
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest
from fastapi.encoders import jsonable_encoder
from parkos_core.runtime import engine_flag


def _spec(table: str):
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME

    return SYNC_CATALOG_BY_NAME[table]


def _model(table: str):
    return _spec(table).model_cls


def _wire(row) -> dict:
    """The payload shape ``POST /sync/pull`` delivers (audit metadata stripped)."""
    from sqlalchemy import inspect as sa_inspect

    skip = {"created_at", "created_by", "sync_status", "sync_attempts", "sync_timestamp"}
    columns = sa_inspect(type(row)).columns
    return jsonable_encoder({c.name: getattr(row, c.name) for c in columns if c.name not in skip})


@pytest.fixture
def pulled(v_fixture_factory):
    """Unsaved rows, as a branch that has none of them locally would receive them."""
    tag = uuid_lib.uuid4().hex[:8]
    f = v_fixture_factory
    sucursal = f.build(_model("sucursal"), nombre=f"S-{tag}")
    tipo = f.build(_model("tipo_subscripciones"))
    cliente = f.build(_model("clientes"), numero_identificacion=f"c{tag}")
    vehiculo = f.build(_model("vehiculos"), placa=f"P{tag}"[:8])
    sub = f.build(
        _model("subscripciones_cliente"),
        uuid_sucursal=sucursal.uuid,
        uuid_cliente=cliente.uuid,
        uuid_tipo_subscripcion=tipo.uuid,
    )
    link = f.build(
        _model("subscripcion_vehiculos"),
        uuid_subscripcion_cliente=sub.uuid,
        uuid_vehiculo=vehiculo.uuid,
    )
    rows = {
        "sucursal": sucursal,
        "tipo_subscripciones": tipo,
        "clientes": cliente,
        "vehiculos": vehiculo,
        "subscripciones_cliente": sub,
        "subscripcion_vehiculos": link,
    }
    return {name: (_spec(name), _wire(row)) for name, row in rows.items()}, rows


async def _apply(pg_engine, rows, *batches):
    """Apply each batch in order inside one rolled-back transaction.

    The branch already holds the catalog parents (``sucursal``, ``tipo_subscripciones``);
    only the derived-scope tables travel in the batches. Returns the per-batch results
    and the uuids present per table at the end.
    """
    from parkos_core.sync.motor.sync_motor import SyncMotor
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    motor = SyncMotor(engine=engine_flag.EngineMode.CATALOG_BRANCH)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as s:
        s.add_all([rows["sucursal"], rows["tipo_subscripciones"]])
        await s.flush()
        results = [
            await motor.apply_batch(s, list(batch), actor_uuid=uuid_lib.uuid4())
            for batch in batches
        ]
        present = {}
        for table in ("clientes", "vehiculos", "subscripciones_cliente", "subscripcion_vehiculos"):
            model = _model(table)
            present[table] = set((await s.execute(select(model.uuid))).scalars().all())
        await s.rollback()  # the shared test DB keeps none of these rows
    return results, present


async def test_children_arriving_first_are_applied_after_their_parents(
    pg_engine, alembic_upgrade, pulled
) -> None:
    payloads, rows = pulled
    child_first = [
        payloads[name]
        for name in (
            "subscripcion_vehiculos",
            "subscripciones_cliente",
            "vehiculos",
            "clientes",
        )
    ]

    (result,), present = await _apply(pg_engine, rows, child_first)

    assert result.failed == []
    assert result.buffered == []
    assert len(result.applied) == 4
    assert rows["clientes"].uuid in present["clientes"]
    assert rows["subscripciones_cliente"].uuid in present["subscripciones_cliente"]
    assert rows["subscripcion_vehiculos"].uuid in present["subscripcion_vehiculos"]


async def test_child_without_its_parent_fails_on_the_fk_and_is_not_buffered(
    pg_engine, alembic_upgrade, pulled
) -> None:
    """The dependency buffer is not engaged: no hook reports ``parent_missing``, so the
    child surfaces as a failed row (the branch worker then freezes its pull cursor)."""
    payloads, rows = pulled
    # cliente and vehiculo are NOT part of this batch (and not local): the scope
    # delivered the subscription before its parent.
    orphan_batch = [payloads["subscripciones_cliente"]]

    (result,), present = await _apply(pg_engine, rows, orphan_batch)

    assert result.buffered == []
    assert [spec.name for spec, _payload, _why in result.failed] == ["subscripciones_cliente"]
    assert result.failed[0][2] == "IntegrityError:23503"  # foreign_key_violation
    assert rows["subscripciones_cliente"].uuid not in present["subscripciones_cliente"]


async def test_child_is_applied_once_its_parent_lands_in_a_later_batch(
    pg_engine, alembic_upgrade, pulled
) -> None:
    """Retry convergence: the failed child re-delivered after its parent applies cleanly."""
    payloads, rows = pulled

    (first, second), present = await _apply(
        pg_engine,
        rows,
        [payloads["subscripciones_cliente"]],
        [payloads["clientes"], payloads["subscripciones_cliente"]],
    )

    assert len(first.failed) == 1
    assert second.failed == []
    assert len(second.applied) == 2
    assert rows["subscripciones_cliente"].uuid in present["subscripciones_cliente"]
