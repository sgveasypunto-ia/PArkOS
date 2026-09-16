"""test_v_catalog_identity_reconciliation_generalized.py — regression
coverage for the 2026-09-10 extension of identity reconciliation to every
``[V]`` ``SYNC_CATALOG`` entry with a real, ER-declared natural key, not
just the 3 original identity masters (``clientes``, ``clientes_b2b``,
``vehiculos``).

**The defect this closes.** Auditing every ``[V]`` entry in
``sync/catalog/entries/sync_entries_v.py`` against ``modelo_datos_er.mmd``'s
own UK01 markers found 20 more tables with a genuine natural key and NO
reconciliation wired at all. Since no sync trigger anywhere is ``AFTER
UPDATE`` (``sync_motor.py``'s own comment; confirmed by grepping every
``fn_*_enqueue_sync*()`` trigger in ``0001_initial_schema.py`` /
``0014_add_catalog_triggers.py``), a rename/update on any of these tables
— even though only ONE node ever writes them (``cloud_to_branch``) — left
the RECEIVING node with a permanently-stale open row: the incoming new
version was a plain INSERT (``current_uuid=None``, nothing in the wire
payload ever named the old row to close), so the old row's
``vigente_hasta`` stayed NULL forever. Exactly the "(a) two simultaneously
open versions for the same identity" / "(b) a node that never learns a
version closed" hazard the original identity-reconciliation fix only
closed for 3 tables.

**The fix** (``sync/motor/identity_lookup.py``, ``sync/catalog/entries/
sync_entries_v.py``): every ``[V]`` entry that the ER model declares a real
UK01 for now also declares ``natural_key``/``hook_pre_insert=
identity_reconciler`` (or, for ``subscripcion_vehiculos``, an enhanced
``subscription_lifecycle`` that consumes the same ``ctx.open_version``).
``identity_lookup.resolve_open_version`` resolves the currently-open local
row for that natural key generically (``_resolve_generic``, built from
``spec.natural_key``) unless the table needs special handling
(``configuracion_tolerancias``/``configuracion_seguridad``, whose natural
key column is NULLABLE and NULL is itself a meaningful identity — the
global-default row).

This test file exercises three distinct RISK CLASSES via the REAL
``POST /api/v1/sync/events`` HTTP path (the only path every real caller —
push, pull, backfill — funnels through, per ``SyncMotor.apply_row``'s own
comment) — never by calling ``apply_row``/``identity_reconciler`` directly,
same discipline as ``test_identity_reconciliation_real_http.py``:

  1. Generic single-authority rename (``impuestos`` — plain string natural
     key, ~18 tables share this exact mechanism).
  2. Nullable-scope singleton (``configuracion_tolerancias`` — NULL
     natural-key value is a meaningful identity, not "unknown").
  3. Composite FK natural key (``cantidad_vehiculos_sucursal`` — 2-column
     natural key, mirrors ``permisos_usuario``/``usuarios_sucursal``/
     ``tarifas_sucursal``).

A 4th file (``test_subscripcion_vehiculos_open_version_fallback.py``)
covers the one table needing hook COMPOSITION (``subscription_lifecycle``
+ ``ctx.open_version``) instead of a bare ``identity_reconciler`` swap.
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest
from parkos_core.runtime import engine_flag


@pytest.fixture(autouse=True)
def _catalog_engine_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
    engine_flag._reset_cache_for_tests()


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_generic_single_authority_rename_reconciles_to_one_open_row(
    client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, v_fixture_factory
) -> None:
    """[V] rename class, generic resolver — ``impuestos`` (codigo, vigente_desde).

    A cloud-authored rename (new percentage under the SAME ``codigo``) is
    pushed as a real ``/sync/events`` row_push, exactly the shape the
    receiving branch's own sync worker would see. Before this fix: plain
    INSERT, old row never closed, 2 open rows. After: exactly 1.
    """
    from parkos_core.models.V.impuestos import Impuestos
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    codigo = f"TAX{uuid_lib.uuid4().hex[:10]}"

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        local_open = v_fixture_factory.build(
            Impuestos,
            codigo=codigo,
            nombre="Impuesto de prueba",
            porcentaje=19,
            tipo_calculo="porcentaje",
            base_calculo="subtotal",
        )
        session.add(local_open)
        await session.commit()

    token = mint_sync_agent_jwt(scope="branch")
    new_uuid = uuid_lib.uuid4()
    resp = await client.post(
        "/api/v1/sync/events",
        json={
            "events": [
                {
                    "event_type": "row_push",
                    "tabla": "impuestos",
                    "uuid_registro": str(new_uuid),
                    "payload": {
                        "uuid": str(new_uuid),
                        "codigo": codigo,
                        "nombre": "Impuesto de prueba (renombrado)",
                        "porcentaje": 5,
                        "tipo_calculo": "porcentaje",
                        "base_calculo": "subtotal",
                    },
                }
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 207), resp.text
    assert resp.json()["results"][0]["status"] == "applied", resp.text

    async with Session() as session:
        open_rows = (
            (
                await session.execute(
                    select(Impuestos).where(
                        Impuestos.codigo == codigo, Impuestos.vigente_hasta.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(open_rows) == 1, (
            f"expected exactly 1 open row for codigo={codigo!r} after the rename push, "
            f"got {len(open_rows)}"
        )
        assert open_rows[0].uuid == new_uuid
        assert float(open_rows[0].porcentaje) == 5

        total_rows = (
            await session.execute(
                select(func.count()).select_from(Impuestos).where(Impuestos.codigo == codigo)
            )
        ).scalar_one()
        assert total_rows == 2, "the OLD version must still exist, just closed, never deleted"


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_nullable_scope_singleton_reconciles_to_one_open_row(
    client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, v_fixture_factory
) -> None:
    """Nullable-natural-key-is-meaningful class — ``configuracion_tolerancias``
    global default (``uuid_sucursal IS NULL``).

    ``_resolve_generic`` refuses to resolve when a natural-key value is
    ``None`` (correct default for most tables); this table is registered
    with its own resolver instead precisely because NULL here means "the
    global default row", a real identity, not "value unknown".
    """
    from parkos_core.models.V.configuracion_tolerancias import ConfiguracionTolerancias
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        # Clean slate — this table's global-default row is a true singleton
        # (uuid_sucursal IS NULL); a leftover open row from another test run
        # sharing this session-scoped DB would make "exactly 1" ambiguous.
        existing = (
            (
                await session.execute(
                    select(ConfiguracionTolerancias).where(
                        ConfiguracionTolerancias.uuid_sucursal.is_(None),
                        ConfiguracionTolerancias.vigente_hasta.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in existing:
            row.vigente_hasta = row.vigente_desde
            row.estado = "inactivo"
        local_open = v_fixture_factory.build(
            ConfiguracionTolerancias,
            uuid_sucursal=None,
            tolerancia_efectivo=100,
            tolerancia_datafono=100,
        )
        session.add(local_open)
        await session.commit()

    token = mint_sync_agent_jwt(scope="branch")
    new_uuid = uuid_lib.uuid4()
    resp = await client.post(
        "/api/v1/sync/events",
        json={
            "events": [
                {
                    "event_type": "row_push",
                    "tabla": "configuracion_tolerancias",
                    "uuid_registro": str(new_uuid),
                    "payload": {
                        "uuid": str(new_uuid),
                        "uuid_sucursal": None,
                        "tolerancia_efectivo": 250,
                        "tolerancia_datafono": 250,
                    },
                }
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 207), resp.text
    assert resp.json()["results"][0]["status"] == "applied", resp.text

    async with Session() as session:
        open_rows = (
            (
                await session.execute(
                    select(ConfiguracionTolerancias).where(
                        ConfiguracionTolerancias.uuid_sucursal.is_(None),
                        ConfiguracionTolerancias.vigente_hasta.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(open_rows) == 1, (
            f"expected exactly 1 open global-default row, got {len(open_rows)}"
        )
        assert open_rows[0].uuid == new_uuid
        assert float(open_rows[0].tolerancia_efectivo) == 250


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_composite_natural_key_reconciles_to_one_open_row(
    client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, v_fixture_factory
) -> None:
    """Composite FK natural key class — ``cantidad_vehiculos_sucursal``
    (uuid_sucursal, uuid_tipo_vehiculo, vigente_desde). Both columns DO
    carry a real DB-level ``ForeignKey`` constraint (unlike ``sucursal``'s
    own outbound FKs, or ``vehiculos``'/``subscripciones_cliente``'s, which
    are application-enforced only) — confirmed live
    (``fk_cantidad_vehiculos_sucursal_uuid_sucursal``), so real parent rows
    are required, not synthetic uuids.
    """
    from parkos_core.models.V.cantidad_vehiculos_sucursal import CantidadVehiculosSucursal
    from parkos_core.models.V.sucursal import Sucursal
    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal_row = v_fixture_factory.build(
            Sucursal, prefijo_nombre=f"SUC{uuid_lib.uuid4().hex[:8]}"
        )
        tipo_vehiculo_row = v_fixture_factory.build(
            TiposVehiculo, tipo=f"TIPO{uuid_lib.uuid4().hex[:8]}"
        )
        session.add_all([sucursal_row, tipo_vehiculo_row])
        await session.commit()
        uuid_sucursal = sucursal_row.uuid
        uuid_tipo_vehiculo = tipo_vehiculo_row.uuid

        local_open = v_fixture_factory.build(
            CantidadVehiculosSucursal,
            uuid_sucursal=uuid_sucursal,
            uuid_tipo_vehiculo=uuid_tipo_vehiculo,
            cantidad=10,
        )
        session.add(local_open)
        await session.commit()

    token = mint_sync_agent_jwt(scope="branch")
    new_uuid = uuid_lib.uuid4()
    resp = await client.post(
        "/api/v1/sync/events",
        json={
            "events": [
                {
                    "event_type": "row_push",
                    "tabla": "cantidad_vehiculos_sucursal",
                    "uuid_registro": str(new_uuid),
                    "payload": {
                        "uuid": str(new_uuid),
                        "uuid_sucursal": str(uuid_sucursal),
                        "uuid_tipo_vehiculo": str(uuid_tipo_vehiculo),
                        "cantidad": 25,
                    },
                }
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 207), resp.text
    assert resp.json()["results"][0]["status"] == "applied", resp.text

    async with Session() as session:
        open_rows = (
            (
                await session.execute(
                    select(CantidadVehiculosSucursal).where(
                        CantidadVehiculosSucursal.uuid_sucursal == uuid_sucursal,
                        CantidadVehiculosSucursal.uuid_tipo_vehiculo == uuid_tipo_vehiculo,
                        CantidadVehiculosSucursal.vigente_hasta.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(open_rows) == 1, (
            f"expected exactly 1 open row for this (sucursal, tipo_vehiculo) pair, "
            f"got {len(open_rows)}"
        )
        assert open_rows[0].uuid == new_uuid
        assert open_rows[0].cantidad == 25
